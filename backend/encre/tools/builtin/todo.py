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



from typing import Any

from encre.tools.base import build_tool


# Ported verbatim from Claude Code's TodoWriteTool/prompt.ts (PROMPT), with the
# tool-name reference adapted to Encre's file_edit. Drives when/when-not to use
# the todo list and the task-state discipline.
_TODO_PROMPT = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

   **IMPORTANT**: Task descriptions must have two forms:
   - content: The imperative form describing what needs to be done (e.g., "Run tests", "Build the project")
   - activeForm: The present continuous form shown during execution (e.g., "Running tests", "Building the project")

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Exactly ONE task must be in_progress at any time (not less, not more)
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - Tests are failing
     - Implementation is partial
     - You encountered unresolved errors
     - You couldn't find necessary files or dependencies

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names
   - Always provide both forms:
     - content: "Fix authentication bug"
     - activeForm: "Fixing authentication bug"

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully."""


async def _todo_execute(**kwargs: Any) -> str:
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
        status = item.get("status", "pending")
        status_icon = {"pending": "○", "in_progress": "●", "completed": "✓"}
        icon = status_icon.get(status, "○")
        priority_flag = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
        flag = priority_flag.get(item.get("priority", "medium"), "\U0001f7e1")
        # Show the present-continuous form while a task is in progress (CC parity).
        label = item.get("activeForm") if status == "in_progress" else item.get("content")
        lines.append(f"{icon} {flag} {label or item.get('content', '')}")

    if not lines:
        return "No todo items."

    return "\n".join(lines)


EncreTodoTool = build_tool(
    name="todo",
    description=_TODO_PROMPT,
    input_schema={
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Imperative form of the task (e.g. \"Run tests\")"},
                        "activeForm": {"type": "string", "description": "Present continuous form shown during execution (e.g. \"Running tests\")"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["content", "status", "activeForm"],
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
    },
    execute=_todo_execute,
    intents=["general", "coding", "data", "research"],
    is_concurrency_safe=lambda _: True,
)
