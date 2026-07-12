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

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from encre.crypto import decrypt, encrypt
from encre.logging_config import get_logger

logger = get_logger("encre.scheduler")


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
                base_str, step_str = part.split("/")
                step = int(step_str)
                if base_str == "*":
                    if value % step == 0:
                        return True
                else:
                    base = int(base_str)
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
        _dow_map = {"sun": "0", "mon": "1", "tue": "2", "wed": "3",
                     "thu": "4", "fri": "5", "sat": "6"}
        result = field.lower()
        for name, num in _dow_map.items():
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

        # Pre-normalize DOW field -- convert named days to numbers once
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
class JobExecution:
    """A single execution record for a job.

    The execution itself lives as a regular sub-agent session under
    ``<data_dir>/sub_agents/<session_id>/`` -- exactly the same place
    where the in-chat ``agent`` tool stores its sub-agent sessions. The
    scheduler only keeps a lightweight reference here so the
    automation history list stays cheap to render. The full messages
    snapshot must be loaded from the sub-agent session on demand via
    :func:`EncreSession.load_from_dir`.
    """
    time: float
    state: str
    result: str
    session_id: str | None = None
    fail_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "state": self.state,
            "result": self.result,
            "session_id": self.session_id,
            "fail_count": self.fail_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobExecution":
        return cls(
            time=d["time"],
            state=d["state"],
            result=d.get("result", ""),
            session_id=d.get("session_id"),
            fail_count=d.get("fail_count", 0),
        )


@dataclass
class ScheduledJob:
    """A job scheduled for future execution.

    Supports both simple prompt-based execution and DAG workflow
    execution.  When ``dag_definition`` is set, the scheduler uses
    :class:`encre.dag.executor.DagExecutor` to run the workflow
    instead of submitting the prompt directly to the agent.
    """
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
    suspended: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    model_index: int = -1
    session_id: str | None = None
    executions: list[JobExecution] = field(default_factory=list)
    _agent_config: dict[str, Any] | None = None
    # DAG workflow fields -- when set, the job executes a multi-step
    # DAG instead of a single prompt.  ``dag_definition`` is a JSON
    # string compatible with ``EncreTaskPlanner.plan_from_json()``.
    dag_definition: str = ""
    push_gateways: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "schedule_type": self.schedule_type.name,
            "cron": self.cron.to_expression() if self.cron else None,
            "fire_at": self.fire_at,
            "state": self.state.name,
            "suspended": self.suspended,
            "created_at": self.created_at,
            "last_fired": self.last_fired,
            "last_result": self.last_result,
            "fail_count": self.fail_count,
            "max_failures": self.max_failures,
            "metadata": self.metadata,
            "model_index": self.model_index,
            "session_id": self.session_id,
            "executions": [e.to_dict() for e in self.executions],
            "agent_config": self._agent_config,
            "dag_definition": self.dag_definition,
            "push_gateways": list(self.push_gateways),
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
            suspended=data.get("suspended", False),
            metadata=data.get("metadata", {}),
            model_index=data.get("model_index", -1),
            dag_definition=data.get("dag_definition", ""),
            push_gateways=data.get("push_gateways", []),
        )
        job.session_id = data.get("session_id")
        job._agent_config = data.get("agent_config")
        # Restore execution history (empty list for older saved jobs)
        execs = data.get("executions") or []
        job.executions = [JobExecution.from_dict(e) for e in execs]
        return job


