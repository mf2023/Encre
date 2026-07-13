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

"""Model-driven context compaction -- Claude Code style.

Architecture
------------
There is ONE compaction mechanism: the model reads the conversation and
produces a structured summary.  No heuristic truncation, no fixed turn
counts -- pure token arithmetic decides when to compact.

The pipeline runs **before every API call** in the agent loop:

1. **Microcompact** -- cheap cleanup of old tool results (no API call).
   Clears tool outputs whose cache TTL has expired, replacing them with
   ``[Previous tool output cleared]`` stubs.

2. **Traditional compact** -- the model summarises the conversation into a
   9-section structured block.  Runs when microcompact isn't enough to
   stay under the token budget.

3. **Reactive compact** -- emergency summarisation when the API returns a
   400 / context-length-exceeded error.

Compact agent
-------------
The summarisation call uses the **same backend** as the main loop, but:
- Thinking is disabled
- Only ``file_read`` tool is available
- Output is capped at 4 096 tokens

The summary is inserted as a pair of boundary messages:

    [role: compact_boundary]
    [role: user, is_compact_summary: true, content: <summary>]

Anchor protection
-----------------
The FIRST user message (task definition) and the LAST 2 complete turns
are never removed.  They are spliced into the compacted result after
the summary.

Boundary format
---------------
Messages carry an ``is_compact_boundary`` marker so the frontend can
render a visual divider, and ``is_compact_summary`` so the model can
distinguish the summary from real user input.
"""

from typing import Any

from encre.logging_config import get_logger
from encre.utils.tokens import count_message_tokens

logger = get_logger("encre.compact")

# ── Thresholds ─────────────────────────────────────────────────────────

AUTOCOMPACT_BUFFER_TOKENS = 13_000   # how far below the effective window we trigger
MICROCOMPACT_CACHE_TTL_MINUTES = 30  # clear tool results older than this
MICROCOMPACT_KEEP_RECENT_TURNS = 5   # keep this many recent turns during microcompact
COMPACT_MAX_OUTPUT_TOKENS = 16_384   # max tokens for the summary response
MAX_CONSECUTIVE_COMPACT_FAILURES = 3  # circuit breaker
COMPACTABLE_TOOLS = frozenset({       # tools whose results can be cleared
    "bash", "grep", "glob", "web_search", "web_fetch",
    "file_read", "file_write", "file_edit", "git", "lsp",
    "notebook", "database", "docker", "pdf", "browser",
    "find_tool", "deploy", "apply_patch", "test_runner",
    "lint_format", "image", "spreadsheet",
})

# ── Compact summary prompt ─────────────────────────────────────────────

_COMPACT_PROMPT = """You are summarising an AI agent conversation that has reached the context limit. Your summary must be COMPLETE enough for the agent to CONTINUE working without losing any important context.  # noqa: E501

Output your response in two parts:
<analysis>
Scratchpad -- note what happened, what was completed, what failed, what remains. This will be removed before the summary is given to the agent.  # noqa: E501
</analysis>
<summary>
The actual summary that will be inserted into the conversation.
</summary>

## Required sections in <summary>

### 1. Primary Request and Intent
The user's original goal. What they asked for. Include any constraints or preferences they specified.  # noqa: E501

### 2. Files and Code Sections
List every file that was read, modified, or created. Note key functions, classes, or sections that were worked on. Quote exact paths.  # noqa: E501

### 3. Key Decisions and Changes Made
What was decided and why. What changes were made. Include architecture decisions, library choices, design patterns.  # noqa: E501

### 4. Errors and Fixes
Every error that occurred and how it was resolved. Include exact error messages when relevant.

### 5. Current State
WHERE the work is right now. What was the last action taken? What is the current value of important variables / configuration / state?  # noqa: E501

### 6. Pending Tasks
What still needs to be done. List explicitly. Note any blockers.

### 7. User Messages
All messages from the user (not tool results). Preserve the exact questions and instructions.

### 8. Workspace Context
Current working directory, active git branch, relevant environment details.

### 9. Next Step (Optional)
If the next action is clear, state it. Otherwise say what information is needed to decide the next step.  # noqa: E501

## Rules
- Be SPECIFIC. Do not say "various files were edited" -- name them.
- Quote exact file paths, function signatures, and error messages.
- The agent reading this summary cannot see the original messages. It must be able to continue from where you left off.  # noqa: E501
- Keep the summary under 4000 words. Prioritise recent information over old.
"""


