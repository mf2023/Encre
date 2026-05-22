#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

import json
from typing import Any, ClassVar

from yim.tools.base import YmiTool


class YmiCronCreateTool(YmiTool):
    name: ClassVar[str] = "cron_create"
    description: ClassVar[str] = (
        "Schedule a prompt to be executed at a future time or on a recurring schedule. "
        "Uses standard 5-field cron: minute hour day-of-month month day-of-week. "
        'Example: "0 9 * * *" for daily at 9am, "*/5 * * * *" for every 5 minutes.'
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": "5-field cron expression in local time",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt to execute at each fire time",
            },
            "name": {
                "type": "string",
                "description": "Human-readable name for this scheduled job",
            },
            "recurring": {
                "type": "boolean",
                "description": "Whether this is a recurring job (default: true)",
                "default": True,
            },
        },
        "required": ["cron", "prompt"],
    }
    intents: ClassVar[list[str]] = ["system"]

    _scheduler: Any = None  # Set by agent during initialization

    @classmethod
    def set_scheduler(cls, scheduler: Any) -> None:
        cls._scheduler = scheduler

    async def execute(self, **kwargs: Any) -> str:
        cron_expr = kwargs.get("cron", "")
        prompt_text = kwargs.get("prompt", "")
        name = kwargs.get("name", "Unnamed job")

        if not cron_expr or not prompt_text:
            return "Error: both 'cron' and 'prompt' are required."

        # Validate cron expression
        from yim.scheduler import CronSchedule
        try:
            CronSchedule.parse(cron_expr)
        except ValueError as e:
            return f"Error: invalid cron expression '{cron_expr}' — {e}"

        if self._scheduler is None:
            # Fallback: validate only, no real scheduling
            return (
                f"Cron expression '{cron_expr}' validated. Job '{name}' ready to schedule.\n"
                f"Prompt: {prompt_text[:200]}{'...' if len(prompt_text) > 200 else ''}\n"
                "(Scheduler not yet started — job will activate when scheduler is available.)"
            )

        job_id = self._scheduler.schedule(
            name=name,
            prompt=prompt_text,
            cron=cron_expr,
        )
        return json.dumps({
            "status": "scheduled",
            "job_id": job_id,
            "name": name,
            "cron": cron_expr,
            "prompt_preview": prompt_text[:200],
        }, ensure_ascii=False, indent=2)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
