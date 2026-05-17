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

from yim.task.manager import YmiTaskManager
from yim.tools.base import YmiTool


class YmiTaskUpdateTool(YmiTool):
    name: ClassVar[str] = "task_update"
    description: ClassVar[str] = "Update the status or result of a task"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task ID to update"},
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "failed", "killed"],
                "description": "New status",
            },
            "result": {"type": "string", "description": "Task result content"},
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["task_id"],
    }

    async def execute(self, **kwargs: Any) -> str:
        task_id = kwargs.get("task_id", "")
        status = kwargs.get("status")
        result = kwargs.get("result")
        error = kwargs.get("error")

        success = YmiTaskManager.update_task(
            task_id=task_id,
            status=status,
            result=result,
            error=error,
        )
        if success:
            return f"Task {task_id} updated successfully."
        return f"Error: Task not found: {task_id}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False