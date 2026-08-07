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

"""Memory tools -- create, read, update, delete persistent encrypted memories."""

import os
import re
from typing import Any

from encre.memdir.system import EncreMemorySystem
from encre.tools.base import build_tool


def _get_memory_dir() -> str:
    """Get memory dir."""
    from encre.config import get_data_dir
    return str(get_data_dir() / "memory")


def _sanitize_filename(name: str) -> str:
    """Normalize a memory name into a safe .md filename."""
    slug = re.sub(r"[^\w\-]", "_", name.strip()).strip("_").lower()
    return slug if slug else "memory"


def _write_encrypted(filepath: str, content: str) -> None:
    """Write encrypted.

    Args:
        filepath: Description of the filepath parameter.
        content: Description of the content parameter.
    """
    from encre.crypto import encrypt
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(encrypt(content))


def _read_encrypted(filepath: str) -> str | None:
    """Read encrypted.

    Args:
        filepath: Description of the filepath parameter.
    """
    from encre.crypto import decrypt
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return ""
        if raw.startswith("---"):
            return raw  # legacy plaintext
        return decrypt(raw)
    except Exception:
        return None


# ── Tools ────────────────────────────────────────────────────────────────────


async def _memory_create_execute(**kwargs: Any) -> str:
    """Memory create execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    filename = kwargs.get("filename", "")
    content = kwargs.get("content", "")
    if not filename.endswith(".md"):
        filename += ".md"
    slug = _sanitize_filename(os.path.splitext(filename)[0])
    filename = f"{slug}.md"

    mem_dir = _get_memory_dir()
    filepath = os.path.join(mem_dir, filename)

    if os.path.exists(filepath):
        return (
            f"Memory file '{filename}' already exists. "
            f"Use memory_update to modify it, or choose a different filename."
        )

    try:
        _write_encrypted(filepath, content)
        ms = EncreMemorySystem(mem_dir)
        ms.refresh_index()
        return f"Memory '{filename}' created and encrypted successfully."
    except Exception as e:
        return f"Error creating memory: {e}"


async def _memory_read_execute(**kwargs: Any) -> str:
    """Memory read execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    filename = kwargs.get("filename", "")
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(_get_memory_dir(), filename)
    content = _read_encrypted(filepath)
    if content is None:
        return f"Memory file '{filename}' not found."

    if not content:
        return f"Memory file '{filename}' is empty."

    return content


async def _memory_update_execute(**kwargs: Any) -> str:
    """Memory update execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    filename = kwargs.get("filename", "")
    content = kwargs.get("content", "")
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(_get_memory_dir(), filename)
    if not os.path.isfile(filepath):
        return f"Memory file '{filename}' does not exist. Use memory_create to create it."

    try:
        _write_encrypted(filepath, content)
        ms = EncreMemorySystem(_get_memory_dir())
        ms.refresh_index()
        return f"Memory '{filename}' updated and encrypted successfully."
    except Exception as e:
        return f"Error updating memory: {e}"


async def _memory_delete_execute(**kwargs: Any) -> str:
    """Memory delete execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    filename = kwargs.get("filename", "")
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(_get_memory_dir(), filename)
    if not os.path.isfile(filepath):
        return f"Memory file '{filename}' does not exist."

    try:
        os.remove(filepath)
        ms = EncreMemorySystem(_get_memory_dir())
        ms.refresh_index()
        return f"Memory '{filename}' deleted."
    except Exception as e:
        return f"Error deleting memory: {e}"


