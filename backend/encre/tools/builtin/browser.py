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

"""Module: builtin/browser.py

Browser implementation for the Encre tool system.
"""
import asyncio
import json
import logging
import re
import urllib.parse
from typing import TYPE_CHECKING, Any

from encre.tools.base import build_tool

if TYPE_CHECKING:
    from encre.computer.browser import EncreBrowserSession

logger = logging.getLogger("encre.tools.builtin.browser")

# Per-session browser state — each chat session gets its own isolated browser
_sessions: dict[str, "EncreBrowserSession"] = {}
_engine_requester: Any | None = None
_cdp_ws_urls: dict[str, str] = {}
_search_engine_url: str | None = None

_session_id: str = ""  # set by the tool executor before each call
_DEFAULT_KEY = "__default__"  # fallback key for CDP URL when no session_id


def set_session_id(sid: str) -> None:
    """Set the current session ID (called by the tool executor)."""
    global _session_id
    _session_id = sid


def set_engine_requester(requester: Any) -> None:
    """Install an engine-install requester on lazily-created browser sessions."""
    global _engine_requester
    _engine_requester = requester
    for s in _sessions.values():
        if hasattr(s, "set_engine_requester"):
            s.set_engine_requester(requester)


def set_cdp_url(url: str) -> None:
    """Set the CDP WebSocket URL for the current session."""
    global _cdp_ws_urls
    if _session_id:
        _cdp_ws_urls[_session_id] = url
    else:
        # Store under default key; will be migrated when session_id is set
        _cdp_ws_urls[_DEFAULT_KEY] = url


def set_search_engine_url(url: str) -> None:
    """Set the search engine URL format for converting search queries."""
    global _search_engine_url
    _search_engine_url = url


def _get_session():
    """Get or create the browser session for the current session ID."""
    global _sessions, _cdp_ws_urls
    key = _session_id if _session_id else _DEFAULT_KEY
    if key not in _sessions:
        from encre.computer.browser import EncreBrowserSession
        _sessions[key] = EncreBrowserSession()
        if _engine_requester is not None and hasattr(_sessions[key], "set_engine_requester"):
            _sessions[key].set_engine_requester(_engine_requester)
    # Migrate URL from default key to real session ID when it becomes available
    if _session_id and _DEFAULT_KEY in _cdp_ws_urls:
        _cdp_ws_urls[_session_id] = _cdp_ws_urls.pop(_DEFAULT_KEY)
    return _sessions[key]


def _get_cdp_url() -> str | None:
    """Get the CDP URL for the current session."""
    if _session_id and _session_id in _cdp_ws_urls:
        return _cdp_ws_urls[_session_id]
    return _cdp_ws_urls.get(_DEFAULT_KEY)


async def _ensure_connected():
    """Ensure the browser session is connected to the CDP relay."""
    session = _get_session()
    cdp_url = _get_cdp_url()
    # If the session thinks it's connected but the transport is dead, reset
    if session._connected:
        if session._transport is None or not session._transport.connected:
            session._connected = False
            logger.info("[browser] transport disconnected, will reconnect")
        elif (cdp_url and session._page_ws_url
              and cdp_url != session._page_ws_url):
            logger.info("[browser] CDP URL changed: %s -> %s, reconnecting",
                        session._page_ws_url, cdp_url)
            await session.close()
            session._connected = False
    if cdp_url and not session._connected:
        logger.info("[browser] connecting to CDP relay at %s", cdp_url)
        for attempt in range(30):
            try:
                await session.connect(cdp_url)
                logger.info("[browser] connected to CDP relay at %s", cdp_url)
                return
            except Exception as e:
                logger.warning("[browser] connect attempt %d/30 failed: %s", attempt + 1, e)
                session._connected = False
                await asyncio.sleep(1)
        logger.error("[browser] failed to connect to CDP relay after 30 attempts")
    elif not cdp_url and not session._connected:
        logger.info("[browser] no CDP URL yet, waiting for frontend to create browser tab")
        for _ in range(300):
            if _get_cdp_url():
                break
            await asyncio.sleep(0.1)
        cdp_url = _get_cdp_url()
        if cdp_url:
            logger.info("[browser] CDP URL received, connecting to %s", cdp_url)
            for attempt in range(30):
                try:
                    await session.connect(cdp_url)
                    logger.info("[browser] connected to CDP relay at %s", cdp_url)
                    return
                except Exception as e:
                    logger.warning("[browser] connect attempt %d/30 failed: %s", attempt + 1, e)
                    session._connected = False
                    await asyncio.sleep(1)
            logger.error("[browser] failed to connect to CDP relay after 30 attempts")
        else:
            logger.error("[browser] CDP URL not received within 30s, browser tool will not work")


