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
import contextlib
import time
import uuid
from typing import Any

from encre.logging_config import get_logger
from encre.prompts.loader import PromptLoader
from encre.utils.types import (
    Finish,
    Reference,
    TextDelta,
    ThinkingDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
)

logger = get_logger(__name__)

# Module-level loader for the sub-agent enforcement block.  Loaded once and
# cached so we don't re-read the .prompt file on every sub-agent spawn.
_enforcement_loader = PromptLoader()
_sub_agent_enforcement: str | None = None


def _get_sub_agent_enforcement() -> str:
    """Return the cached sub-agent enforcement prompt.

    The enforcement block is prepended to every sub-agent's system_prompt so
    that all sub-agents — regardless of their role .prompt file — receive:
    - English-only enforcement (thinking + output + tool calls)
    - Delivery discipline (act-don't-describe, no stub, no fabrication, verify)
    - Safety rules (tool output is data, never expose secrets)
    - Sub-agent constraints (no nesting, limited tools, clear result)

    Sub-agents do NOT go through the full EncrePromptBuilder, so without
    this injection they would miss the universal discipline blocks that the
    main agent gets.
    """
    global _sub_agent_enforcement
    if _sub_agent_enforcement is None:
        _sub_agent_enforcement = _enforcement_loader.load("sub_agent_enforcement")
    return _sub_agent_enforcement


