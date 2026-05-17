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

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

from yim.config import YmiConfig
from yim.logging_config import get_logger

logger = get_logger("yim.scheduler")


class ScheduleType(Enum):
    ONE_SHOT = auto()
    RECURRING = auto()


class JobState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class CronSchedule:
    """5-field cron expression: minute hour dom month dow"""
    minute: str = "*"
    hour: str = "*"
    day_of_month: str = "*"
    month: str = "*"
    day_of_week: str = "*"

    @classmethod
    def parse(cls, expr: str) -> "CronSchedule":
        fields = expr.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expr}. Expected 5 fields.")
        return cls(*fields)

    def to_expression(self) -> str:
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month} {self.day_of_week}"

    def _match_field(self, value: int, field: str) -> bool:
        """Check if a numeric value matches a cron field."""
        for part in field.split(","):
            part = part.strip()
            if part == "*":
                return True
            if "/" in part:
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    if value % step == 0:
                        return True
                else:
                    base = int(base)
                    if value >= base and (value - base) % step == 0:
                        return True
            elif "-" in part:
                lo_s, hi_s = part.split("-")
                lo, hi = int(lo_s), int(hi_s)
                if lo <= value <= hi:
                    return True
            else:
                try:
                    if int(part) == value:
                        return True
                except ValueError:
                    pass
        return False

    @staticmethod
    def _normalize_dow(field: str) -> str:
        """Convert named days to numbers. Cron: 0=Sun, 1=Mon, ..., 6=Sat, 7=Sun."""
        _DOW_MAP = {"sun": "0", "mon": "1", "tue": "2", "wed": "3",
                     "thu": "4", "fri": "5", "sat": "6"}
        result = field.lower()
        for name, num in _DOW_MAP.items():
            result = result.replace(name, num)
        return result

    @staticmethod
    def _weekday_cron(year: int, month: int, day: int) -> int:
        """Return cron-style weekday (0=Sun, 1=Mon, ..., 6=Sat)."""
        from datetime import datetime
        py_wday = datetime(year, month, day).weekday()  # 0=Mon, 6=Sun
        return (py_wday + 1) % 7  # Convert to 0=Sun

    def next_fire(self, from_ts: float | None = None) -> float | None:
        """Calculate the next fire time from the given timestamp.
        Returns None if no match within the next year.
        """
        if from_ts is None:
            from_ts = time.time()
        t = time.localtime(from_ts)
        current = list(t[:5])  # (year, month, day, hour, min)
        current[4] += 1  # increment minute

        # Pre-normalize DOW field — convert named days to numbers once
        normalized_dow = self._normalize_dow(self.day_of_week)

        max_iter = 525600  # 1 year in minutes
        for _ in range(max_iter):
            year, month, day, hour, minute = current
            # Normalize
            if minute >= 60:
                minute = 0
                hour += 1
            if hour >= 24:
                hour = 0
                day += 1
            days_in_month = [31, 29 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 28,
                             31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            if day > days_in_month[month - 1]:
                day = 1
                month += 1
            if month > 12:
                month = 1
                year += 1

            current = [year, month, day, hour, minute]

            if (self._match_field(minute, self.minute) and
                self._match_field(hour, self.hour) and
                self._match_field(day, self.day_of_month) and
                self._match_field(month, self.month) and
                self._match_field(
                    self._weekday_cron(year, month, day),
                    normalized_dow,
                )):
                from datetime import datetime
                dt = datetime(year, month, day, hour, minute)
                return dt.timestamp()

            current[4] += 1  # next minute
        return None


@dataclass
class ScheduledJob:
    """A job scheduled for future execution."""
    id: str
    name: str
    prompt: str
    schedule_type: ScheduleType
    cron: CronSchedule | None = None
    fire_at: float | None = None  # absolute timestamp for one-shot
    state: JobState = JobState.PENDING
    created_at: float = field(default_factory=time.time)
    last_fired: float | None = None
    last_result: str | None = None
    fail_count: int = 0
    max_failures: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    _agent_config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "schedule_type": self.schedule_type.name,
            "cron": self.cron.to_expression() if self.cron else None,
            "fire_at": self.fire_at,
            "state": self.state.name,
            "created_at": self.created_at,
            "last_fired": self.last_fired,
            "last_result": self.last_result,
            "fail_count": self.fail_count,
            "max_failures": self.max_failures,
            "metadata": self.metadata,
            "agent_config": self._agent_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledJob":
        job = cls(
            id=data["id"],
            name=data["name"],
            prompt=data["prompt"],
            schedule_type=ScheduleType[data["schedule_type"]],
            cron=CronSchedule.parse(data["cron"]) if data.get("cron") else None,
            fire_at=data.get("fire_at"),
            state=JobState[data.get("state", "PENDING")],
            created_at=data.get("created_at", 0),
            last_fired=data.get("last_fired"),
            last_result=data.get("last_result"),
            fail_count=data.get("fail_count", 0),
            max_failures=data.get("max_failures", 3),
            metadata=data.get("metadata", {}),
        )
        job._agent_config = data.get("agent_config")
        return job


class YmiScheduler:
    """Persistent cron-based job scheduler for autonomous agent workflows.

    Jobs survive restarts when `durable_path` is set.
    Supports one-shot reminders and recurring cron jobs.

    Usage:
        sched = YmiScheduler()  # persists to ~/.dunimd/yim/jobs.json
        job_id = sched.schedule(
            name="daily PR review",
            prompt="Review all open PRs and report issues",
            cron="0 9 * * 1-5",
        )
        await sched.start(agent)  # starts background polling
    """

    def __init__(
        self,
        durable_path: str = "",
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        if not durable_path:
            from yim.config import get_data_dir
            durable_path = str(get_data_dir() / "jobs.json")
        self._durable_path = Path(durable_path)
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._agent_factory: Callable[[], Any] | None = None
        self._on_complete: Callable[[ScheduledJob], None] | None = None

        self._load()

    def schedule(
        self,
        name: str,
        prompt: str,
        cron: str = "",
        fire_at: float | None = None,
        max_failures: int = 3,
        metadata: dict[str, Any] | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> str:
        """Schedule a new job. Returns the job ID."""
        import uuid
        job_id = uuid.uuid4().hex[:12]

        if cron:
            schedule_type = ScheduleType.RECURRING
            cron_obj = CronSchedule.parse(cron)
        elif fire_at:
            schedule_type = ScheduleType.ONE_SHOT
            cron_obj = None
        else:
            # Default: fire immediately once
            schedule_type = ScheduleType.ONE_SHOT
            cron_obj = None
            fire_at = time.time() + 1

        job = ScheduledJob(
            id=job_id,
            name=name,
            prompt=prompt,
            schedule_type=schedule_type,
            cron=cron_obj,
            fire_at=fire_at,
            max_failures=max_failures,
            metadata=metadata or {},
        )
        job._agent_config = agent_config
        self._jobs[job_id] = job
        if self._durable_path:
            self._save()
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or recurring job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.state = JobState.CANCELLED
        if self._durable_path:
            self._save()
        return True

    def cancel_all(self) -> int:
        """Cancel all jobs. Returns count of cancelled jobs."""
        count = 0
        for job in self._jobs.values():
            if job.state in (JobState.PENDING, JobState.RUNNING):
                job.state = JobState.CANCELLED
                count += 1
        if self._durable_path and count > 0:
            self._save()
        return count

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self, state: JobState | None = None) -> list[ScheduledJob]:
        jobs = list(self._jobs.values())
        if state is not None:
            jobs = [j for j in jobs if j.state == state]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def on_job_complete(self, callback: Callable[[ScheduledJob], None]) -> None:
        """Register a callback for job completion."""
        self._on_complete = callback

    async def start(self, agent_factory: Callable[[], Any]) -> None:
        """Start the background scheduler loop.

        Args:
            agent_factory: A callable that returns a fresh YmiAgent instance.
                          Called for each job execution.
        """
        self._agent_factory = agent_factory
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        """Main scheduler loop — polls for due jobs."""
        while self._running:
            now = time.time()
            due_jobs: list[ScheduledJob] = []

            for job in self._jobs.values():
                if job.state not in (JobState.PENDING,):
                    continue
                if job.schedule_type == ScheduleType.ONE_SHOT:
                    if job.fire_at and now >= job.fire_at:
                        due_jobs.append(job)
                elif job.schedule_type == ScheduleType.RECURRING:
                    if job.cron:
                        if job.last_fired is None:
                            next_fire = job.cron.next_fire(now - 60)
                        else:
                            next_fire = job.cron.next_fire(job.last_fired)
                        if next_fire and now >= next_fire:
                            due_jobs.append(job)

            for job in due_jobs:
                await self._execute_job(job)

            if self._durable_path:
                self._save()

            await asyncio.sleep(self._poll_interval)

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a single scheduled job."""
        if self._agent_factory is None:
            return

        job.state = JobState.RUNNING
        job.last_fired = time.time()

        try:
            agent = self._agent_factory()
            result_parts: list[str] = []
            async for event in agent.run(job.prompt):
                from yim.utils.types import TextDelta, Finish
                if hasattr(event, "text"):
                    result_parts.append(event.text)
                elif isinstance(event, Finish):
                    pass

            job.last_result = "".join(result_parts)[:2000]
            job.state = JobState.COMPLETED
            job.fail_count = 0

        except Exception as e:
            job.fail_count += 1
            job.last_result = f"Error: {e}"
            if job.fail_count >= job.max_failures:
                job.state = JobState.FAILED
            else:
                job.state = JobState.PENDING  # retry next cycle

        if job.schedule_type == ScheduleType.ONE_SHOT:
            pass  # stays COMPLETED/FAILED

        if self._on_complete:
            self._on_complete(job)

    def _save(self) -> None:
        if not self._durable_path:
            return
        self._durable_path.parent.mkdir(parents=True, exist_ok=True)
        data = [j.to_dict() for j in self._jobs.values()]
        with open(self._durable_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self) -> None:
        if not self._durable_path or not self._durable_path.exists():
            return
        try:
            with open(self._durable_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                job = ScheduledJob.from_dict(item)
                self._jobs[job.id] = job
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse durable job store {self._durable_path}: {e}")
        except KeyError as e:
            logger.warning(f"Missing key in durable job store entry: {e}")
        except Exception as e:
            logger.error(f"Failed to load durable job store {self._durable_path}: {e}", exc_info=True)
