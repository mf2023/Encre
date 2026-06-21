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

from collections import deque
from collections.abc import Iterator

from encre.workflow.task import WorkflowTask, WorkflowTaskStatus, make_ready_predicate


class DAGError(Exception):
    """Raised when a graph operation violates DAG constraints."""


class CycleError(DAGError):
    """Raised when a cycle is detected in the graph."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Cycle detected in workflow graph: {' -> '.join(cycle)}")


class DAGGraph:
    """Directed acyclic graph (DAG) data structure for workflow orchestration.

    Manages a set of :class:`WorkflowTask` nodes connected by directed edges
    where an edge ``A -> B`` means *A must complete before B can start*.

    The graph enforces acyclicity on every edge addition and provides
    efficient dependency resolution via adjacency lists.
    """

    def __init__(self) -> None:
        # node_id -> WorkflowTask
        self._nodes: dict[str, WorkflowTask] = {}
        # Forward edges: node -> set of successors (dependents)
        self._forward: dict[str, set[str]] = {}
        # Reverse edges: node -> set of predecessors (dependencies)
        self._reverse: dict[str, set[str]] = {}

    # ── Node management ────────────────────────────────────────────────

    def add_node(self, task: WorkflowTask) -> None:
        """Register a task node in the graph.

        If the task declares ``dependencies``, corresponding edges are
        automatically added (the dependency must already exist in the graph
        unless ``allow_missing_deps`` is True -- currently all deps must be
        present).
        """
        if task.id in self._nodes:
            msg = f"Task '{task.id}' already exists in the graph"
            raise DAGError(msg)

        self._nodes[task.id] = task
        self._forward.setdefault(task.id, set())
        self._reverse.setdefault(task.id, set())

        # Auto-register edges from declared dependencies
        for dep_id in task.dependencies:
            if dep_id not in self._nodes:
                msg = f"Dependency task '{dep_id}' not found when adding '{task.id}'"
                raise DAGError(msg)
            self._add_edge_unchecked(dep_id, task.id)

    def remove_node(self, task_id: str) -> WorkflowTask | None:
        """Remove a task and all its incident edges from the graph.

        Returns the removed task, or ``None`` if it did not exist.
        """
        task = self._nodes.pop(task_id, None)
        if task is None:
            return None

        # Remove all edges where this node is the target
        for pred_id in list(self._reverse.get(task_id, set())):
            self._forward.get(pred_id, set()).discard(task_id)
        self._reverse.pop(task_id, None)

        # Remove all edges where this node is the source
        for succ_id in list(self._forward.get(task_id, set())):
            self._reverse.get(succ_id, set()).discard(task_id)
        self._forward.pop(task_id, None)

        return task

    def get_node(self, task_id: str) -> WorkflowTask | None:
        """Look up a task by its ID."""
        return self._nodes.get(task_id)

    @property
    def nodes(self) -> dict[str, WorkflowTask]:
        """Read-only view of all nodes."""
        return dict(self._nodes)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # ── Edge management ────────────────────────────────────────────────

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add a directed edge ``from_id -> to_id`` (``from_id`` must complete
        before ``to_id`` can start).

        Raises :class:`DAGError` if either node does not exist or if adding
        the edge would create a cycle.
        """
        if from_id not in self._nodes:
            msg = f"Source node '{from_id}' not found"
            raise DAGError(msg)
        if to_id not in self._nodes:
            msg = f"Target node '{to_id}' not found"
            raise DAGError(msg)

        # Detect cycle before mutating
        if self._would_create_cycle(from_id, to_id):
            raise CycleError([from_id, to_id])

        self._add_edge_unchecked(from_id, to_id)

    def remove_edge(self, from_id: str, to_id: str) -> bool:
        """Remove a directed edge. Returns ``True`` if the edge existed."""
        succs = self._forward.get(from_id)
        if succs is None or to_id not in succs:
            return False
        succs.discard(to_id)
        self._reverse[to_id].discard(from_id)
        return True

    # ── Traversal / analysis ───────────────────────────────────────────

    def topological_sort(self) -> list[WorkflowTask]:
        """Return tasks in topological order using Kahn's algorithm.

        Raises :class:`CycleError` if the graph contains a cycle.
        """
        in_degree: dict[str, int] = {}
        for node_id in self._nodes:
            in_degree[node_id] = len(self._reverse[node_id])

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        sorted_ids: list[str] = []

        while queue:
            nid = queue.popleft()
            sorted_ids.append(nid)
            for succ_id in self._forward.get(nid, set()):
                in_degree[succ_id] -= 1
                if in_degree[succ_id] == 0:
                    queue.append(succ_id)

        if len(sorted_ids) != len(self._nodes):
            missing = [nid for nid in self._nodes if nid not in sorted_ids]
            raise CycleError(missing)

        return [self._nodes[nid] for nid in sorted_ids]

    def detect_cycles(self) -> list[list[str]]:
        """Detect and return all elementary cycles in the graph.

        Uses Johnson's algorithm.  Returns a list of cycles, each cycle
        being a list of node IDs forming the cycle.

        .. note::
           For large graphs this may be expensive.  Consider using
           :meth:`has_cycle` for a simple boolean check.
        """
        return self._johnson_cycles()

    def has_cycle(self) -> bool:
        """Return ``True`` if the graph contains at least one cycle."""
        try:
            self.topological_sort()
            return False
        except CycleError:
            return True

    def get_ready_nodes(self) -> list[WorkflowTask]:
        """Return all tasks whose dependencies are fully satisfied
        (i.e. all dependencies have status ``COMPLETED`` or the task has
        no dependencies)."""
        completed_ids = {
            tid
            for tid, t in self._nodes.items()
            if t.status == WorkflowTaskStatus.COMPLETED
        }
        return [
            t for t in self._nodes.values()
            if make_ready_predicate(t, completed_ids)
        ]

    def get_dependents(self, task_id: str) -> list[WorkflowTask]:
        """Return all tasks that directly depend on *task_id*."""
        if task_id not in self._nodes:
            return []
        return [
            self._nodes[succ_id]
            for succ_id in self._forward.get(task_id, set())
            if succ_id in self._nodes
        ]

    def get_dependencies(self, task_id: str) -> list[WorkflowTask]:
        """Return all tasks that *task_id* directly depends on."""
        if task_id not in self._nodes:
            return []
        return [
            self._nodes[pred_id]
            for pred_id in self._reverse.get(task_id, set())
            if pred_id in self._nodes
        ]

    def get_all_dependents(self, task_id: str) -> set[str]:
        """Return the IDs of all tasks that transitively depend on
        *task_id* (direct and indirect downstream nodes)."""
        if task_id not in self._forward:
            return set()
        visited: set[str] = set()
        stack = [task_id]
        while stack:
            nid = stack.pop()
            for succ_id in self._forward.get(nid, set()):
                if succ_id not in visited:
                    visited.add(succ_id)
                    stack.append(succ_id)
        return visited

    def get_all_dependencies(self, task_id: str) -> set[str]:
        """Return the IDs of all tasks that *task_id* transitively depends
        on (direct and indirect upstream nodes)."""
        if task_id not in self._reverse:
            return set()
        visited: set[str] = set()
        stack = [task_id]
        while stack:
            nid = stack.pop()
            for pred_id in self._reverse.get(nid, set()):
                if pred_id not in visited:
                    visited.add(pred_id)
                    stack.append(pred_id)
        return visited

    def validate(self) -> None:
        """Validate graph integrity.

        Raises :class:`DAGError` or :class:`CycleError` if the graph is
        inconsistent.
        """
        # 1. All references in edges must point to existing nodes
        for src, targets in self._forward.items():
            if src not in self._nodes:
                msg = f"Orphaned forward edge source '{src}'"
                raise DAGError(msg)
            for tgt in targets:
                if tgt not in self._nodes:
                    msg = f"Forward edge '{src} -> {tgt}' targets non-existent node"
                    raise DAGError(msg)
        for tgt, sources in self._reverse.items():
            if tgt not in self._nodes:
                msg = f"Orphaned reverse edge target '{tgt}'"
                raise DAGError(msg)
            for src in sources:
                if src not in self._nodes:
                    msg = f"Reverse edge '{src} -> {tgt}' references non-existent node"
                    raise DAGError(msg)

        # 2. Consistency check: forward and reverse must agree
        for src in self._nodes:
            for tgt in self._forward.get(src, set()):
                if src not in self._reverse.get(tgt, set()):
                    msg = f"Inconsistent edge: '{src} -> {tgt}' missing from reverse map"
                    raise DAGError(msg)

        # 3. No cycles
        self.topological_sort()

    # ── Iteration ──────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[WorkflowTask]:
        return iter(self._nodes.values())

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    # ── Private helpers ────────────────────────────────────────────────

    def _add_edge_unchecked(self, from_id: str, to_id: str) -> None:
        """Add edge without cycle detection (internal use)."""
        self._forward.setdefault(from_id, set()).add(to_id)
        self._reverse.setdefault(to_id, set()).add(from_id)

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """Check if adding ``from_id -> to_id`` would introduce a cycle.

        A cycle would be created if there is already a path from *to_id*
        back to *from_id* -- i.e. if *from_id* is reachable from *to_id*.
        """
        visited: set[str] = set()
        stack = [to_id]
        while stack:
            nid = stack.pop()
            if nid == from_id:
                return True
            if nid in visited:
                continue
            visited.add(nid)
            stack.extend(self._forward.get(nid, set()))
        return False

    def _johnson_cycles(self) -> list[list[str]]:
        """Johnson's algorithm for finding all elementary cycles in a
        directed graph.  Implementation follows the classic 1975 paper."""
        all_cycles: list[list[str]] = []
        node_list = list(self._nodes)
        index_of = {nid: i for i, nid in enumerate(node_list)}
        n = len(node_list)
        blocked: list[bool] = [False] * n
        b_list: list[set[int]] = [set() for _ in range(n)]
        stack: list[int] = []
        s = 0
        adjacency: list[list[int]] = [
            [index_of[succ] for succ in self._forward.get(node_list[i], set()) if succ in index_of]
            for i in range(n)
        ]

        def _circuit(v: int) -> bool:
            f = False
            stack.append(v)
            blocked[v] = True
            for w in adjacency[v]:
                if w == s:
                    # Found a cycle containing s
                    cycle_ids = [node_list[s]] + [node_list[i] for i in stack]
                    all_cycles.append(cycle_ids)
                    f = True
                elif not blocked[w]:
                    if _circuit(w):
                        f = True
            if f:
                _unblock(v)
            else:
                for w in adjacency[v]:
                    if v not in b_list[w]:
                        b_list[w].add(v)
            stack.pop()
            return f

        def _unblock(u: int) -> None:
            blocked[u] = False
            for w in list(b_list[u]):
                b_list[u].discard(w)
                if blocked[w]:
                    _unblock(w)

        for s in range(n):
            # Subgraph induced by nodes s..n-1
            adjacency = [
                [w for w in adj if w >= s]
                for adj in adjacency
            ]
            # Run circuit for starting node s
            _circuit(s)
            # Clear blocked state for next iteration
            blocked = [False] * n
            b_list = [set() for _ in range(n)]

        return all_cycles
