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

"""Module: builtin/todo.py

Todo implementation for the Encre tool system.
"""
from typing import Any

from encre.tools.base import build_tool


async def _todo_execute(**kwargs: Any) -> str:
    """Render the current task list with status icons and priority flags."""
    todos = kwargs.get("todos", [])
    if not isinstance(todos, list):
        return "Error: 'todos' must be a list of task objects."
    summary = kwargs.get("summary", "")
    reset = kwargs.get("reset", False)

    lines: list[str] = []
    if summary:
        lines.append(f"Summary: {summary}\n")

    if reset:
        lines.append("Todo list has been reset.")

    for item in todos:
        status = item.get("status", "pending")
        icon = {"pending": "○", "in_progress": "●", "completed": "✓"}.get(status, "○")
        label = item.get("activeForm") if status == "in_progress" else item.get("content")
        lines.append(f"{icon} {label or item.get('content', '')}")

    return "\n".join(lines) if lines else "No todo items."


EncreTodoTool = build_tool(
    name="todo",
    description=(
        "Create and manage a structured task list for multi-step work, "
        "rendered as an interactive checklist in the UI.\n\n"
        "WHEN to use: any task with 3+ distinct steps, multi-file changes, or "
        "when the user asks for a plan/progress tracking.\n"
        "WHEN NOT to use: single trivial tasks (< 3 steps) or purely "
        "conversational requests -- writing a todo list for those adds noise.\n"
        "TIPS: keep exactly ONE item in_progress at a time; mark items "
        "completed immediately as you finish them; update the whole list in "
        "one call rather than many small edits.\n"
        "PITFALLS: do not add items for work you don't actually intend to do; "
        "do not leave items perpetually in_progress -- advance them."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Short imperative description of the task (e.g. \"Run tests\")."},
                        "activeForm": {"type": "string", "description": "Present-continuous form shown while the task is in_progress (e.g. \"Running tests\")."},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["content", "status"],
                },
                "description": "Full task list -- pass the entire list every call (this tool replaces, not appends). Only one item may be in_progress at a time.",
            },
            "summary": {"type": "string", "description": "Optional short summary of work accomplished, shown at the top of the rendered list."},
            "reset": {"type": "boolean", "description": "When true, clears the existing todo list before rendering the new one (default false)."},
        },
        "required": ["todos"],
    },
    execute=_todo_execute,
    intents=["general", "coding", "data", "research"],
    category="task",
    triggers=["todo", "task list", "task", "plan", "track", "progress"],
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
