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

# Tools whose errors should cancel concurrently-executing siblings.
# For example, a failed bash command often invalidates the context
# for parallel read-only tools.
_ERROR_CASCADE_TOOLS: frozenset[str] = frozenset({
    "bash", "bash_io", "powershell",
})

# Tools whose errors should NEVER cascade to siblings (isolated).
_NON_CASCADE_TOOLS: frozenset[str] = frozenset({
    "question", "agent", "workflow",
})


class AbortController:
    """Shared abort signal for a batch of tools.

    When a tool error triggers cancellation, the controller records
    the reason so every subsequently-checked tool sees why it was
    aborted — no separate per-tool signalling needed.
    """

    def __init__(self) -> None:
        self._reason: str | None = None

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str) -> None:
        if self._reason is None:
            self._reason = reason

    def reset(self) -> None:
        self._reason = None


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
    paths: frozenset[str] = field(default_factory=frozenset)
    abort_controller: AbortController | None = None
    abort_reason: str | None = None


def _extract_paths(
    tool: TrackedTool,
    tool_registry: Any = None,
) -> frozenset[str]:
    """Extract filesystem paths a tool call touches, for overlap detection.

    First tries the tool's ``get_effective_path`` hook (Tool Protocol 4.3).
    Falls back to :func:`encre.safety._extract_tool_target_paths` for tools
    that do not implement the hook.  Paths are normalized (``~`` expanded,
    backslashes to forward slashes, lowercased) so ``./Foo.txt`` and
    ``foo.txt`` collapse to the same key.
    """
    # Try the tool's own get_effective_path hook first
    if tool_registry is not None:
        try:
            tool_obj = tool_registry.get(tool.name)
            if tool_obj is not None and hasattr(tool_obj, "get_effective_path"):
                ep = tool_obj.get_effective_path(tool.args or {})
                if ep:
                    from encre.safety import _normalize_path_for_immune_check
                    norm = _normalize_path_for_immune_check(ep)
                    if norm:
                        return frozenset({norm})
        except Exception:
            pass

    # Fallback: generic arg scanning via safety module
        from encre.safety import _extract_tool_target_paths, _normalize_path_for_immune_check
    raw = _extract_tool_target_paths(tool.name, tool.args or {})
    out: set[str] = set()
    for p in raw:
        norm = _normalize_path_for_immune_check(p)
        if norm:
            out.add(norm)
    return frozenset(out)


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
        tool_registry: Any = None,
        abort_controller: AbortController | None = None,
    ) -> None:
        """Initialize the streaming executor.

        Args:
            execute_fn: Async callable invoked for each tracked tool.
            emit_fn: Optional callable to emit results for a tracked tool.
            concurrency: Maximum number of concurrent tool executions.
            tool_registry: Optional ToolRegistry for resolving hooks.
            abort_controller: Shared abort signal for sibling propagation.
        """
        self._tools: list[TrackedTool] = []
        self._execute_fn = execute_fn
        self._emit_fn = emit_fn or self._default_emit_results
        self._semaphore = asyncio.Semaphore(concurrency)
        self._discarded = False
        self._tool_registry = tool_registry
        self._abort = abort_controller or AbortController()

    def discard(self) -> None:
        """Discard all pending and in-progress tools.

        Called when streaming fallback occurs and results from the
        failed attempt should be abandoned.
        """
        self._discarded = True

    def add_tool(self, tool: TrackedTool) -> None:
        """Queue a tool for execution. Starts executing if concurrency allows."""
        if not tool.paths:
            tool.paths = _extract_paths(tool, self._tool_registry)
        tool.abort_controller = self._abort
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

        Path-aware serialization: even two concurrency-safe tools are
        serialized when they touch the same filesystem path (e.g. a
        ``file_read`` and ``file_write`` of the same file must not race).
        Tools that touch no extractable path fall back to the original
        concurrency-safety rule.
        """
        executing = [t for t in self._tools if t.status == "executing"]
        if not executing:
            return True
        # Path overlap check: if this tool shares a path with any executing
        # tool, it must wait (regardless of concurrency-safety flags) so a
        # reader doesn't observe a half-written file.  Only applies when the
        # tool actually declared paths; path-less tools skip this.
        if tool.paths:
            for t in executing:
                if t.paths and (tool.paths & t.paths):
                    return False
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
        """Determine why a tool should be aborted before execution."""
        if self._discarded:
            return "streaming_fallback"
        if self._abort.reason:
            return self._abort.reason
        return None

    def _propagate_error(self, errored_tool: TrackedTool) -> None:
        """Cancel siblings when a cascade-eligible tool errors.

        Cancels ALL siblings (executing + queued) so the batch halts
        quickly instead of wasting resources on doomed work.

        Excluded tools (``_NON_CASCADE_TOOLS`` like ``question`` or
        ``agent``) are never cancelled — they are always isolated.
        """
        if errored_tool.name in _NON_CASCADE_TOOLS:
            return
        reason = (
            f"sibling error: {errored_tool.name} failed"
        )
        self._abort.cancel(reason)
        for t in self._tools:
            if t is errored_tool:
                continue
            if t.name in _NON_CASCADE_TOOLS:
                continue
            if t.promise is not None and not t.promise.done():
                t.promise.cancel()

    async def _execute_tool(self, tool: TrackedTool) -> None:
        """Execute a single tool with lifecycle management."""
        abort_reason = self._get_abort_reason(tool)
        if abort_reason:
            err_msg = abort_reason
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
                if tool.is_error and tool.name in _ERROR_CASCADE_TOOLS:
                    self_tool_errored = True
                    self._propagate_error(tool)

            except asyncio.CancelledError:
                if self._abort.reason:
                    tool.abort_reason = self._abort.reason
                    tool.result_content = (
                        f"Tool execution was cancelled: {self._abort.reason}"
                    )
                    tool.is_error = True
                elif not self_tool_errored:
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
                if tool.name in _ERROR_CASCADE_TOOLS:
                    self._propagate_error(tool)

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
