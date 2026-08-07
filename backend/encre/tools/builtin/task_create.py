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

"""Module: builtin/task_create.py

Task create implementation for the Encre tool system.
"""
from typing import Any

from encre.task.manager import EncreTaskManager
from encre.tools.base import build_tool


async def _task_create_execute(**kwargs: Any) -> str:
    """Task create execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    name = kwargs.get("name", "")
    description = kwargs.get("description", "")
    task_type = kwargs.get("task_type", "bash")
    prompt = kwargs.get("prompt", "")
    parent_id = kwargs.get("parent_id")

    task_id = EncreTaskManager.create_task(
        name=name,
        description=description,
        task_type=task_type,
        prompt=prompt,
        parent_id=parent_id,
    )
    return f"Task created: {task_id}"


EncreTaskCreateTool = build_tool(
    name="task_create",
    description=(
        "Create a new background sub-task (bash command, delegated agent, or "
        "workflow) that runs independently and can be polled later.\n\n"
        "WHEN to use: long-running work that would block the main conversation "
        "(builds, test suites, research delegations); parallelizable "
        "sub-problems you want to fan out to sub-agents.\n"
        "WHEN NOT to use: for short synchronous actions just use the relevant "
        "tool directly; for the model's own task tracking use the todo tool.\n"
        "TIPS: give the task a descriptive name and prompt so a sub-agent "
        "knows exactly what to do; set parent_id when spawning from another "
        "task to keep the hierarchy navigable.\n"
        "PITFALLS: returns immediately with a task ID -- you must poll with "
        "task_output or task_get to retrieve the result."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short human-readable name for the task (shown in task listings)."},
            "description": {"type": "string", "description": "Longer description of what the task should accomplish."},
            "task_type": {
                "type": "string",
                "enum": ["bash", "agent", "workflow"],
                "description": "Execution backend: 'bash' runs a shell command, 'agent' delegates to a sub-agent LLM, 'workflow' runs a defined multi-step workflow.",
            },
            "prompt": {"type": "string", "description": "The instructions/command for the task: shell command for bash, the natural-language brief for agent, or the workflow spec for workflow."},
            "parent_id": {"type": "string", "description": "Optional ID of a parent task to nest this one under, building a task hierarchy."},
        },
        "required": ["name", "task_type", "prompt"],
    },
    execute=_task_create_execute,
    intents=["general", "coding", "data", "research"],
    category="task",
    semantic_type="write",
    is_destructive=True,
)
