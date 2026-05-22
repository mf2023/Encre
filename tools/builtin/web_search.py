#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

from typing import Any, ClassVar

import httpx

from yim.tools.base import YmiTool


class YmiWebSearchTool(YmiTool):
    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = "Search the internet and return results"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "num": {
                "type": "integer",
                "description": "Maximum number of results (default: 5)",
            },
        },
        "required": ["query"],
    }
    intents: ClassVar[list[str]] = ["general", "research"]

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        num = kwargs.get("num", 5)

        search_url = f"https://html.duckduckgo.com/html/?q={httpx.utils.quote(query)}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; YmiBot/1.0)",
                },
            ) as client:
                resp = await client.get(search_url)
                resp.raise_for_status()

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                results: list[str] = []
                for i, result in enumerate(soup.select(".result")):
                    if i >= num:
                        break
                    title_tag = result.select_one(".result__title a")
                    snippet_tag = result.select_one(".result__snippet")
                    title = title_tag.get_text(strip=True) if title_tag else "No title"
                    link = title_tag.get("href", "") if title_tag else ""
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else "No description"
                    results.append(f"{i+1}. [{title}]({link})\n   {snippet}")

                if not results:
                    return "No search results found."

                return "\n\n".join(results)

        except httpx.TimeoutException:
            return "Error: Search request timed out"
        except Exception as e:
            return f"Error performing search: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return True