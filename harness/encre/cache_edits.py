#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 漏 2025-2026 Wenze Wei. All Rights Reserved.
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
2. **Decide what to delete** -- when the registered tool count exceeds the
3. **Build the block** -- ``{"type": "cache_edits", "edits": [{"type":
4. **Insert at the API layer** -- the block is spliced into the *last* user
5. **Consume once** -- after the block is attached to an outgoing request it

NOTE: ``cache_edits`` is an Anthropic first-party capability.  It only takes
effect when Encre is pointed at the real Anthropic Messages API (``backend_type
= "anthropic"``).  Other backends (OpenAI-compatible / DeepSeek / Ollama ...)
silently ignore the block, so this is a no-op there -- cached microcompact
simply doesn't run on non-Anthropic backends.
"""


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


    def to_block(self) -> dict[str, Any]:


@dataclass
class PinnedEdits:



@dataclass
class CacheEditsState:





def create_state(
) -> CacheEditsState:


def _collect_tool_use_ids(messages: list[dict[str, Any]]) -> list[str]:

    for msg in messages:
        if not isinstance(msg, dict):
        if not isinstance(content, list):
        for block in content:
            if (


def register_tool_results(
) -> None:

    for tool_use_id in _collect_tool_use_ids(messages):
        if tool_use_id in state.registered:


def mark_sent_to_api(state: CacheEditsState) -> None:



def get_tool_results_to_delete(state: CacheEditsState) -> list[str]:


    if len(state.tool_order) < state.trigger_threshold:
    # The most recent keep_recent are preserved; everything older is a
    # candidate.  tool_order is insertion order, so the head is oldest.
        for tid in candidates
        if tid in state.sent_to_api and tid not in state.deleted_refs


def create_cache_edits_block(
) -> CacheEditsBlock | None:

    if not tool_use_ids:
    for tid in tool_use_ids:


def consume_pending(state: CacheEditsState) -> CacheEditsBlock | None:



def get_pinned(state: CacheEditsState) -> list[PinnedEdits]:


def pin_edits(state: CacheEditsState, user_message_index: int, block: CacheEditsBlock) -> None:



def deduplicate(block: CacheEditsBlock, seen: set[str]) -> CacheEditsBlock:

    for edit in block.edits:
        if ref in seen:


def reset(state: CacheEditsState) -> None:


# 鈹€鈹€ API-layer insertion (mirrors addCacheBreakpoints in claude.ts) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def attach_cache_edits(
) -> list[dict[str, Any]]:



    if not pending and not pinned:

    # Shallow-copy the list and each message dict so we never mutate caller state.

    # Re-insert pinned blocks at their recorded positions.
    for p in pinned:
        if 0 <= p.user_message_index < len(result):
            if msg.get("role") != "user":
            if not isinstance(content, list):
            if deduped.edits:

    # Insert the pending block into the last user message.
    if pending is not None:
        if deduped.edits:
            for i in range(len(result) - 1, -1, -1):
                if msg.get("role") == "user":
                    if not isinstance(content, list):



def _insert_after_tool_results(
) -> list[dict[str, Any]]:

    for j in range(len(new_content) - 1, -1, -1):
        if (
