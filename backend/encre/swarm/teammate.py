#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

# A "teammate" is one collaborating agent inside a swarm.
#
# ``EncreTeammate`` wraps an ``EncreAgent`` configured with a task, a tool set,
# and an optional config, and runs it as a background asyncio task.  While
# running, the teammate streams text into a result string and pushes tool
# outputs onto its own ``EncreMailbox`` so other agents can read them.  The
# ``TeammateHandle`` is the awaitable handle observers use to track status and
# retrieve the finished result.

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from encre.swarm.mailbox import EncreMailbox

if TYPE_CHECKING:
    from encre.config import EncreConfig
    from encre.tools.base import EncreTool


@dataclass
class TeammateHandle:
    """Live status record for a running teammate.

    Created when a teammate starts and mutated as the run progresses; observers
    read ``status`` (``pending``/``running``/``completed``/``failed``/
    ``cancelled``) and ``result`` once finished.  The bound ``_task`` lets the
    manager await completion.
    """
    teammate_id: str
    name: str
    status: str = "pending"
    result: str = ""
    error: str = ""
    mailbox: EncreMailbox | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)


class EncreTeammate:
    """One agent participant in a swarm.

    Construction only records configuration; ``run`` actually launches the
    underlying ``EncreAgent`` in a background task and returns a handle.  The
    agent's text deltas are accumulated into ``handle.result`` and its tool
    results are forwarded to the teammate's mailbox for cross-agent visibility.
    """
    def __init__(
        self,
        name: str,
        task: str,
        tools: "list[EncreTool] | None" = None,
        config: "EncreConfig | None" = None,
        allowed_tools: "list[str] | None" = None,
        sub_agent_runner: Any = None,
    ):
        self.teammate_id = str(uuid.uuid4())
        self.name = name
        self.task = task
        self.tools = tools or []
        self.config = config
        self.allowed_tools = allowed_tools
        self.sub_agent_runner = sub_agent_runner
        self.mailbox = EncreMailbox(owner_id=f"{name}:{self.teammate_id[:8]}")
        self._run_task: asyncio.Task | None = None
        self._run_handle: TeammateHandle | None = None

    async def run(self) -> TeammateHandle:
        """Start the teammate's agent as a background task and return its handle."""
        handle = TeammateHandle(
            teammate_id=self.teammate_id,
            name=self.name,
            status="running",
            mailbox=self.mailbox,
        )
        self._run_task = asyncio.create_task(self._run(handle))
        handle._task = self._run_task
        self._run_handle = handle
        return handle

    async def _run(self, handle: TeammateHandle) -> None:
        """Background coroutine driving the wrapped agent.

        When a ``sub_agent_runner`` is configured the teammate delegates to the
        host loop's ``_run_sub_agent`` (inheriting depth fencing, live progress
        streaming, transcript persistence, and the safety / tool-policy hooks).
        Otherwise it streams ``TextDelta``/``ToolResult`` events from a
        self-spawned ``EncreAgent``, accumulating text into ``handle.result``
        and posting tool outputs to the mailbox for cross-agent visibility.
        Translates ``CancelledError`` into a ``cancelled`` status (re-raising
        so callers can detect cancellation) and any other exception into
        ``failed``.
        """
        try:
            if self.sub_agent_runner is not None:
                result = await self.sub_agent_runner(
                    self.task, system_prompt="", max_turns=15,
                )
                if isinstance(result, dict):
                    handle.result = result.get("content", "") or ""
                else:
                    handle.result = str(result)
                handle.status = "completed"
                return

            from encre.agent import EncreAgent
            from encre.config import EncreConfig
            from encre.tools.registry import ToolRegistry

            config = self.config or EncreConfig(max_turns=15)
            tool_registry = ToolRegistry()
            for tool in self.tools:
                tool_registry.register(tool)
            agent = EncreAgent(config=config, tool_registry=tool_registry)

            parts: list[str] = []
            from encre.utils.types import TextDelta, ToolResult
            async for event in agent.run(self.task):
                if isinstance(event, TextDelta) and event.text:
                    parts.append(event.text)
                elif isinstance(event, ToolResult):
                    content = event.content if event.content else str(event.is_error)
                    await self.mailbox.send(self.mailbox, content)
            handle.result = "".join(parts)
            handle.status = "completed"
        except asyncio.CancelledError:
            handle.status = "cancelled"
            handle.error = "Cancelled by user"
            # Re-raise so the caller (e.g. SwarmManager or asyncio.gather)
            # knows this task was cancelled rather than completed.
            raise
        except Exception as e:
            handle.error = str(e)
            handle.status = "failed"

    async def cancel(self) -> None:
        """Cancel the teammate's running agent task.

        Sends a cancellation request to the underlying asyncio Task and
        updates the handle status to 'cancelled'.  Safe to call even if
        the teammate has not been started or has already finished.
        """
        if self._run_task is not None and not self._run_task.done():
            self._run_task.cancel()
        if self._run_handle is not None:
            self._run_handle.status = "cancelled"
