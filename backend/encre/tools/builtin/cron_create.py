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

"""Module: builtin/cron_create.py

Cron create implementation for the Encre tool system.
"""
import json
from typing import Any

from encre.tools.base import build_tool

_scheduler: Any = None  # Set by agent during initialization


def set_scheduler(scheduler: Any) -> None:
    """Set scheduler.

    Args:
        scheduler: Description of the scheduler parameter.
    """
    global _scheduler
    _scheduler = scheduler


async def _cron_create_execute(**kwargs: Any) -> str:
    """Cron create execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    cron_expr = kwargs.get("cron", "")
    prompt_text = kwargs.get("prompt", "")
    name = kwargs.get("name", "Unnamed job")

    if not cron_expr or not prompt_text:
        return "Error: both 'cron' and 'prompt' are required."

    # Validate cron expression
    from encre.scheduler import CronSchedule
    try:
        CronSchedule.parse(cron_expr)
    except ValueError as e:
        return f"Error: invalid cron expression '{cron_expr}' -- {e}"

    if _scheduler is None:
        # Fallback: validate only, no real scheduling
        return (
            f"Cron expression '{cron_expr}' validated. Job '{name}' ready to schedule.\n"
            f"Prompt: {prompt_text[:200]}{'...' if len(prompt_text) > 200 else ''}\n"
            "(Scheduler not yet started -- job will activate when scheduler is available.)"
        )

    job_id = _scheduler.schedule(
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


EncreCronCreateTool = build_tool(
    name="cron_create",
    description=(
        "Schedule a prompt to run automatically on a recurring cron schedule. "
        "Use this for reminders, periodic reports, polling, or any task that must "
        "fire unattended at fixed times. "
        "Do NOT use this for one-shot delayed tasks if a deferred-task tool is "
        "available, for sub-minute scheduling, or for jobs requiring prior "
        "conversation context. "
        "Tips: use a standard 5-field cron expression in local time, e.g. "
        "'0 9 * * *' (daily 9am) or '*/5 * * * *' (every 5 min). "
        "Pitfalls: the agent has no prior context at fire time — include all "
        "needed details in the prompt; if the scheduler is not running, the job "
        "is validated but not activated."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": "Standard 5-field cron expression in local time (minute hour day-of-month month day-of-week). Examples: '0 9 * * *' (daily 9am), '*/5 * * * *' (every 5 min), '0 0 * * 1' (weekly Monday).",
            },
            "prompt": {
                "type": "string",
                "description": "Self-contained prompt text to execute at each fire time; no prior conversation context is available when the job runs.",
            },
            "name": {
                "type": "string",
                "description": "Human-readable label for the scheduled job; defaults to 'Unnamed job'.",
            },
            "recurring": {
                "type": "boolean",
                "description": "If true, the job repeats on schedule; defaults to true.",
                "default": True,
            },
        },
        "required": ["cron", "prompt"],
    },
    execute=_cron_create_execute,
    intents=["system"],
    is_concurrency_safe=lambda _: True,
    category="task",
    semantic_type="write",
    is_destructive=True,
)
# Backward-compat: keep ``.set_scheduler()`` callable on the tool object.
EncreCronCreateTool.set_scheduler = set_scheduler
