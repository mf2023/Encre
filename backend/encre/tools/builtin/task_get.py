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

"""Module: builtin/task_get.py

Task get implementation for the Encre tool system.
"""
from typing import Any

from encre.task.manager import EncreTaskManager
from encre.tools.base import build_tool


async def _task_get_execute(**kwargs: Any) -> str:
    """Task get execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    task_id = kwargs.get("task_id", "")
    task = EncreTaskManager.get_task(task_id)
    if task is None:
        return f"Error: Task not found: {task_id}"

    lines = [
        f"ID: {task.id}",
        f"Name: {task.name}",
        f"Type: {task.task_type}",
        f"Status: {task.status}",
        f"Description: {task.description}",
    ]
    if task.result:
        lines.append(f"Result: {task.result[:500]}")
    if task.error:
        lines.append(f"Error: {task.error}")
    if task.parent_id:
        lines.append(f"Parent: {task.parent_id}")
    return "\n".join(lines)


EncreTaskGetTool = build_tool(
    name="task_get",
    description=(
        "Get the details (name, type, status, description, result, error, "
        "parent) of a single task by its ID.\n\n"
        "WHEN to use: you have a task ID from task_create or task_list and "
        "want a one-shot snapshot of its current state and any stored "
        "result/error.\n"
        "WHEN NOT to use: to wait for a running task to finish, use "
        "task_output (it can block until completion); to enumerate many tasks, "
        "use task_list.\n"
        "TIP: the returned 'result' field is truncated to 500 chars in this "
        "view -- use task_output for the full (up to 5000 char) payload."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The unique ID of the task to retrieve (returned by task_create or shown in task_list).",
            },
        },
        "required": ["task_id"],
    },
    execute=_task_get_execute,
    intents=["general", "coding", "data", "research"],
    category="task",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
