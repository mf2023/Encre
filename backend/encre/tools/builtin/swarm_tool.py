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

"""Swarm tool -- multi-agent orchestration with role specialisation.

Unlike the lighter-weight ``workflow`` tool (which decomposes a goal and runs
each task as a plain sub-agent in dependency order), the swarm tool runs the
goal through ``EncreSwarmSession``: each task is assigned a specialised role
(architect / coder / reviewer / tester / researcher / debugger), coder output
passes a reviewer gate, results are shared through a blackboard, and when two
or more results are produced a proposal-vote consensus step runs.

Every teammate executes via the host loop's ``_run_sub_agent`` (passed as the
``sub_agent_runner``), so swarm participants inherit the same infrastructure
as a normal ``agent``-tool sub-agent: depth fencing (no swarm-inside-swarm
recursion), live progress streaming to the frontend, transcript persistence
under ``sub_agents/<id>/``, and the safety / tool-policy hooks.
"""

import contextlib
import uuid
from typing import Any

from encre.logging_config import get_logger
from encre.swarm import EncreSwarmSession
from encre.tools.base import build_tool

logger = get_logger(__name__)


def _consensus_to_dict(cr: Any) -> dict[str, Any]:
    """Best-effort serialisation of a ``ConsensusResult`` for the frontend."""
    try:
        if hasattr(cr, "to_dict"):
            return cr.to_dict()
        return {
            "outcome": getattr(cr, "outcome", ""),
            "vote_counts": getattr(cr, "vote_counts", {}),
        }
    except Exception:
        return {}


async def _swarm_execute(**kwargs: Any) -> Any:
    """Execute a goal as a role-specialised multi-agent swarm."""
    goal = kwargs.get("goal", "")
    progress_callback = kwargs.get("progress_callback")

    from encre.tools.builtin.agent import _resolve_loop

    loop = _resolve_loop()
    if loop is None:
        return {"content": "Error: No active agent loop found", "messages": []}

    # Depth fence: a sub-agent (depth > 0) must not spawn a swarm, which would
    # itself spawn sub-agents -- the runtime only allows one level of
    # delegation.  This mirrors the ``agent`` tool's hard fence and is also
    # enforced by the pre-tool policy hook in ``tools.builtin.agent``.
    if getattr(loop, "sub_agent_depth", 0) > 0:
        return {
            "content": (
                "Error: swarm orchestration cannot be invoked from a sub-agent. "
                "The runtime only allows one level of delegation. Complete the "
                "assigned task with your own tools and return the result."
            ),
            "messages": [],
        }

    logger.info("[swarm] goal=%s", goal[:200])

    workflow_id = f"swarm_{uuid.uuid4().hex[:10]}"

    async def _runner(
        prompt: str,
        *,
        system_prompt: str = "",
        max_turns: int = 15,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        """Delegate a swarm task to the host loop's ``_run_sub_agent``."""
        return await loop._run_sub_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            max_turns=max_turns,
            progress_callback=progress_callback,
        )

    async def _on_event(event: Any) -> None:
        """Map a ``SwarmEvent`` onto the frontend progress-callback protocol."""
        if progress_callback is None:
            return
        msg: dict[str, Any] = {"role": "swarm", "workflow_id": workflow_id}
        et = event.type
        if et == "planning":
            msg.update({
                "type": "workflow_started",
                "goal": goal,
                "progress": event.progress,
            })
        elif et == "task_started":
            msg.update({
                "type": "workflow_task",
                "task_id": event.task_id,
                "task_name": event.task_name,
                "role": event.role,
                "status": "started",
            })
        elif et == "task_completed":
            msg.update({
                "type": "workflow_task",
                "task_id": event.task_id,
                "task_name": event.task_name,
                "role": event.role,
                "status": "completed",
                "result": (event.result or "")[:500],
            })
        elif et == "task_failed":
            msg.update({
                "type": "workflow_task",
                "task_id": event.task_id,
                "task_name": event.task_name,
                "status": "failed",
                "error": event.error,
            })
        elif et == "consensus":
            msg.update({
                "type": "swarm_consensus",
                "consensus": _consensus_to_dict(event.consensus),
            })
        elif et == "team_finished":
            msg.update({
                "type": "workflow_completed",
                "summary": event.result,
                "progress": event.progress,
                "success": True,
            })
        elif et == "error":
            msg.update({
                "type": "workflow_completed",
                "error": event.error,
                "success": False,
            })
        else:
            return
        with contextlib.suppress(Exception):
            await progress_callback([msg])

    session = EncreSwarmSession(
        agent=None,
        goal=goal,
        sub_agent_runner=_runner,
    )

    try:
        result = await session.execute(goal=goal, on_event=_on_event)
    except Exception as exc:
        logger.exception("[swarm] execution failed")
        return {"content": f"Swarm failed: {exc}", "messages": []}

    # Format the consolidated result for the parent model.
    lines = [f"## Swarm Result: {goal}\n"]
    lines.append(result.summary)
    lines.append("")
    lines.append(
        f"Tasks: {result.completed_tasks}/{result.total_tasks} succeeded, "
        f"{result.failed_tasks} failed in {result.elapsed_seconds:.1f}s"
    )
    if result.results:
        lines.append("\n### Per-task results:")
        for tid, res in result.results.items():
            lines.append(f"- [{tid}] {res[:300]}")
    if result.consensus is not None:
        cr = _consensus_to_dict(result.consensus)
        lines.append(f"\n### Consensus: {cr.get('outcome', 'n/a')}")
        lines.append(f"Votes: {cr.get('vote_counts', {})}")
    return {"content": "\n".join(lines), "messages": []}


EncreSwarmTool = build_tool(
    name="swarm",
    description=(
        "Orchestrate a complex goal as a role-specialised multi-agent swarm "
        "with built-in review and consensus.\n\n"
        "WHAT: decomposes the goal into a DAG of tasks, assigns each a "
        "specialised role (architect / coder / reviewer / tester / researcher "
        "/ debugger), runs tasks with dependency-aware concurrency, gates "
        "coder output through a reviewer, shares context via a blackboard, "
        "and runs a proposal-vote consensus step when two or more agents "
        "produce results.\n"
        "WHEN to use: large goals that benefit from role specialisation and "
        "cross-agent verification (e.g. ship a feature end-to-end with design "
        "+ impl + review + test).\n"
        "WHEN NOT to use: for simpler multi-step goals without role "
        "specialisation prefer the 'workflow' tool; for independent parallel "
        "sub-tasks with no review gate use the 'agent' tool.\n"
        "TIPS: state the desired end result and acceptance criteria "
        "explicitly; the planner infers roles from the goal, so a precise "
        "goal yields a cleaner task decomposition.\n"
        "PITFALLS: swarms cannot be spawned from inside a sub-agent (one "
        "level of delegation only); swarms are heavier than workflows -- "
        "don't use one for a 2-step task.\n"
        "IMPORTANT: The goal MUST be written in English -- all swarm "
        "participants think, reason, and respond in English for reliable "
        "state matching and output parsing."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "The complete goal to accomplish with a multi-agent swarm. "
                    "MUST be written in English -- swarm participants think and "
                    "respond in English for reliable parsing. Be specific about "
                    "the desired end result, scope, and any acceptance criteria "
                    "so the planner can assign the right roles."
                ),
            },
        },
        "required": ["goal"],
    },
    execute=_swarm_execute,
    intents=["general", "coding", "system"],
    category="delegation",
    semantic_type="orchestrate",
)
