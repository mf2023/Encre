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

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Limits ────────────────────────────────────────────────────────────
MAX_EMPTY_RESPONSE_RETRIES = 2
MAX_TRUNCATED_TOOL_CALL_RETRIES = 2
MAX_MESSAGE_REPAIR_DEPTH = 50
PRE_API_COMPACT_THRESHOLD_RATIO = 0.85
POST_TOOL_COMPACT_THRESHOLD_RATIO = 0.80
MAX_STEER_MESSAGES = 5

# ── Surrogate / control character patterns ────────────────────────────
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\n{4,}")


# ── 1. Message Repair ─────────────────────────────────────────────────

def repair_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repair message list before sending to the API.

    Fixes:
    - Role alternation: ensure user/assistant/tool roles alternate properly
    - Surrogate characters: remove invalid Unicode surrogates
    - Control characters: strip non-printable control chars
    - Excessive whitespace: collapse 4+ newlines to 2
    - Empty messages: remove or pad with whitespace
    - Tool call / tool result pairing: ensure every tool_call has a result

    Mirrors Hermes agent's message sanitization in conversation_loop.py.
    """
    if not messages:
        return messages

    repaired: list[dict[str, Any]] = []

    for msg in messages:
        msg = dict(msg)  # shallow copy
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Strip surrogates and control characters from string content
        if isinstance(content, str):
            content = _SURROGATE_RE.sub("", content)
            content = _CONTROL_RE.sub("", content)
            content = _WHITESPACE_RE.sub("\n\n", content)
            msg["content"] = content

        # Also fix tool call arguments
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                args = tc.get("function", {}).get("arguments", "")
                if isinstance(args, str):
                    args = _SURROGATE_RE.sub("", args)
                    args = _CONTROL_RE.sub("", args)
                    tc["function"]["arguments"] = args

        # Skip completely empty messages (no content, no tool_calls, no tool_call_id)
        if (not content and not msg.get("tool_calls")
                and not msg.get("tool_call_id")):
            continue

        # Pad empty assistant content when it has tool_calls (API requires content)
        if role == "assistant" and msg.get("tool_calls") and not content:
            msg["content"] = ""

        # Pad empty tool results (API requires non-null content)
        if role == "tool" and not content:
            msg["content"] = "(tool returned no output)"

        repaired.append(msg)

    # Fix role alternation: ensure the first message is system/user,
    # and tool messages are preceded by assistant with tool_calls.
    repaired = _fix_role_alternation(repaired)

    return repaired


def _fix_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure messages alternate properly for the chat completions API.

    Rules:
    - Consecutive same-role messages get merged
    - Tool messages are left untouched; pairing is handled separately
      by _sanitize_tool_groups so we don't insert empty tool_calls blocks
      that DeepSeek/OpenAI reject.
    - Leading assistant messages get a user placeholder
    """
    if not messages:
        return messages

    result: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")

        # Merge consecutive same-role user/assistant messages.  We deep-copy
        # when mutating so the original session state is not affected.
        if result and result[-1].get("role") == role and role in ("user", "assistant"):
            prev = result[-1]
            prev_content = str(prev.get("content") or "")
            cur_content = str(msg.get("content") or "")
            if prev_content and cur_content:
                prev["content"] = prev_content + "\n" + cur_content
            elif cur_content:
                prev["content"] = cur_content
            # Merge tool_calls for assistant messages, preserving order.
            if role == "assistant" and msg.get("tool_calls"):
                prev_tc = list(prev.get("tool_calls") or [])
                prev_tc.extend(msg["tool_calls"])
                prev["tool_calls"] = prev_tc
            continue

        result.append(dict(msg))

    # Ensure first non-system message is a user message
    first_idx = 0
    if result and result[0].get("role") == "system":
        first_idx = 1
    if first_idx < len(result) and result[first_idx].get("role") == "assistant":
        result.insert(first_idx, {
            "role": "user",
            "content": "(continue)",
        })

    return result


# ── 2. Empty Response Detection ───────────────────────────────────────

def is_empty_response(
    text_parts: list[str],
    tool_call_buffers: dict[int, dict[str, Any]],
    thinking_parts: list[str],
) -> bool:
    """Return True if the model returned no usable content."""
    has_text = any(part.strip() for part in text_parts)
    has_tools = bool(tool_call_buffers)
    has_thinking = any(part.strip() for part in thinking_parts)
    return not (has_text or has_tools or has_thinking)


def build_empty_retry_message(retry_count: int) -> str:
    """Build the retry message for empty responses."""
    if retry_count == 1:
        return (
            "Your previous response was empty. Please provide a response. "
            "If you need to use a tool, do so. If you're done, say so explicitly."
        )
    return (
        "Your response was empty again. You must respond with text or a tool call. "
        "Do not return an empty response."
    )


# ── 3. Truncated Tool Call Detection ──────────────────────────────────

