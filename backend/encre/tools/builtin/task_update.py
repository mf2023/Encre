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

"""Module: builtin/task_update.py

Task update implementation for the Encre tool system.
"""
from typing import Any

from encre.task.manager import EncreTaskManager
from encre.tools.base import build_tool


async def _task_update_execute(**kwargs: Any) -> str:
    """Task update execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    task_id = kwargs.get("task_id", "")
    status = kwargs.get("status")
    result = kwargs.get("result")
    error = kwargs.get("error")

    success = EncreTaskManager.update_task(
        task_id=task_id,
        status=status,
        result=result,
        error=error,
    )
    if success:
        return f"Task {task_id} updated successfully."
    return f"Error: Task not found: {task_id}"


EncreTaskUpdateTool = build_tool(
    name="task_update",
    description=(
        "Update the status and/or result/error of an existing task.\n\n"
        "WHEN to use: a sub-agent or workflow has produced a result to record; "
        "a task needs to move from 'running' to 'completed' or 'failed'.\n"
        "WHEN NOT to use: to stop a running task at the user's request use "
        "task_stop (it sets the cancelled state with a clear reason); to read "
        "task state use task_get/task_output.\n"
        "TIPS: set 'result' when transitioning to 'completed'; set 'error' "
        "when transitioning to 'failed' so callers can diagnose the failure.\n"
        "PITFALLS: this is a low-level mutation -- prefer task_stop for "
        "cancellation since it guards against double-stopping."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The unique ID of the task to update."},
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "failed", "killed"],
                "description": "New lifecycle status to set on the task.",
            },
            "result": {"type": "string", "description": "Task output/result to store. Populate this when marking a task 'completed'."},
            "error": {"type": "string", "description": "Error message describing why the task failed. Populate this when marking a task 'failed'."},
        },
        "required": ["task_id"],
    },
    execute=_task_update_execute,
    intents=["general", "coding", "data", "research"],
    category="task",
    semantic_type="write",
    is_destructive=True,
)
