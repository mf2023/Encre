#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

import json
import time
from typing import Any, ClassVar

from yim.tools.base import YmiTool


class YmiCronListTool(YmiTool):
    name: ClassVar[str] = "cron_list"
    description: ClassVar[str] = "List all scheduled cron jobs"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    intents: ClassVar[list[str]] = ["system"]

    _scheduler: Any = None  # Set by agent during initialization

    @classmethod
    def set_scheduler(cls, scheduler: Any) -> None:
        cls._scheduler = scheduler

    async def execute(self, **kwargs: Any) -> str:
        if self._scheduler is None:
            return json.dumps({"jobs": [], "message": "Scheduler not available."}, ensure_ascii=False)

        jobs = self._scheduler.list_jobs()
        if not jobs:
            return json.dumps({"jobs": [], "message": "No scheduled jobs."}, ensure_ascii=False)

        now = time.time()
        result = []
        for job in jobs:
            entry = {
                "id": job.id,
                "name": job.name,
                "state": job.state.name,
                "schedule_type": job.schedule_type.name,
                "prompt_preview": job.prompt[:100] + "..." if len(job.prompt) > 100 else job.prompt,
                "created_at": job.created_at,
            }
            if job.cron:
                entry["cron"] = job.cron.to_expression()
                next_fire = job.cron.next_fire(now) if job.state.name == "PENDING" else None
                if next_fire:
                    entry["next_fire"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(next_fire))
            elif job.fire_at:
                entry["fire_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.fire_at))
            if job.last_fired:
                entry["last_fired"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.last_fired))
            if job.fail_count > 0:
                entry["fail_count"] = job.fail_count
            result.append(entry)

        return json.dumps({"jobs": result, "total": len(result)}, ensure_ascii=False, indent=2)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return True
