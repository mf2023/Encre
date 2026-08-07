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

"""Module: builtin/web_fetch.py

Fetch a URL via Exa's crawler (handles JS rendering + anti-scraping that
plain httpx cannot), with an httpx fallback for raw HTML or when Exa is
unreachable. Shares the Exa MCP connection (and embedded API key) with
web_search.
"""
from typing import Any

import httpx
from markdownify import markdownify as md

from encre.tools.base import build_tool
from encre.tools.builtin.web_search import _get_manager

_MAX_BODY = 5 * 1024 * 1024


async def _httpx_fetch(url: str, fmt: str, timeout: int) -> str:
    """Fallback fetch via httpx (raw bytes). Used for HTML format or when Exa fails."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                is_html = "text/html" in content_type or "application/xhtml+xml" in content_type

                size = 0
                chunks: list[bytes] = []
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_BODY:
                        chunks.append(b"... (truncated)")
                        break
                    chunks.append(chunk)
                body = b"".join(chunks)
                text = body.decode("utf-8", errors="replace")[:50000]

                if fmt == "html":
                    return text

                if fmt == "markdown" and is_html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, "lxml")
                    for tag in soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    return md(str(soup), heading_style="ATX")[:50000]

                if is_html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, "lxml")
                    for tag in soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    text2 = soup.get_text(separator="\n", strip=True)
                    lines = [line.strip() for line in text2.split("\n") if line.strip()]
                    return "\n".join(lines[:500])

                return text

    except httpx.TimeoutException:
        return f"Error: Request timed out fetching {url}"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP {e.response.status_code}: {url}"
    except Exception as e:
        return f"Error fetching {url}: {e}"


async def _web_fetch_execute(**kwargs: Any) -> str:
    """Fetch a URL and return its content.

    Prefers Exa's crawler (JS rendering + anti-scraping); falls back to httpx
    for the HTML format or when Exa returns nothing.
    """
    url = kwargs.get("url", "")
    fmt = (kwargs.get("format") or "text").strip().lower()
    try:
        timeout = max(5, min(int(kwargs.get("timeout", 30)), 120))
    except (TypeError, ValueError):
        timeout = 30

    if not url:
        return "Error: No URL provided."

    # Raw HTML needs the original bytes -- Exa only returns markdown.
    if fmt == "html":
        return await _httpx_fetch(url, "html", timeout)

    # text/markdown: prefer Exa crawler (handles JS + anti-scraping).
    manager = _get_manager()
    body = await manager.fetch(url)
    if body:
        return body

    # Exa returned nothing (rate-limited / unreachable / empty page) -- fall
    # back to httpx for the common static-page case.
    return await _httpx_fetch(url, fmt, timeout)


EncreWebFetchTool = build_tool(
    name="web_fetch",
    description=(
        "Fetch a single URL and return its content as text or markdown.\n\n"
        "WHAT: uses an Exa-based crawler that renders JavaScript and bypasses "
        "common anti-scraping, with an httpx fallback for raw HTML or when the "
        "crawler is unreachable.\n"
        "WHEN to use: the user pastes a specific URL, or web_search returned a "
        "URL whose inline content was truncated/empty and you need the full "
        "page.\n"
        "WHEN NOT to use: do NOT call this right after web_search -- the search "
        "already inlines page content; for interactive/log-in flows use the "
        "browser tool instead.\n"
        "TIPS: prefer format=markdown for readable article content; use "
        "format=html only when you need the raw DOM; the httpx fallback cannot "
        "render JS, so SPA pages may come back empty.\n"
        "PITFALLS: response bodies are truncated to 50K chars; login-gated or "
        "aggressively anti-bot sites may return empty strings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Absolute URL to fetch, including the scheme (http:// or https://). Relative paths are not supported.",
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "description": "Output format: 'text' (default, plain text extracted from HTML), 'markdown' (converted HTML suitable for reading), or 'html' (raw HTML bytes via plain HTTP, bypasses the Exa crawler).",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds for the httpx fallback only, clamped to 5-120 (default: 30). The Exa crawler has its own server-side timeout.",
            },
        },
        "required": ["url"],
    },
    execute=_web_fetch_execute,
    intents=["general", "research"],
    category="web",
    semantic_type="network",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
