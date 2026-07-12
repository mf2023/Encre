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

Web fetch implementation for the Encre tool system.
"""
from typing import Any

import httpx
from markdownify import markdownify as md

from encre.tools.base import build_tool


async def _web_fetch_execute(**kwargs: Any) -> str:
    """Fetch a URL and return content in the requested format."""
    url = kwargs.get("url", "")
    fmt = (kwargs.get("format") or "text").strip().lower()
    timeout = kwargs.get("timeout", 30)

    try:
        timeout = max(5, min(int(timeout), 120))
    except (TypeError, ValueError):
        timeout = 30

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            is_html = "text/html" in content_type or "html" in content_type

            if fmt == "html":
                return resp.text[:50000] + "\n... (truncated)" if len(resp.text) > 50000 else resp.text

            if fmt == "markdown" and is_html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return md(str(soup), heading_style="ATX")[:50000]

            if is_html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                return "\n".join(lines[:500])

            return resp.text[:50000] + "\n... (truncated)" if len(resp.text) > 50000 else resp.text

    except httpx.TimeoutException:
        return f"Error: Request timed out fetching {url}"
    except httpx.HTTPStatusError as e:
        return f"Error HTTP {e.response.status_code}: {url}"
    except Exception as e:
        return f"Error fetching {url}: {e}"


EncreWebFetchTool = build_tool(
    name="web_fetch",
    description="Fetch a URL and return content in text, markdown, or HTML format.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "description": "Output format: text (plain stripped, default), markdown (HTML→Markdown), html (raw). For HTML pages only.",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (5-120, default 30).",
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
