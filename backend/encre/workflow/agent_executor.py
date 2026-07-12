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

"""Agent-integrated DAG workflow executor.

Bridges the DAG workflow engine with the agent loop. Each task node in a
:class:`TaskTree` executes as a sub-agent run. Progress is streamed as
:class:`AgentEvent` objects that the WebSocket server dispatches to the
frontend for real-time workflow visualisation.

Independent tasks run in parallel, with each task's events tagged by
``task_id`` so the frontend can group them correctly.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

from encre.logging_config import get_logger
from encre.swarm.planner import TaskNode, TaskTree
from encre.utils.types import (
    WorkflowCompletedEvent,
    WorkflowStartedEvent,
    WorkflowTaskEvent,
)

logger = get_logger("encre.workflow.agent_executor")

AgentFactory = Callable[[str, str], Coroutine[Any, Any, str]]
"""A callable that takes (task_id, prompt) and returns the agent result string.

The factory is responsible for running the agent loop and streaming its
events to the frontend. It receives the task_id so it can tag events.
"""


class WorkflowAgentExecutor:
    """Execute a :class:`TaskTree` by running each node as an agent.

    Each task node becomes an independent agent run. Nodes whose dependencies
    are satisfied execute in parallel. Failures cascade-skip downstream
    dependents.

    The executor yields :class:`WorkflowStartedEvent`, :class:`WorkflowTaskEvent`,
    and :class:`WorkflowCompletedEvent` at lifecycle boundaries. The actual
    agent events (``TextDelta``, ``ToolCallStart``, etc.) are produced by the
    *agent_factory* and streamed directly to the frontend by the WebSocket
    server, so this executor only handles orchestration.

    Usage::

        async def run_task(task_id: str, prompt: str) -> str:
            '''Run the agent loop for *task_id* and return result text.'''
            ...

        executor = WorkflowAgentExecutor(agent_factory=run_task)
        async for event in executor.run(task_tree):
            await ws_dispatch(event)
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        max_retries: int = 1,
        retry_delay: float = 2.0,
        fail_fast: bool = False,
    ) -> None:
        self._agent_factory = agent_factory
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._fail_fast = fail_fast

    async def run(
        self,
        tree: TaskTree,
        workflow_id: str = "",
    ) -> AsyncGenerator[Any, None]:
        """Execute all nodes in the task tree.

        Yields workflow lifecycle events. Agent events (text, tool calls)
        are streamed by the *agent_factory* directly; this method only
        produces orchestration markers.
        """
        if not tree.nodes:
            return

        workflow_id = workflow_id or f"wf_{uuid.uuid4().hex[:10]}"
        # Track lifecycle outcomes so we can emit an accurate summary event.
        failed_ids: set[str] = set()
        skipped_ids: set[str] = set()
        completed_count = 0
        # enqueued = nodes we have scheduled at least once.
        enqueued: set[str] = set()
        completed: set[str] = set()
        in_flight: set[str] = set()

        yield WorkflowStartedEvent(
            workflow_id=workflow_id,
            goal=tree.goal,
            total_tasks=len(tree.nodes),
            task_ids=list(tree.nodes.keys()),
        )

        # Seed entry nodes
        ready = list(tree.entry_nodes)
        started_at = time.monotonic()

        while True:
            # Gather the next batch of runnable nodes for this round.
            executable = self._collect_executable(
                tree, ready, enqueued, completed, failed_ids, skipped_ids,
            )

            if not executable:
                remaining = set(tree.nodes.keys()) - enqueued
                if remaining:
                    ready = list(remaining)
                    continue
                if not in_flight:
                    break
                # Wait for in-flight tasks
                await asyncio.sleep(0.05)
                ready = []
                continue

            # Yield started events
            for nid in executable:
                enqueued.add(nid)
                node = tree.nodes[nid]
                node.status = "running"
                yield WorkflowTaskEvent(
                    workflow_id=workflow_id,
                    task_id=nid,
                    task_name=node.name,
                    status="started",
                )

            # Run all executable nodes in parallel
            tasks_map: dict[str, asyncio.Task[str]] = {}
            # Spawn one asyncio task per ready node; each calls the agent factory.
            for nid in executable:
                node = tree.nodes[nid]
                prompt = _build_task_prompt(node)
                tasks_map[nid] = asyncio.create_task(
                    self._execute_with_retry(nid, node.name, prompt)
                )
            in_flight.update(executable)

            # Wait for all in this batch
            for nid, task in tasks_map.items():
                try:
                    outcome = await task
                except Exception as exc:
                    outcome = f"FAILED:{type(exc).__name__}: {exc}"

                in_flight.discard(nid)
                completed.add(nid)
                node = tree.nodes[nid]

                if outcome.startswith("FAILED: "):
                    node.status = "failed"
                    # Strip the "FAILED: " tag and keep the raw error text.
                    node.error = outcome[7:]
                    failed_ids.add(nid)
                    yield WorkflowTaskEvent(
                        workflow_id=workflow_id,
                        task_id=nid,
                        task_name=node.name,
                        status="failed",
                    )
                    if self._fail_fast:
                        break
                elif outcome.startswith("SKIPPED: "):
                    node.status = "skipped"
                    skipped_ids.add(nid)
                    yield WorkflowTaskEvent(
                        workflow_id=workflow_id,
                        task_id=nid,
                        task_name=node.name,
                        status="skipped",
                    )
                else:
                    node.status = "completed"
                    node.result = outcome
                    completed_count += 1
                    yield WorkflowTaskEvent(
                        workflow_id=workflow_id,
                        task_id=nid,
                        task_name=node.name,
                        status="completed",
                    )

            if self._fail_fast and failed_ids:
                self._skip_remaining(tree, enqueued, completed, failed_ids, skipped_ids)
                for nid in skipped_ids:
                    if nid not in enqueued:
                        continue
                    yield WorkflowTaskEvent(
                        workflow_id=workflow_id,
                        task_id=nid,
                        task_name=tree.nodes[nid].name,
                        status="skipped",
                    )
                break

            # Find newly ready nodes
            ready = [
                nid for nid in tree.nodes
                if nid not in enqueued and nid not in completed
            ]

        total_duration = time.monotonic() - started_at
        yield WorkflowCompletedEvent(
            workflow_id=workflow_id,
            goal=tree.goal,
            success=len(failed_ids) == 0,
            completed_count=completed_count,
            failed_count=len(failed_ids),
            skipped_count=len(skipped_ids),
            total_duration=total_duration,
        )

    async def _execute_with_retry(
        self, task_id: str, task_name: str, prompt: str,
    ) -> str:
        """Run the agent factory for *task_id* with retry support."""
        for attempt in range(self._max_retries + 1):
            try:
                # Hand the task to the user-supplied agent factory.
                return await self._agent_factory(task_id, prompt)
            except Exception as exc:
                logger.info(
                    "[workflow] task '%s' attempt %d/%d failed: %s",
                    task_name, attempt + 1, self._max_retries + 1, exc,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                else:
                    return f"FAILED:{type(exc).__name__}: {exc}"
        return ""

    def _collect_executable(
        self,
        tree: TaskTree,
        candidates: list[str],
        enqueued: set[str],
        completed: set[str],
        failed_ids: set[str],
        skipped_ids: set[str],
    ) -> list[str]:
        """Filter *candidates* down to nodes ready for execution."""
        executable: list[str] = []
        # Keep candidates that are not yet enqueued and have met dependencies.
        for nid in candidates:
            if nid in enqueued or nid in completed or nid in failed_ids or nid in skipped_ids:
                continue
            node = tree.nodes.get(nid)
            if node is None:
                continue
            # Check all dependencies met
            deps_met = all(
                dep in completed or tree.nodes[dep].status == "completed"
                for dep in node.dependencies
            )
            if not deps_met:
                continue
            # Skip if any dependency failed
            failed_deps = [d for d in node.dependencies if d in failed_ids]
            if failed_deps:
                node.status = "skipped"
                node.error = f"dependency failed: {failed_deps[0]}"
                skipped_ids.add(nid)
                enqueued.add(nid)
                continue
            executable.append(nid)
        return executable

    def _skip_remaining(
        self,
        tree: TaskTree,
        _enqueued: set[str],
        completed: set[str],
        failed_ids: set[str],
        skipped_ids: set[str],
    ) -> None:
        for nid in tree.nodes:
            if nid not in completed and nid not in failed_ids and nid not in skipped_ids:
                skipped_ids.add(nid)
                tree.nodes[nid].status = "skipped"


def _build_task_prompt(node: TaskNode) -> str:
    """Build a focused agent prompt for a single task node."""
    parts = [f"## Task: {node.name}"]
    # Include the richer description when the planner provided one.
    if node.description:
        parts.append(f"\n{node.description}")
    parts.append("\n\nComplete this task thoroughly. Report your results clearly.\n")
    return "".join(parts)
