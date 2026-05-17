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

from yim.tools.base import YmiTool


class YmiTodoTool(YmiTool):
    name: ClassVar[str] = "todo"
    description: ClassVar[str] = "Create or update a structured todo list for task tracking"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["content", "status", "priority"],
                },
                "description": "List of todo items",
            },
            "summary": {
                "type": "string",
                "description": "Summary of work accomplished",
            },
            "reset": {
                "type": "boolean",
                "description": "Whether to reset the todo list",
            },
        },
        "required": ["todos"],
    }

    async def execute(self, **kwargs: Any) -> str:
        todos = kwargs.get("todos", [])
        summary = kwargs.get("summary", "")
        reset = kwargs.get("reset", False)

        lines: list[str] = []
        if summary:
            lines.append(f"Summary: {summary}")
            lines.append("")

        if reset:
            lines.append("Todo list has been reset.")

        for item in todos:
            status_icon = {"pending": "○", "in_progress": "●", "completed": "✓"}
            icon = status_icon.get(item.get("status", "pending"), "○")
            priority_flag = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            flag = priority_flag.get(item.get("priority", "medium"), "🟡")
            lines.append(f"{icon} {flag} {item.get('content', '')}")

        if not lines:
            return "No todo items."

        return "\n".join(lines)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False