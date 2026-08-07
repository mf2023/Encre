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

"""Module: builtin/desktop.py

Desktop implementation for the Encre tool system.
"""
import json
from typing import Any

from encre.tools.base import build_tool

_session: Any = None


def _get_session():
    """Get session."""
    global _session
    if _session is None:
        from encre.computer.desktop import EncreDesktopSession
        _session = EncreDesktopSession()
    return _session


async def _desktop_execute(**kwargs: Any) -> str:
    """Desktop execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    session = _get_session()
    coord_space = str(kwargs.get("coord_space", "auto"))
    if coord_space not in ("auto", "physical", "logical"):
        return f"Error: invalid coord_space '{coord_space}'"

    try:
        if action == "screenshot":
            state = session.screenshot_with_cursor()
            payload: dict[str, Any] = {
                "width": state.width,
                "height": state.height,
                "logical_width": state.logical_width,
                "logical_height": state.logical_height,
                "dpi_scale_x": state.dpi_scale_x,
                "dpi_scale_y": state.dpi_scale_y,
                "cursor_x": state.cursor_x,
                "cursor_y": state.cursor_y,
                "platform": state.platform,
                "screenshot_base64": state.screenshot_b64,
            }
            if state.active_window_b64:
                payload["active_window_b64"] = state.active_window_b64
                payload["active_window_left"] = state.active_window_left
                payload["active_window_top"] = state.active_window_top
                payload["active_window_width"] = state.active_window_width
                payload["active_window_height"] = state.active_window_height
            return json.dumps(payload, ensure_ascii=False)

        elif action == "get_screen_size":
            size = session.get_screen_size()
            return json.dumps(size)

        elif action == "get_cursor_position":
            pos = session.get_cursor_position()
            return json.dumps(pos)

        elif action == "move_mouse":
            x = kwargs.get("x")
            y = kwargs.get("y")
            if x is None or y is None:
                return "Error: x and y coordinates required for move_mouse"
            result = session.move_mouse(int(x), int(y), coord_space=coord_space)
            return json.dumps(result)

        elif action == "click":
            x = kwargs.get("x")
            y = kwargs.get("y")
            result = session.click(
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
                coord_space=coord_space,
            )
            return json.dumps(result)

        elif action == "double_click":
            x = kwargs.get("x")
            y = kwargs.get("y")
            result = session.double_click(
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
                coord_space=coord_space,
            )
            return json.dumps(result)

        elif action == "right_click":
            x = kwargs.get("x")
            y = kwargs.get("y")
            result = session.right_click(
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
                coord_space=coord_space,
            )
            return json.dumps(result)

        elif action == "drag":
            x1 = kwargs.get("x")
            y1 = kwargs.get("y")
            x2 = kwargs.get("x2")
            y2 = kwargs.get("y2")
            if x1 is None or y1 is None or x2 is None or y2 is None:
                return "Error: x, y (start) and x2, y2 (end) required for drag"
            result = session.drag(int(x1), int(y1), int(x2), int(y2),
                                  coord_space=coord_space)
            return json.dumps(result)

        elif action == "type_text":
            text = kwargs.get("text", "")
            if not text:
                return "Error: text parameter required for type_text"
            result = session.type_text(str(text))
            return json.dumps(result)

        elif action == "press_key":
            key = kwargs.get("key", "")
            if not key:
                return "Error: key parameter required for press_key"
            result = session.press_key(str(key))
            return json.dumps(result)

        elif action == "hotkey":
            keys = kwargs.get("keys", [])
            if not keys:
                return "Error: keys array required for hotkey"
            result = session.hotkey([str(k) for k in keys])
            return json.dumps(result)

        elif action == "scroll":
            clicks = kwargs.get("clicks")
            if clicks is None:
                return "Error: clicks parameter required for scroll"
            x = kwargs.get("x")
            y = kwargs.get("y")
            result = session.scroll(
                int(clicks),
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
            )
            return json.dumps(result)

        elif action == "locate_on_screen":
            template = kwargs.get("template", "")
            if not template:
                return "Error: template (base64 PNG) required for locate_on_screen"
            confidence = float(kwargs.get("confidence", 0.9))
            result = session.locate_on_screen(template, confidence=confidence)
            if result.found:
                return json.dumps({
                    "found": True,
                    "x": result.x,
                    "y": result.y,
                    "width": result.width,
                    "height": result.height,
                    "confidence": result.confidence,
                })
            return json.dumps({"found": False})

        elif action == "accessibility_tree":
            max_depth = int(kwargs.get("max_depth", 6))
            max_nodes = int(kwargs.get("max_nodes", 500))
            tree = session.accessibility_tree(max_depth=max_depth, max_nodes=max_nodes)
            return json.dumps(tree, ensure_ascii=False)

        elif action == "find_element_by_name":
            name = kwargs.get("name", "")
            if not name:
                return "Error: name parameter required for find_element_by_name"
            control_type = kwargs.get("control_type") or None
            result = session.find_element_by_name(name, control_type=control_type)
            return json.dumps(result, ensure_ascii=False)

        elif action == "get_elements":
            min_text_len = int(kwargs.get("min_text_length", 2))
            from encre.computer.ocr import ocr_image
            prefer_window = bool(kwargs.get("prefer_active_window", True))
            window_capture = (
                session._capture_active_window_png() if prefer_window else None
            )
            used_window_capture = window_capture is not None
            if used_window_capture:
                # OCR the foreground window -- this catches DirectX /
                # Direct2D content and occluded windows that the OS
                # compositor strips from the desktop screenshot.
                img_bytes = window_capture.png_bytes
                ocr_offset_x = int(window_capture.left)
                ocr_offset_y = int(window_capture.top)
            else:
                state = session.screenshot_with_cursor()
                img_bytes = __import__("base64").b64decode(state.screenshot_b64)
                ocr_offset_x = 0
                ocr_offset_y = 0
            elements = ocr_image(img_bytes)
            # Filter very short fragments
            elements = [e for e in elements if len(e["text"]) >= min_text_len]
            if used_window_capture:
                # Translate OCR bbox from window-local coords to screen
                # coords so downstream click_text / find_text keep
                # working without any caller-side changes.
                for e in elements:
                    e["x"] = int(e["x"]) + ocr_offset_x
                    e["y"] = int(e["y"]) + ocr_offset_y
                    e["center_x"] = int(e["center_x"]) + ocr_offset_x
                    e["center_y"] = int(e["center_y"]) + ocr_offset_y
            # For the visual screenshot we still prefer the regular
            # desktop capture -- it shows window + desktop context.
            # When the window capture is available, attach it as well
            # so the model can read window content that the compositor
            # hid (DirectX / Direct2D / occluded regions).
            state = session.screenshot_with_cursor()
            payload: dict[str, Any] = {
                "screen_width": state.width,
                "screen_height": state.height,
                "logical_width": state.logical_width,
                "logical_height": state.logical_height,
                "dpi_scale_x": state.dpi_scale_x,
                "dpi_scale_y": state.dpi_scale_y,
                "cursor_x": state.cursor_x,
                "cursor_y": state.cursor_y,
                "elements_count": len(elements),
                "elements": elements,
                "screenshot_base64": state.screenshot_b64,
            }
            if used_window_capture:
                payload["window_screenshot_base64"] = (
                    __import__("base64").b64encode(
                        window_capture.png_bytes
                    ).decode("ascii")
                )
                payload["window_left"] = int(window_capture.left)
                payload["window_top"] = int(window_capture.top)
                payload["window_width"] = int(window_capture.width)
                payload["window_height"] = int(window_capture.height)
                payload["ocr_source"] = "active_window"
            else:
                payload["ocr_source"] = "desktop"
            return json.dumps(payload, ensure_ascii=False)

        elif action == "triple_click":
            x = kwargs.get("x")
            y = kwargs.get("y")
            result = session.triple_click(
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
                coord_space=coord_space,
            )
            return json.dumps(result)

        elif action == "wait":
            ms = int(kwargs.get("ms", 0))
            return json.dumps(session.wait(ms))

        elif action == "clipboard_get":
            return session.clipboard_get()

        elif action == "clipboard_set":
            text = kwargs.get("text", "")
            if text is None:
                return "Error: text parameter required for clipboard_set"
            return json.dumps(session.clipboard_set(str(text)))

        elif action == "file_drop":
            paths = kwargs.get("paths") or kwargs.get("files") or []
            if isinstance(paths, str):
                paths = [paths]
            if not paths:
                return "Error: paths (list of file paths) required for file_drop"
            x = kwargs.get("x")
            y = kwargs.get("y")
            if x is None or y is None:
                return "Error: x and y coordinates required for file_drop"
            return json.dumps(
                session.file_drop(int(x), int(y), [str(p) for p in paths],
                                  coord_space=coord_space)
            )

        elif action == "click_text":
            text = kwargs.get("text", "")
            if not text:
                return "Error: text parameter required for click_text"
            fuzzy = bool(kwargs.get("fuzzy", False))
            occurrence = int(kwargs.get("occurrence", 1))
            button = str(kwargs.get("button", "left"))
            result = session.click_text(
                str(text), fuzzy=fuzzy, occurrence=occurrence,
                button=button, coord_space=coord_space,
            )
            return json.dumps(result, ensure_ascii=False)

        elif action == "find_text":
            text = kwargs.get("text", "")
            if not text:
                return "Error: text parameter required for find_text"
            fuzzy = bool(kwargs.get("fuzzy", False))
            occurrence = int(kwargs.get("occurrence", 1))
            result = session.find_text(
                str(text), fuzzy=fuzzy, occurrence=occurrence,
            )
            return json.dumps(result, ensure_ascii=False)

        elif action == "take_screenshot_png":
            png_bytes = session.take_screenshot_png()
            import base64
            return base64.b64encode(png_bytes).decode("ascii")

        else:
            return f"Error: unknown action '{action}'"

    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Desktop action '{action}' failed: {e}"


EncreDesktopTool = build_tool(
    name="desktop",
    description=(
        "WHAT: Cross-platform desktop automation -- screenshots (with DPI "
        "scale info), click, type, scroll, drag, hotkey, locate image on "
        "screen, and on Windows walk the UI Automation accessibility tree. "
        "WHEN: Use for OS-level UI automation of native applications, "
        "taking screenshots to inspect what is on screen, clicking UI that "
        "has no CSS selectors, or reading visible text via OCR. "
        "WHEN NOT: Use `computer_use` for a unified API across browser and "
        "desktop, `browser` for in-page web actions, or `vlm_computer_use` "
        "when the model should delegate pixel-level decisions to a vision "
        "model. "
        "TIPS: Use `get_elements` to OCR visible text + bounding boxes so "
        "the model can see what is on screen without vision; pass "
        "coord_space='physical' (default 'auto') to click directly with "
        "coordinates read off a screenshot; call `accessibility_tree` on "
        "Windows for structured element data instead of OCR. "
        "PITFALLS: HiDPI displays require the right coord_space -- clicking "
        "with logical coords while in physical space (or vice versa) lands "
        "in the wrong spot. Coordinates are screen-relative, so if a window "
        "moves between screenshot and click the click lands in the wrong "
        "place. `accessibility_tree` and `find_element_by_name` are "
        "Windows-only and return empty on other platforms; OCR may miss "
        "stylised fonts or low-contrast text."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "screenshot",
                    "click",
                    "double_click",
                    "right_click",
                    "triple_click",
                    "move_mouse",
                    "drag",
                    "type_text",
                    "press_key",
                    "hotkey",
                    "scroll",
                    "wait",
                    "clipboard_get",
                    "clipboard_set",
                    "file_drop",
                    "click_text",
                    "find_text",
                    "locate_on_screen",
                    "get_screen_size",
                    "get_cursor_position",
                    "accessibility_tree",
                    "find_element_by_name",
                    "get_elements",
                    "take_screenshot_png",
                ],
                "description": (
                    "Required. Desktop action to perform. Read-only "
                    "actions (screenshot, get_screen_size, "
                    "get_cursor_position, accessibility_tree, "
                    "find_element_by_name, get_elements, find_text, "
                    "locate_on_screen, take_screenshot_png, "
                    "clipboard_get, wait) are concurrency-safe; "
                    "mutating actions are not."
                ),
            },
            "x": {
                "type": "integer",
                "description": (
                    "X coordinate for click, double_click, right_click, "
                    "triple_click, move_mouse, drag start, scroll anchor, "
                    "file_drop target. Coordinate space is governed by "
                    "coord_space."
                ),
            },
            "y": {
                "type": "integer",
                "description": (
                    "Y coordinate, same coordinate space as `x`. Required "
                    "alongside `x` for the actions that take `x`."
                ),
            },
            "x2": {
                "type": "integer",
                "description": (
                    "End X coordinate for drag (drop target). Required "
                    "for `drag` alongside `y2`."
                ),
            },
            "y2": {
                "type": "integer",
                "description": (
                    "End Y coordinate for drag (drop target). Required "
                    "for `drag` alongside `x2`."
                ),
            },
            "coord_space": {
                "type": "string",
                "enum": ["auto", "physical", "logical"],
                "description": (
                    "Coordinate system of (x, y). 'physical' = pixels of "
                    "the screenshot, 'logical' = pyautogui's scaled "
                    "coords, 'auto' (default) detects from value "
                    "magnitude."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "Text to type for type_text, or clipboard content for "
                    "clipboard_set."
                ),
            },
            "key": {
                "type": "string",
                "description": (
                    "Single key name for press_key (e.g. 'enter', 'tab', "
                    "'escape', 'f1'). Use `keys` for combinations."
                ),
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ordered key list for hotkey, pressed sequentially "
                    "then released in reverse (e.g. [\"ctrl\", \"c\"] "
                    "for copy)."
                ),
            },
            "clicks": {
                "type": "integer",
                "description": (
                    "Scroll amount for scroll. Positive scrolls up, "
                    "negative scrolls down (note: opposite sign of "
                    "computer_use's scroll_amount)."
                ),
            },
            "template": {
                "type": "string",
                "description": (
                    "Base64-encoded PNG image to locate on screen via "
                    "template matching. Required for locate_on_screen."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "locate_on_screen: minimum match confidence in "
                    "[0.0, 1.0]. Matches below this threshold are "
                    "discarded. Default 0.9."
                ),
            },
            "max_depth": {
                "type": "integer",
                "description": (
                    "accessibility_tree: maximum recursion depth from "
                    "the desktop root. Default 6."
                ),
            },
            "max_nodes": {
                "type": "integer",
                "description": (
                    "accessibility_tree: cap on number of nodes "
                    "returned. Default 500."
                ),
            },
            "name": {
                "type": "string",
                "description": (
                    "find_element_by_name: substring match against the "
                    "accessible name. Case-insensitive."
                ),
            },
            "control_type": {
                "type": "string",
                "description": (
                    "find_element_by_name: filter by UIA control type "
                    "(e.g. ButtonControl, EditControl). Optional."
                ),
            },
            "min_text_length": {
                "type": "integer",
                "description": (
                    "get_elements: ignore OCR text fragments shorter "
                    "than this to filter noise. Default 2."
                ),
            },
            "ms": {
                "type": "integer",
                "description": (
                    "wait: milliseconds to sleep before returning. Use "
                    "short values for animation settle, longer for "
                    "loading states."
                ),
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "file_drop: list of absolute file paths to drop on "
                    "(x, y). Required for file_drop."
                ),
            },
            "button": {
                "type": "string",
                "enum": ["left", "middle", "right"],
                "description": (
                    "Mouse button for click / click_text. Default 'left'."
                ),
            },
            "fuzzy": {
                "type": "boolean",
                "description": (
                    "click_text / find_text: when true, treat the query "
                    "as a sequence of whitespace-separated tokens that "
                    "must all appear in order inside the matched text. "
                    "Default false."
                ),
            },
            "occurrence": {
                "type": "integer",
                "description": (
                    "click_text / find_text: 1-based index of the match "
                    "to use when the same text appears multiple times. "
                    "Default 1."
                ),
            },
        },
        "required": ["action"],
    },
    execute=_desktop_execute,
    intents=["coding", "system"],
    is_concurrency_safe=lambda data: data.get("action") in (
        "screenshot",
        "get_screen_size",
        "get_cursor_position",
        "accessibility_tree",
        "locate_on_screen",
        "find_element_by_name",
        "find_text",
        "get_elements",
        "take_screenshot_png",
        "clipboard_get",
        "wait",
    ),
    category="system",
    semantic_type="exec",
    is_destructive=lambda args: args.get("action", "") in ("click", "type", "scroll", "drag", "hotkey", "keyboard_write"),
)
