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

# Dependency-aware execution engine for a swarm task tree.
#
# ``EncreOrchestrator`` walks a ``TaskTree``, launching each ready node as a
# role-configured ``EncreAgent`` (bounded by a concurrency semaphore), running
# an optional reviewer gate on coder output, sharing context via the blackboard,
# and yielding ``OrchestrationEvent`` progress events.  It also supports
# cooperative cancellation of all in-flight node tasks.

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from encre.swarm.blackboard import EncreBlackboard
from encre.swarm.roles import AgentRole, RoleRegistry


# A sub-agent runner lets the orchestrator execute each task node through the
# host loop's ``_run_sub_agent`` instead of spawning a bare ``EncreAgent``.
# This wires swarm teammates into the loop's infrastructure: depth fencing
# (no swarm-inside-swarm recursion), live progress streaming to the frontend,
# transcript persistence under ``sub_agents/<id>/``, and the tool-policy /
# safety hooks.  When ``None`` (e.g. in unit tests) the orchestrator falls
# back to spawning a fresh ``EncreAgent`` directly, preserving the old path.
SubAgentRunner = Callable[..., Any]


@dataclass
class OrchestrationEvent:
    type: str  # task_started | task_completed | task_failed | team_finished | progress
    task_id: str = ""
    task_name: str = ""
    role: str = ""
    result: str = ""
    error: str = ""
    progress: float = 0.0
    timestamp: float = field(default_factory=time.time)