class SubAgentRunner:
    """Runs a sub-agent as a fully isolated session.

    Delegated from EncreLoop._run_sub_agent.  All callers that previously
    accessed ``loop._run_sub_agent(...)`` continue to work through a
    forwarding bridge on EncreLoop.
    """

    def __init__(
        self,
        config: Any,
        tool_registry: Any,
        memory_system: Any,
        profile_system: Any,
        soul_system: Any,
        skill_registry: Any,
        hook_system: Any,
        safety: Any,
        sub_agent_depth: int,
        child_loops: set[Any],
        session: Any,
    ) -> None:
        self._config = config
        self._tool_registry = tool_registry
        self._memory_system = memory_system
        self._profile_system = profile_system
        self._soul_system = soul_system
        self._skill_registry = skill_registry
        self._hook_system = hook_system
        self._safety = safety
        self._sub_agent_depth = sub_agent_depth
        self._child_loops = child_loops
        self._session = session

    async def run(
        self,
        prompt: str,
        system_prompt: str = "",
        max_turns: int = 0,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        tool_policy: str = "all",
        progress_callback: Any = None,
        event_callback: Any = None,
        session_id: str | None = None,
        cache_context: Any = None,
    ) -> dict[str, Any]:
        """Run a sub-agent as a fully isolated session.

        The sub-agent is ALWAYS a full EncreAgent spawned from this runner.
        The caller can observe execution through two hooks:

        * ``progress_callback(messages_snapshot)`` is awaited on every
          streaming event with the canonical session messages plus any
          uncommitted draft. Used by the chat UI to render live tokens.
        * ``event_callback(event)`` is awaited on every raw AgentEvent
          before it is folded into the draft.

        Returns the standard sub-agent result dict:

            ``{"content": str, "messages": list[dict], "session_id": str}``
        """
        if prompt is None:
            prompt = ""
        if system_prompt is None:
            system_prompt = ""

        # Prepend the sub-agent enforcement block so every sub-agent gets
        # English enforcement + delivery discipline + safety, even though
        # sub-agents don't go through the full EncrePromptBuilder.
        _enforcement = _get_sub_agent_enforcement()
        if _enforcement:
            system_prompt = f"{_enforcement}\n\n{system_prompt}" if system_prompt else _enforcement

        logger.info("[sub_agent] run | prompt_len=%s | sys_prompt_len=%s | tool_policy=%s",
                    len(prompt), len(system_prompt), tool_policy)
        logger.info("[sub_agent] prompt_text=%.300s", prompt)

        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.tools.builtin.agent import MAX_SUB_AGENT_DEPTH
        from encre.tools.builtin.agent import (
            _enforce_tool_policy as _agent_enforce_policy,
        )
        from encre.tools.registry import ToolRegistry

        sub_config = EncreConfig(
            model=model or self._config.model,
            api_key=api_key or self._config.api_key,
            base_url=base_url or self._config.base_url,
            max_tokens=self._config.max_tokens,
            max_turns=max_turns,
            permission_mode="bypass",
            backend_type=self._config.backend_type,
            backend_kwargs=self._config.backend_kwargs,
        )
        tool_registry = ToolRegistry()
        tool_registry._tools = dict(self._tool_registry._tools)

        sub_agent = EncreAgent(
            config=sub_config,
            tool_registry=tool_registry,
            memory_system=self._memory_system,
            profile_system=self._profile_system,
            soul_system=self._soul_system,
            skill_registry=self._skill_registry,
            hook_system=self._hook_system,
            safety=self._safety,
        )
        sub_agent.loop.sub_agent_depth = self._sub_agent_depth + 1
        if self._sub_agent_depth >= MAX_SUB_AGENT_DEPTH and "agent" in tool_registry._tools:
            try:
                del tool_registry._tools["agent"]
                logger.info("[sub_agent] depth=%s reached MAX=%s, removed 'agent' tool from sub-agent registry",
                            self._sub_agent_depth + 1, MAX_SUB_AGENT_DEPTH)
            except Exception:
                pass
        sub_agent.config.current_tool_policy = tool_policy

        if tool_policy in ("readonly", "no_writes"):
            def _policy_hook(tool_name: str, _tool_input: dict[str, Any]) -> dict[str, Any] | None:
                err = _agent_enforce_policy(tool_name, _tool_input)
                if err is not None:
                    return {"block": True, "block_reason": err}
                return None

            original_emit_pre_tool = sub_agent.loop.hook_system.emit_pre_tool

            async def _emit_pre_tool_with_policy(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
                result = _policy_hook(tool_name, tool_input)
                if result is not None:
                    return result
                return await original_emit_pre_tool(tool_name, tool_input)

            sub_agent.loop.hook_system.emit_pre_tool = _emit_pre_tool_with_policy

        sub_agent.add_message("user", prompt)

        if cache_context is not None and hasattr(cache_context, "wrap_prompt"):
            system_prompt = cache_context.wrap_prompt(system_prompt or "")
            logger.info("[sub_agent] applied cache context from parent session=%s hash=%s",
                        getattr(cache_context, "parent_session_id", "?"),
                        getattr(cache_context, "prefix_hash", "?"))

        sub_agent.session.id = session_id or sub_agent.session.id or str(uuid.uuid4())
        saved_session_id = sub_agent.session.id
        sub_agent.session.metadata["channel"] = "sub_agent"
        sub_agent.session.parent_session_id = self._session.id or ""

        def _save():
            try:
                from encre.config import get_data_dir
                _dir = get_data_dir() / "sub_agents" / saved_session_id
                _dir.mkdir(parents=True, exist_ok=True)
                sub_agent.session.save_to_dir(str(_dir))
            except Exception:
                logger.warning("[sub_agent] failed to persist session", exc_info=True)

        result_parts: list[str] = []
        text_buffer = ""
        sub_refs: list[dict[str, Any]] = []
        draft_content: list[str] = []
        draft_reasoning: list[str] = []
        draft_tool_calls: list[dict[str, Any]] = []
        draft_tool_id_to_idx: dict[str, int] = {}
        draft_segments: list[dict[str, Any]] = []
        last_seen_msg_count = 0
        last_seen_assistant_id: str | None = None
        # Throttle live transcript emissions.  Without this, every streaming
        # delta re-serialises the FULL sub-agent message history and pushes it
        # over the WebSocket, and the frontend re-merges + re-renders the whole
        # sub-agent card on every frame -- O(n^2) traffic that freezes the UI.
        # We coalesce emissions to at most one per interval; the final state is
        # always flushed with ``force=True``.
        last_emit_ts: float = 0.0
        EMIT_INTERVAL = 0.08

        def _has_uncommitted_draft() -> bool:
            return bool(
                draft_content
                or draft_reasoning
                or draft_tool_calls
                or draft_segments
            )

        def _reset_draft() -> None:
            draft_content.clear()
            draft_reasoning.clear()
            draft_tool_calls.clear()
            draft_tool_id_to_idx.clear()
            draft_segments.clear()

        def _draft_as_message() -> dict[str, Any]:
            return {
                "role": "assistant",
                "content": "".join(draft_content),
                "reasoning_content": "".join(draft_reasoning),
                "tool_calls": [dict(tc) for tc in draft_tool_calls],
                "segments": [dict(s) for s in draft_segments],
                "created_at": time.time(),
            }

        def _sync_draft_with_session() -> None:
            nonlocal last_seen_msg_count, last_seen_assistant_id
            msgs = sub_agent.session.messages
            current_count = len(msgs)
            current_assistant_id: str | None = None
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    current_assistant_id = str(m.get("id") or "")
                    break
            if (
                current_assistant_id is not None
                and current_assistant_id != last_seen_assistant_id
            ):
                last_seen_msg_count = current_count
                last_seen_assistant_id = current_assistant_id
                _reset_draft()
            elif current_count != last_seen_msg_count:
                last_seen_msg_count = current_count

        def _build_snapshot() -> list[dict[str, Any]]:
            _sync_draft_with_session()
            snapshot = [dict(m) for m in sub_agent.session.messages]
            if _has_uncommitted_draft():
                snapshot.append(_draft_as_message())
            return snapshot

        async def _emit_live(*, force: bool = False) -> None:
            nonlocal last_emit_ts
            if progress_callback is None:
                return
            now = time.time()
            if not force and now - last_emit_ts < EMIT_INTERVAL:
                return
            last_emit_ts = now
            await progress_callback(_build_snapshot())

        def _flush_text_buffer() -> None:
            nonlocal text_buffer
            text = text_buffer.strip()
            if text:
                result_parts.append(f"### Assistant\n{text}\n")
            text_buffer = ""

        self._child_loops.add(sub_agent.loop)
        cancelled = False
        try:
            async for event in sub_agent.run(prompt=prompt, system_prompt=system_prompt or None):
                if event_callback is not None:
                    try:
                        await event_callback(event)
                    except Exception:
                        logger.warning("[sub_agent] event_callback raised", exc_info=True)
                if isinstance(event, TextDelta):
                    text_buffer += event.text
                    draft_content.append(event.text)
                    if draft_segments and draft_segments[-1].get("kind") == "text":
                        draft_segments[-1]["text"] = (
                            str(draft_segments[-1].get("text") or "") + event.text
                        )
                    else:
                        draft_segments.append({"kind": "text", "text": event.text})
                    await _emit_live()
                elif isinstance(event, ThinkingDelta):
                    _flush_text_buffer()
                    thought = event.text.strip()
                    if thought:
                        result_parts.append(f"### Thought\n{thought}\n")
                        draft_reasoning.append(event.text)
                        if draft_segments and draft_segments[-1].get("kind") == "thinking":
                            draft_segments[-1]["text"] = (
                                str(draft_segments[-1].get("text") or "") + event.text
                            )
                        else:
                            draft_segments.append({"kind": "thinking", "text": event.text})
                        await _emit_live()
                elif isinstance(event, ToolCallStart):
                    _flush_text_buffer()
                    result_parts.append(f"### Tool Start\n- id: `{event.id}`\n- name: `{event.name}`\n")
                    tc_dict = {
                        "id": event.id,
                        "type": "function",
                        "function": {"name": event.name, "arguments": "{}"},
                    }
                    draft_tool_calls.append(tc_dict)
                    draft_tool_id_to_idx[event.id] = len(draft_tool_calls) - 1
                    draft_segments.append({"kind": "tool", "tool_id": event.id})
                    await _emit_live()
                elif isinstance(event, ToolProgress):
                    _flush_text_buffer()
                    result_parts.append(f"### Tool Progress\n- id: `{event.id}`\n- name: `{event.tool_name}`\n- status: `{event.status}`\n")
                    if progress_callback is not None and event.sub_agent_messages:
                        with contextlib.suppress(Exception):
                            await progress_callback(event.sub_agent_messages)
                    else:
                        await _emit_live()
                elif isinstance(event, ToolCallEnd):
                    _flush_text_buffer()
                    result_parts.append(f"### Tool End\n- id: `{event.id}`\n")
                    await _emit_live()
                elif isinstance(event, ToolResult):
                    _flush_text_buffer()
                    content = event.content.strip()
                    if len(content) > 2000:
                        content = f"{content[:2000]}\n... (truncated)"
                    result_parts.append(
                        f"### Tool Result\n- id: `{event.id}`\n- error: `{'yes' if event.is_error else 'no'}`\n\n```text\n{content}\n```\n"
                    )
                    await _emit_live()
                elif isinstance(event, Reference):
                    if event.reference:
                        sub_refs.append(event.reference)
                elif isinstance(event, Finish):
                    _flush_text_buffer()
                    await _emit_live(force=True)
                    if event.reason == "error":
                        _save()
                        return {
                            "content": "Error: Sub-agent failed",
                            "messages": sub_agent.session.messages,
                            "session_id": saved_session_id,
                            "references": sub_refs,
                        }
        except asyncio.CancelledError:
            cancelled = True
            logger.info("[sub_agent] cancelled by parent, session_id={sid}", sid=saved_session_id)
        finally:
            _save()
            self._child_loops.discard(sub_agent.loop)

        final_text = ""
        for msg in reversed(sub_agent.session.messages):
            if msg.get("role") != "assistant":
                continue
            txt = str(msg.get("content") or "")
            if txt.strip():
                final_text = txt
                break
            rsn = str(msg.get("reasoning_content") or "")
            if rsn.strip():
                final_text = f"[Thinking]\n{rsn}"
                break
            tcs = msg.get("tool_calls") or []
            if tcs:
                names = [tc.get("function", {}).get("name", "?") for tc in tcs]
                final_text = f"[Tool calls executed: {', '.join(names)}]"
                break
        logger.info("[sub_agent] done session_id={sid} final_len={flen} msgs={mcount} cancelled={cancelled}",
                      sid=saved_session_id, flen=len(final_text), mcount=len(sub_agent.session.messages), cancelled=cancelled)
        logger.info("[sub_agent] final_text={t:.200s}", t=final_text)
        return {
            "content": final_text or ("[Cancelled by user]" if cancelled else "No output from sub-agent"),
            "messages": sub_agent.session.messages,
            "session_id": saved_session_id,
            "references": sub_refs,
        }