async def _memory_search_execute(**kwargs: Any) -> str:
    """Memory search execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    query = kwargs.get("query", "")
    top_k = kwargs.get("top_k", 5)

    ms = EncreMemorySystem(_get_memory_dir())
    results = ms.search(query, top_k=top_k)

    if not results:
        return f"No memories found matching '{query}'."

    lines: list[str] = [f"Memory search results for '{query}':", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r.file_name}** (score: {r.score:.2f})")
        snippet = r.snippet
        if snippet:
            lines.append(f"   {snippet[:200]}")
        lines.append("")
    return "\n".join(lines)


async def _memory_profile_execute(**kwargs: Any) -> str:
    """Memory profile execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    field = kwargs.get("field", "")
    value = kwargs.get("value")
    confidence = float(kwargs.get("confidence", 0.7))

    from encre.config import get_data_dir
    from encre.profile.system import EncreProfileSystem
    mem_dir = str(get_data_dir() / "memory")
    ps = EncreProfileSystem(mem_dir)
    ps.load()

    if value is not None:
        # ── Update mode ──────────────────────────────────────────
        if not field:
            return "Error: field is required when updating."
        valid_fields = {
            "expertise_level", "domain", "formality", "detail_preference",
            "tone", "response_style", "testing_preference", "learning_style",
            "error_tolerance", "os", "editor", "name",
            "language_preference", "timezone",
            "preferred_languages", "preferred_frameworks",
            "skill_levels", "common_goals",
        }
        if field not in valid_fields:
            return (
                f"Unknown field '{field}'. Valid fields: "
                f"{', '.join(sorted(valid_fields))}"
            )
        try:
            ps.update_field(field, value, confidence=confidence)
            return (
                f"Profile field '{field}' updated to '{value}' "
                f"(confidence: {confidence:.2f})."
            )
        except Exception as e:
            return f"Error updating profile: {e}"

    # ── Query mode ───────────────────────────────────────────────
    data = ps.get_data()
    if field:
        if field not in data or not data[field]:
            return f"Profile field '{field}' is not set."
        conf = data.get("confidence", {}).get(field, 0)
        val = data[field]
        if isinstance(val, list):
            val = ", ".join(val)
        elif isinstance(val, dict):
            val = ", ".join(f"{k}: {v}" for k, v in val.items())
        return f"{field}: {val} (confidence: {conf:.2f})"

    # Full profile dump
    lines: list[str] = ["## User Profile", ""]
    sections = {
        "Basic": ["name", "language_preference", "timezone", "expertise_level", "domain"],
        "Communication": ["formality", "detail_preference", "tone", "response_style"],
        "Technical": ["preferred_languages", "preferred_frameworks", "skill_levels", "os", "editor"],
        "Behavioral": ["testing_preference", "learning_style", "error_tolerance", "common_goals"],
    }
    has_any = False
    for section_name, fields in sections.items():
        section_parts: list[str] = []
        for f in fields:
            val = data.get(f)
            if val and val != "" and val != [] and val != {}:
                conf = data.get("confidence", {}).get(f, 0)
                display = val
                if isinstance(val, list):
                    display = ", ".join(val)
                elif isinstance(val, dict):
                    display = ", ".join(f"{k}: {v}" for k, v in val.items())
                section_parts.append(f"  - {f}: {display} (conf: {conf:.2f})")
                has_any = True
        if section_parts:
            lines.append(f"### {section_name}")
            lines.extend(section_parts)
            lines.append("")
    if not has_any:
        lines.append("No profile data yet. Profile is built over time as you interact.")
    lines.append(f"Total updates: {data.get('update_count', 0)}")
    return "\n".join(lines)


EncreMemoryCreateTool = build_tool(
    name="memory_create",
    description=(
        "Create a new persistent memory file that is encrypted at rest and "
        "automatically loaded into the agent's context on future runs. "
        "Use this to record durable user preferences, project context, feedback, or "
        "reference notes that should outlive the current session. "
        "Do NOT use this for ephemeral scratch data (use todo/task tools), for "
        "bulk file storage (use file_write), or to overwrite an existing memory "
        "(use memory_update instead). "
        "Tips: include YAML frontmatter (between --- lines) to set name, "
        "description, type (user/feedback/project/reference), and tags for richer "
        "retrieval. "
        "Pitfalls: filenames must use the .md extension; creating a file that "
        "already exists will overwrite it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The .md filename for the memory (e.g. 'user_preferences.md').",
            },
            "content": {
                "type": "string",
                "description": "Full markdown body, optionally starting with YAML frontmatter (--- ... ---) declaring name, description, type, and tags.",
            },
        },
        "required": ["filename", "content"],
    },
    execute=_memory_create_execute,
    intents=["general", "coding"],
    category="memory",
    semantic_type="write",
    is_destructive=True,
)

