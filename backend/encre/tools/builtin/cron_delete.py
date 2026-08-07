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

"""Module: builtin/cron_delete.py

Cron delete implementation for the Encre tool system.
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


async def _cron_delete_execute(**kwargs: Any) -> str:
    """Cron delete execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    job_id = kwargs.get("job_id", "")
    if not job_id:
        return "Error: job_id is required."

    if _scheduler is None:
        return f"Job '{job_id}' cancellation noted. (Scheduler not available -- no active jobs to cancel.)"

    cancelled = _scheduler.cancel(job_id)
    if cancelled:
        return json.dumps({"status": "cancelled", "job_id": job_id}, ensure_ascii=False)
    return json.dumps({"status": "not_found", "job_id": job_id,
                      "message": "No such job or already cancelled"}, ensure_ascii=False)


EncreCronDeleteTool = build_tool(
    name="cron_delete",
    description=(
        "Cancel or delete a previously scheduled cron job by its ID so it stops "
        "firing. "
        "Use this when a scheduled task is no longer needed or was created by "
        "mistake. "
        "Do NOT use this to pause a job temporarily (reschedule with cron_create "
        "instead) or to inspect jobs (use cron_list). "
        "Tips: obtain the `job_id` from cron_list before deleting. "
        "Pitfalls: deletion cannot be undone — a deleted recurring job must be "
        "recreated with cron_create if needed again; deleting a non-existent job "
        "returns a 'not_found' status."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Unique identifier of the scheduled job to cancel; obtain it via cron_list.",
            },
        },
        "required": ["job_id"],
    },
    execute=_cron_delete_execute,
    intents=["system"],
    is_concurrency_safe=lambda _: True,
    category="task",
    semantic_type="write",
    is_destructive=True,
)
# Backward-compat: keep ``.set_scheduler()`` callable on the tool object.
EncreCronDeleteTool.set_scheduler = set_scheduler