async def _browser_execute(**kwargs: Any) -> str:
    """Browser execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    global _session_id
    # Extract session_id from kwargs (injected by the tool executor)
    _session_id = kwargs.pop("_session_id", "")
    action = kwargs.get("action", "")
    session = _get_session()
    await _ensure_connected()

    if not session._connected or session._transport is None or not session._transport.connected:
        return "Error: browser not connected to webview. Try opening the browser tab in the sidebar first."

    if action == "navigate":
        url = kwargs.get("url", "")
        if not url:
            return "Error: url parameter required for navigate action"
        # Convert search queries to the configured search engine URL
        if not re.match(r'^https?://', url):
            engine_url = _search_engine_url or "https://www.google.com/search?q={query}"
            url = engine_url.replace('{query}', urllib.parse.quote(url))
        state = await session.navigate(url)
        return f"Navigated to {state.url}\nTitle: {state.title}"

    elif action == "click":
        selector = kwargs.get("selector", "")
        if not selector:
            return "Error: selector parameter required for click action"
        ok = await session.click(selector)
        return f"Clicked {selector}" if ok else f"Error: failed to click {selector}"

    elif action == "click_at":
        x = kwargs.get("x")
        y = kwargs.get("y")
        if x is None or y is None:
            return "Error: x and y coordinates required for click_at"
        ok = await session.click_at(int(x), int(y))
        return f"Clicked at ({x}, {y})" if ok else f"Error: failed to click at ({x}, {y})"

    elif action == "double_click_at":
        x = kwargs.get("x")
        y = kwargs.get("y")
        if x is None or y is None:
            return "Error: x and y coordinates required for double_click_at"
        ok = await session.double_click_at(int(x), int(y))
        return f"Double-clicked at ({x}, {y})" if ok else "Error: failed"

    elif action == "right_click_at":
        x = kwargs.get("x")
        y = kwargs.get("y")
        if x is None or y is None:
            return "Error: x and y coordinates required for right_click_at"
        ok = await session.right_click_at(int(x), int(y))
        return f"Right-clicked at ({x}, {y})" if ok else "Error: failed"

    elif action == "type":
        selector = kwargs.get("selector", "")
        text = kwargs.get("text", "")
        if not selector:
            return "Error: selector parameter required for type action"
        ok = await session.type_text(selector, text)
        return f"Typed into {selector}" if ok else f"Error: failed to type into {selector}"

    elif action == "type_at":
        x = kwargs.get("x")
        y = kwargs.get("y")
        text = kwargs.get("text", "")
        if x is None or y is None:
            return "Error: x and y coordinates required for type_at"
        if not text:
            return "Error: text parameter required for type_at"
        ok = await session.type_at(int(x), int(y), text)
        return f"Typed at ({x}, {y})" if ok else f"Error: failed to type at ({x}, {y})"

    elif action == "screenshot":
        full_page = kwargs.get("full_page", False)
        selector = kwargs.get("selector")
        return await session.screenshot(full_page=full_page, selector=selector)

    elif action == "screenshot_viewport":
        info = await session.screenshot_viewport()
        return json.dumps(info, ensure_ascii=False)

    elif action == "get_html":
        return await session.get_html()

    elif action == "get_text":
        selector = kwargs.get("selector")
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
        timeout = kwargs.get("timeout")
        ok = await session.wait_for_selector(selector, timeout=timeout)
        return (
            f"Element found: {selector}"
            if ok
            else f"Timeout: element not found: {selector}"
        )

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

    elif action == "hotkey":
        keys = kwargs.get("keys", [])
        if not keys:
            return "Error: keys array required for hotkey"
        ok = await session.hotkey([str(k) for k in keys])
        return f"Pressed hotkey: {'+'.join(keys)}" if ok else "Error: hotkey failed"

    elif action == "hover":
        selector = kwargs.get("selector", "")
        if not selector:
            return "Error: selector parameter required for hover action"
        ok = await session.hover(selector)
        return f"Hovered {selector}" if ok else f"Error: failed to hover {selector}"

    elif action == "hover_at":
        x = kwargs.get("x")
        y = kwargs.get("y")
        if x is None or y is None:
            return "Error: x and y coordinates required for hover_at"
        ok = await session.hover_at(int(x), int(y))
        return f"Hovered at ({x}, {y})" if ok else "Error: failed"

    elif action == "drag":
        x1 = kwargs.get("x")
        y1 = kwargs.get("y")
        x2 = kwargs.get("x2")
        y2 = kwargs.get("y2")
        if x1 is None or y1 is None or x2 is None or y2 is None:
            return "Error: x, y (start) and x2, y2 (end) required for drag"
        ok = await session.drag(int(x1), int(y1), int(x2), int(y2))
        return f"Dragged from ({x1},{y1}) to ({x2},{y2})" if ok else "Error: drag failed"

    elif action == "get_viewport":
        vp = await session.get_viewport()
        return json.dumps({
            "width": vp.width,
            "height": vp.height,
            "scroll_x": vp.scroll_x,
            "scroll_y": vp.scroll_y,
            "device_pixel_ratio": vp.device_pixel_ratio,
        })

    elif action == "get_state":
        state = await session.get_state()
        return f"URL: {state.url}\nTitle: {state.title}"

    elif action == "save_cookies":
        cookies = await session.save_cookies()
        return json.dumps(cookies)

    elif action == "load_cookies":
        cookies = kwargs.get("cookies", [])
        if not cookies:
            return "Error: cookies parameter required for load_cookies action"
        await session.load_cookies(cookies)
        return f"Loaded {len(cookies)} cookies"

    elif action == "close_session":
        await session.close()
        global _session
        _session = None
        return "Browser session closed"

    elif action == "a11y_snapshot":
        interesting_only = bool(kwargs.get("interesting_only", True))
        root_selector = kwargs.get("root_selector") or None
        snap = await session.a11y_snapshot(
            interesting_only=interesting_only,
            root_selector=root_selector,
        )
        return json.dumps(snap, ensure_ascii=False)

    elif action == "click_by_role":
        role = kwargs.get("role", "")
        name = kwargs.get("name", "")
        if not role or not name:
            return "Error: 'role' and 'name' are required for click_by_role"
        exact = bool(kwargs.get("exact", False))
        ok = await session.click_by_role(role, name, exact=exact)
        return (
            f"Clicked role={role} name={name!r}"
            if ok else f"Error: failed to click role={role} name={name!r}"
        )

    elif action == "get_by_text_count":
        text = kwargs.get("name") or kwargs.get("text") or ""
        if not text:
            return "Error: 'name' (text to match) required for get_by_text_count"
        exact = bool(kwargs.get("exact", False))
        count = await session.get_by_text_count(text, exact=exact)
        return json.dumps({"text": text, "count": count, "exact": exact})

    elif action == "get_page_structure":
        elements = await session.get_page_structure()
        return json.dumps({
            "url": session._state.url,
            "viewport_width": session.viewport_width,
            "viewport_height": session.viewport_height,
            "elements_count": len(elements),
            "elements": elements,
        }, ensure_ascii=False)

    elif action == "select_option":
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        by = str(kwargs.get("by", "value"))
        if not selector:
            return "Error: selector parameter required for select_option"
        ok = await session.select_option(selector, value, by=by)
        return f"Selected option {value!r} in {selector}" if ok else \
            f"Error: select_option failed for {selector}"

    elif action == "get_attribute":
        selector = kwargs.get("selector", "")
        name = kwargs.get("name") or kwargs.get("attr", "")
        if not selector or not name:
            return "Error: selector and name required for get_attribute"
        value = await session.get_attribute(selector, str(name))
        return json.dumps({"selector": selector, "name": name, "value": value},
                          ensure_ascii=False)

    elif action == "get_property":
        selector = kwargs.get("selector", "")
        name = kwargs.get("name") or kwargs.get("property", "")
        if not selector or not name:
            return "Error: selector and name required for get_property"
        value = await session.get_property(selector, str(name))
        return json.dumps({"selector": selector, "name": name, "value": value},
                          ensure_ascii=False)

    elif action == "get_all_text":
        max_chars = int(kwargs.get("max_chars", 200000))
        return await session.get_all_text(max_chars=max_chars)

    elif action == "list_tabs":
        tabs = await session.list_tabs()
        return json.dumps(tabs, ensure_ascii=False)

    elif action == "switch_tab":
        index = kwargs.get("index")
        if index is None:
            return "Error: index required for switch_tab"
        ok = await session.switch_tab(int(index))
        return f"Switched to tab {index}" if ok else f"Error: tab {index} not found"

    elif action == "new_tab":
        url = kwargs.get("url") or None
        info = await session.new_tab(url=url)
        return json.dumps(info, ensure_ascii=False)

    elif action == "close_tab":
        index = kwargs.get("index")
        ok = await session.close_tab(int(index) if index is not None else None)
        return "Closed tab" if ok else "Error: failed to close tab"

    elif action == "set_dialog_handler":
        accept = bool(kwargs.get("accept", True))
        prompt_text = str(kwargs.get("prompt_text", ""))
        await session.set_dialog_handler(accept=accept, prompt_text=prompt_text)
        return f"Dialog handler installed (accept={accept})"

    elif action == "set_file_chooser_handler":
        paths = kwargs.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return "Error: paths required for set_file_chooser_handler"
        await session.set_file_chooser_handler([str(p) for p in paths])
        return f"File chooser handler installed with {len(paths)} file(s)"

    elif action == "click_text":
        text = kwargs.get("text", "")
        if not text:
            return "Error: text parameter required for click_text"
        fuzzy = bool(kwargs.get("fuzzy", False))
        exact = bool(kwargs.get("exact", False))
        occurrence = int(kwargs.get("occurrence", 1))
        ok = await session.click_text(
            str(text), fuzzy=fuzzy, exact=exact, occurrence=occurrence,
        )
        return f"Clicked text {text!r}" if ok else f"Error: text {text!r} not found"

    elif action == "find_text":
        text = kwargs.get("text", "")
        if not text:
            return "Error: text parameter required for find_text"
        fuzzy = bool(kwargs.get("fuzzy", False))
        exact = bool(kwargs.get("exact", False))
        occurrence = int(kwargs.get("occurrence", 1))
        result = await session.find_text(
            str(text), fuzzy=fuzzy, exact=exact, occurrence=occurrence,
        )
        return json.dumps(result, ensure_ascii=False)

    elif action == "wait":
        ms = int(kwargs.get("ms", 0))
        await session.wait(ms)
        return json.dumps({"action": "wait", "ms": ms})

    elif action == "execute_cdp":
        method = kwargs.get("method", "")
        if not method:
            return "Error: 'method' parameter required for execute_cdp (e.g. 'Network.enable')"
        params = kwargs.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        result = await session._transport.send(method, params)
        return json.dumps(result, ensure_ascii=False, default=str)

    else:
        return f"Error: unknown action '{action}'"


EncreBrowserTool = build_tool(
    name="browser",
    description=(
        "Control an embedded Chromium webview to browse the web, interact with pages, "
        "and extract information.\n\n"
        "WHEN to use: tasks that need real browser interaction -- logins, "
        "clicking buttons, filling forms, scraping JS-rendered SPAs, or taking "
        "screenshots for vision-based reasoning.\n"
        "WHEN NOT to use: for plain keyword search use web_search (returns "
        "content inline, no browser needed); for a single static URL use "
        "web_fetch; for raw JSON API calls use rest_client.\n\n"
        "WORKFLOW:\n"
        "1. Start with `navigate(url)` to load a page, or pass a plain search query (e.g. "
        "\"today's weather\") and it will be sent to the configured search engine.\n"
        "2. Wait for the page to load, then call `get_page_structure()` to get all "
        "interactive elements (buttons, links, inputs, headings) with their bounding boxes, "
        "roles, and accessible names -- this gives you a complete 'map' of the page.\n"
        "3. Interact using text/role-based methods first (more reliable):\n"
        "   - `click_text(\"Sign in\")` -- click visible text\n"
        "   - `click_by_role(\"button\", \"Submit\")` -- click by ARIA role + name\n"
        "   - `type(selector, text)` -- type into a field (selector from get_page_structure)\n"
        "4. If text/role methods fail, use CSS selectors from get_page_structure:\n"
        "   - `click(selector)`, `type(selector, text)`, `select_option(selector, value)`\n"
        "5. For vision-capable models, use coordinate actions:\n"
        "   - `screenshot()` first to see the page, then `click_at(x, y)` / `type_at(x, y, text)`\n"
        "6. Extract results with `get_all_text()` or `get_text(selector)`.\n\n"
        "SEARCH:\n"
        "`navigate(url)` treats any non-URL input as a search query and routes it through "
        "the user's configured default search engine (set in browser settings).\n\n"
        "TIPS:\n"
        "- Always call `get_page_structure()` after navigation to discover what's on the page.\n"
        "- Prefer text-based methods (`click_text`, `click_by_role`) over CSS selectors -- "
        "they're more robust to page changes.\n"
        "- Prefer CSS selectors over coordinates -- coordinates break on different viewports.\n"
        "- Use `wait(ms)` to pause between actions (e.g. after a click that triggers navigation).\n"
        "- Use `screenshot()` with `screenshot_viewport()` for vision models -- the viewport "
        "info tells you the scroll position and page dimensions.\n"
        "- For advanced DevTools access, use `execute_cdp(method, params)` to call any Chrome "
        "DevTools Protocol method directly (e.g. Network.enable, Console.enable, DOM.getDocument).\n\n"
        "PITFALLS: if a `click` or `type` fails, the element might not be visible -- try "
        "`scroll_to(x, y)` first; the webview lives in the desktop app sidebar (no external "
        "window opens), so make sure the user has the browser tab open."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "click", "click_at", "double_click_at",
                    "right_click_at", "type", "type_at", "screenshot",
                    "screenshot_viewport", "get_html", "get_text",
                    "get_all_text", "execute_js", "wait_for_selector",
                    "wait", "scroll_to", "fill_form", "press_key",
                    "hotkey", "hover", "hover_at", "drag", "get_viewport",
                    "get_state", "save_cookies", "load_cookies",
                    "close_session", "a11y_snapshot", "click_by_role",
                    "click_text", "find_text", "get_by_text_count",
                    "get_page_structure", "select_option", "get_attribute",
                    "get_property", "list_tabs", "switch_tab", "new_tab",
                    "close_tab", "set_dialog_handler",
                    "set_file_chooser_handler", "execute_cdp",
                ],
                "description": "Browser action to perform. See tool description for workflow guidance on which action to use when",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to, or a plain search query (e.g. 'today's news') which will be sent to the configured search engine",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for DOM-based actions (click, type, hover, etc.). Get valid selectors from get_page_structure() output",
            },
            "x": {
                "type": "integer",
                "description": "X coordinate in viewport pixels "
                "(for click_at, type_at, hover_at, move_mouse, drag start)",
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate in viewport pixels "
                "(for click_at, type_at, hover_at, move_mouse, drag start)",
            },
            "x2": {
                "type": "integer",
                "description": "Target X coordinate (for drag end)",
            },
            "y2": {
                "type": "integer",
                "description": "Target Y coordinate (for drag end)",
            },
            "text": {
                "type": "string",
                "description": "Text to match or type: for click_text/find_text the visible text to find; for type/type_at the text to input",
            },
            "full_page": {
                "type": "boolean",
                "description": "screenshot: when true, capture the entire scrollable page instead of just the visible viewport (default false).",
            },
            "code": {
                "type": "string",
                "description": "execute_js: JavaScript expression or statement block to evaluate in the page context. Must return a JSON-serializable value to be readable.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (for wait_for_selector)",
            },
            "fields": {
                "type": "object",
                "description": "Dict of selector:value pairs (for fill_form)",
            },
            "key": {
                "type": "string",
                "description": "Key name to press (for press_key)",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key combination (e.g. [\"Control\", \"c\"] for copy)",
            },
            "cookies": {
                "type": "array",
                "description": "List of cookie dicts (for load_cookies)",
            },
            "interesting_only": {
                "type": "boolean",
                "description": "a11y_snapshot: prune uninteresting nodes (default true)",
            },
            "role": {
                "type": "string",
                "description": "ARIA role for click_by_role (button, link, textbox, ...)",
            },
            "name": {
                "type": "string",
                "description": "Accessible name for click_by_role / get_by_text_count",
            },
            "exact": {
                "type": "boolean",
                "description": "Use exact name matching (click_by_role / get_by_text_count)",
            },
            "root_selector": {
                "type": "string",
                "description": "Optional CSS root for a11y_snapshot to limit the tree",
            },
            "value": {
                "type": "string",
                "description": "select_option: option value (or label/index -- see by)",
            },
            "by": {
                "type": "string",
                "enum": ["value", "label", "index"],
                "description": "select_option: how value is matched (default value)",
            },
            "index": {
                "type": "integer",
                "description": "switch_tab / close_tab: 0-based tab index",
            },
            "ms": {
                "type": "integer",
                "description": "wait: milliseconds to sleep before returning",
            },
            "method": {
                "type": "string",
                "description": "CDP method name for execute_cdp (e.g. 'Network.enable', 'Console.enable', 'DOM.getDocument', 'Network.getCookies')",
            },
            "params": {
                "type": "object",
                "description": "CDP method parameters as JSON object for execute_cdp",
            },
            "accept": {
                "type": "boolean",
                "description": "set_dialog_handler: True=accept, False=dismiss (default True)",
            },
            "prompt_text": {
                "type": "string",
                "description": "set_dialog_handler: text to feed prompt() dialogs",
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "set_file_chooser_handler: list of file paths to inject",
            },
            "fuzzy": {
                "type": "boolean",
                "description": (
                    "click_text / find_text: when true, match the query as a "
                    "sequence of whitespace-separated tokens appearing in order"
                ),
            },
            "occurrence": {
                "type": "integer",
                "description": "click_text / find_text: 1-based match index",
            },
            "max_chars": {
                "type": "integer",
                "description": (
                    "get_all_text: truncate the response to this many "
                    "chars (default 200000)"
                ),
            },
        },
        "required": ["action"],
    },
    execute=_browser_execute,
    intents=["coding", "system"],
    category="web",
    semantic_type="network",
    is_destructive=lambda args: args.get("action", "") in ("click", "type", "fill_form", "navigate", "execute_js", "press_key", "drag"),
)
