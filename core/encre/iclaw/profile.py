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

"""iClaw launcher profile: self-improvement add-ons over the core server.

The former ``IClawEngine`` re-assembled the entire runtime (sessions,
router, WS transport, scheduler, hooks, safety, plugins) that
:class:`encre.server.app.EncreServer` already provides.  That duplication
is gone: the daemon now boots through the core server launcher and this
profile layers only what is unique to iClaw:

- learning / evolution / reflex / metacognition / feedback subsystems
- memory consolidator and goal runner
- the post-run self-improvement pipeline
- housekeeping loops (cleanup, heartbeat, reflex scan)
- the channel submit pipeline (hooks + compaction + learning feed)
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from encre.agent import EncreAgent
from encre.compact.engine import EncreCompactEngine
from encre.compact.strategies import EncreMultiStagePipeline
from encre.config import EncreConfig, get_data_dir
from encre.goal import (
    EncreGoalRunner,
    GoalDefinition,
    GoalEvent,
    GoalResult,
    GoalStatus,
)
from encre.iclaw.post_run import PostRunOrchestrator, PostRunPipeline, RunSummary
from encre.improve.evolution.config import EvolutionConfig  # noqa: F401  (re-exported for profile consumers)
from encre.improve.evolution.learner import EncreEvolutionLearner
from encre.improve.evolution.meta import EncreMetaCognition
from encre.improve.evolution.reflex import EncreReflexLoop
from encre.improve.feedback.learner import EncreFeedbackLearner
from encre.improve.learning.consolidator import MemoryConsolidator
from encre.improve.learning.engine import LearningEngine
from encre.protocol.session_router import EventRouter
from encre.scheduler import EncreScheduler, ScheduledJob
from encre.swarm.blackboard import EncreBlackboard
from encre.swarm.consensus import EncreConsensus
from encre.swarm.orchestrator import EncreOrchestrator  # noqa: F401  (swarm surface)
from encre.swarm.planner import EncreTaskPlanner
from encre.swarm.roles import AgentRole, RoleRegistry  # noqa: F401  (AgentRole re-exported)
from encre.swarm.session import EncreSwarmSession
from encre.utils.types import (
    AgentEvent,
    Finish,
    ToolResult,
)

logger = logging.getLogger("encre.iclaw")


@dataclass
class DaemonStats:
    started_at: float = 0.0
    sessions_created: int = 0
    sessions_completed: int = 0
    jobs_executed: int = 0
    skills_generated: int = 0
    consolidation_runs: int = 0
    swarm_tasks_executed: int = 0
    compact_runs: int = 0
    evolution_observations: int = 0
    reflex_evaluations: int = 0
    feedback_records: int = 0
    errors: int = 0


class IclawProfile:
    """iClaw add-on profile attached to a running :class:`EncreServer`.

    Owns only the self-improvement and autonomy subsystems; transport,
    sessions, and scheduling come from the server.  Mirrors the public
    surface of the former ``IClawEngine`` (submit / run_goal / run_swarm /
    schedule_job / stats) so callers keep working unchanged.
    """

    def __init__(
        self,
        agent: EncreAgent,
        *,
        router: EventRouter,
        scheduler: EncreScheduler,
        max_concurrent: int = 20,
        consolidation_interval: int = 3600,
        enable_compact: bool = True,
        enable_evolution: bool = True,
        enable_reflex: bool = True,
        enable_metacognition: bool = True,
        enable_feedback: bool = True,
        enable_swarm: bool = True,
    ) -> None:
        self._agent = agent
        self._router = router
        self._scheduler = scheduler
        self._max_concurrent = max_concurrent
        self._consolidation_interval = consolidation_interval
        self._running = False

        # 鈹€鈹€ Compact engine 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._compact_engine: EncreCompactEngine | None = None
        self._enable_compact = enable_compact
        self._compact_max_tokens = 128000

        # 鈹€鈹€ Learning subsystems 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._learning_engine: LearningEngine | None = None
        self._consolidator: MemoryConsolidator | None = None
        self._evolution_learner: EncreEvolutionLearner | None = None
        self._reflex_loop: EncreReflexLoop | None = None
        self._meta_cognition: EncreMetaCognition | None = None
        self._feedback_learner: EncreFeedbackLearner | None = None

        # 鈹€鈹€ Swarm / multi-agent subsystems 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._swarm_session: EncreSwarmSession | None = None
        self._consensus: EncreConsensus | None = None
        self._blackboard: EncreBlackboard | None = None
        self._task_planner: EncreTaskPlanner | None = None
        self._role_registry: RoleRegistry | None = None

        # 鈹€鈹€ Goal runner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._goal_runner: EncreGoalRunner | None = None

        # 鈹€鈹€ Lifecycle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._cleanup_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reflex_scan_task: asyncio.Task[None] | None = None

        # 鈹€鈹€ Stats 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self.stats = DaemonStats()

        # 鈹€鈹€ Post-run pipeline 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._post_run: PostRunOrchestrator | None = None

    @property
    def is_running(self) -> bool:
        """Return ``True`` while the profile is running."""
        return self._running

    @property
    def session_manager(self):
        """The server-owned session manager (compat accessor)."""
        return self._router.session_manager

    # 鈹€鈹€ Start / Stop 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def start(self) -> None:
        """Initialise the iClaw-unique subsystems and background loops.

        Transport, sessions, and scheduler come from the server launcher;
        only the self-improvement add-ons are assembled here.
        """
        if self._running:
            return
        self._running = True
        self.stats.started_at = time.time()
        agent = self._agent
        data_dir = get_data_dir()

        # 鈹€鈹€ Compact engine 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if self._enable_compact:
            self._compact_engine = EncreCompactEngine(
                strategy=EncreMultiStagePipeline(),
            )

        # 鈹€鈹€ Learning engine 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._learning_engine = LearningEngine(agent)
        await self._learning_engine.start()

        # 鈹€鈹€ Evolution learner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        evo_path = data_dir / "evolution" / "state.json"
        evo_path.parent.mkdir(parents=True, exist_ok=True)
        self._evolution_learner = EncreEvolutionLearner(storage_path=str(evo_path))

        # 鈹€鈹€ Reflex loop 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._reflex_loop = EncreReflexLoop(enabled=True)
        self._reflex_scan_task = asyncio.create_task(self._reflex_scan_loop())

        # 鈹€鈹€ Metacognition 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._meta_cognition = EncreMetaCognition()

        # 鈹€鈹€ Feedback learner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        fb_path = data_dir / "feedback" / "corrections.json"
        fb_path.parent.mkdir(parents=True, exist_ok=True)
        self._feedback_learner = EncreFeedbackLearner(storage_path=str(fb_path))

        # 鈹€鈹€ Memory consolidator 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if self._consolidation_interval > 0:
            self._consolidator = MemoryConsolidator(
                agent,
                interval=self._consolidation_interval,
            )
            await self._consolidator.start()

        # 鈹€鈹€ Goal runner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._goal_runner = EncreGoalRunner(
            config=agent.config,
            tool_registry=agent.tool_registry,
            hook_system=agent.hook_system,
            safety=agent.safety,
            memory_system=getattr(agent, "memory_system", None),
            skill_registry=getattr(agent, "skill_registry", None),
            telemetry=getattr(agent, "telemetry", None),
        )

        # 鈹€鈹€ Swarm subsystems 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._blackboard = EncreBlackboard()
        self._consensus = EncreConsensus()
        self._task_planner = EncreTaskPlanner()
        self._role_registry = RoleRegistry()
        self._swarm_session = EncreSwarmSession(
            agent=agent,
            max_concurrent=min(10, self._max_concurrent),
        )

        # 鈹€鈹€ Post-run self-improvement pipeline 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        soul_system = getattr(agent, "soul_system", None)
        pipeline = PostRunPipeline(
            agent,
            learning_engine=self._learning_engine,
            evolution_learner=self._evolution_learner,
            feedback_learner=self._feedback_learner,
            consolidator=self._consolidator,
            soul_system=soul_system,
            analyze_fn=self._make_analyze_fn(),
        )
        self._post_run = PostRunOrchestrator(pipeline)

        # 鈹€鈹€ Background housekeeping 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            "iClaw profile ready -- consolidation=%ds evolution=%s reflex=%s "
            "metacognition=%s feedback=%s swarm=%s",
            self._consolidation_interval,
            self._evolution_learner is not None,
            self._reflex_loop is not None,
            self._meta_cognition is not None,
            self._feedback_learner is not None,
            self._swarm_session is not None,
        )

    async def stop(self) -> None:
        """Shut down the profile's subsystems and background tasks."""
        if not self._running:
            return
        self._running = False
        logger.info("Shutting down iClaw profile...")

        for task in (self._cleanup_task, self._heartbeat_task, self._reflex_scan_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        if self._consolidator:
            await self._consolidator.stop()
            self._consolidator = None
        if self._learning_engine:
            await self._learning_engine.stop()
            self._learning_engine = None

        logger.info("iClaw profile stopped")

    # 鈹€鈹€ Submit pipeline 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def submit(
        self,
        channel_name: str,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Submit a one-shot prompt to a channel and return a session id."""
        result = await self._router.submit(
            channel_name, prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        )
        self.stats.sessions_created += 1
        return result

    async def submit_stream(
        self,
        channel_name: str,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Stream an agent run, wrapped with the self-improvement pipeline."""
        self.stats.sessions_created += 1

        # 鈹€鈹€ Hook: pre-turn 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        # Fire the pre-turn hook (best effort) before any model work.
        hook_system = getattr(self._agent, "hook_system", None)
        if hook_system:
            with contextlib.suppress(Exception):
                await hook_system.emit_turn_start(turn=0, prompt=prompt)

        # 鈹€鈹€ Compact: check if context needs compaction 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if self._compact_engine and len(prompt) > 50000:
            try:
                messages = [{"role": "user", "content": prompt}]
                if await self._compact_engine.should_compact(messages, self._compact_max_tokens):
                    compressed = await self._compact_engine.compact(messages, self._compact_max_tokens)
                    if compressed and len(compressed) > 0:
                        prompt = compressed[0].get("content", prompt)
                        self.stats.compact_runs += 1
                        logger.debug("Context compacted: %d chars -> %d chars",
                                     len(prompt), len(compressed[0].get("content", "")))
            except Exception:
                pass

        collected_events: list[AgentEvent] = []
        tool_names: list[str] = []
        stream_start = time.monotonic()
        async for event in self._router.submit_stream(
            channel_name, prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        ):
            if isinstance(event, ToolResult):
                tool_names.append(getattr(event, "id", "unknown"))
                if self._evolution_learner:
                    self.stats.evolution_observations += 1
            elif isinstance(event, Finish):
                self.stats.sessions_completed += 1

            collected_events.append(event)
            yield event

        stream_duration = time.monotonic() - stream_start

        # 鈹€鈹€ Post-run self-improvement pipeline 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if self._post_run is not None:
            try:
                pr_result = await self._post_run.collect_and_process(
                    prompt, collected_events,
                    duration_seconds=stream_duration,
                )
                if pr_result.get("completed"):
                    self.stats.skills_generated = pr_result.get("stages", {}).get("learning", {}).get(
                        "skills_generated", self.stats.skills_generated
                    )
            except Exception:
                pass

        # 鈹€鈹€ Hook: post-turn 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if hook_system:
            with contextlib.suppress(Exception):
                await hook_system.emit_turn_end(turn=0, event_count=len(tool_names))

    # 鈹€鈹€ Goal execution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def run_goal(
        self,
        description: str,
        success_criteria: str,
        *,
        max_attempts: int = 20,
        timeout_seconds: int = 3600,
        on_progress: Callable[[GoalEvent], None] | None = None,
    ) -> GoalResult:
        """Run a goal-driven autonomous session via the goal runner."""
        if self._goal_runner is None:
            return GoalResult(
                status=GoalStatus.FAILED,
                summary="Goal runner not available",
            )
        goal = GoalDefinition(
            description=description,
            success_criteria=success_criteria,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )
        return await self._goal_runner.run(goal, on_attempt=on_progress)

    # 鈹€鈹€ Swarm / multi-agent operations 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def run_swarm(
        self,
        goal: str,
        *,
        max_concurrent: int = 5,
        _enable_reviewer: bool = True,
        _timeout_seconds: float = 3600.0,
        on_event: Callable[[Any], None] | None = None,
    ) -> Any:
        """Execute a goal across the swarm, returning its result dict."""
        if self._swarm_session is None:
            return {"error": "Swarm session not available"}
        result = await self._swarm_session.execute(
            goal=goal,
            max_concurrent=max_concurrent,
            on_event=on_event,
        )
        self.stats.swarm_tasks_executed += 1
        return result

    async def run_swarm_stream(
        self,
        goal: str,
    ) -> AsyncGenerator[Any, None]:
        """Stream a swarm goal execution, yielding swarm events."""
        if self._swarm_session is None:
            return
        async for event in self._swarm_session.execute_streaming(goal=goal):
            yield event
            self.stats.swarm_tasks_executed += 1

    def create_consensus_proposal(
        self,
        title: str,
        description: str,
        options: list[str],
        proposed_by: str = "",
    ) -> Any:
        """Create a swarm consensus proposal."""
        if self._consensus is None:
            return None
        return self._consensus.create_proposal(title, description, options, proposed_by)

    def blackboard_put(self, namespace: str, key: str, value: Any, owner: str = "") -> int | None:
        """Write a value to the swarm blackboard; return its slot id."""
        if self._blackboard is None:
            return None
        return self._blackboard.put(namespace, key, value, owner)

    def blackboard_get(self, namespace: str, key: str) -> Any:
        """Read the first value stored for a blackboard key, or ``None``."""
        if self._blackboard is None:
            return None
        result = self._blackboard.get(namespace, key)
        if result:
            return result[0]
        return None

    # 鈹€鈹€ Scheduled job operations 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def schedule_job(
        self,
        name: str,
        prompt: str,
        cron: str = "",
        fire_at: float | None = None,
        max_failures: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Schedule a recurring/one-shot job via the server scheduler."""
        job_id = self._scheduler.schedule(
            name=name,
            prompt=prompt,
            cron=cron,
            fire_at=fire_at,
            max_failures=max_failures,
            metadata=metadata,
        )
        self.stats.jobs_executed += 1
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a scheduled job by id."""
        return self._scheduler.cancel(job_id)

    def list_jobs(self) -> list[ScheduledJob]:
        """Return all currently scheduled jobs."""
        return self._scheduler.list_jobs()

    # 鈹€鈹€ Stats / Health 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of running counters and uptime stats."""
        now = time.time()
        uptime = now - self.stats.started_at if self.stats.started_at > 0 else 0
        return {
            "uptime_seconds": uptime,
            "uptime_human": self._format_duration(uptime),
            "sessions_created": self.stats.sessions_created,
            "sessions_completed": self.stats.sessions_completed,
            "jobs_executed": self.stats.jobs_executed,
            "skills_generated": self.stats.skills_generated,
            "consolidation_runs": self.stats.consolidation_runs,
            "swarm_tasks_executed": self.stats.swarm_tasks_executed,
            "compact_runs": self.stats.compact_runs,
            "evolution_observations": self.stats.evolution_observations,
            "reflex_evaluations": self.stats.reflex_evaluations,
            "feedback_records": self.stats.feedback_records,
            "errors": self.stats.errors,
            "active_sessions": self._router.session_manager.active_count,
        }

    def get_health(self) -> dict[str, Any]:
        """Return a lightweight health/status summary of the profile."""
        return {
            "status": "ok" if self._running else "stopped",
            "running": self._running,
            "uptime_seconds": time.time() - self.stats.started_at if self.stats.started_at > 0 else 0,
            "active_sessions": self._router.session_manager.active_count,
            "scheduled_jobs": len(self.list_jobs()),
            "subsystems": {
                "evolution": self._evolution_learner is not None,
                "reflex": self._reflex_loop is not None,
                "metacognition": self._meta_cognition is not None,
                "feedback": self._feedback_learner is not None,
                "swarm": self._swarm_session is not None,
                "scheduler": self._scheduler is not None,
                "learning": self._learning_engine is not None,
                "consolidator": self._consolidator is not None,
                "goals": self._goal_runner is not None,
            },
        }

    # 鈹€鈹€ Internal loops 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _reflex_scan_loop(self) -> None:
        """Background loop that periodically marks reflex evaluation runs."""
        while self._running and self._reflex_loop:
            await asyncio.sleep(900)
            if not self._running:
                break
            if self._evolution_learner:
                self.stats.reflex_evaluations += 1

    async def _cleanup_loop(self, session_manager=None) -> None:
        """Background loop that periodically evicts idle sessions."""
        mgr = session_manager or self._router.session_manager
        while self._running:
            await asyncio.sleep(600)
            if not self._running:
                break
            try:
                removed = await mgr.cleanup_idle()
                if removed > 0:
                    logger.info("Cleaned up %d idle session(s)", removed)
            except Exception:
                self.stats.errors += 1

    async def _heartbeat_loop(self) -> None:
        """Background loop that logs periodic daemon heartbeat stats."""
        while self._running:
            await asyncio.sleep(300)
            if not self._running:
                break
            logger.debug(
                "iClaw heartbeat -- sessions=%d jobs=%d evolution=%d",
                self._router.session_manager.active_count,
                len(self.list_jobs()),
                self.stats.evolution_observations,
            )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format a duration in seconds as a compact ``Nh Mm Ss`` string."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    # 鈹€鈹€ LLM-powered run analysis 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _make_analyze_fn(self) -> Callable[[RunSummary], Awaitable[dict[str, Any]]]:
        """Build the LLM-powered run-analysis callable for the post-run pipeline."""
        agent = self._agent

        async def _analyze(summary: RunSummary) -> dict[str, Any]:
            if not summary.tool_calls:
                return {}
            prompt_for_llm = (
                f"Analyze this agent session and extract key learnings:\n\n"
                f"User goal: {summary.prompt[:500]}\n\n"
                f"Tools used ({summary.tool_call_count}): "
                f"{', '.join(sorted(summary.unique_tools))}\n\n"
                f"Repeated patterns: {summary.repeated_patterns[:5] if summary.repeated_patterns else 'none'}\n\n"
                f"Response preview: {summary.text_output[:300]}\n\n"
                f"Extract the following as JSON:\n"
                f'{{"task_summary": "one-sentence summary of what was accomplished",\n'
                f' "user_preferences": ["any user preferences or patterns observed as strings, or empty list"],\n'
                f' "skill_candidates": ["reusable workflows worth saving as skills, or empty list"],\n'
                f' "key_insights": ["any important learnings, or empty list"]}}'
            )
            try:
                backend = agent.loop.backend
                if backend is None:
                    return {}
                result = await backend.chat(
                    messages=[{"role": "user", "content": prompt_for_llm}]
                )
                text = ""
                async for part in result:
                    if hasattr(part, "text") and part.text:
                        text += part.text
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(text[start:end + 1])
                    return {
                        "task_summary": parsed.get("task_summary", ""),
                        "user_preferences": parsed.get("user_preferences", []),
                        "skill_candidates": parsed.get("skill_candidates", []),
                        "key_insights": parsed.get("key_insights", []),
                    }
            except Exception:
                pass
            return {}

        return _analyze


