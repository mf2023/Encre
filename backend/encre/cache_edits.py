#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Cached microcompact -- delete old tool results via ``cache_edits``.

This mirrors Claude Code's ``cachedMicrocompact`` path (see
``services/compact/microCompact.ts`` and the cache-edits handling in
``services/api/claude.ts``).  The idea:

Normal microcompact **replaces** an old tool_result with a ``[cleared]``
stub.  That changes the message bytes, which busts the prompt-cache prefix
-- every subsequent turn re-sends the whole conversation (no cache discount).

``cache_edits`` is an Anthropic Messages-API content-block type that tells
the server to **evict specific cached tool_results by reference** without the
client rewriting the message content.  The prefix stays byte-identical, so
the cache hit is preserved and the deleted tokens stop counting against the
context window.

Lifecycle (mirrors Claude Code exactly):

1. **Register** -- before each API call, walk the messages and record every
   ``tool_result`` block (its ``tool_use_id`` is its ``cache_reference``),
   grouped by the user message that contains it.  Each tool_result is
   registered exactly once.
2. **Decide what to delete** -- when the registered tool count exceeds the
   keep-recent window, the oldest ones (past the keep window AND already sent
   to the API at least once) become deletion candidates.
3. **Build the block** -- ``{"type": "cache_edits", "edits": [{"type":
   "delete", "cache_reference": tool_use_id}, ...]}``.
4. **Insert at the API layer** -- the block is spliced into the *last* user
   message's content (right after its tool_results), NOT into the local
   message list.  The local messages stay unchanged so the prefix is
   preserved.  Pinned so it's re-sent at the same position on future calls
   until the server confirms deletion.
5. **Consume once** -- after the block is attached to an outgoing request it
   is consumed (cleared from ``pending``); the pinned copy keeps it alive for
   retries / subsequent turns until the API confirms deletion via
   ``cache_deleted_input_tokens``.

NOTE: ``cache_edits`` is an Anthropic first-party capability.  It only takes
effect when Encre is pointed at the real Anthropic Messages API (``backend_type
= "anthropic"``).  Other backends (OpenAI-compatible / DeepSeek / Ollama ...)
silently ignore the block, so this is a no-op there -- cached microcompact
simply doesn't run on non-Anthropic backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from encre.logging_config import get_logger

logger = get_logger("encre.cache_edits")

# Beta header Anthropic requires for cache editing.  Mirrors Claude Code's
# cache-editing header latch (services/api/claude.ts:1431).  Latch-on so the
# header stays for the rest of the session once enabled, matching Anthropic's
# requirement that cache_control / cache_edits betas not be toggled mid-stream
# (toggling busts the cache prefix).
CACHE_EDITING_BETA_HEADER = "context-management-2025-06-27"

# Default keep-recent window: never delete a tool_result that is among the most
# recent N registered ones.  Mirrors Claude Code's ``keepRecent`` config (the
# GrowthBook ``tengu_hawthorn_cached_mc_keep_recent`` default).
DEFAULT_KEEP_RECENT = 6

# Default trigger threshold: don't bother deleting until at least this many
# tool_results are registered.  Matches Claude Code's triggerThreshold.
DEFAULT_TRIGGER_THRESHOLD = 8


@dataclass
class CacheEditsBlock:
    """The ``cache_edits`` content block queued for the API layer."""

    edits: list[dict[str, str]] = field(default_factory=list)

    def to_block(self) -> dict[str, Any]:
        """Serialise into an Anthropic content block."""
        return {"type": "cache_edits", "edits": list(self.edits)}


@dataclass
class PinnedEdits:
    """A cache_edits block pinned to a user-message index so it is re-sent at
    the same position on future calls until the server confirms the deletion.
    """

    user_message_index: int
    block: CacheEditsBlock


