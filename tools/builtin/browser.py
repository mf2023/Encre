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

from typing import Any, ClassVar, TYPE_CHECKING

from yim.tools.base import YmiTool

if TYPE_CHECKING:
    from yim.computer.browser import YmiBrowserSession


class YmiBrowserTool(YmiTool):
    name: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "Browser automation tool supporting navigate, click, type, screenshot, "
        "get_html, get_text, execute_js, wait_for_selector, scroll_to, fill_form, "
        "press_key, get_state, save_cookies, load_cookies, and close_session actions "
        "on a headless Chromium browser"
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "click", "type", "screenshot",
                    "get_html", "get_text", "execute_js",
                    "wait_for_selector", "scroll_to", "fill_form",
                    "press_key", "get_state", "save_cookies",
                    "load_cookies", "close_session",
                ],
                "description": "Browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for navigate action)",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector (for click, type, screenshot, get_text, wait_for_selector, scroll_to actions)",
            },
            "text": {
                "type": "string",
                "description": "Text to type (for type action)",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page screenshot (for screenshot action)",
            },
            "code": {
                "type": "string",
                "description": "JavaScript code to execute (for execute_js action)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (for wait_for_selector action)",
            },
            "x": {
                "type": "integer",
                "description": "Horizontal scroll position (for scroll_to action)",
            },
            "y": {
                "type": "integer",
                "description": "Vertical scroll position (for scroll_to action)",
            },
            "fields": {
                "type": "object",
                "description": "Dict of selector:value pairs (for fill_form action)",
            },
            "key": {
                "type": "string",
                "description": "Key name to press (for press_key action)",
            },
            "cookies": {
                "type": "array",
                "description": "List of cookie dicts (for load_cookies action)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, browser_session: YmiBrowserSession | None = None) -> None:
        self._session = browser_session

    def _get_session(self):
        if self._session is None:
            from yim.computer.browser import YmiBrowserSession
            self._session = YmiBrowserSession()
        return self._session

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        session = self._get_session()

        try:
            if action == "navigate":
                url = kwargs.get("url", "")
                if not url:
                    return "Error: url parameter required for navigate action"
                state = await session.navigate(url)
                return f"Navigated to {state.url}\nTitle: {state.title}"

            elif action == "click":
                selector = kwargs.get("selector", "")
                if not selector:
                    return "Error: selector parameter required for click action"
                ok = await session.click(selector)
                return f"Clicked {selector}" if ok else f"Error: failed to click {selector}"

            elif action == "type":
                selector = kwargs.get("selector", "")
                text = kwargs.get("text", "")
                if not selector:
                    return "Error: selector parameter required for type action"
                ok = await session.type_text(selector, text)
                return f"Typed into {selector}" if ok else f"Error: failed to type into {selector}"

            elif action == "screenshot":
                full_page = kwargs.get("full_page", False)
                selector = kwargs.get("selector", None)
                return await session.screenshot(full_page=full_page, selector=selector)

            elif action == "get_html":
                return await session.get_html()

            elif action == "get_text":
                selector = kwargs.get("selector", None)
                return await session.get_text(selector=selector)

            elif action == "execute_js":
                code = kwargs.get("code", "")
                if not code:
                    return "Error: code parameter required for execute_js action"
                result = await session.execute_js(code)
                return str(result)

            elif action == "wait_for_selector":
                selector = kwargs.get("selector", "")
                if not selector:
                    return "Error: selector parameter required for wait_for_selector action"
                timeout = kwargs.get("timeout", None)
                ok = await session.wait_for_selector(selector, timeout=timeout)
                return f"Element found: {selector}" if ok else f"Timeout: element not found: {selector}"

            elif action == "scroll_to":
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                await session.scroll_to(x=x, y=y)
                return f"Scrolled to ({x}, {y})"

            elif action == "fill_form":
                fields = kwargs.get("fields", {})
                if not fields:
                    return "Error: fields parameter required for fill_form action"
                ok = await session.fill_form(fields)
                return "Form filled successfully" if ok else "Error: failed to fill form"

            elif action == "press_key":
                key = kwargs.get("key", "")
                if not key:
                    return "Error: key parameter required for press_key action"
                await session.press_key(key)
                return f"Pressed key: {key}"

            elif action == "get_state":
                state = await session.get_state()
                return f"URL: {state.url}\nTitle: {state.title}"

            elif action == "save_cookies":
                cookies = await session.save_cookies()
                import json
                return json.dumps(cookies)

            elif action == "load_cookies":
                cookies = kwargs.get("cookies", [])
                if not cookies:
                    return "Error: cookies parameter required for load_cookies action"
                await session.load_cookies(cookies)
                return f"Loaded {len(cookies)} cookies"

            elif action == "close_session":
                await session.close()
                self._session = None
                return "Browser session closed"

            else:
                return f"Error: unknown action '{action}'"

        except RuntimeError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Browser action '{action}' failed: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