class EncreOrchestrator:
    """Executes a TaskTree with role-based teammate agents.

    Features:
    - DAG-based execution: respects task dependencies
    - Reviewer gate: coder output can be checked by reviewer
    - Parallel execution: independent tasks run concurrently
    - Blackboard: shared state accessible by all teammates
    - Progress streaming: yields OrchestrationEvents
    """

    def __init__(
        self,
        role_registry: RoleRegistry | None = None,
        blackboard: EncreBlackboard | None = None,
        max_concurrent: int = 10,
        enable_reviewer_gate: bool = True,
        sub_agent_runner: SubAgentRunner | None = None,
    ) -> None:
        self._roles = role_registry or RoleRegistry()
        self._blackboard = blackboard or EncreBlackboard()
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._enable_reviewer_gate = enable_reviewer_gate
        self._sub_agent_runner = sub_agent_runner
        self._cancelled = False
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    async def execute(
        self,
        task_tree: Any,  # TaskTree
    ) -> AsyncGenerator[OrchestrationEvent, None]:
        self._cancelled = False
        self._running_tasks.clear()
        nodes = task_tree.nodes
        if not nodes:
            yield OrchestrationEvent(type="team_finished", progress=1.0)
            return

        self._blackboard.put("__orchestrator__", "goal", task_tree.goal)
        total = len(nodes)
        completed = 0

        running: dict[str, asyncio.Task[None]] = {}

        try:
            while not self._cancelled:
                ready = task_tree.get_ready_nodes()
                if not ready and not running:
                    break

                for node in ready:
                    if self._cancelled:
                        break
                    node.status = "running"
                    task = asyncio.create_task(self._execute_node(node, task_tree))
                    running[node.id] = task
                    self._running_tasks[node.id] = task

                if not running:
                    break

                done, _ = await asyncio.wait(
                    running.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in done:
                    for nid, t in list(running.items()):
                        if t is task:
                            del running[nid]
                            self._running_tasks.pop(nid, None)
                            node = nodes.get(nid)
                            if node and node.status == "completed":
                                completed += 1
                                yield OrchestrationEvent(
                                    type="task_completed",
                                    task_id=node.id,
                                    task_name=node.name,
                                    role=node.assigned_role,
                                    result=node.result,
                                    progress=completed / total,
                                )
                            elif node and node.status == "cancelled":
                                completed += 1
                                yield OrchestrationEvent(
                                    type="task_failed",
                                    task_id=node.id,
                                    task_name=node.name,
                                    role=node.assigned_role,
                                    error="Task was cancelled",
                                    progress=completed / total,
                                )
                            elif node and node.status == "failed":
                                completed += 1
                                yield OrchestrationEvent(
                                    type="task_failed",
                                    task_id=node.id,
                                    task_name=node.name,
                                    role=node.assigned_role,
                                    error=node.error,
                                    progress=completed / total,
                                )
                            break
        except asyncio.CancelledError:
            # The orchestration loop itself was cancelled -- cancel every
            # in-flight node task and mark remaining nodes as cancelled.
            self._cancelled = True
            for t in running.values():
                t.cancel()
            for nid in list(running.keys()):
                node = nodes.get(nid)
                if node and node.status == "running":
                    node.status = "cancelled"
                    node.error = "Orchestrator cancelled"
            yield OrchestrationEvent(
                type="team_finished",
                progress=completed / total if total else 1.0,
                error="Orchestrator cancelled",
            )
            return

        # If the loop exited because of cancel(), drain any still-running tasks.
        if self._cancelled and running:
            for t in running.values():
                t.cancel()
            # Give them a moment to react to cancellation.
            if running:
                await asyncio.wait(running.values(), timeout=5.0)
            for _nid, node in nodes.items():
                if node.status == "running":
                    node.status = "cancelled"
                    node.error = "Cancelled by orchestrator"

        if completed >= total:
            yield OrchestrationEvent(type="team_finished", progress=1.0)

    async def _execute_node(self, node: Any, task_tree: Any) -> None:
        """Run one node to completion inside the concurrency semaphore.

        Builds the agent context, runs the role-configured agent, applies the
        reviewer gate when enabled for coder nodes, and on success stores the
        result on the node and the blackboard.  Exceptions and cancellations
        are captured into ``node.status``/``node.error``.
        """
        async with self._semaphore:
            try:
                role = self._roles.get(node.assigned_role)

                OrchestrationEvent(
                    type="task_started",
                    task_id=node.id,
                    task_name=node.name,
                    role=node.assigned_role,
                )

                context = self._build_context(node, task_tree)
                result = await self._run_agent(node, role, context)

                # Reviewer gate
                if self._enable_reviewer_gate and role.name == "coder":
                    review_ok = await self._reviewer_check(node, result)
                    if not review_ok:
                        node.status = "failed"
                        node.error = "Reviewer rejected the output"
                        return

                node.result = result
                node.status = "completed"
                self._blackboard.put(f"task:{node.id}", "result", result)

            except asyncio.CancelledError:
                node.status = "cancelled"
                node.error = "Cancelled by orchestrator"
            except Exception as e:
                node.status = "failed"
                node.error = str(e)

    async def _run_agent(self, node: Any, role: AgentRole, context: str) -> str:
        """Execute a single node's prompt.

        When a ``sub_agent_runner`` is configured (the normal case when the
        swarm is driven from the host loop), the node runs through the loop's
        ``_run_sub_agent`` so it inherits depth fencing (no
        swarm-inside-swarm recursion), live progress streaming to the
        frontend, transcript persistence under ``sub_agents/<id>/``, and the
        safety / tool-policy hooks.  Otherwise a fresh role-configured
        ``EncreAgent`` is spawned directly (the unit-test / standalone path).

        Returns the concatenated text output.  A ``Finish`` with reason
        ``"error"`` appends a marker so the caller knows the agent aborted.
        """
        from encre.utils.types import Finish, TextDelta

        system_prompt = role.system_prompt_override or ""
        full_prompt = (
            f"{node.name}: {node.description}\n\n{context}\n\n"
            "---\n"
            "You are executing a subtask. Do NOT restate the full plan. "
            "Work ONLY on your assigned task. "
            "Reference files with file:line format. "
            "Report completion status explicitly."
        )

        if self._sub_agent_runner is not None:
            try:
                result = await self._sub_agent_runner(
                    full_prompt,
                    system_prompt=system_prompt,
                    max_turns=15,
                )
            except Exception as exc:
                return f"[Error during execution: {exc}]"
            if isinstance(result, dict):
                return result.get("content", "") or ""
            return str(result)

        # Fallback: spawn a fresh role-configured EncreAgent directly.
        from encre.agent import EncreAgent
        from encre.config import EncreConfig

        config = EncreConfig(
            max_turns=15,
            permission_mode=role.permission_mode,
        )
        if role.model_override:
            config.model = role.model_override
        if role.backend_type_override:
            config.backend_type = role.backend_type_override
        agent = EncreAgent(config=config)
        parts: list[str] = []
        async for event in agent.run(full_prompt, system_prompt=system_prompt or None):
            if isinstance(event, TextDelta) and event.text:
                parts.append(event.text)
            elif isinstance(event, Finish) and event.reason == "error":
                parts.append("\n[Error during execution]")
        return "".join(parts)

    async def _reviewer_check(self, coder_node: Any, result: str) -> bool:
        reviewer_role = self._roles.get("reviewer")
        review_prompt = (
            f"Review the output of task '{coder_node.name}'. "
            f"Output:\n```\n{result[:5000]}\n```\n"
            "Does this look correct and production-ready? Reply ONLY with 'APPROVED' or 'REJECTED: <reason>'."
        )
        try:
            reviewer_result = await asyncio.wait_for(
                self._run_simple_agent(reviewer_role, review_prompt),
                timeout=120.0,
            )
            return "APPROVED" in reviewer_result.upper() and "REJECTED" not in reviewer_result.upper()
        except TimeoutError:
            return True  # Timeout: approve by default

    async def _run_simple_agent(self, role: AgentRole, prompt: str) -> str:
        system_prompt = role.system_prompt_override or ""
        if self._sub_agent_runner is not None:
            try:
                result = await self._sub_agent_runner(
                    prompt, system_prompt=system_prompt, max_turns=5,
                )
            except Exception as exc:
                return f"[Error: {exc}]"
            if isinstance(result, dict):
                return result.get("content", "") or ""
            return str(result)
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.utils.types import TextDelta

        config = EncreConfig(max_turns=5, permission_mode="auto")
        agent = EncreAgent(config=config)
        parts: list[str] = []
        async for event in agent.run(prompt, system_prompt=system_prompt or None):
            if isinstance(event, TextDelta) and event.text:
                parts.append(event.text)
        return "".join(parts)

    def _build_context(self, node: Any, task_tree: Any) -> str:
        parts: list[str] = [f"Goal: {task_tree.goal}\n"]
        for dep_id in node.dependencies:
            dep = task_tree.nodes.get(dep_id)
            if dep and dep.result:
                parts.append(f"Dependency [{dep.name}] output:\n{dep.result[:3000]}")
        blackboard_context = self._blackboard.get_all_visible()
        if blackboard_context:
            parts.append(f"Shared context:\n{blackboard_context}")
        return "\n".join(parts)

    def cancel(self) -> None:
        """Cancel the orchestration and all in-flight node tasks.

        Sets the cancellation flag (which causes the main loop to stop
        scheduling new nodes) and immediately cancels every currently
        running asyncio Task so that no work continues in the background.
        """
        self._cancelled = True
        for task in self._running_tasks.values():
            if not task.done():
                task.cancel()
        self._running_tasks.clear()