def is_truncated_tool_call(tool_call_buffers: dict[int, dict[str, Any]]) -> bool:
    """Return True if any tool call has truncated/invalid JSON arguments."""
    for tc in tool_call_buffers.values():
        args = tc.get("arguments", "")
        if not args:
            return True
        if isinstance(args, str):
            stripped = args.strip()
            if not stripped:
                return True
            # Check if it looks like truncated JSON
            if stripped.startswith("{") and not stripped.endswith("}"):
                return True
            if stripped.startswith("[") and not stripped.endswith("]"):
                return True
            # Try to parse
            import json
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                # Could be truncated or just bad JSON
                if len(stripped) > 10:
                    return True
    return False


def build_truncated_retry_message(tool_name: str, args_preview: str) -> str:
    """Build the retry message for truncated tool calls."""
    return (
        f"The tool call for '{tool_name}' was truncated or had invalid arguments. "
        f"Arguments received: {args_preview[:200]}... "
        f"Please re-issue the tool call with complete, valid JSON arguments."
    )


# ── 4. Pre-API Token Pressure Check ──────────────────────────────────

def check_token_pressure(
    messages: list[dict[str, Any]],
    context_window: int,
    max_tokens: int,
) -> float:
    """Return the ratio of estimated input tokens to available context.

    Values > 1.0 mean the request will likely overflow.
    Values > PRE_API_COMPACT_THRESHOLD_RATIO mean we should compact first.
    """
    try:
        from encre.utils.tokens import count_message_tokens
        input_tokens = count_message_tokens(messages)
    except Exception:
        # Fallback: rough estimate (4 chars per token)
        total_chars = sum(
            len(str(m.get("content", "")))
            + len(str(m.get("tool_calls", "")))
            for m in messages
        )
        input_tokens = total_chars // 4

    available = context_window - max_tokens
    if available <= 0:
        return 1.0
    return input_tokens / available


# ── 5. Post-Tool Compression Check ────────────────────────────────────

def should_post_tool_compact(
    messages: list[dict[str, Any]],
    context_window: int,
    max_tokens: int,
) -> bool:
    """Return True if context should be compressed after tool execution."""
    ratio = check_token_pressure(messages, context_window, max_tokens)
    return ratio > POST_TOOL_COMPACT_THRESHOLD_RATIO


# ── 6. Interrupt / Abort Check ────────────────────────────────────────

class InterruptSignal:
    """Lightweight interrupt signal that can be checked cheaply."""

    def __init__(self) -> None:
        self._aborted = False

    def abort(self) -> None:
        self._aborted = True

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    def reset(self) -> None:
        self._aborted = False


def check_interrupt(loop: Any) -> bool:
    """Return True if the loop should abort before the next API call.

    Checks the loop's cancel flag and any pending interrupt signals.
    """
    # Check the loop's existing _cancelled() method
    cancelled = getattr(loop, "_cancelled", lambda: False)
    if callable(cancelled):
        try:
            return bool(cancelled())
        except Exception:
            pass

    # Check for abort event
    cancel_event = getattr(loop, "_cancel_event", None)
    if cancel_event is not None:
        try:
            return cancel_event.is_set()
        except Exception:
            pass

    return False


# ── 7. Tombstone Generation ───────────────────────────────────────────

def build_tombstone_messages(
    tool_call_buffers: dict[int, dict[str, Any]],
    reason: str,
) -> list[dict[str, Any]]:
    """Build tombstone messages for orphaned tool calls.

    When the streaming is interrupted or the model fails mid-response,
    any tool_use blocks that were emitted need matching tool_result
    blocks or the API will reject the next request.

    Unlike the simple orphan cleanup in recovery_loop.py, tombstones
    also include a placeholder assistant message so the conversation
    history clearly shows where the interruption happened.

    Mirrors Claude Code's tombstone pattern in query.ts.
    """
    tombstones: list[dict[str, Any]] = []

    # Add a placeholder assistant message marking the interruption
    if tool_call_buffers:
        tombstones.append({
            "role": "assistant",
            "content": f"[Response interrupted: {reason}]",
        })

    # Add tool_result blocks for each orphaned tool call
    for tc in tool_call_buffers.values():
        tc_id = tc.get("id", "") or tc.get("_client_id", "")
        if not tc_id:
            continue
        tombstones.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "name": tc.get("name", ""),
            "content": f"[Tool execution was interrupted: {reason}]",
            "is_error": True,
        })

    return tombstones


# ── 8. Withheld Error Pattern ────────────────────────────────────────

