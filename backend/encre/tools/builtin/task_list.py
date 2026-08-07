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

"""Module: builtin/task_list.py

Task list implementation for the Encre tool system.
"""
from typing import Any

from encre.task.manager import EncreTaskManager
from encre.tools.base import build_tool


async def _task_list_execute(**kwargs: Any) -> str:
    """Task list execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    status = kwargs.get("status")
    tasks = EncreTaskManager.list_tasks(status=status)

    if not tasks:
        return "No tasks found."

    lines: list[str] = []
    for task in tasks:
        status_icon = {
            "pending": "○",
            "running": "●",
            "completed": "✓",
            "failed": "✗",
            "killed": "⊘",
        }
        icon = status_icon.get(task.status, "○")
        lines.append(f"{icon} {task.id}: {task.name} ({task.status})")

    return "\n".join(lines)


EncreTaskListTool = build_tool(
    name="task_list",
    description=(
        "List all tasks (or those matching a status filter), each shown with "
        "an ID, name, and status icon.\n\n"
        "WHEN to use: discover what tasks exist, find the ID of a task you "
        "forgot, or check the spread of pending/running/completed work.\n"
        "WHEN NOT to use: for the full details of one known task use task_get; "
        "to wait for a specific running task use task_output.\n"
        "TIPS: pass a status filter (e.g. 'running') to focus on actionable "
        "work; the IDs returned here are inputs to task_get/task_output/"
        "task_stop."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "failed", "killed"],
                "description": "Optional status filter. Omit to list tasks in every state. Common values: 'running' to find in-flight work, 'failed' to find tasks needing attention.",
            },
        },
    },
    execute=_task_list_execute,
    intents=["general", "coding", "data", "research"],
    category="task",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
