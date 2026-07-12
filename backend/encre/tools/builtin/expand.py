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

"""Module: builtin/expand.py

Expand implementation for the Encre tool system.
"""

import json
from contextvars import ContextVar
from typing import Any

from encre.tools.base import build_tool
from encre.utils.tokens import count_message_tokens

_current_loop: ContextVar[Any] = ContextVar("encre_expand_loop", default=None)

_parent_loop: Any = None


def set_parent_loop(loop: Any) -> None:
    """Set the fallback parent loop reference for the expand context."""
    global _parent_loop
    _parent_loop = loop


def set_active_loop(loop: Any) -> Any:
    """Set the loop that expand should consult during this turn."""
    token = _current_loop.set(loop)
    return token


def reset_active_loop(token: Any) -> None:
    """Restore the active loop to its previous value using a token from set_active_loop()."""
    _current_loop.reset(token)


def _resolve_loop() -> Any:
    """Resolve loop."""
    ctx_loop = _current_loop.get()
    if ctx_loop is not None:
        return ctx_loop
    return _parent_loop


async def _expand_execute(**kwargs: Any) -> str:
    """Restore or preview compacted conversation history from the session archive."""
    loop = _resolve_loop()
    if loop is None:
        return "Error: expand requires a parent loop reference."

    session = getattr(loop, "session", None)
    if session is None:
        return "Error: no active session."

    archive = session.get_compact_archive()
    if not archive:
        return "No compact archive available. There is no previous conversation to expand."

    mode = (kwargs.get("mode") or "summary").strip().lower()

    user_msgs = [m for m in archive if m.get("role") == "user" and not m.get("is_compact_summary")]
    assistant_msgs = [m for m in archive if m.get("role") == "assistant"]
    tool_msgs = [m for m in archive if m.get("role") == "tool"]
    total_tokens = count_message_tokens(archive)

    if mode == "summary":
        return json.dumps({
            "status": "available",
            "message_count": len(archive),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "tool_results": len(tool_msgs),
            "estimated_tokens": total_tokens,
            "note": "Call expand with mode='full' to restore the complete conversation.",
        }, ensure_ascii=False, indent=2)

    if mode == "restore":
        session.messages = list(archive)
        session.mark_messages_dirty()
        session.turn_count = len(assistant_msgs)
        session.tool_call_count = len(tool_msgs)
        session.compact_archive = None
        return json.dumps({
            "status": "restored",
            "message_count": len(archive),
            "note": "Full conversation restored.",
        }, ensure_ascii=False, indent=2)

    return (
        f"Unknown mode '{mode}'. Use 'summary' to preview or 'restore' to restore."
    )


EncreExpandTool = build_tool(
    name="expand",
    description="Preview or restore compacted conversation history.",
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["summary", "restore"],
                "description": "summary to preview archived content; restore to restore full conversation.",
            },
        },
        "required": ["mode"],
    },
    execute=_expand_execute,
    intents=["general", "coding", "research", "data"],
    category="meta",
    triggers=["expand", "archive", "restore context", "retrieve compacted"],
    always_available=True,
    is_concurrency_safe=lambda _: True,
    semantic_type="read",
)