def _make_agent_factory(main_agent: EncreAgent) -> Callable[[dict[str, Any] | None], EncreAgent]:
    """Build a factory that spawns agents sharing the main agent's registry.

    Shared registries (tools/hooks/memory/safety/plugins) come from the
    main agent; per-job model overrides are applied from ``agent_config``.
    """
    def _factory(agent_config: dict[str, Any] | None = None) -> EncreAgent:
        config = replace(main_agent.config)
        if agent_config:
            if agent_config.get("backend_type"):
                config.backend_type = agent_config["backend_type"]
            if agent_config.get("api_key"):
                config.api_key = agent_config["api_key"]
            if agent_config.get("base_url"):
                config.base_url = agent_config["base_url"]
            if agent_config.get("model_id"):
                config.model = agent_config["model_id"]
                config.target_model_ids = [agent_config["model_id"]]
            if agent_config.get("max_tokens"):
                config.max_tokens = agent_config["max_tokens"]
            if agent_config.get("workspace"):
                config.workspace = agent_config["workspace"]
        return EncreAgent(
            config=config,
            tool_registry=main_agent.tool_registry,
            hook_system=main_agent.hook_system,
            memory_system=main_agent.memory_system,
            safety=main_agent.safety,
            plugin_registry=main_agent.plugin_registry,
        )
    return _factory
