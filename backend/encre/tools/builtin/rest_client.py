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

"""Module: builtin/rest_client.py

Rest client implementation for the Encre tool system.
"""
import json
from typing import Any

import httpx

from encre.tools.base import build_tool


async def _rest_client_execute(**kwargs: Any) -> str:
    """Rest client execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    method = kwargs.get("method", "GET")
    url = kwargs.get("url", "")
    headers = kwargs.get("headers", {}) or {}
    body = kwargs.get("body", "")
    timeout = kwargs.get("timeout", 30)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(timeout)),
            follow_redirects=True,
        ) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers={k: str(v) for k, v in headers.items()},
                content=body if body else None,
            )

            status = resp.status_code
            content_type = resp.headers.get("content-type", "")
            response_body = resp.text

            if len(response_body) > 50000:
                response_body = response_body[:50000] + "\n... (truncated to 50K chars)"

            if "application/json" in content_type or response_body.strip().startswith(("{", "[")):
                try:
                    parsed = json.loads(response_body)
                    return json.dumps({"status": status, "headers": dict(resp.headers), "body": parsed}, indent=2, default=str)
                except (json.JSONDecodeError, ValueError):
                    pass

            return f"HTTP {status}\n{response_body}"

    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s for {url}"
    except httpx.InvalidURL:
        return f"Error: Invalid URL: {url}"
    except Exception as e:
        return f"Error making {method} request to {url}: {e}"


EncreRESTTool = build_tool(
    name="rest_client",
    description=(
        "Make an HTTP request to a REST or GraphQL API endpoint and return the "
        "status code, headers, and parsed body.\n\n"
        "WHEN to use: call a documented REST/GraphQL API by its URL, integrate "
        "with a third-party service, or fetch a JSON resource that is not a "
        "human-readable web page.\n"
        "WHEN NOT to use: for fetching a web page to read, use web_fetch "
        "(renders JS, strips boilerplate); for browser interactions (clicks, "
        "form fills, logins) use the browser tool.\n"
        "TIPS: pass the body as a JSON string for JSON APIs and set the "
        "Content-Type header accordingly; JSON responses are auto-parsed and "
        "returned as a structured {status, headers, body} object.\n"
        "PITFALLS: response bodies over 50K chars are truncated; non-GET "
        "methods (POST/PUT/PATCH/DELETE) are flagged as destructive -- make "
        "sure the user actually wants the side effect."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "description": "HTTP method. GET is safe/read-only; POST/PUT/PATCH/DELETE mutate state and are flagged as destructive.",
            },
            "url": {
                "type": "string",
                "description": "Absolute URL of the API endpoint, including scheme and query string (e.g. https://api.example.com/v1/users?page=1).",
            },
            "headers": {
                "type": "object",
                "description": "HTTP request headers as key-value pairs. Always include Content-Type (e.g. application/json) and any Authorization header the API requires.",
            },
            "body": {
                "type": "string",
                "description": "Raw request body as a string. For JSON APIs, pass a JSON-serialized string; values are sent verbatim (no automatic encoding).",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default: 30). Increase for slow endpoints, decrease to fail fast on unreachable hosts.",
            },
        },
        "required": ["method", "url"],
    },
    execute=_rest_client_execute,
    intents=["coding", "system"],
    is_concurrency_safe=lambda _: True,
    category="web",
    semantic_type="network",
    is_destructive=lambda args: args.get("method", "GET").upper() in ("POST", "PUT", "DELETE", "PATCH"),
)
