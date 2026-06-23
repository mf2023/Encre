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



"""DAG workflow executor -- runs :class:`TaskTree` nodes in dependency order.

Independent nodes execute concurrently via :func:`asyncio.gather`, and
failures propagate according to a configurable policy (skip downstream,
abort all, or retry individual nodes).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from encre.swarm.planner import TaskNode, TaskTree

logger = logging.getLogger("encre.dag.executor")

# Type alias: an async callable that receives (node, context) and returns a
# result string.  ``context`` is a mutable dict shared across all nodes
# in the workflow, useful for passing intermediate results.
NodeRunner = Callable[[TaskNode, dict[str, Any]], str | None]


class SkipNodeError(Exception):
    """Raise inside a node runner to skip this node (no error logged)."""


@dataclass
class NodeResult:
    """Outcome of a single DAG node execution."""

    node_id: str
    node_name: str
    status: str  # completed | failed | skipped
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    attempts: int = 1


@dataclass
class DagExecutionResult:
    """Aggregated result of a full DAG workflow execution."""

    goal: str
    success: bool
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    total_duration: float = 0.0
    error: str = ""


class DagExecutor:
    """Async DAG workflow executor.

    Usage::

        executor = DagExecutor(runner=my_async_node_runner)
        result = await executor.run(task_tree, context={})
    """

    def __init__(
        self,
        runner: NodeRunner,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        fail_fast: bool = False,
    ) -> None:
        self._runner = runner
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._fail_fast = fail_fast
        self._node_results: dict[str, NodeResult] = {}
        self._context: dict[str, Any] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._skipped: set[str] = set()
        self._tree: TaskTree | None = None

    # ── Public API ─────────────────────────────────────────────────────

    async def run(
        self,
        tree: TaskTree,
        context: dict[str, Any] | None = None,
        progress_cb: Callable[[str, NodeResult], None] | None = None,
    ) -> DagExecutionResult:
        """Execute a ``TaskTree`` from root to leaves.

        Args:
            tree: The DAG to execute.
            context: Shared mutable dict passed to every node runner.
            progress_cb: Optional callback fired after each node completes
                (receives node_id and NodeResult).

        Returns:
            Aggregated ``DagExecutionResult``.
        """
        self._tree = tree
        self._context = context or {}
        self._node_results.clear()
        self._completed.clear()
        self._failed.clear()
        self._skipped.clear()

        if not tree.nodes:
            return self._build_result(success=True)

        # Validate DAG -- check for missing dependencies and cycles
        validation_error = self._validate(tree)
        if validation_error:
            return self._build_result(success=False, error=validation_error)

        started = time.monotonic()

        # Seed the queue with entry nodes
        for nid in tree.entry_nodes:
            if nid in tree.nodes:
                self._queue.put_nowait(nid)

        # Track which nodes have been queued
        enqueued: set[str] = set(tree.entry_nodes)
        in_flight: set[str] = set()

        while True:
            # Dequeue as many ready nodes as possible
            ready_nodes: list[str] = []
            while not self._queue.empty():
                try:
                    nid = self._queue.get_nowait()
                    if nid not in enqueued or nid in self._completed or nid in self._failed or nid in self._skipped:
                        continue
                    ready_nodes.append(nid)
                except asyncio.QueueEmpty:
                    break

            if not ready_nodes and not in_flight:
                # All done
                break

            # Execute ready nodes concurrently
            tasks = {nid: self._execute_node(nid, tree.nodes[nid]) for nid in ready_nodes}
            in_flight.update(ready_nodes)
            enqueued.update(ready_nodes)

            # Wait for all concurrent tasks to finish
            completed = await asyncio.gather(*tasks.values(), return_exceptions=True)

            results: dict[str, NodeResult] = {}
            for nid, outcome in zip(tasks.keys(), completed, strict=False):
                in_flight.discard(nid)
                if isinstance(outcome, NodeResult):
                    results[nid] = outcome
                    self._node_results[nid] = outcome
                    if outcome.status == "completed":
                        self._completed.add(nid)
                    elif outcome.status == "failed":
                        self._failed.add(nid)
                    elif outcome.status == "skipped":
                        self._skipped.add(nid)
                    if progress_cb:
                        progress_cb(nid, outcome)
                elif isinstance(outcome, Exception):
                    results[nid] = NodeResult(
                        node_id=nid,
                        node_name=tree.nodes[nid].name,
                        status="failed",
                        error=str(outcome),
                    )
                    self._node_results[nid] = results[nid]
                    self._failed.add(nid)
                    if progress_cb:
                        progress_cb(nid, results[nid])

            # Abort on failure if fail_fast
            if self._fail_fast and self._failed:
                # Cancel any remaining in-flight nodes by marking them as skipped
                for fid in in_flight:
                    if fid not in self._completed:
                        self._skipped.add(fid)
                break

            # Enqueue newly ready nodes (all dependencies satisfied)
            for nid, node in tree.nodes.items():
                if nid in enqueued or nid in self._completed or nid in self._failed or nid in self._skipped:
                    continue
                if self._deps_met(node):
                    # Check if any dependency failed -- if so, skip this node
                    failed_deps = [d for d in node.dependencies if d in self._failed]
                    if failed_deps:
                        self._skipped.add(nid)
                        skip_result = NodeResult(
                            node_id=nid,
                            node_name=node.name,
                            status="skipped",
                            result="",
                            error=f"dependency failed: {failed_deps[0]}",
                        )
                        self._node_results[nid] = skip_result
                        enqueued.add(nid)
                        if progress_cb:
                            progress_cb(nid, skip_result)
                        continue
                    enqueued.add(nid)
                    self._queue.put_nowait(nid)

        total_duration = time.monotonic() - started
        success = len(self._failed) == 0 and len(tree.nodes) > 0
        return self._build_result(
            success=success,
            duration=total_duration,
        )

    # ── Internal ───────────────────────────────────────────────────────

    async def _execute_node(self, nid: str, node: TaskNode) -> NodeResult:
        """Run a single node with retry logic."""
        node.status = "running"
        started = time.monotonic()
        last_error = ""
        for attempt in range(1, self._max_retries + 2):
            try:
                result = await asyncio.to_thread(self._runner, node, self._context)
                node.status = "completed"
                node.result = result or ""
                return NodeResult(
                    node_id=nid,
                    node_name=node.name,
                    status="completed",
                    result=result or "",
                    started_at=started,
                    finished_at=time.monotonic(),
                    attempts=attempt,
                )
            except SkipNodeError:
                node.status = "skipped"
                return NodeResult(
                    node_id=nid,
                    node_name=node.name,
                    status="skipped",
                    started_at=started,
                    finished_at=time.monotonic(),
                    attempts=attempt,
                )
            except Exception as e:
                last_error = str(e)
                if attempt <= self._max_retries:
                    logger.info("[dag] retrying node=%s attempt=%d/%d error=%s",
                                nid, attempt, self._max_retries, last_error)
                    await asyncio.sleep(self._retry_delay * (2 ** (attempt - 1)))
                continue

        node.status = "failed"
        node.error = last_error
        return NodeResult(
            node_id=nid,
            node_name=node.name,
            status="failed",
            error=last_error,
            started_at=started,
            finished_at=time.monotonic(),
            attempts=self._max_retries + 1,
        )

    def _deps_met(self, node: TaskNode) -> bool:
        """Check whether all dependencies of *node* are completed."""
        if not node.dependencies:
            return True
        tree = self._tree
        if tree is None:
            return False
        return all(
            dep in tree.nodes and (
                dep in self._completed or tree.nodes[dep].status == "completed"
            )
            for dep in node.dependencies
        )

    def _validate(self, tree: TaskTree) -> str | None:
        """Validate the DAG: check for missing deps and obvious cycles."""
        all_ids = set(tree.nodes.keys())
        for nid, node in tree.nodes.items():
            for dep in node.dependencies:
                if dep not in all_ids:
                    return f"node {nid!r} depends on unknown node {dep!r}"
        # Quick cycle check via DFS
        visited: set[str] = set()
        stack: set[str] = set()

        def _has_cycle(nid: str) -> bool:
            visited.add(nid)
            stack.add(nid)
            for dep in tree.nodes[nid].dependencies:
                if dep not in visited:
                    if _has_cycle(dep):
                        return True
                elif dep in stack:
                    return True
            stack.discard(nid)
            return False

        for nid in all_ids:
            if nid not in visited and _has_cycle(nid):
                return f"cycle detected involving node {nid!r}"
        return None

    def _build_result(
        self,
        success: bool,
        error: str = "",
        duration: float = 0.0,
    ) -> DagExecutionResult:
        goal = self._tree.goal if self._tree else ""
        return DagExecutionResult(
            goal=goal,
            success=success,
            node_results=dict(self._node_results),
            total_duration=duration,
            error=error,
        )
