#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

import json
from typing import Any, ClassVar

from yim.tools.base import YmiTool


class YmiCronDeleteTool(YmiTool):
    name: ClassVar[str] = "cron_delete"
    description: ClassVar[str] = "Cancel/delete a previously scheduled cron job by its ID"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The ID of the scheduled job to cancel",
            },
        },
        "required": ["job_id"],
    }
    intents: ClassVar[list[str]] = ["system"]

    _scheduler: Any = None  # Set by agent during initialization

    @classmethod
    def set_scheduler(cls, scheduler: Any) -> None:
        cls._scheduler = scheduler

    async def execute(self, **kwargs: Any) -> str:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return "Error: job_id is required."

        if self._scheduler is None:
            return f"Job '{job_id}' cancellation noted. (Scheduler not available — no active jobs to cancel.)"

        cancelled = self._scheduler.cancel(job_id)
        if cancelled:
            return json.dumps({"status": "cancelled", "job_id": job_id}, ensure_ascii=False)
        return json.dumps({"status": "not_found", "job_id": job_id,
                          "message": "No such job or already cancelled"}, ensure_ascii=False)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
