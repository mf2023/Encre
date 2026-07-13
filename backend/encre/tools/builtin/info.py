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

"""Module: builtin/info.py

Info-card tool for the Encre tool system.

Provides a generic rich-content container that lets the model render
self-contained HTML/CSS/JS snippets inside the chat timeline.  The payload
is treated as opaque content and passed through to the frontend, which
sandboxes it in an iframe for safety.
"""
import json
from typing import Any

from encre.tools.base import build_tool


async def _info_execute(**kwargs: Any) -> str:
    """Validate and echo the info-card payload back to the frontend.

    The frontend is responsible for rendering the HTML/CSS/JS inside a
    sandboxed iframe.  This executor only performs lightweight validation
    and normalization so the model receives clear feedback on errors.
    """
    content = kwargs.get("content", "")
    if not isinstance(content, str):
        return "Error: 'content' must be a string containing HTML/CSS/JS."

    title = kwargs.get("title", "")
    card_type = kwargs.get("type", "html")
    if card_type not in {"html", "widget"}:
        card_type = "html"

    # Detect whether the HTML payload looks like a complete document. Fragments
    # and bare <style> blocks are still rendered, but the model is encouraged to
    # provide a full <html>/<body> document for best results.
    is_complete_html = False
    if card_type == "html":
        lowered = content.lower().strip()
        is_complete_html = (
            lowered.startswith("<!doctype")
            or lowered.startswith("<html")
            or "<body" in lowered
        )

    display = kwargs.get("display", "base")
    if display not in {"base", "code", "split"}:
        display = "base"

    # Structured widget types that the model must provide data for manually.
    widget = kwargs.get("widget", "")
    if widget not in {"", "flight", "train", "ship"}:
        widget = ""

    payload = {
        "type": card_type,
        "display": display,
        "widget": widget,
        "title": title if isinstance(title, str) else "",
        "content": content,
        "is_complete_html": is_complete_html,
    }
    return json.dumps(payload, ensure_ascii=False)


EncreInfoTool = build_tool(
    name="info",
    description=(
        "Optional rich-card visualization tool. Do NOT use this for ordinary "
        "text answers; reply with normal markdown text instead. Only invoke this "
        "tool when the user explicitly asks for a card, widget, or visual layout, "
        "or when the information naturally fits a compact real-time card such as "
        "a flight, train, or ship itinerary. "
        "Always specify the 'display' parameter. "
        "Use display='base' together with type='html' to render a self-contained "
        "HTML/CSS/JS document. A complete document including <html>, <body> and all "
        "required CSS is strongly preferred; fragments or a bare <style> block will "
        "still be rendered but may look broken. "
        "Use display='code' to show the raw source instead of rendering it. "
        "The model may also set type='widget' with widget='flight', widget='train', "
        "or widget='ship' to request that the model itself fills in the travel "
        "data (no external travel API is connected yet); widgets are rendered by "
        "fixed frontend templates, not by the HTML sandbox. "
        "Keep content self-contained; external resources are loaded at the user's risk."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["html", "widget"],
                "description": "Card rendering mode: html for free-form rendering, widget for structured templates.",
            },
            "display": {
                "type": "string",
                "enum": ["base", "code", "split"],
                "description": "Display mode. 'base' renders the HTML/CSS/JS card (default); 'code' shows the source; 'split' is reserved for future use.",
            },
            "widget": {
                "type": "string",
                "enum": ["", "flight", "train", "ship"],
                "description": "Structured widget type. 'flight', 'train' and 'ship' mean the model must provide the travel data itself (no live API yet); leave empty for free-form html cards.",
            },
            "title": {
                "type": "string",
                "description": "Optional card title shown above the rendered content.",
            },
            "content": {
                "type": "string",
                "description": (
                    "For type='html' this is a self-contained HTML/CSS/JS payload. "
                    "A complete document including <html>, <head>, <body> is strongly preferred; "
                    "fragments or a bare <style> block will still be rendered but may look broken. "
                    "For type='widget' this is a JSON object with the widget data. "
                    "Flight widget expects: flightNo, airline, departureCode, departureAirport, "
                    "departureTime, arrivalCode, arrivalAirport, arrivalTime, plus optional gate, seat, status, terminal. "
                    "Train widget expects: trainNo, type, departureStation, departureTime, arrivalStation, arrivalTime, "
                    "plus optional platform, seat, status. "
                    "Ship widget expects: shipName, operator, departurePort, departureTime, arrivalPort, arrivalTime, "
                    "plus optional dock, cabin, status."
                ),
            },
        },
        "required": ["display", "content"],
    },
    execute=_info_execute,
    intents=["general", "communication", "data", "research"],
    category="communication",
    triggers=[
        "card", "info card", "widget",
        "flight", "airplane", "plane", "boarding pass", "flight status",
        "train", "railway", "high speed rail", "bullet train", "CRH",
        "ship", "cruise", "ferry", "vessel", "sailing",
        "itinerary", "travel card", "trip card",
    ],
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
