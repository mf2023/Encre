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

"""Module: builtin/task_output.py

Task output implementation for the Encre tool system.
"""
import asyncio
import json
from typing import Any

from encre.tools.base import build_tool
from encre.utils.types import TaskStatus


async def _task_output_execute(**kwargs: Any) -> str:
    """Task output execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    from encre.task.manager import EncreTaskManager

    task_id = kwargs.get("task_id", "")
    block = kwargs.get("block", True)
    timeout_ms = kwargs.get("timeout", 30000)

    if not task_id:
        return "Error: task_id is required."

    task = EncreTaskManager.get_task(task_id)
    if task is None:
        return f"Error: task '{task_id}' not found."

    # If blocking, poll until terminal status or timeout
    if block and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.2, remaining))
            task = EncreTaskManager.get_task(task_id)
            if task is None:
                return f"Error: task '{task_id}' disappeared."

    status_icon = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.RUNNING: "\U0001f504",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.CANCELLED: "\U0001f6ab",
    }.get(task.status, "❓")

    result = {
        "id": task.id,
        "name": task.name,
        "status": task.status.name,
        "icon": status_icon,
        "result": task.result or "",
        "error": task.error or "",
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }

    if task.result and len(task.result) > 5000:
        result["result"] = task.result[:5000] + "\n... (truncated)"
    if task.error and len(task.error) > 2000:
        result["error"] = task.error[:2000] + "\n... (truncated)"

    return json.dumps(result, ensure_ascii=False, indent=2)


EncreTaskOutputTool = build_tool(
    name="task_output",
    description=(
        "Retrieve the output (status, result, error, timestamps) of a "
        "background task, optionally blocking until it finishes.\n\n"
        "WHEN to use: right after task_create to wait for and collect the "
        "task's result; periodically to monitor a long-running task's "
        "progress.\n"
        "WHEN NOT to use: for a quick non-blocking snapshot where you don't "
        "want to wait, call this with block=false; to enumerate tasks use "
        "task_list.\n"
        "TIPS: with block=true (default) the call polls until the task "
        "reaches a terminal state or the timeout elapses; results over 5000 "
        "chars and errors over 2000 chars are truncated.\n"
        "PITFALLS: a timeout does NOT cancel the task -- it just returns the "
        "current state; the task keeps running in the background."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The unique ID of the task to read output from (from task_create or task_list).",
            },
            "block": {
                "type": "boolean",
                "description": "When true (default), wait for the task to reach a terminal state (completed/failed/cancelled) before returning. When false, return the current state immediately.",
                "default": True,
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum time to wait in milliseconds when block=true (default: 30000). The call returns the latest state once this elapses even if the task is still running.",
                "default": 30000,
            },
        },
        "required": ["task_id"],
    },
    execute=_task_output_execute,
    intents=["general", "coding", "data"],
    category="task",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