class CompactEngine:
    """Model-driven context compaction engine.

    Provides three levels:

    1. :meth:`microcompact` -- cheap, no API call.  Clears old tool results.
    2. :meth:`compact` -- the model reads the conversation and produces a
       structured summary.  This is the primary mechanism.
    3. :meth:`should_compact` -- pure token arithmetic: should we compact?

    The engine is designed to be called **before every API call** in the
    agent loop.  It does NOT modify session state -- it returns new
    message lists that the caller can choose to adopt.

    **Archive fallback**: Before compaction, original messages are saved
    to ``session.compact_archives``.  If the model realises the summary
    is missing critical details, it can request the archive content from
    previous compact events (displayed as compact boundary cards in the
    UI).  This prevents permanent information loss from a single lossy
    summary.
    """

    def __init__(self) -> None:
        """Initialise the compaction engine.

        Sets up the consecutive-failure counter used by the circuit
        breaker and the pre-compact message cache that backs the archive
        fallback (so the model can recall original context if a summary
        drops critical details).
        """
        self._failure_count = 0
        self._last_compact_turn = -1
        # Pre-compact message cache: maps session_id → list of original messages
        # before the most recent compaction.  Saved BEFORE compact runs so
        # the model can request a recall if the summary missed critical info.
        self._pre_compact_cache: dict[str, list[dict[str, Any]]] = {}

    def sanitize(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fix broken tool_call groups (backward compat with EncreCompactEngine).

        Strips orphaned tool results and incomplete assistant tool_call
        blocks that would cause 400 errors from backends.
        """
        return _sanitize_tool_groups(messages)

    # ── Decision ───────────────────────────────────────────────────────

    def should_compact(
        self,
        messages: list[dict[str, Any]],
        context_window: int,
        max_output_tokens: int = 32_768,
        *,
        min_turns: int = 4,
    ) -> bool:
        """Return True if the token count exceeds the compact threshold.

        The threshold is::

            effective_window = context_window - min(max_output_tokens, 32_768)
            trigger = effective_window - AUTOMATICALLY_BUFFER_TOKENS

        This fires BEFORE context is dangerously full so the model has
        headroom to consume the summary.
        """
        if len(messages) < min_turns * 2:
            return False
        effective = context_window - min(max_output_tokens, 32_768)
        threshold = effective - AUTOCOMPACT_BUFFER_TOKENS
        est = count_message_tokens(messages)
        return est > threshold

    def should_microcompact(
        self,
        messages: list[dict[str, Any]],
        context_window: int,
    ) -> bool:
        """Return True if microcompact could free meaningful space."""
        est = count_message_tokens(messages)
        # Trigger only once we cross 40% of the window -- microcompact is
        # cheap but pointless when there is still plenty of headroom.
        return est > context_window * 0.40

    # ── Microcompact (no API call) ─────────────────────────────────────

    async def microcompact(
        self,
        messages: list[dict[str, Any]],
        _context_window: int,
        keep_recent_turns: int = MICROCOMPACT_KEEP_RECENT_TURNS,
    ) -> list[dict[str, Any]]:
        """Clear old tool results to free cache-able space.

        This is the cheapest form of compaction -- no API call, just
        replaces old tool outputs with stubs.  It preserves:
        - System messages
        - All user messages
        - The last *keep_recent_turns* assistant messages and their tools
        - Tool results within the recent window

        Returns a NEW message list.  Does not mutate the input.
        """
        if len(messages) < keep_recent_turns * 2:
            return list(messages)

        # Find the cutoff: the keep_recent_turns-th assistant from the end
        assistant_count = 0
        cutoff = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                assistant_count += 1
                if assistant_count >= keep_recent_turns:
                    cutoff = i
                    break

        if cutoff == 0:
            return list(messages)

        result: list[dict[str, Any]] = []
        cleared = 0
        for i, msg in enumerate(messages):
            if i < cutoff and msg.get("role") == "tool":
                tool_name = msg.get("name", "")
                if tool_name in COMPACTABLE_TOOLS:
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) > 200:
                        new_msg = dict(msg)
                        new_msg["content"] = "[Previous tool output cleared]"
                        result.append(new_msg)
                        cleared += 1
                        continue
            result.append(msg)

        if cleared:
            logger.info(
                "[microcompact] cleared %d old tool results, "
                "kept %d recent turns", cleared, keep_recent_turns,
            )
        return result

    # ── Traditional compact (model-driven) ─────────────────────────────

    async def compact(
        self,
        messages: list[dict[str, Any]],
        backend: Any,  # BaseBackend instance
        turn_count: int = 0,
        system_prompt: str = "",
        workspace_context: str = "",
        session_id: str = "",
    ) -> list[dict[str, Any]] | None:
        """Run model-driven summarisation.

        Uses *backend* to generate a structured summary of the
        conversation.  Returns a new message list with:
        - System message preserved
        - Summary inserted as user message with ``is_compact_summary: True``
        - Last 2 turns preserved after the summary

        **Archive fallback**: Before compaction, the original messages are
        cached in ``_pre_compact_cache`` keyed by *session_id*.  The
        compacted result includes an archive marker so the model can
        reference it if the summary missed details.

        Returns ``None`` if summarisation fails (circuit breaker open,
        API error, etc.).
        """
        if self._failure_count >= MAX_CONSECUTIVE_COMPACT_FAILURES:
            logger.warning("[compact] circuit breaker open -- %d consecutive failures, falling back to budget truncation",
                           self._failure_count)
            return _budget_fallback(messages, backend.context_window_size())

        # Save pre-compact messages to archive cache BEFORE compaction
        if session_id:
            self._pre_compact_cache[session_id] = list(messages)

        # Build the compact prompt -- strip images/documents
        compact_msgs = _prepare_compact_input(messages, system_prompt)

        est = count_message_tokens(compact_msgs)
        logger.info(
            "[compact] starting turn=%d est=%dk failures=%d",
            turn_count, est // 1000, self._failure_count,
        )

        try:
            summary = await _generate_summary(backend, compact_msgs)
        except Exception as exc:
            logger.warning("[compact] API call failed: %s", exc, exc_info=True)
            self._failure_count += 1
            # Fallback: budget-based truncation as last resort
            return _budget_fallback(messages, backend.context_window_size())

        if not summary or len(summary) < 100:
            logger.warning("[compact] empty or too-short summary (%d chars)",
                           len(summary) if summary else 0)
            self._failure_count += 1
            return _budget_fallback(messages, backend.context_window_size())

        self._failure_count = 0
        self._last_compact_turn = turn_count

        # Build the compacted message list
        compacted = _build_compacted(messages, summary, workspace_context, system_prompt, session_id)
        new_est = count_message_tokens(compacted)
        logger.info(
            "[compact] done turn=%d msgs %d->%d tokens %dk->%dk "
            "(summary %d chars)",
            turn_count, len(messages), len(compacted),
            est // 1000, new_est // 1000, len(summary),
        )

        return compacted

    def get_archive(self, session_id: str) -> list[dict[str, Any]] | None:
        """Retrieve pre-compact messages for *session_id* from the archive cache.

        Returns ``None`` if no archive exists for this session.
        """
        return self._pre_compact_cache.get(session_id)


# ── Internal helpers ───────────────────────────────────────────────────


def _prepare_compact_input(
    messages: list[dict[str, Any]],
    _system_prompt: str = "",
) -> list[dict[str, Any]]:
    """Strip images/documents from messages, add compact prompt.

    Only keeps text content -- images and binary attachments waste tokens
    in the summary call.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        msg.get("role", "")
        content = msg.get("content", "")

        # Strip image/document blocks from array content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "image":
                        text_parts.append("[image]")
                    elif btype == "document":
                        text_parts.append("[document]")
                    else:
                        text_parts.append(str(block)[:200])
            content = " ".join(text_parts)

        if isinstance(content, str) and len(content) > 80_000:
            content = content[:80_000] + "\n... [truncated for compact input]"

        new_msg = dict(msg)
        new_msg["content"] = content
        result.append(new_msg)

    # Append the compact instruction as a user message
    result.append({
        "role": "user",
        "content": _COMPACT_PROMPT,
    })
    return result


async def _generate_summary(
    backend: Any,
    messages: list[dict[str, Any]],
) -> str | None:
    """Call the backend to produce a conversation summary.

    Uses a non-streaming request with:
    - thinking explicitly disabled
    - no tools
    - a compact output token budget
    """
    text_parts: list[str] = []

    try:
        async for event in backend.chat(
            messages=messages,
            tools=None,        # NO tools during compact
            tool_choice="none",
            temperature=0.0,
            max_tokens=COMPACT_MAX_OUTPUT_TOKENS,
            stream=True,
            enable_caching=False,
        ):
            from encre.utils.types import BackendText
            if isinstance(event, BackendText) and event.text:
                text_parts.append(event.text)
    except Exception:
        raise

    full_text = "".join(text_parts).strip()
    if not full_text:
        return None

    # Strip <analysis> block
    import re
    full_text = re.sub(
        r"<analysis>[\s\S]*?</analysis>", "", full_text, flags=re.IGNORECASE,
    )

    # Extract <summary> block
    m = re.search(r"<summary>([\s\S]*?)</summary>", full_text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # If no tags found, return the entire output
    return full_text


def _build_compacted(
    messages: list[dict[str, Any]],
    summary: str,
    workspace_context: str = "",
    _system_prompt: str = "",
    session_id: str = "",
) -> list[dict[str, Any]]:
    """Build the compacted message list.

    Structure:
        [system message if present]
        [compact boundary marker]
        [summary user message]
        [archive reference hint]
        [workspace context if present]
        [first user message -- task anchor]
        [last 4 complete turns]

    The first user message is ALWAYS included so the model never forgets
    the original task.  An archive reference is appended so the model
    knows it can request older context if the summary is insufficient.
    """
    result: list[dict[str, Any]] = []

    # Keep system message
    for msg in messages:
        if msg.get("role") == "system":
            result.append(dict(msg))
            break

    # Compact boundary marker
    result.append({
        "role": "user",
        "content": summary,
        "name": "compact_summary",
        "is_compact_boundary": True,
        "is_compact_summary": True,
    })

    # Archive reference: hint that older context is still available
    if session_id:
        result.append({
            "role": "user",
            "content": (
                "[The full pre-compact conversation history is archived and "
                "available on request. If the summary above missed any critical "
                "details (error messages, file contents, user instructions), "
                "you may request the archive.]"
            ),
            "is_compact_archive_hint": True,
        })

    if workspace_context:
        result.append({
            "role": "user",
            "content": workspace_context,
            "is_compact_context": True,
        })

    # Anchor: first user message
    first_user = None
    for msg in messages:
        if msg.get("role") == "user":
            first_user = dict(msg)
            break
    if first_user:
        result.append(first_user)

    # Last 4 turns -- increased from 2 to provide more recent context
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    keep_from = user_idxs[-4] if len(user_idxs) >= 4 else user_idxs[-2] if len(user_idxs) >= 2 else 0
    keep_from = max(keep_from, messages.index(first_user) if first_user else 0)

    seen_ids = {m.get("id", "") for m in result}
    for msg in messages[keep_from:]:
        mid = msg.get("id", "")
        if mid and mid in seen_ids:
            continue
        if mid:
            seen_ids.add(mid)
        result.append(dict(msg))

    return _sanitize_tool_groups(result)


def _sanitize_tool_groups(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove / repair tool_call groups so the backend never rejects a turn.

    Handles two orphan shapes that both produce 400 errors -- the classic
    pause/resume failure where a cancelled turn leaves a half-finished
    assistant+tools block behind:

    1. **Orphan tool result** -- a ``role:tool`` message whose
       ``tool_call_id`` no preceding kept assistant declared. The backend
       rejects this as "tool_use_id not found". Fixed by dropping it.

    2. **Incomplete assistant group** -- an assistant ``tool_calls`` block
       missing one or more matching tool_results (a tool was cancelled mid
       turn before its result was written). The backend rejects this as
       "messages must end with a tool_result" / "insufficient tool messages".
       Fixed by synthesizing an error tombstone for each missing id, so the
       already-executed sibling results are preserved instead of dropping the
       whole group.

    An assistant block whose ``tool_calls`` carry no usable id at all is
    dropped together with its trailing tool messages, since it can never be
    matched.
    """
    if not messages:
        return messages

    # tombstone body reused for every synthesized missing result
    tombstone = (
        "[Error: This tool call's result was not persisted. "
        "The tool did not complete.]"
    )

    result: list[dict[str, Any]] = []
    # ids declared by an assistant we have already KEPT (and that therefore
    # may legitimately be referenced by a later tool_result).
    seen_declared: set[str] = set()
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]
        role = msg.get("role", "")

        if role == "tool":
            tid = msg.get("tool_call_id", "")
            # Keep only if a preceding kept assistant declared this id.
            if tid and tid in seen_declared:
                result.append(dict(msg))
            # else: orphan result (no matching tool_call) -> drop
            i += 1
            continue

        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
            expected = {tc.get("id", "") for tc in tool_calls if tc.get("id")}
            if not expected:
                # Assistant claims tool_calls but none have an id -- the
                # block can never be matched.  Drop it and any immediately
                # following tool messages so the API never sees an
                # unmatched tool_call block.
                i += 1
                while i < n and messages[i].get("role") == "tool":
                    i += 1
                continue

            # Collect following tool results (consecutive tool messages).
            j = i + 1
            found: set[str] = set()
            while j < n and messages[j].get("role") == "tool":
                tid = messages[j].get("tool_call_id", "")
                if tid:
                    found.add(tid)
                j += 1

            missing = expected - found
            # Keep the assistant + only the tool results it declared. Any
            # other tool messages in the consecutive run are orphans (their
            # id belongs to no preceding kept assistant) -- drop them.
            declared_results = [
                dict(messages[k]) for k in range(i + 1, j)
                if messages[k].get("tool_call_id") in expected
            ]
            result.append(dict(msg))
            seen_declared |= expected
            result.extend(declared_results)
            if missing:
                # Incomplete group -- synthesize tombstones for the missing
                # ids so the sibling results are preserved instead of
                # discarding the whole turn's work.
                for mid in missing:
                    result.append({
                        "role": "tool",
                        "tool_call_id": mid,
                        "content": tombstone,
                    })
            i = j
            continue

        result.append(dict(msg))
        i += 1

    return result


def _budget_fallback(
    messages: list[dict[str, Any]],
    _context_window: int,
    keep_recent: int = 4,
) -> list[dict[str, Any]] | None:
    """Last-resort budget-based truncation when the model call fails.

    Keeps: system + first user + last *keep_recent* turns.
    """
    if len(messages) <= keep_recent * 2 + 2:
        return list(messages)

    system = [m for m in messages if m.get("role") == "system"]
    first_user = None
    for m in messages:
        if m.get("role") == "user":
            first_user = dict(m)
            break

    non_system = [m for m in messages if m.get("role") != "system"]
    recent = non_system[-(keep_recent * 2):]

    result = system + ([first_user] if first_user else []) + recent
    return _sanitize_tool_groups(result)


# ── Backward-compatible alias ──────────────────────────────────────────

EncreCompactEngine = CompactEngine
