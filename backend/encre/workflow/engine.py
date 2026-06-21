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
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from encre.logging_config import get_logger
from encre.workflow.graph import DAGGraph
from encre.workflow.task import WorkflowTask, WorkflowTaskStatus

logger = get_logger("encre.workflow.engine")


# ── Event types for status reporting ──────────────────────────────────


@dataclass
class WorkflowEvent:
    """Base event emitted during workflow execution."""

    workflow_id: str
    timestamp: float = field(default_factory=time.time)


@dataclass(kw_only=True)
class WorkflowStarted(WorkflowEvent):
    """Emitted when a workflow run begins."""

    total_tasks: int


@dataclass(kw_only=True)
class WorkflowCompleted(WorkflowEvent):
    """Emitted when a workflow run finishes (success, failure, or
    cancellation)."""

    total_tasks: int = 0
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    blocked_count: int = 0


@dataclass(kw_only=True)
class TaskStarted(WorkflowEvent):
    """Emitted when an individual task starts execution."""

    task_id: str = ""
    task_name: str = ""


@dataclass(kw_only=True)
class TaskCompleted(WorkflowEvent):
    """Emitted when an individual task finishes successfully."""

    task_id: str = ""
    task_name: str = ""
    result: str = ""
    duration: float = 0.0


@dataclass(kw_only=True)
class TaskFailed(WorkflowEvent):
    """Emitted when an individual task fails (after exhausting retries)."""

    task_id: str = ""
    task_name: str = ""
    error: str = ""
    retry_count: int = 0
    duration: float = 0.0


@dataclass(kw_only=True)
class TaskRetrying(WorkflowEvent):
    """Emitted when a task fails but will be retried."""

    task_id: str = ""
    task_name: str = ""
    error: str = ""
    retry_count: int = 0
    next_retry_delay: float = 0.0


@dataclass(kw_only=True)
class TaskSkipped(WorkflowEvent):
    """Emitted when a task is skipped due to a dependency failure."""

    task_id: str = ""
    task_name: str = ""
    reason: str = ""


# ── Engine implementation ─────────────────────────────────────────────