class EncreScheduler:
    """Persistent cron-based job scheduler for autonomous agent workflows.

    Jobs survive restarts when `durable_path` is set.
    Supports one-shot reminders and recurring cron jobs.

    Usage:
        sched = EncreScheduler()  # persists to ~/.dunimd/encre/jobs.json
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
            from encre.config import get_data_dir
            durable_path = str(get_data_dir() / "jobs.json")
        self._durable_path = Path(durable_path)
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._agent_factory: Callable[[dict[str, Any] | None], Any] | None = None
        self._on_complete: Callable[[ScheduledJob], None] | None = None
        self._on_progress: Callable[[ScheduledJob, str, dict[str, Any]], Awaitable[None]] | None = None

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
        model_index: int = -1,
        push_gateways: list[str] | None = None,
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
            model_index=model_index,
            push_gateways=push_gateways or [],
        )
        job._agent_config = agent_config
        self._jobs[job_id] = job
        if self._durable_path:
            self._save()
        return job_id

    def schedule_workflow(
        self,
        name: str,
        dag_definition: str,
        cron: str = "",
        fire_at: float | None = None,
        max_failures: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Schedule a DAG workflow job. Returns the job ID.

        Args:
            name: Human-readable name for this workflow.
            dag_definition: JSON string compatible with
                ``EncreTaskPlanner.plan_from_json()``.  Contains
                ``tasks``, ``entry_tasks``, and ``exit_tasks``.
            cron: Optional cron expression for recurring execution.
            fire_at: Optional absolute timestamp for one-shot execution.
            max_failures: Maximum consecutive failures before suspension.
            metadata: Optional metadata dict.

        Returns:
            The newly-created job ID.
        """
        import uuid
        job_id = uuid.uuid4().hex[:12]

        if cron:
            schedule_type = ScheduleType.RECURRING
            cron_obj = CronSchedule.parse(cron)
        elif fire_at:
            schedule_type = ScheduleType.ONE_SHOT
            cron_obj = None
        else:
            schedule_type = ScheduleType.ONE_SHOT
            cron_obj = None
            fire_at = time.time() + 1

        job = ScheduledJob(
            id=job_id,
            name=name,
            prompt="",  # DAG workflows do not use the prompt directly
            schedule_type=schedule_type,
            cron=cron_obj,
            fire_at=fire_at,
            max_failures=max_failures,
            metadata=metadata or {},
            dag_definition=dag_definition,
        )
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

    def toggle_job(self, job_id: str) -> bool:
        """Suspend or resume a job. Returns True if now running (resumed), False if suspended."""
        job = self._jobs.get(job_id)
        if job is None or job.state == JobState.CANCELLED:
            return False
        job.suspended = not job.suspended
        if self._durable_path:
            self._save()
        return not job.suspended

    def update_job(self, job_id: str, *, name: str, prompt: str, cron: str, tag: str, model_index: int = -1, agent_config: dict[str, Any] | None = None, push_gateways: list[str] | None = None) -> bool:
        """Update a job's properties. Returns True on success."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.name = name
        job.prompt = prompt
        job.cron = CronSchedule.parse(cron) if cron else None
        job.metadata["tag"] = tag
        job.model_index = model_index
        job._agent_config = agent_config
        if push_gateways is not None:
            job.push_gateways = push_gateways
        if self._durable_path:
            self._save()
        return True

    def delete_job(self, job_id: str) -> bool:
        """Remove a job entirely. Returns True on success."""
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        if self._durable_path:
            self._save()
        return True

    def delete_job_execution_by_session_id(self, session_id: str) -> bool:
        """Delete any execution record with the given session_id across all jobs.

        Returns True if an execution was found and removed.
        """
        for job in self._jobs.values():
            for i, exec_entry in enumerate(job.executions):
                if exec_entry.session_id == session_id:
                    del job.executions[i]
                    if self._durable_path:
                        self._save()
                    return True
        return False

    def delete_job_execution(self, entry_id: str) -> str | None:
        """Delete a single execution record by entry_id (format: job_id_timestamp).

        Returns the session_id of the deleted execution if found, None otherwise.
        The caller should clean up the sub-agent session directory from disk.
        """
        try:
            job_id, time_str = entry_id.rsplit("_", 1)
            exec_time = float(time_str)
        except (ValueError, IndexError):
            return None
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for i, exec_entry in enumerate(job.executions):
            if abs(exec_entry.time - exec_time) < 0.001:
                sid = exec_entry.session_id
                del job.executions[i]
                if self._durable_path:
                    self._save()
                return sid
        return None

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

    def on_job_progress(self, callback: Callable[[ScheduledJob, str, dict[str, Any]], Awaitable[None]]) -> None:
        """Register an async callback for real-time job execution progress.

        Called for each streaming event during ``agent.run()`` with
        the job, event type name (e.g. ``"text_delta"``), and event data dict.
        The callback is awaited so events are broadcast in order.
        """
        self._on_progress = callback

    async def start(self, agent_factory: Callable[[dict[str, Any] | None], Any]) -> None:
        """Start the background scheduler loop.

        Args:
            agent_factory: A callable(config_dict) that returns a fresh EncreAgent instance.
                          Called for each job execution with the job's stored agent_config.
        """
        self._agent_factory = agent_factory
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        """Main scheduler loop -- polls for due jobs."""
        while self._running:
            now = time.time()
            due_jobs: list[ScheduledJob] = []

            for job in self._jobs.values():
                if job.state not in (JobState.PENDING,):
                    continue
                if job.suspended:
                    continue
                if job.schedule_type == ScheduleType.ONE_SHOT:
                    if job.fire_at and now >= job.fire_at:
                        due_jobs.append(job)
                elif job.schedule_type == ScheduleType.RECURRING and job.cron:
                    if job.last_fired is None:  # noqa: SIM108
                        # First time the scheduler sees this recurring job after
                        # creation or restart: only consider future fire times so
                        # the job does not execute immediately on application
                        # startup just because its creation time is in the past.
                        next_fire = job.cron.next_fire(now)
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
        """Execute a single scheduled job.

        Every job execution is ALWAYS a sub-agent -- the same ``agent``
        tool path used by the main conversation. The parent ``EncreAgent``
        built by ``agent_factory`` is just a config/transport holder;
        the actual work is delegated to :meth:`EncreLoop._run_sub_agent`,
        which:

        * creates a fresh ``EncreAgent`` (depth 1),
        * tags it with ``channel = "sub_agent"``,
        * persists it under ``<data_dir>/sub_agents/<session_id>/``,
        * returns ``{"content", "messages", "session_id"}``.

        DAG jobs follow the same rule: each node is run via
        :meth:`EncreLoop._run_sub_agent` and produces its own sub-agent
        session.
        """
        if self._agent_factory is None:
            return

        job.state = JobState.RUNNING
        job.last_fired = time.time()

        # Lightweight execution record. The full transcript is owned by
        # the sub-agent session that _run_sub_agent will create.
        exec_entry = JobExecution(
            time=job.last_fired,
            state="RUNNING",
            result="",
            session_id=None,
            fail_count=0,
        )
        job.executions.append(exec_entry)

        # Parent agent is a transport/config holder only. _run_sub_agent
        # will create a fresh sub-EncreAgent internally.
        parent_agent = self._agent_factory(job._agent_config)

        # Notify frontend that execution has started. session_id is
        # filled in once the sub-agent is created.
        if self._on_progress:
            try:
                await self._on_progress(job, "start", {
                    "id": job.id,
                    "name": job.name,
                    "prompt": job.prompt,
                    "session_id": None,
                })
            except Exception:
                logger.warning("[scheduler] progress callback failed for 'start' event", exc_info=True)

        # Build an event translator that turns raw AgentEvents into the
        # existing automation_stream_event wire format. This is the only
        # place that knows the wire format -- everything else speaks the
        # sub-agent protocol.
        async def _translate_event(event: Any) -> None:
            from encre.utils.types import (
                TextDelta,
                ThinkingDelta,
                ToolCallDelta,
                ToolCallEnd,
                ToolCallStart,
                ToolProgress,
                ToolResult,
            )
            event_data: dict[str, Any] = {}
            event_name = ""
            if isinstance(event, TextDelta):
                event_name = "text_delta"
                event_data = {"text": event.text}
            elif isinstance(event, ThinkingDelta):
                event_name = "thinking_delta"
                event_data = {"text": event.text}
            elif isinstance(event, ToolCallStart):
                event_name = "tool_call_start"
                event_data = {"id": event.id, "name": event.name}
            elif isinstance(event, ToolCallDelta):
                event_name = "tool_call_delta"
                event_data = {"id": event.id, "key": event.key, "value": event.value}
            elif isinstance(event, ToolCallEnd):
                event_name = "tool_call_end"
                event_data = {"id": event.id}
            elif isinstance(event, ToolProgress):
                event_name = "tool_progress"
                event_data = {
                    "id": event.id,
                    "tool_name": event.tool_name,
                    "status": event.status,
                    "sub_agent_messages": event.sub_agent_messages,
                }
            elif isinstance(event, ToolResult):
                event_name = "tool_result"
                content = event.content
                if len(content) > 100000:
                    content = content[:100000] + "\n... (truncated)"
                event_data = {
                    "id": event.id,
                    "content": content,
                    "is_error": event.is_error,
                    "sub_agent_messages": event.sub_agent_messages,
                }
            else:
                return
            if self._on_progress is not None:
                try:
                    await self._on_progress(job, event_name, event_data)
                except Exception:
                    logger.warning("[scheduler] progress callback failed for '%s'", event_name, exc_info=True)

        try:
            if job.dag_definition:
                # DAG path: each node is a sub-agent run.
                node_session_ids = await self._execute_dag_job(
                    job, parent_agent, _translate_event,
                )
                exec_entry.session_id = node_session_ids[0] if node_session_ids else None
                # The wrapper session is the first node; remaining nodes
                # are reachable from its context but are also listed
                # below for the history view.
                job.session_id = exec_entry.session_id
                if job.state == JobState.RUNNING:
                    job.state = JobState.COMPLETED
                    job.fail_count = 0
                    exec_entry.state = "COMPLETED"
                else:
                    exec_entry.state = "FAILED" if job.state == JobState.FAILED else "PENDING"
                exec_entry.result = (job.last_result or "")[:5000]
            else:
                # Non-DAG path: a single sub-agent run. The sub-agent
                # owns the session -- we just consume its return value.
                sub_result = await parent_agent.loop._run_sub_agent(
                    prompt=job.prompt,
                    system_prompt=None,
                    tool_policy="all",
                    progress_callback=None,
                    event_callback=_translate_event,
                )

                session_id = sub_result.get("session_id")
                exec_entry.session_id = session_id
                job.session_id = session_id

                final_content = sub_result.get("content") or ""
                job.last_result = final_content[:2000]
                job.state = JobState.COMPLETED
                job.fail_count = 0
                exec_entry.state = "COMPLETED"
                exec_entry.result = final_content[:5000]

        except Exception as e:
            logger.exception("[scheduler] job execution failed: %s", e)
            job.fail_count += 1
            job.last_result = f"Error: {e}"
            exec_entry.state = "FAILED" if job.fail_count >= job.max_failures else "PENDING"
            exec_entry.result = job.last_result
            exec_entry.fail_count = job.fail_count
            if job.fail_count >= job.max_failures:
                job.state = JobState.FAILED
            else:
                job.state = JobState.PENDING

        # Notify frontend that execution has finished
        if self._on_progress:
            try:
                await self._on_progress(job, "finish", {
                    "state": job.state.name,
                    "result": (job.last_result or "")[:2000],
                })
            except Exception:
                logger.warning("[scheduler] progress callback failed for 'finish' event", exc_info=True)

        if self._on_complete:
            self._on_complete(job)

        if job.schedule_type == ScheduleType.RECURRING:
            job.state = JobState.PENDING  # reset for next cycle after notification
        # ONE_SHOT stays COMPLETED/FAILED

    async def _execute_dag_job(
        self,
        job: ScheduledJob,
        parent_agent: Any,
        event_callback: Any = None,
    ) -> list[str]:
        """Execute a scheduled DAG workflow job.

        Each DAG node is run via :meth:`EncreLoop._run_sub_agent` so that
        every node produces a real sub-agent session persisted under
        ``<data_dir>/sub_agents/<session_id>/``. The returned list is
        the ordered session_ids of the nodes, in execution order.
        """
        from encre.dag.executor import DagExecutor
        from encre.swarm.planner import EncreTaskPlanner

        if not job.dag_definition.strip():
            raise ValueError("dag_definition is empty")

        planner = EncreTaskPlanner()
        task_tree = planner.plan_from_json(job.name, job.dag_definition)

        if not task_tree.nodes:
            raise ValueError("dag_definition produced an empty task tree")

        node_session_ids: list[str] = []
        node_summaries: list[str] = []

        def _dag_node_runner(node, context):
            """Run a single DAG node as a sub-agent.

            ``DagExecutor`` invokes runners synchronously, so we bridge
            to the asyncio loop via :func:`asyncio.run_coroutine_threadsafe`
            (or :func:`asyncio.run` if no loop is running).
            """
            nonlocal node_session_ids, node_summaries
            prompt = node.description or node.name
            coro = self._run_dag_node_sub_agent(
                parent_agent=parent_agent,
                prompt=prompt,
                node_name=node.name,
                event_callback=event_callback,
            )
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                result = future.result()
            except RuntimeError:
                # No running loop -- execute in a fresh one.
                result = asyncio.run(coro)
            session_id, content = result
            if session_id:
                node_session_ids.append(session_id)
            context[node.id] = content
            node_summaries.append(
                f"[{node.name}] session={session_id or '-'} text_len={len(content)}"
            )
            node.result = content
            return content

        executor = DagExecutor(
            runner=_dag_node_runner,
            max_retries=1,
            retry_delay=1.0,
        )

        dag_result = await executor.run(
            task_tree,
            context={},
        )

        # Build a human-readable summary for the job record.
        summary_lines = [
            f"DAG workflow completed: success={dag_result.success}",
            f"Total duration: {dag_result.total_duration:.2f}s",
            f"Sub-agent sessions: {len(node_session_ids)}",
        ]
        for _nid, nr in dag_result.node_results.items():
            summary_lines.append(
                f"  [{nr.status}] {nr.node_name} ({nr.attempts} attempt(s), "
                f"{nr.finished_at - nr.started_at:.1f}s)"
            )
            if nr.error:
                summary_lines.append(f"    error: {nr.error}")

        job.last_result = "\n".join(summary_lines)[:5000]
        if not dag_result.success:
            job.fail_count += 1
            if job.fail_count >= job.max_failures:
                job.state = JobState.FAILED
            else:
                job.state = JobState.PENDING
        return node_session_ids

    async def _run_dag_node_sub_agent(
        self,
        parent_agent: Any,
        prompt: str,
        node_name: str,
        event_callback: Any = None,
    ) -> tuple[str | None, str]:
        """Run a single DAG node via ``_run_sub_agent``.

        Returns ``(session_id, content)``. The session_id is the
        sub-agent's persisted session, the content is the assistant
        text extracted from the sub-agent's messages.
        """
        result = await parent_agent.loop._run_sub_agent(
            prompt=prompt,
            system_prompt=f"You are executing a single step of a scheduled workflow. Step: {node_name}",
            tool_policy="all",
            progress_callback=None,
            event_callback=event_callback,
        )
        session_id = result.get("session_id")
        content = result.get("content") or ""
        return session_id, content

    def _save(self) -> None:
        if not self._durable_path:
            return
        self._durable_path.parent.mkdir(parents=True, exist_ok=True)
        data = [j.to_dict() for j in self._jobs.values()]
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with contextlib.suppress(Exception):
            payload = encrypt(payload)
        with open(self._durable_path, "w", encoding="utf-8") as f:
            f.write(payload)

    def _load(self) -> None:
        if not self._durable_path or not self._durable_path.exists():
            return
        try:
            with open(self._durable_path, encoding="utf-8") as f:
                raw = f.read().strip()
            if raw and not raw.startswith("["):
                with contextlib.suppress(Exception):
                    raw = decrypt(raw)
            data = json.loads(raw)
            for item in data:
                job = ScheduledJob.from_dict(item)
                self._jobs[job.id] = job
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse durable job store {self._durable_path}: {e}")
        except KeyError as e:
            logger.warning(f"Missing key in durable job store entry: {e}")
        except Exception as e:
            logger.error(f"Failed to load durable job store {self._durable_path}: {e}", exc_info=True)
