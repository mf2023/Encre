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

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass, field
from typing import Any

from encre.utils.types import (
    AgentEvent,
    create_tool_call_end,
    create_tool_result,
)

_BASH_TOOL_NAMES = frozenset({"bash", "bash_io", "powershell"})


@dataclass
class TrackedTool:
    """A tool being tracked through its execution lifecycle.

    States: queued → executing → completed → yielded
    """

    id: str
    name: str
    args: dict[str, Any]
    client_id: str
    status: str = "queued"
    is_concurrency_safe: bool = False
    promise: asyncio.Task | None = None
    results: list[AgentEvent] = field(default_factory=list)
    pending_progress: list[AgentEvent] = field(default_factory=list)
    is_error: bool = False
    latency_ms: float = 0.0
    result_content: str | None = None
    sub_agent_messages: list[dict[str, Any]] | None = None
    sub_agent_session_id: str | None = None


class StreamingToolExecutor:
    """Executes tools as they stream in with concurrency control.

    - Concurrent-safe tools execute in parallel with other concurrent-safe tools
    - Non-concurrent tools execute exclusively (one at a time)
    - Results are buffered and emitted in the order tools were received
    - Bash errors cancel sibling concurrent tools via a shared abort signal
    """

    def __init__(
        self,
        execute_fn: Callable[[TrackedTool], Any],
        emit_fn: Callable[[TrackedTool], Generator[AgentEvent, None, None]] | None = None,
        concurrency: int = 10,
    ) -> None:
        """Initialize the streaming executor.

        Args:
            execute_fn: Async callable invoked for each tracked tool.
            emit_fn: Optional callable to emit results for a tracked tool.
            concurrency: Maximum number of concurrent tool executions.
        """
        self._tools: list[TrackedTool] = []
        self._execute_fn = execute_fn
        self._emit_fn = emit_fn or self._default_emit_results
        self._semaphore = asyncio.Semaphore(concurrency)
        self._discarded = False

    def discard(self) -> None:
        """Discard all pending and in-progress tools.

        Called when streaming fallback occurs and results from the
        failed attempt should be abandoned.
        """
        self._discarded = True

    def add_tool(self, tool: TrackedTool) -> None:
        """Queue a tool for execution. Starts executing if concurrency allows."""
        self._tools.append(tool)
        task = asyncio.create_task(self._process_tool(tool))
        tool.promise = task

    async def _process_tool(self, tool: TrackedTool) -> None:
        """Wait for concurrency conditions and execute the tool.

        Non-concurrency-safe tools must wait for every preceding
        non-concurrency-safe tool to finish.  Concurrency-safe tools wait
        only until no unsafe tool is running.  We use an event-driven wait
        instead of busy-polling to avoid burning CPU while queued.
        """
        if not tool.is_concurrency_safe:
            for prev in self._tools:
                if prev.client_id == tool.client_id:
                    break
                if not prev.is_concurrency_safe and prev.promise is not None:
                    try:
                        await prev.promise
                    except asyncio.CancelledError:
                        pass

        while not self._can_execute(tool):
            await self._wait_for_state_change()

        await self._execute_tool(tool)

    def _can_execute(self, tool: TrackedTool) -> bool:
        """Check whether the tool can execute given current concurrency state.

        Args:
            tool: The tracked tool to check.

        Returns:
            True if the tool can proceed (no concurrent unsafe tools running).
        """
        executing = [t for t in self._tools if t.status == "executing"]
        if not executing:
            return True
        return tool.is_concurrency_safe and all(t.is_concurrency_safe for t in executing)

    def _wait_for_state_change(self) -> asyncio.Future[Any]:
        """Return a future that resolves when any tool finishes executing."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        def _on_complete(_task: asyncio.Task[Any]) -> None:
            if not future.done():
                future.set_result(None)

        for t in self._tools:
            if t.status == "executing" and t.promise is not None:
                t.promise.add_done_callback(_on_complete)
                break
        else:
            # No executing tools -- resolve immediately so the caller re-checks.
            future.set_result(None)
        return future

    def _get_abort_reason(self, tool: TrackedTool) -> str | None:
        """Determine why a tool should be aborted before execution.

        Args:
            tool: The tracked tool to check.

        Returns:
            An abort reason string, or None if the tool should proceed.
        """
        if self._discarded:
            return "streaming_fallback"
        return None

    def _cancel_sibling_safe_tools(self, errored_tool: TrackedTool) -> None:
        """Cancel other concurrently-running safe tools when a bash tool fails.

        A failing bash command often invalidates the context for parallel
        read-only tools, so we cancel siblings in the same batch.  Queued
        tools are allowed to run afterwards rather than being blanket-blocked.
        """
        for t in self._tools:
            if (
                t is not errored_tool
                and t.status == "executing"
                and t.is_concurrency_safe
                and t.promise is not None
                and not t.promise.done()
            ):
                t.promise.cancel()

    async def _execute_tool(self, tool: TrackedTool) -> None:
        """Execute a single tool with lifecycle management."""
        abort_reason = self._get_abort_reason(tool)
        if abort_reason:
            err_msg = "Streaming fallback -- tool execution discarded"
            tool.results.append(
                create_tool_result(id=tool.client_id, content=err_msg, is_error=True)
            )
            tool.is_error = True
            tool.status = "completed"
            return

        tool.status = "executing"
        async with self._semaphore:
            self_tool_errored = False
            try:
                await self._execute_fn(tool)
                if tool.is_error and tool.name in _BASH_TOOL_NAMES:
                    self_tool_errored = True
                    self._cancel_sibling_safe_tools(tool)

            except asyncio.CancelledError:
                if not self_tool_errored:
                    tool.result_content = "Tool execution was cancelled"
                    tool.is_error = True
                tool.status = "completed"
                return
            except Exception as exc:
                tool.result_content = (
                    f"Tool execution crashed: {type(exc).__name__}: {exc}"
                )
                tool.is_error = True
                self_tool_errored = True
                if tool.name in _BASH_TOOL_NAMES:
                    self._cancel_sibling_safe_tools(tool)

        tool.status = "completed"

    def get_completed_results(self) -> Generator[AgentEvent, None, None]:
        """Yield completed results that haven't been yielded yet, in order.

        Non-blocking — use this to drain ready results between iterations.
        """
        if self._discarded:
            return

        for tool in self._tools:
            while tool.pending_progress:
                yield tool.pending_progress.pop(0)

            if tool.status == "yielded":
                continue

            if tool.status == "completed":
                tool.status = "yielded"
                yield from self._emit_tool_results(tool)
            elif tool.status == "executing" and not tool.is_concurrency_safe:
                break

    async def get_remaining_results(self) -> AsyncGenerator[AgentEvent, None]:
        """Wait for all tools to complete and yield results in order."""
        if self._discarded:
            return

        while self._has_unfinished_tools():
            for event in self.get_completed_results():
                yield event

            if self._has_executing_tools():
                executing_promises = [
                    t.promise
                    for t in self._tools
                    if t.status == "executing" and t.promise is not None
                ]
                if executing_promises:
                    await asyncio.wait(
                        executing_promises, return_when=asyncio.FIRST_COMPLETED
                    )

        for event in self.get_completed_results():
            yield event

    def _has_unfinished_tools(self) -> bool:
        """Has unfinished tools."""
        return any(t.status != "yielded" for t in self._tools)

    def _has_executing_tools(self) -> bool:
        """Has executing tools."""
        return any(t.status == "executing" for t in self._tools)

    def _emit_tool_results(self, tool: TrackedTool) -> Generator[AgentEvent, None, None]:
        """Emit results for a completed tool via the configured emit function."""
        yield from self._emit_fn(tool)

    @staticmethod
    def _default_emit_results(tool: TrackedTool) -> Generator[AgentEvent, None, None]:
        """Default result emission — basic tool_result + tool_call_end."""
        yield create_tool_result(
            id=tool.client_id,
            content=tool.result_content or "",
            is_error=tool.is_error,
            sub_agent_messages=tool.sub_agent_messages,
            sub_agent_session_id=tool.sub_agent_session_id,
        )
        yield create_tool_call_end(id=tool.client_id)