EncreMemoryReadTool = build_tool(
    name="memory_read",
    description=(
        "Read a memory file by filename, returning the full decrypted content "
        "including any YAML frontmatter. "
        "Use this when you already know the memory filename and want its full "
        "contents loaded into context. "
        "Do NOT use this to discover memories by meaning (use memory_search) or to "
        "inspect the user profile (use memory_profile). "
        "Tips: pair with memory_search to first locate the relevant filename. "
        "Pitfalls: returns an error if the filename does not exist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The .md filename to read (e.g. 'user_preferences.md').",
            },
        },
        "required": ["filename"],
    },
    execute=_memory_read_execute,
    intents=["general", "coding", "research"],
    category="memory",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)

EncreMemoryUpdateTool = build_tool(
    name="memory_update",
    description=(
        "Replace the entire contents of an existing memory file with new content, "
        "encrypted on save. "
        "Use this to refresh or correct a memory that has grown stale. "
        "Do NOT use this to create a new memory (use memory_create) or to delete "
        "(use memory_delete); for partial edits, read first then write the merged "
        "content. "
        "Tips: preserve any YAML frontmatter so metadata stays intact. "
        "Pitfalls: the previous content is overwritten with no history retained."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The .md filename to update.",
            },
            "content": {
                "type": "string",
                "description": "The new full content for the memory file (frontmatter plus markdown body).",
            },
        },
        "required": ["filename", "content"],
    },
    execute=_memory_update_execute,
    intents=["general", "coding"],
    category="memory",
    semantic_type="write",
    is_destructive=True,
)

EncreMemoryDeleteTool = build_tool(
    name="memory_delete",
    description=(
        "Permanently delete a memory file. "
        "Use this to remove obsolete or incorrect memories that should no longer "
        "influence future sessions. "
        "Do NOT use this for routine updates (use memory_update) or to clear the "
        "user profile (use memory_profile with appropriate updates). "
        "Tips: confirm the filename with memory_read or memory_search first. "
        "Pitfalls: deletion cannot be undone and there is no trash bin."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The .md filename to delete.",
            },
        },
        "required": ["filename"],
    },
    execute=_memory_delete_execute,
    intents=["general", "coding"],
    category="memory",
    semantic_type="write",
    is_destructive=True,
)

EncreMemorySearchTool = build_tool(
    name="memory_search",
    description=(
        "Search memory files semantically and return the most relevant matches "
        "for the query. "
        "Use this when you need to recall a memory by meaning rather than by "
        "filename, e.g. 'what does the user prefer for testing?'. "
        "Do NOT use this when you already know the filename (use memory_read) or "
        "for structured user profile fields (use memory_profile). "
        "Tips: write the query as a natural-language question for best recall; "
        "raise `top_k` to broaden the result set. "
        "Pitfalls: very generic queries can surface many similar memories — "
        "narrow the wording or reduce `top_k` to focus results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language query used to find relevant memories.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return; defaults to 5.",
            },
        },
        "required": ["query"],
    },
    execute=_memory_search_execute,
    intents=["general", "coding", "research"],
    category="memory",
    semantic_type="search",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)

EncreMemoryProfileTool = build_tool(
    name="memory_profile",
    description=(
        "Read or update the user profile — structured observations about the user "
        "(expertise, communication style, preferences, OS, editor, etc.) stored as "
        "_profile.md inside the unified memory system.\n\n"
        "Use this to tailor responses to the user (query) or to record a new "
        "observation (update).\n"
        "Do NOT use this for free-form memories (use memory_create/update) or for "
        "one-off facts that do not belong in the profile.\n"
        "Tips: query with no args to dump the whole profile; pass field+value to "
        "record an observation, optionally with a confidence score.\n"
        "Pitfalls: profile fields are a fixed enumeration — see the `field` enum "
        "description for the supported set."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "description": (
                    "Profile field to query or update. Valid fields: "
                    "expertise_level, domain, formality, detail_preference, "
                    "tone, response_style, testing_preference, learning_style, "
                    "error_tolerance, os, editor, name, language_preference, "
                    "timezone, preferred_languages, preferred_frameworks, "
                    "skill_levels, common_goals"
                ),
            },
            "value": {
                "type": "string",
                "description": (
                    "If set, updates the field with this value. "
                    "If omitted, queries the field (or all fields if "
                    "field is also omitted)."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in the observation, from 0.0 to 1.0; only used when updating. Defaults to 0.7.",
            },
        },
    },
    execute=_memory_profile_execute,
    intents=["general", "coding", "research"],
    category="memory",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