@dataclass
class CacheEditsState:
    """Per-loop accounting for cached microcompact.

    Mirrors Claude Code's ``CachedMCState`` (cachedMicrocompact module):

    - ``tool_order`` -- insertion order of registered tool_use_ids; the head
      of this list is the oldest, i.e. the first deletion candidate.
    - ``registered`` -- set of tool_use_ids already registered, so each
      tool_result is only registered once (re-registering would reset its
      "age" and defeat the LRU eviction).
    - ``sent_to_api`` -- tool_use_ids that have appeared in at least one
      outgoing request.  A tool_result is only deletable once it has actually
      been cached on the server (you can't delete a reference the server has
      never seen).
    - ``deleted_refs`` -- tool_use_ids whose delete edit has been queued/pinned.
      Tracked so we never queue the same deletion twice.
    - ``pending`` -- the block built this turn, consumed once by the backend
      when it is attached to an outgoing request.
    - ``pinned`` -- blocks pinned to a user-message index, re-sent every
      turn until the API confirms deletion.
    """

    tool_order: list[str] = field(default_factory=list)
    registered: set[str] = field(default_factory=set)
    sent_to_api: set[str] = field(default_factory=set)
    deleted_refs: set[str] = field(default_factory=set)
    pending: CacheEditsBlock | None = None
    pinned: list[PinnedEdits] = field(default_factory=list)
    keep_recent: int = DEFAULT_KEEP_RECENT
    trigger_threshold: int = DEFAULT_TRIGGER_THRESHOLD


def create_state(
    keep_recent: int = DEFAULT_KEEP_RECENT,
    trigger_threshold: int = DEFAULT_TRIGGER_THRESHOLD,
) -> CacheEditsState:
    """Create a fresh per-loop cache-edits accounting state."""
    return CacheEditsState(
        keep_recent=keep_recent,
        trigger_threshold=trigger_threshold,
    )


