#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

from typing import Any, ClassVar

from yim.tools.base import YmiTool
from yim.utils.types import TaskStatus


class YmiTaskStopTool(YmiTool):
    name: ClassVar[str] = "task_stop"
    description: ClassVar[str] = "Stop a running background task by its ID"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The ID of the background task to stop",
            },
        },
        "required": ["task_id"],
    }
    intents: ClassVar[list[str]] = ["general", "coding", "data"]

    async def execute(self, **kwargs: Any) -> str:
        from yim.task.manager import YmiTaskManager

        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "Error: task_id is required."

        task = YmiTaskManager.get_task(task_id)
        if task is None:
            return f"Error: task '{task_id}' not found."

        if task.status == TaskStatus.COMPLETED:
            return f"Task '{task_id}' already completed."
        if task.status == TaskStatus.CANCELLED:
            return f"Task '{task_id}' already cancelled."

        YmiTaskManager.update_task(task_id, status=TaskStatus.CANCELLED, error="Stopped by user request")
        return f"Task '{task_id}' stopped."

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
