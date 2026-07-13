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

"""Web search via encre's built-in search engine -- no API keys, no Docker.

Uses ``EncreSearchManager`` (Exa MCP search service by default).  Zero
configuration required.  Page content is returned inline by default so the
model rarely needs a follow-up ``web_fetch`` (which anti-crawling sites often
block); pass ``content=false`` for link-only results.
"""

from typing import Any

from encre.search.manager import EncreSearchManager
from encre.tools.base import build_tool

# Global manager singleton -- shared across all tool instances.
_manager: EncreSearchManager | None = None


def _get_manager() -> EncreSearchManager:
    """Return the global EncreSearchManager singleton (lazy-init)."""
    global _manager
    if _manager is None:
        _manager = EncreSearchManager()
    return _manager


async def _web_search_execute(**kwargs: Any) -> str:
    """Search the web via EncreSearchManager (Exa MCP). Returns formatted results with inline page content by default."""
    query = kwargs.get("query", "")
    if not query:
        return "Error: No search query provided."

    try:
        num = max(1, min(int(kwargs.get("num", 10)), 10))
    except (TypeError, ValueError):
        num = 5
    language = kwargs.get("language", "")
    categories = kwargs.get("categories", "general")

    manager = _get_manager()
    result = await manager.search(
        query,
        num=num,
        language=language,
        categories=categories,
        content=bool(kwargs.get("content", True)),
    )

    error = result.get("_error", "")
    if error and not result.get("results"):
        return f"Error: {error}"

    results = result.get("results", [])
    suggestions = result.get("suggestions", [])

    if not results:
        if suggestions:
            return f"No results found. Did you mean: {' | '.join(suggestions)}?"
        return "No results found."

    lines: list[str] = []
    for i, r in enumerate(results[:num], 1):
        title = r.get("title", "").strip()
        url = r.get("url", "")
        content = r.get("content", "").strip()
        entry = f"{i}. [{title}]({url})"
        if content:
            # Indent multi-line content under the title for readability.
            indented = content.replace("\n", "\n   ")
            entry += f"\n   {indented}"
        lines.append(entry)

    output = "\n\n".join(lines)
    if suggestions:
        output += f"\n\nSuggestions: {' | '.join(suggestions[:5])}"

    return output


EncreWebSearchTool = build_tool(
    name="web_search",
    description=(
        "Search the web for up-to-date information. Returns each result with "
        "title, URL, and -- by default -- the page content inline, so you "
        "usually do NOT need a follow-up web_fetch (which anti-crawling sites "
        "often block). Use for: current events, recent data, documentation, "
        "flight/train/hotel lookups, or any question needing information beyond "
        "the training cutoff."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "num": {
                "type": "integer",
                "description": "Maximum number of results (default: 10, max: 10). Lower this when content=true to keep the payload small.",
            },
            "language": {
                "type": "string",
                "description": "Search language code, e.g. zh-CN, en-US (default: all)",
            },
            "categories": {
                "type": "string",
                "description": "Search category (used with external SearXNG): general, news",
            },
            "content": {
                "type": "boolean",
                "description": "Whether to return page content inline (default: true). Set false for link-only results when you just need URLs.",
            },
        },
        "required": ["query"],
    },
    execute=_web_search_execute,
    intents=["general", "research"],
    category="web",
    triggers=["search web", "internet search", "google", "duckduckgo", "bing", "lookup", "browse web"],
    semantic_type="network",
    cost_level="medium",
    retryability="auto",
    safe_fallback="Refine the query, reduce the requested result count, or rely on local context if the search is non-essential.",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)


__all__ = ["EncreWebSearchTool", "_get_manager"]