class WithheldError:
    """Wraps an error that should be withheld from the user until
    recovery has been attempted.

    If recovery succeeds, the error is silently consumed.
    If recovery fails, the error is released and shown to the user.

    Mirrors Claude Code's withheld error pattern in query.ts.
    """

    def __init__(self, error: Exception, *, kind: str = "unknown") -> None:
        self.error = error
        self.kind = kind
        self._released = False

    @property
    def should_withhold(self) -> bool:
        """Return True if the error should be withheld (not yet released)."""
        return not self._released

    def release(self) -> Exception:
        """Release the error so it will be shown to the user."""
        self._released = True
        return self.error

    def consume(self) -> None:
        """Silently consume the error (recovery succeeded)."""
        self._released = True


def classify_error(exc: Exception) -> str:
    """Classify an error to determine which recovery strategy to try.

    Returns one of: 'context_overflow', 'rate_limit', 'empty_response',
    'truncated_tool_call', 'network', 'auth', 'unknown'.
    """
    msg = str(exc).lower()

    if is_rate_limit_or_overload_msg(msg):
        return "rate_limit"
    if is_context_overflow_msg(msg):
        return "context_overflow"
    if "timeout" in msg or "timed out" in msg or "connection" in msg:
        return "network"
    if "auth" in msg or "unauthorized" in msg or "api key" in msg:
        return "auth"
    return "unknown"


def is_rate_limit_or_overload_msg(msg: str) -> bool:
    patterns = [
        "rate limit", "too many requests", "overloaded",
        "capacity", "throttl", "429", "503",
        "service unavailable", "high demand",
    ]
    return any(p in msg for p in patterns)


def is_context_overflow_msg(msg: str) -> bool:
    patterns = [
        "prompt is too long", "context length exceeded",
        "input length exceeds", "input is too long",
        "maximum context length", "reduce the length",
        "too many tokens", "413", "request too large",
    ]
    return any(p in msg for p in patterns)


# ── 9. Thinking Prefill ───────────────────────────────────────────────

def build_thinking_prefill(
    prompt: str,
    *,
    enabled: bool = False,
    hint: str = "",
) -> str | None:
    """Build a thinking block prefill to guide the model.

    When enabled, this returns a partial thinking block that the model
    will continue from, helping it start reasoning immediately.

    Mirrors Hermes agent's thinking prefill in conversation_loop.py.
    """
    if not enabled:
        return None

    # Build a brief thinking hint based on the prompt
    if not hint:
        if "?" in prompt:
            hint = "Let me analyze this question step by step."
        elif "error" in prompt.lower() or "bug" in prompt.lower():
            hint = "Let me investigate this issue systematically."
        else:
            hint = "Let me think about the best approach."

    return hint


# ── 10. Budget Grace Call ─────────────────────────────────────────────

class BudgetState:
    """Tracks token budget and whether a grace call has been used."""

    def __init__(self, *, max_tokens: int = 0, grace_enabled: bool = True) -> None:
        self.max_tokens = max_tokens
        self.used_tokens = 0
        self.grace_enabled = grace_enabled
        self._grace_used = False

    @property
    def is_exhausted(self) -> bool:
        return self.max_tokens > 0 and self.used_tokens >= self.max_tokens

    @property
    def can_grace(self) -> bool:
        """Return True if a grace call is available."""
        return self.grace_enabled and self.is_exhausted and not self._grace_used

    def use_grace(self) -> None:
        self._grace_used = True

    def add_usage(self, tokens: int) -> None:
        self.used_tokens += tokens


def build_grace_message(remaining_work: str = "") -> str:
    """Build the grace call message when budget is exhausted."""
    msg = (
        "Token budget exhausted. This is a grace call - please wrap up your "
        "current task concisely. Provide a summary of what was done and "
        "what remains."
    )
    if remaining_work:
        msg += f"\n\nRemaining work: {remaining_work}"
    return msg


# ── 11. /steer Injection ──────────────────────────────────────────────

class SteerQueue:
    """Queue for user mid-conversation instruction injections.

    Users can inject instructions via /steer commands while the agent
    is running. These are queued and drained before each API call.

    Mirrors Hermes agent's /steer mechanism.
    """

    def __init__(self) -> None:
        self._queue: list[str] = []
        self._max = MAX_STEER_MESSAGES

    def push(self, message: str) -> None:
        """Add a steer message to the queue."""
        if len(self._queue) < self._max:
            self._queue.append(message)
            logger.info("[steer] queued instruction: %s", message[:80])

    def drain(self) -> list[str]:
        """Drain and return all queued steer messages."""
        if not self._queue:
            return []
        items = list(self._queue)
        self._queue.clear()
        return items

    @property
    def has_pending(self) -> bool:
        return bool(self._queue)


def build_steer_injection(steer_messages: list[str]) -> str:
    """Build a user message from queued steer instructions."""
    if not steer_messages:
        return ""
    if len(steer_messages) == 1:
        return f"[User instruction mid-conversation]\n{steer_messages[0]}"
    parts = "\n".join(f"- {m}" for m in steer_messages)
    return f"[User instructions mid-conversation]\n{parts}"
