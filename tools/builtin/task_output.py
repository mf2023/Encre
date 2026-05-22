#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

import asyncio
import json
from typing import Any, ClassVar

from yim.tools.base import YmiTool
from yim.utils.types import TaskStatus


class YmiTaskOutputTool(YmiTool):
    name: ClassVar[str] = "task_output"
    description: ClassVar[str] = (
        "Retrieve output from a running or completed background task. "
        "Can block waiting for completion, or return current status."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The ID of the task to get output from",
            },
            "block": {
                "type": "boolean",
                "description": "Wait for task completion (default: true)",
                "default": True,
            },
            "timeout": {
                "type": "integer",
                "description": "Max wait time in milliseconds (default: 30000)",
                "default": 30000,
            },
        },
        "required": ["task_id"],
    }
    intents: ClassVar[list[str]] = ["general", "coding", "data"]

    async def execute(self, **kwargs: Any) -> str:
        from yim.task.manager import YmiTaskManager

        task_id = kwargs.get("task_id", "")
        block = kwargs.get("block", True)
        timeout_ms = kwargs.get("timeout", 30000)

        if not task_id:
            return "Error: task_id is required."

        task = YmiTaskManager.get_task(task_id)
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
                task = YmiTaskManager.get_task(task_id)
                if task is None:
                    return f"Error: task '{task_id}' disappeared."

        status_icon = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
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

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return True