class WorkflowEngine:
    """Asynchronous DAG execution engine.

    Drives a :class:`DAGGraph` through its lifecycle:
    ``PENDING -> READY -> RUNNING -> COMPLETED/FAILED/SKIPPED/BLOCKED``.

    Ready tasks are executed concurrently via ``asyncio.gather``.  The
    engine supports per-task timeouts, automatic retries with exponential
    back-off, and external progress reporting via an event callback.
    """

    def __init__(self) -> None:
        self._running = False
        self._cancel_requested = False
        self._workflow_id: str = ""
        self._on_event: Callable[[WorkflowEvent], None] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    async def run_workflow(
        self,
        graph: DAGGraph,
        workflow_id: str = "",
        *,
        on_event: Callable[[WorkflowEvent], None] | None = None,
    ) -> DAGGraph:
        """Execute a full DAG workflow to completion.

        Args:
            graph: The DAG to execute.  The graph is mutated in place -- each
                task's ``status`` is updated as execution progresses.
            workflow_id: Optional identifier for this workflow run.
            on_event: Optional callback invoked for each lifecycle event
                (see ``WorkflowEvent`` subtypes).  The callback is called
                synchronously from the engine's async context -- keep it fast
                or delegate to a queue.

        Returns:
            The same *graph* object with all task statuses updated.

        Raises:
            RuntimeError: If the engine is already running a workflow.
        """
        if self._running:
            raise RuntimeError("WorkflowEngine is already running a workflow")

        self._running = True
        self._cancel_requested = False
        self._on_event = on_event
        self._workflow_id = workflow_id or f"wf_{int(time.time())}"

        try:
            # Validate graph integrity before execution
            graph.validate()

            return await self._execute_graph(graph)
        finally:
            self._running = False
            self._cancel_requested = False
            self._on_event = None
            self._workflow_id = ""

    async def cancel(self) -> None:
        """Request cancellation of the currently running workflow.

        Tasks that are currently running will be allowed to complete (or
        time out), but no new tasks will be started.
        """
        self._cancel_requested = True
        logger.info(f"[workflow:{self._workflow_id}] cancellation requested")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    # ── Internal execution loop ────────────────────────────────────────

    async def _execute_graph(self, graph: DAGGraph) -> DAGGraph:
        total = graph.node_count
        self._emit(WorkflowStarted(
            workflow_id=self._workflow_id,
            total_tasks=total,
        ))

        ready_queue: list[WorkflowTask] = []
        completed_ids: set[str] = set()

        # Seed the ready queue with root tasks (no dependencies)
        for task in graph:
            if not task.dependencies:
                task.status = WorkflowTaskStatus.READY
                ready_queue.append(task)

        while ready_queue and not self._cancel_requested:
            # Sort ready tasks by priority (descending), then run in parallel
            ready_queue.sort(key=lambda t: t.priority, reverse=True)
            await self._run_ready_tasks(ready_queue, completed_ids)

            # Check for newly ready tasks
            ready_queue = self._collect_ready_tasks(graph, completed_ids)

        # Handle tasks blocked by failures
        self._mark_blocked_tasks(graph)

        # Emit completion summary
        statuses = [t.status for t in graph]
        self._emit(WorkflowCompleted(
            workflow_id=self._workflow_id,
            total_tasks=total,
            completed_count=sum(1 for s in statuses if s == WorkflowTaskStatus.COMPLETED),
            failed_count=sum(1 for s in statuses if s == WorkflowTaskStatus.FAILED),
            skipped_count=sum(1 for s in statuses if s == WorkflowTaskStatus.SKIPPED),
            blocked_count=sum(1 for s in statuses if s == WorkflowTaskStatus.BLOCKED),
        ))

        return graph

    async def _run_ready_tasks(
        self,
        ready_queue: list[WorkflowTask],
        completed_ids: set[str],
    ) -> None:
        """Execute all tasks in *ready_queue* concurrently.

        Results are collected and each task's status is updated accordingly.
        """
        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(self._execute_single_task(task, completed_ids))
            for task in ready_queue
        ]
        ready_queue.clear()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_single_task(
        self,
        task: WorkflowTask,
        completed_ids: set[str],
    ) -> None:
        """Execute one task with retry & timeout support."""
        task.status = WorkflowTaskStatus.RUNNING
        task.started_at = time.time()
        self._emit(TaskStarted(
            workflow_id=self._workflow_id,
            task_id=task.id,
            task_name=task.name,
        ))

        attempt = 0
        max_attempts = task.max_retries + 1

        while attempt < max_attempts:
            attempt += 1
            try:
                if task.execute is None:
                    # No-op leaf task
                    await asyncio.sleep(0)
                else:
                    coro = task.execute
                    if task.timeout is not None:
                        coro = asyncio.wait_for(coro, timeout=task.timeout)
                    result = await coro
                    task.result = str(result) if result is not None else ""

                # Success
                task.status = WorkflowTaskStatus.COMPLETED
                task.completed_at = time.time()
                task.retry_count = attempt - 1
                completed_ids.add(task.id)
                duration = task.completed_at - (task.started_at or task.completed_at)
                self._emit(TaskCompleted(
                    workflow_id=self._workflow_id,
                    task_id=task.id,
                    task_name=task.name,
                    result=task.result,
                    duration=duration,
                ))
                return

            except asyncio.CancelledError:
                task.status = WorkflowTaskStatus.FAILED
                task.error = "Task was cancelled"
                task.completed_at = time.time()
                completed_ids.discard(task.id)
                duration = task.completed_at - (task.started_at or task.completed_at)
                self._emit(TaskFailed(
                    workflow_id=self._workflow_id,
                    task_id=task.id,
                    task_name=task.name,
                    error=task.error,
                    retry_count=attempt - 1,
                    duration=duration,
                ))
                return

            except Exception as exc:
                task.error = f"{type(exc).__name__}: {exc}"
                task.retry_count = attempt

                if attempt < max_attempts:
                    # Schedule retry with exponential back-off
                    delay = min(2.0 ** attempt, 60.0)
                    self._emit(TaskRetrying(
                        workflow_id=self._workflow_id,
                        task_id=task.id,
                        task_name=task.name,
                        error=task.error,
                        retry_count=attempt,
                        next_retry_delay=delay,
                    ))
                    logger.info(
                        "[workflow:%s] task '%s' failed (attempt %d/%d), "
                        "retrying in %.1fs: %s",
                        self._workflow_id, task.name, attempt, max_attempts,
                        delay, task.error,
                    )
                    await asyncio.sleep(delay)
                else:
                    # Final failure
                    task.status = WorkflowTaskStatus.FAILED
                    task.completed_at = time.time()
                    duration = task.completed_at - (task.started_at or task.completed_at)
                    self._emit(TaskFailed(
                        workflow_id=self._workflow_id,
                        task_id=task.id,
                        task_name=task.name,
                        error=task.error,
                        retry_count=attempt,
                        duration=duration,
                    ))
                    logger.error(
                        "[workflow:%s] task '%s' failed after %d attempts: %s",
                        self._workflow_id, task.name, attempt, task.error,
                    )
                    return

    def _collect_ready_tasks(
        self,
        graph: DAGGraph,
        completed_ids: set[str],
    ) -> list[WorkflowTask]:
        """Scan the graph and return tasks whose dependencies are satisfied."""
        ready: list[WorkflowTask] = []
        for task in graph:
            if task.status != WorkflowTaskStatus.PENDING:
                continue
            if not task.dependencies or all(
                dep_id in completed_ids for dep_id in task.dependencies
            ):
                task.status = WorkflowTaskStatus.READY
                ready.append(task)
        return ready

    def _mark_blocked_tasks(self, graph: DAGGraph) -> None:
        """Mark tasks as BLOCKED or SKIPPED when a dependency has failed.

        Also handles cancellation -- remaining PENDING tasks are marked
        SKIPPED.
        """
        skipped_ids: set[str] = set()

        for task in graph:
            if task.status != WorkflowTaskStatus.PENDING:
                continue

            # Check for cancelled workflow
            if self._cancel_requested:
                task.status = WorkflowTaskStatus.SKIPPED
                task.completed_at = time.time()
                self._emit(TaskSkipped(
                    workflow_id=self._workflow_id,
                    task_id=task.id,
                    task_name=task.name,
                    reason="Workflow was cancelled",
                ))
                skipped_ids.add(task.id)
                continue

            # Check for failed dependencies
            has_failed_dep = False
            has_skipped_dep = False
            for dep_id in task.dependencies:
                dep = graph.get_node(dep_id)
                if dep is None:
                    continue
                if dep.status == WorkflowTaskStatus.FAILED:
                    has_failed_dep = True
                if dep.status in (WorkflowTaskStatus.SKIPPED, WorkflowTaskStatus.BLOCKED):
                    has_skipped_dep = True

            if has_failed_dep:
                task.status = WorkflowTaskStatus.BLOCKED
                task.error = "Blocked by failed dependency"
                task.completed_at = time.time()
                self._emit(TaskSkipped(
                    workflow_id=self._workflow_id,
                    task_id=task.id,
                    task_name=task.name,
                    reason="A dependency has failed",
                ))
                skipped_ids.add(task.id)
            elif has_skipped_dep:
                task.status = WorkflowTaskStatus.SKIPPED
                task.completed_at = time.time()
                self._emit(TaskSkipped(
                    workflow_id=self._workflow_id,
                    task_id=task.id,
                    task_name=task.name,
                    reason="A dependency was skipped",
                ))
                skipped_ids.add(task.id)

    def _emit(self, event: WorkflowEvent) -> None:
        """Forward *event* to the registered callback, if any."""
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                logger.warning(
                    "[workflow:%s] event callback raised", self._workflow_id,
                    exc_info=True,
                )