def _collect_tool_use_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Return every ``tool_use_id`` seen in ``tool_result`` blocks, in order.

    Order matters: it is the insertion order fed to ``tool_order``, so the
    head of the list is the oldest registered tool_result -- the first
    deletion candidate.
    """
    ids: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("tool_use_id")
            ):
                ids.append(str(block["tool_use_id"]))
    return ids


def register_tool_results(
    state: CacheEditsState,
    messages: list[dict[str, Any]],
) -> None:
    """Register every ``tool_result`` in *messages* with the accounting state.

    Each tool_use_id is registered exactly once (re-registration would reset
    its position in ``tool_order`` and defeat LRU eviction).  Mirrors Claude
    Code's second pass in ``cachedMicrocompactPath`` (microCompact.ts:315).
    """
    for tool_use_id in _collect_tool_use_ids(messages):
        if tool_use_id in state.registered:
            continue
        state.registered.add(tool_use_id)
        state.tool_order.append(tool_use_id)


def mark_sent_to_api(state: CacheEditsState) -> None:
    """Mark every currently-registered tool_result as sent to the API.

    Called after the backend attaches the queued edits (or simply sends the
    messages) so that the next turn's deletion candidates are eligible.
    Mirrors Claude Code's ``markToolsSentToAPI``.
    """
    state.sent_to_api.update(state.tool_order)


def get_tool_results_to_delete(state: CacheEditsState) -> list[str]:
    """Return the tool_use_ids that should be deleted this turn.

    A tool_result is deletable when:
      - it is past the keep-recent window (the most recent ``keep_recent``
        are always preserved), AND
      - it has already been sent to the API at least once (you can't delete a
        reference the server has never cached), AND
      - it hasn't already been queued for deletion.

    Returns an empty list when the registered count is below the trigger
    threshold, so cached microcompact is a no-op on short conversations.
    """
    if len(state.tool_order) < state.trigger_threshold:
        return []
    # The most recent keep_recent are preserved; everything older is a
    # candidate.  tool_order is insertion order, so the head is oldest.
    cutoff = len(state.tool_order) - state.keep_recent
    candidates = state.tool_order[:max(0, cutoff)]
    return [
        tid
        for tid in candidates
        if tid in state.sent_to_api and tid not in state.deleted_refs
    ]


def create_cache_edits_block(
    state: CacheEditsState,
    tool_use_ids: list[str],
) -> CacheEditsBlock | None:
    """Build a ``cache_edits`` block for *tool_use_ids* and mark them deleted.

    Returns ``None`` (no block) when *tool_use_ids* is empty.  Mirrors Claude
    Code's ``createCacheEditsBlock``: each deletion is
    ``{"type": "delete", "cache_reference": tool_use_id}``.
    """
    if not tool_use_ids:
        return None
    edits = [{"type": "delete", "cache_reference": tid} for tid in tool_use_ids]
    for tid in tool_use_ids:
        state.deleted_refs.add(tid)
    block = CacheEditsBlock(edits=edits)
    state.pending = block
    return block


def consume_pending(state: CacheEditsState) -> CacheEditsBlock | None:
    """Pop and return the pending block (called once by the backend per request).

    Mirrors Claude Code's ``consumePendingCacheEdits`` -- it's consumed once
    so that retries / multiple paramsFromContext calls don't each steal the
    edits (claude.ts:1531 comment).
    """
    block = state.pending
    state.pending = None
    return block


def get_pinned(state: CacheEditsState) -> list[PinnedEdits]:
    """Return the pinned edits list (re-sent every turn until confirmed)."""
    return list(state.pinned)


def pin_edits(state: CacheEditsState, user_message_index: int, block: CacheEditsBlock) -> None:
    """Pin a cache_edits block to a user-message index.

    Mirrors Claude Code's ``pinCacheEdits`` -- the block is re-sent at the same
    position on future calls until the API confirms deletion via
    ``cache_deleted_input_tokens``.
    """
    state.pinned.append(PinnedEdits(user_message_index=user_message_index, block=block))


def deduplicate(block: CacheEditsBlock, seen: set[str]) -> CacheEditsBlock:
    """Return a copy of *block* with already-seen delete refs removed.

    Mirrors Claude Code's ``deduplicateEdits`` (claude.ts:3116): the same
    ``cache_reference`` must not appear twice across pending + pinned blocks
    in a single request.
    """
    unique = []
    for edit in block.edits:
        ref = edit.get("cache_reference", "")
        if ref in seen:
            continue
        seen.add(ref)
        unique.append(edit)
    return CacheEditsBlock(edits=unique)


def reset(state: CacheEditsState) -> None:
    """Clear per-run accounting (call at session end)."""
    state.tool_order.clear()
    state.registered.clear()
    state.sent_to_api.clear()
    state.deleted_refs.clear()
    state.pending = None
    state.pinned.clear()


# ── API-layer insertion (mirrors addCacheBreakpoints in claude.ts) ────────


def attach_cache_edits(
    messages: list[dict[str, Any]],
    pending: CacheEditsBlock | None,
    pinned: list[PinnedEdits],
) -> list[dict[str, Any]]:
    """Return a copy of *messages* with cache_edits blocks spliced in.

    This is the API-layer step: the local message list is NEVER mutated (that
    would bust the cache prefix).  Instead a shallow-copied list has
    ``cache_edits`` blocks inserted into user messages:

    - **Pinned** blocks are re-inserted at their original user-message index
      (so a deletion requested last turn but not yet confirmed by the server
      keeps being requested).
    - **Pending** (new this turn) is inserted into the LAST user message,
      right after its tool_results.

    Mirrors Claude Code's ``addCacheBreakpoints`` (claude.ts:3107-3162): the
    pending block goes into the last user message; pinned blocks go back to
    their recorded index.  Both go through ``deduplicate`` against a shared
    ``seen`` set so no reference is deleted twice in one request.
    """
    if not pending and not pinned:
        return messages

    # Shallow-copy the list and each message dict so we never mutate caller state.
    result: list[dict[str, Any]] = [dict(m) for m in messages]
    seen: set[str] = set()

    # Re-insert pinned blocks at their recorded positions.
    for p in pinned:
        if 0 <= p.user_message_index < len(result):
            msg = result[p.user_message_index]
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                content = [{"type": "text", "text": content or ""}]
            deduped = deduplicate(p.block, seen)
            if deduped.edits:
                content = _insert_after_tool_results(content, deduped.to_block())
                msg["content"] = content

    # Insert the pending block into the last user message.
    if pending is not None:
        deduped = deduplicate(pending, seen)
        if deduped.edits:
            for i in range(len(result) - 1, -1, -1):
                msg = result[i]
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if not isinstance(content, list):
                        content = [{"type": "text", "text": content or ""}]
                    content = _insert_after_tool_results(content, deduped.to_block())
                    msg["content"] = content
                    break

    return result


def _insert_after_tool_results(
    content: list[dict[str, Any]],
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    """Insert *block* into *content* right after the last ``tool_result``.

    Mirrors Claude Code's ``insertBlockAfterToolResults``: the cache_edits
    block must come after all tool_results in the same user message so the
    references it deletes are already defined.  If there are no tool_results,
    the block is appended at the end.
    """
    new_content = list(content)
    insert_at = len(new_content)
    for j in range(len(new_content) - 1, -1, -1):
        if (
            isinstance(new_content[j], dict)
            and new_content[j].get("type") == "tool_result"
        ):
            insert_at = j + 1
            break
    new_content.insert(insert_at, block)
    return new_content
