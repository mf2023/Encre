#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

import uuid
from typing import Any

from yim.hooks.types import (
    HookEventType,
    HookHandler,
    HookResult,
    HookStartedEvent,
    HookResponseEvent,
)


class YmiHookSystem:
    """Hook system with 20+ event types covering the full agent lifecycle.

    Events:
      Tool: pre_tool_exec, post_tool_exec, on_tool_progress, pre_bash
      Session: on_session_start, on_session_end, on_checkpoint
      Turn: on_turn_start, on_turn_end
      Model: pre_model_request, post_model_response
      Safety: on_permission_request, on_permission_response
      Error: on_error, on_backend_error, on_rate_limit
      Compact: pre_compact, post_compact
      Agent: pre_sub_agent, post_sub_agent
      Goal: on_goal_progress
      IO: on_file_change
      Meta: on_telemetry

    Handlers are async callables returning HookResult dicts with optional:
      - block: bool — block the operation
      - block_reason: str
      - modified_input: dict — override tool/model input
      - extra_context: str — inject into output
    """

    _ALL_EVENTS: tuple[HookEventType, ...] = (
        "pre_tool_exec", "post_tool_exec", "on_tool_progress", "pre_bash",
        "on_session_start", "on_session_end", "on_checkpoint",
        "on_turn_start", "on_turn_end",
        "pre_model_request", "post_model_response",
        "on_permission_request", "on_permission_response",
        "on_error", "on_backend_error", "on_rate_limit",
        "pre_compact", "post_compact",
        "pre_sub_agent", "post_sub_agent",
        "on_goal_progress",
        "on_file_change",
        "on_telemetry",
    )

    def __init__(self) -> None:
        self._handlers: dict[HookEventType, list[tuple[str, HookHandler]]] = {
            e: [] for e in self._ALL_EVENTS
        }
        self._event_handlers: list[callable] = []
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_handler(
        self,
        event_type: HookEventType,
        handler: HookHandler,
        handler_id: str | None = None,
    ) -> str:
        hid = handler_id or str(uuid.uuid4())
        if event_type not in self._handlers:
            raise ValueError(f"Unknown hook event type: {event_type}")
        self._handlers[event_type].append((hid, handler))
        return hid

    def unregister_handler(self, handler_id: str) -> bool:
        for handlers in self._handlers.values():
            for i, (hid, _) in enumerate(handlers):
                if hid == handler_id:
                    handlers.pop(i)
                    return True
        return False

    def on_event(self, callback: callable) -> None:
        """Register a global event observer (receives all HookStartedEvent/HookResponseEvent)."""
        self._event_handlers.append(callback)

    # ── Tool hooks ────────────────────────────────────────────────

    async def emit_pre_tool(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Raised before a tool executes. Handlers may block or modify input."""
        return await self._emit_with_modify("pre_tool_exec", tool_name, tool_input)

    async def emit_post_tool(
        self, tool_name: str, tool_input: dict[str, Any], tool_output: str
    ) -> str | None:
        """Raised after a tool executes. Handlers may inject extra context."""
        return await self._emit_with_extra(
            "post_tool_exec", tool_name,
            {"input": tool_input, "output": tool_output}
        )

    async def emit_tool_progress(
        self, tool_name: str, status: str, detail: str = ""
    ) -> None:
        """Raised during long-running tool execution."""
        await self._run_handlers("on_tool_progress", tool_name,
                                {"status": status, "detail": detail})

    async def emit_pre_bash(
        self, command: str
    ) -> dict[str, Any] | None:
        """Raised specifically before bash commands. May block dangerous commands."""
        return await self._emit_with_modify("pre_bash", "bash", {"command": command})

    # ── Session hooks ──────────────────────────────────��─────────

    async def emit_session_start(self) -> None:
        await self._run_handlers("on_session_start", "_session", {})

    async def emit_session_end(self) -> None:
        await self._run_handlers("on_session_end", "_session", {})

    async def emit_checkpoint(self, label: str) -> None:
        await self._run_handlers("on_checkpoint", label, {})

    # ── Turn hooks ────────────────────────────────────────────────

    async def emit_turn_start(self, turn: int) -> None:
        await self._run_handlers("on_turn_start", "_turn", {"turn": turn})

    async def emit_turn_end(self, turn: int, event_count: int = 0) -> None:
        await self._run_handlers("on_turn_end", "_turn",
                                {"turn": turn, "event_count": event_count})

    # ── Model hooks ───────────────────────────────────────────────

    async def emit_pre_model_request(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """Raised before each model API call. Handlers may modify messages or tools."""
        return await self._emit_with_modify("pre_model_request", "_model",
                                            {"messages": messages, "tools": tools})

    async def emit_post_model_response(
        self, response_text: str, tool_calls_count: int
    ) -> str | None:
        """Raised after model responds. Handlers may inject feedback."""
        return await self._emit_with_extra(
            "post_model_response", "_model",
            {"text": response_text, "tool_calls_count": tool_calls_count}
        )

    # ── Permission hooks ──────────────────────────────────────────

    async def emit_permission_request(self, tool_name: str, reason: str) -> dict[str, Any] | None:
        """Raised when a tool requires user permission."""
        return await self._emit_with_modify("on_permission_request", tool_name,
                                            {"reason": reason})

    async def emit_permission_response(self, tool_name: str, approved: bool) -> None:
        """Raised when user responds to a permission request."""
        await self._run_handlers("on_permission_response", tool_name,
                                {"approved": approved})

    # ── Error hooks ───────────────────────────────────────────────

    async def emit_error(self, error: Exception, context: str) -> None:
        await self._run_handlers("on_error", type(error).__name__,
                                {"message": str(error), "context": context})

    async def emit_backend_error(self, error_message: str, provider: str) -> None:
        await self._run_handlers("on_backend_error", provider,
                                {"message": error_message})

    async def emit_rate_limit(self, provider: str, retry_after: float = 0) -> None:
        await self._run_handlers("on_rate_limit", provider,
                                {"retry_after": retry_after})

    # ── Compact hooks ─────────────────────────────────────────────

    async def emit_pre_compact(
        self, message_count: int, estimated_tokens: int
    ) -> dict[str, Any] | None:
        """Raised before context compaction. May block compaction."""
        return await self._emit_with_modify("pre_compact", "_compact",
                                            {"message_count": message_count,
                                             "estimated_tokens": estimated_tokens})

    async def emit_post_compact(
        self, old_count: int, new_count: int
    ) -> None:
        await self._run_handlers("post_compact", "_compact",
                                {"old_message_count": old_count,
                                 "new_message_count": new_count})

    # ── Sub-agent hooks ───────────────────────────────────────────

    async def emit_pre_sub_agent(self, prompt: str, tool_names: list[str]) -> dict[str, Any] | None:
        """Raised before spawning a sub-agent. May block or modify prompt."""
        return await self._emit_with_modify("pre_sub_agent", "_sub_agent",
                                            {"prompt": prompt, "tools": tool_names})

    async def emit_post_sub_agent(self, result: str, latency_ms: float) -> str | None:
        return await self._emit_with_extra("post_sub_agent", "_sub_agent",
                                          {"result": result, "latency_ms": latency_ms})

    # ── Goal progress ─────────────────────────────────────────────

    async def emit_goal_progress(self, attempt: int, status: str, message: str) -> None:
        await self._run_handlers("on_goal_progress", "_goal",
                                {"attempt": attempt, "status": status,
                                 "message": message})

    # ── File change ───────────────────────────────────────────────

    async def emit_file_change(self, path: str, operation: str) -> None:
        """Raised when the agent writes or modifies a file."""
        await self._run_handlers("on_file_change", path, {"operation": operation})

    # ── Telemetry ─────────────────────────────────────────────────

    async def emit_telemetry(self, data: dict[str, Any]) -> None:
        await self._run_handlers("on_telemetry", "_telemetry", data)

    # ── Internal helpers ──────────────────────────────────────────

    async def _emit_with_modify(
        self, event_type: HookEventType, name: str, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Run handlers that may block or modify input."""
        if not self._enabled:
            return None
        results = await self._run_handlers(event_type, name, context)
        merged: dict[str, Any] = {}
        modified: dict[str, Any] = dict(context)
        for r in results:
            if r.get("block"):
                return {
                    "block": True,
                    "block_reason": r.get("block_reason", f"Blocked by hook: {name}"),
                }
            if r.get("modified_input"):
                modified.update(r["modified_input"])
        if modified != context:
            merged["modified_input"] = modified
        return merged if merged else None

    async def _emit_with_extra(
        self, event_type: HookEventType, name: str, context: dict[str, Any]
    ) -> str | None:
        """Run handlers that may inject extra context."""
        if not self._enabled:
            return None
        results = await self._run_handlers(event_type, name, context)
        parts: list[str] = []
        for r in results:
            ec = r.get("extra_context")
            if ec:
                parts.append(str(ec))
        return "\n".join(parts) if parts else None

    async def _run_handlers(
        self,
        event_type: HookEventType,
        name: str,
        context: dict[str, Any],
    ) -> list[HookResult]:
        results: list[HookResult] = []
        for hid, handler in self._handlers.get(event_type, []):
            self._dispatch_event(
                HookStartedEvent(hook_id=hid, hook_name=name, event_type=event_type)
            )
            try:
                r = await handler(name, context, None)
                if r:
                    results.append(r)
                self._dispatch_event(
                    HookResponseEvent(
                        hook_id=hid, hook_name=name, event_type=event_type,
                        output=str(r) if r else "",
                    )
                )
            except Exception as e:
                self._dispatch_event(
                    HookResponseEvent(
                        hook_id=hid, hook_name=name, event_type=event_type,
                        output=str(e), exit_code=1, outcome="error",
                    )
                )
        return results

    def _dispatch_event(self, event: HookStartedEvent | HookResponseEvent) -> None:
        for cb in self._event_handlers:
            try:
                cb(event)
            except Exception:
                pass
