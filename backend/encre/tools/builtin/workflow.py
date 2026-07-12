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

"""Workflow tool -- plans and executes a DAG of sub-tasks.

When the agent encounters a complex, multi-step goal, it can use this tool
to decompose the goal into a task tree and execute each task as an
independent sub-agent run. Tasks with satisfied dependencies run in
parallel, and progress is streamed to the frontend in real time.
"""

import asyncio
import uuid
from typing import Any

from encre.logging_config import get_logger
from encre.swarm.planner import EncreTaskPlanner, TaskNode
from encre.tools.base import build_tool

logger = get_logger(__name__)


async def _workflow_execute(**kwargs: Any) -> Any:
    """Execute a complex goal by decomposing it into a DAG of sub-tasks.

    The workflow tool:
    1. Plans: decomposes the goal into a TaskTree
    2. Executes: runs each task as a sub-agent in dependency order
    3. Reports: yields progress events to the frontend
    """
    goal = kwargs.get("goal", "")
    progress_callback = kwargs.get("progress_callback")

    from encre.tools.builtin.agent import _resolve_loop

    loop = _resolve_loop()
    if loop is None:
        return {"content": "Error: No active agent loop found", "messages": []}

    logger.info("[workflow] goal=%s", goal[:200])

    # Phase 1: Plan
    planner = EncreTaskPlanner()
    tree = planner.plan(goal)

    workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
    all_messages: list[dict[str, Any]] = []
    node_results: dict[str, str] = {}
    failed_ids: set[str] = set()
    skipped_ids: set[str] = set()

    # Notify frontend: workflow started
    if progress_callback:
        await progress_callback([{
            "role": "workflow",
            "type": "workflow_started",
            "workflow_id": workflow_id,
            "goal": tree.goal,
            "total_tasks": len(tree.nodes),
            "task_ids": list(tree.nodes.keys()),
        }])

    # Phase 2: Execute tasks in dependency order
    completed: set[str] = set()
    enqueued: set[str] = set()

    # Seed entry nodes
    ready = list(tree.entry_nodes)

    while True:
        # Collect executable tasks (all deps satisfied)
        executable: list[tuple[str, TaskNode]] = []
        for nid in ready:
            if nid in enqueued or nid in completed or nid in failed_ids:
                continue
            node = tree.nodes.get(nid)
            if node is None:
                continue
            deps_met = all(
                dep in completed or tree.nodes[dep].status == "completed"
                for dep in node.dependencies
            )
            if not deps_met:
                continue
            failed_deps = [d for d in node.dependencies if d in failed_ids]
            if failed_deps:
                node.status = "skipped"
                node.error = f"dependency failed: {failed_deps[0]}"
                skipped_ids.add(nid)
                enqueued.add(nid)
                if progress_callback:
                    await progress_callback([{
                        "role": "workflow",
                        "type": "workflow_task",
                        "workflow_id": workflow_id,
                        "task_id": nid,
                        "task_name": node.name,
                        "status": "skipped",
                    }])
                continue
            executable.append((nid, node))

        if not executable:
            remaining = set(tree.nodes.keys()) - enqueued
            if remaining:
                ready = list(remaining)
                continue
            break

        # Mark as enqueued and notify
        for nid, node in executable:
            enqueued.add(nid)
            node.status = "running"
            if progress_callback:
                await progress_callback([{
                    "role": "workflow",
                    "type": "workflow_task",
                    "workflow_id": workflow_id,
                    "task_id": nid,
                    "task_name": node.name,
                    "status": "started",
                }])

        # Execute ready tasks in parallel as sub-agents
        async def _run_task_node(
            nid: str, node: TaskNode
        ) -> tuple[str, str, dict[str, Any] | None]:
            """Run task node.

            Args:
                nid: Description of the nid parameter.
                node: Description of the node parameter.
            """
            prompt = f"## Task: {node.name}\n\n{node.description}\n\nComplete this task thoroughly. Report results clearly."
            try:
                sub_result = await loop._run_sub_agent(
                    prompt=prompt,
                    max_turns=0,
                    progress_callback=None,  # sub-agent events stream via normal channels
                )
                msgs = sub_result.get("messages", []) if isinstance(sub_result, dict) else []
                content = sub_result.get("content", "") if isinstance(sub_result, dict) else str(sub_result)
                return nid, content, msgs
            except Exception as exc:
                return nid, f"FAILED: {exc}", None

        tasks = {
            nid: asyncio.create_task(_run_task_node(nid, node))
            for nid, node in executable
        }

        for nid, task in tasks.items():
            try:
                tid, result, messages = await task
            except Exception as exc:
                tid = nid
                result = f"FAILED: {exc}"
                messages = None

            completed.add(tid)
            node = tree.nodes[tid]

            if messages:
                all_messages.extend(messages)

            if result.startswith("FAILED: "):
                node.status = "failed"
                node.error = result[7:]
                failed_ids.add(tid)
                status = "failed"
            else:
                node.status = "completed"
                node.result = result
                node_results[tid] = result
                status = "completed"

            if progress_callback:
                await progress_callback([{
                    "role": "workflow",
                    "type": "workflow_task",
                    "workflow_id": workflow_id,
                    "task_id": tid,
                    "task_name": node.name,
                    "status": status,
                }])

        # Collect newly ready nodes
        ready = [
            nid for nid in tree.nodes
            if nid not in enqueued and nid not in completed
        ]

    # Phase 3: Aggregate results
    success = len(failed_ids) == 0
    result_parts = [f"## Workflow Results: {tree.goal}\n"]
    for _nid, node in tree.nodes.items():
        status_icon = "✓" if node.status == "completed" else "✗" if node.status == "failed" else "--"
        result_parts.append(f"- {status_icon} **{node.name}**: {node.result[:200] if node.result else node.status}")

    if progress_callback:
        await progress_callback([{
            "role": "workflow",
            "type": "workflow_completed",
            "workflow_id": workflow_id,
            "goal": tree.goal,
            "success": success,
            "completed_count": sum(1 for n in tree.nodes.values() if n.status == "completed"),
            "failed_count": len(failed_ids),
            "skipped_count": len(skipped_ids),
        }])

    return {
        "content": "\n".join(result_parts),
        "messages": all_messages,
    }


EncreWorkflowTool = build_tool(
    name="workflow",
    description=(
        "Execute a complex, multi-step goal by orchestrating sub-agent tasks in a DAG. "
        "Use this when the goal requires multiple independent or sequential steps, "
        "like building a full app, researching a topic with multiple angles, or "
        "refactoring a codebase. Each step runs as a fully-capable sub-agent."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The complete goal to accomplish. Be specific about what "
                               "the end result should look like.",
            },
        },
        "required": ["goal"],
    },
    execute=_workflow_execute,
    intents=["general", "coding", "system"],
    category="delegation",
    semantic_type="orchestrate",
)
