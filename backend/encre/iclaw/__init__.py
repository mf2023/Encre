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

"""
iClaw -- Encre headless background daemon for autonomous agent execution.

A self-improving, multi-session agent daemon that runs silently in the
background exposing the full EncreAgent capability over WebSocket and
pluggable external channel adapters (WhatsApp, Telegram, etc.).

Managed by the desktop application -- no terminal interaction, no CLI prompts.

Architecture::

    ┌─────────────────────────────────────────────────────────┐
    │                     iClawDaemon                         │
    │  ┌───────────────────────────────────────────────┐     │
    │  │                iClawEngine                     │     │
    │  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │     │
    │  │  │ Scheduler │ │ Learning │ │ Memory       │  │     │
    │  │  │ (cron)   │ │ (engine) │ │ (consolid.)  │  │     │
    │  │  ├──────────┤ ├──────────┤ ├──────────────┤  │     │
    │  │  │ Evolution│ │ Compact  │ │ Feedback     │  │     │
    │  │  │ Learner  │ │ Engine   │ │ Learner      │  │     │
    │  │  ├──────────┤ ├──────────┤ ├──────────────┤  │     │
    │  │  │ Swarm    │ │ Safety   │ │ Hooks        │  │     │
    │  │  │ Session  │ │ Engine   │ │ System       │  │     │
    │  │  ├──────────┤ ├──────────┤ ├──────────────┤  │     │
    │  │  │ MCP      │ │ Plugin   │ │ Notebook     │  │     │
    │  │  │ Manager  │ │ Registry │ │              │  │     │
    │  │  ├──────────┤ ├──────────┤ ├──────────────┤  │     │
    │  │  │ Channel  │ │ Session  │ │ WebSocket    │  │     │
    │  │  │ Adapters │ │ Manager  │ │ Channel      │  │     │
    │  │  └──────────┘ └──────────┘ └──────────────┘  │     │
    │  └───────────────────────────────────────────────┘     │
    └─────────────────────────────────────────────────────────┘

Capabilities:
  - Multi-session WebSocket server (RFC 6455) for the desktop app
  - Pluggable channel adapters for external platforms
  - Persistent cron-based job scheduling (survives restarts)
  - Automatic skill generation from repeated tool-use patterns
  - Multi-agent swarm orchestration (plan -> execute -> consensus)
  - Context-aware compaction engine (8 strategies + multi-stage pipeline)
  - Evolution learning (success/error tracking, reflex loop, metacognition)
  - Feedback learning (correction record with Jaccard similarity)
  - Full safety engine (permission modes, auto-classifier, container sandbox, SSRF)
  - Hook system (pre/post tool, session lifecycle, turn lifecycle)
  - Plugin registry for third-party extensions
  - MCP (Model Context Protocol) client for external tools
  - Computer/browser automation (Playwright-based)
  - LSP code intelligence (Python/TS/JS/Rust/Go)
  - Interactive notebook kernel
  - Periodic memory consolidation
  - Goal-driven autonomous execution
  - 40+ built-in tools
  - PID file management for desktop lifecycle control
  - File-based logging

The desktop app (Electron) spawns this as a child process::

    python -m encre.iclaw [--host 127.0.0.1] [--port 18791]

Or programmatically::

    from encre.iclaw import iClawDaemon, run_iclaw  # noqa: E402
    daemon = iClawDaemon(agent)
    await daemon.start()
    await daemon.wait()
    await daemon.stop()
"""

import asyncio
import atexit
import contextlib
import json
import logging
import os
import signal
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from encre.agent import EncreAgent
from encre.channels.base import Channel, EventRouter
from encre.channels.websocket import WebSocketChannel
from encre.compact.engine import EncreCompactEngine
from encre.compact.strategies import EncreMultiStagePipeline
from encre.config import EncreConfig, get_data_dir
from encre.evolution.config import EvolutionConfig
from encre.evolution.learner import EncreEvolutionLearner
from encre.evolution.meta import EncreMetaCognition
from encre.evolution.reflex import EncreReflexLoop
from encre.feedback.learner import EncreFeedbackLearner
from encre.gateway.ws_bridge.server import WsBridgeServer
from encre.goal import (
    EncreGoalRunner,
    GoalDefinition,
    GoalEvent,
    GoalResult,
    GoalStatus,
)
from encre.hooks.system import EncreHookSystem
from encre.iclaw.post_run import PostRunOrchestrator, PostRunPipeline, RunSummary
from encre.learning.consolidator import MemoryConsolidator
from encre.learning.engine import LearningEngine
from encre.logging_config import get_logger
from encre.plugins.registry import PluginRegistry
from encre.safety import EncreSafetyEngine
from encre.scheduler import EncreScheduler, ScheduledJob
from encre.server.session_manager import SessionManager
from encre.swarm.blackboard import EncreBlackboard
from encre.swarm.consensus import EncreConsensus
from encre.swarm.orchestrator import EncreOrchestrator
from encre.swarm.planner import EncreTaskPlanner
from encre.swarm.roles import AgentRole, RoleRegistry
from encre.swarm.session import EncreSwarmSession
from encre.tools.registry import ToolRegistry
from encre.utils.types import (
    AgentEvent,
    Finish,
    PermissionRequest,
    TextDelta,
    ThinkingDelta,
    ToolProgress,
    ToolResult,
)

logger = get_logger("encre.iclaw")

__all__ = [
    "DaemonStats",
    "IClawDaemon",
    "IClawEngine",
    "is_running",
    "run_iclaw",
    "stop_daemon",
]

_PID_FILE = "iclaw.pid"
_LOG_FILE = "iclaw.log"


def _data_dir() -> Path:
    """Return the Encre data directory used for daemon state files."""
    # Centralise all pid/log/state files under the Encre data directory.
    return get_data_dir()


def _pid_path() -> Path:
    """Return the path to the daemon PID file."""
    return _data_dir() / _PID_FILE


def _log_path() -> Path:
    """Return the path to the daemon log file."""
    return _data_dir() / _LOG_FILE


def _write_pid(pid: int) -> None:
    """Persist the running daemon's process id to the PID file."""
    _data_dir().mkdir(parents=True, exist_ok=True)
    _pid_path().write_text(str(pid))


def _clear_pid() -> None:
    """Remove the PID file, ignoring any error (e.g. already gone)."""
    with contextlib.suppress(Exception):
        _pid_path().unlink(missing_ok=True)


def _read_pid() -> int | None:
    """Read the daemon PID from disk, or ``None`` if absent/unreadable."""
    try:
        return int(_pid_path().read_text().strip())
    except Exception:
        return None


def is_running() -> bool:
    """Return ``True`` if a daemon PID file points to a live process."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        _clear_pid()
        return False


def stop_daemon() -> bool:
    """Send SIGTERM to the running daemon; return ``True`` if signalled."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        _clear_pid()
        return False


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


def _create_default_agent(config: EncreConfig | None = None) -> EncreAgent:
    """Build an :class:`EncreAgent` with the given or a default config."""
    if config is None:
        config = EncreConfig()
    agent = EncreAgent(config=config)
    return agent


class IClawEngine:
    """Core orchestration engine for the iClaw daemon.

    Manages ALL encre subsystems: session manager, event router, scheduler,
    learning engine, memory consolidator, goal runner, channel adapters,
    swarm orchestrator, compact engine, evolution learner, reflex loop,
    feedback learner, hook system, safety engine, plugin registry,
    MCP manager, and more.
    """

    def __init__(
        self,
        agent: EncreAgent,
        *,
        max_concurrent: int = 20,
        consolidation_interval: int = 3600,
        scheduler_poll_interval: float = 30.0,
        enable_compact: bool = True,
        enable_evolution: bool = True,
        enable_reflex: bool = True,
        enable_metacognition: bool = True,
        enable_feedback: bool = True,
        enable_swarm: bool = True,
        enable_hooks: bool = True,
        compact_max_tokens: int = 128000,
    ) -> None:
        self._agent = agent
        self._max_concurrent = max_concurrent
        self._consolidation_interval = consolidation_interval
        self._scheduler_poll_interval = scheduler_poll_interval
        self._running = False

        # ── Core subsystems ──────────────────────────────────────────
        self._session_manager: SessionManager | None = None
        self._router: EventRouter | None = None
        self._ws_channel: WebSocketChannel | None = None
        self._gateway: Any = None
        self._scheduler: EncreScheduler | None = None
        self._goal_runner: EncreGoalRunner | None = None
        self._compact_engine: EncreCompactEngine | None = None
        self._hook_system: EncreHookSystem | None = None
        self._safety_engine: EncreSafetyEngine | None = None

        # ── Learning subsystems ──────────────────────────────────────
        self._learning_engine: LearningEngine | None = None
        self._consolidator: MemoryConsolidator | None = None
        self._evolution_learner: EncreEvolutionLearner | None = None
        self._reflex_loop: EncreReflexLoop | None = None
        self._meta_cognition: EncreMetaCognition | None = None
        self._feedback_learner: EncreFeedbackLearner | None = None

        # ── Swarm / multi-agent subsystems ───────────────────────────
        self._swarm_session: EncreSwarmSession | None = None
        self._consensus: EncreConsensus | None = None
        self._blackboard: EncreBlackboard | None = None
        self._orchestrator: EncreOrchestrator | None = None
        self._task_planner: EncreTaskPlanner | None = None
        self._role_registry: RoleRegistry | None = None

        # ── Plugin & MCP subsystems ──────────────────────────────────
        self._plugin_registry: PluginRegistry | None = None

        # ── Configuration flags ──────────────────────────────────────
        self._enable_compact = enable_compact
        self._enable_evolution = enable_evolution
        self._enable_reflex = enable_reflex
        self._enable_metacognition = enable_metacognition
        self._enable_feedback = enable_feedback
        self._enable_swarm = enable_swarm
        self._enable_hooks = enable_hooks
        self._compact_max_tokens = compact_max_tokens

        # ── Lifecycle ────────────────────────────────────────────────
        self._shutdown_event: asyncio.Event | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reflex_scan_task: asyncio.Task[None] | None = None

        # ── Stats ────────────────────────────────────────────────────
        self.stats = DaemonStats()

        # ── Post-run pipeline ─────────────────────────────────────────
        self._post_run: PostRunOrchestrator | None = None

    # ── Property accessors ──────────────────────────────────────────────

    @property
    def session_manager(self) -> SessionManager | None:
        """The active session manager, or ``None`` before start."""
        return self._session_manager

    @property
    def router(self) -> EventRouter | None:
        """The event router that dispatches channel submissions."""
        return self._router

    @property
    def scheduler(self) -> EncreScheduler | None:
        """The cron-based job scheduler, or ``None`` before start."""
        return self._scheduler

    @property
    def hook_system(self) -> EncreHookSystem | None:
        """The hook system, or ``None`` if hooks are disabled."""
        return self._hook_system

    @property
    def safety_engine(self) -> EncreSafetyEngine | None:
        """The safety engine guarding tool execution."""
        return self._safety_engine

    @property
    def compact_engine(self) -> EncreCompactEngine | None:
        """The context compaction engine, or ``None`` if disabled."""
        return self._compact_engine

    @property
    def evolution_learner(self) -> EncreEvolutionLearner | None:
        """The evolution learning subsystem, or ``None`` if disabled."""
        return self._evolution_learner

    @property
    def reflex_loop(self) -> EncreReflexLoop | None:
        """The reflex evaluation loop, or ``None`` if disabled."""
        return self._reflex_loop

    @property
    def meta_cognition(self) -> EncreMetaCognition | None:
        """The metacognition subsystem, or ``None`` if disabled."""
        return self._meta_cognition

    @property
    def feedback_learner(self) -> EncreFeedbackLearner | None:
        """The feedback learning subsystem, or ``None`` if disabled."""
        return self._feedback_learner

    @property
    def swarm_session(self) -> EncreSwarmSession | None:
        """The multi-agent swarm session, or ``None`` if disabled."""
        return self._swarm_session

    @property
    def consensus(self) -> EncreConsensus | None:
        """The swarm consensus proposer, or ``None`` if disabled."""
        return self._consensus

    @property
    def blackboard(self) -> EncreBlackboard | None:
        """The swarm shared blackboard, or ``None`` if disabled."""
        return self._blackboard

    @property
    def orchestrator(self) -> EncreOrchestrator | None:
        """The swarm orchestrator, or ``None`` if disabled."""
        return self._orchestrator

    @property
    def task_planner(self) -> EncreTaskPlanner | None:
        """The swarm task planner, or ``None`` if disabled."""
        return self._task_planner

    @property
    def role_registry(self) -> RoleRegistry | None:
        """The swarm agent role registry, or ``None`` if disabled."""
        return self._role_registry

    @property
    def plugin_registry(self) -> PluginRegistry | None:
        """The plugin registry, or ``None`` before start."""
        return self._plugin_registry

    @property
    def learning_engine(self) -> LearningEngine | None:
        """The learning engine, or ``None`` before start."""
        return self._learning_engine

    @property
    def is_running(self) -> bool:
        """Return ``True`` while the engine is running."""
        return self._running

    # ── Start / Stop ───────────────────────────────────────────────────

    async def start(
        self,
        ws_host: str = "127.0.0.1",
        ws_port: int = 18791,
    ) -> None:
        """Initialise and start every subsystem, then open the WS/gateway.

        Idempotent: returns immediately if already running. Wires up the
        safety engine, hooks, plugins, learning/evolution/reflex/feedback
        subsystems, compaction, sessions, event router, WebSocket channel,
        gateway, scheduler, memory consolidator, goal runner, swarm, and the
        post-run self-improvement pipeline.
        """
        if self._running:
            return
        self._running = True
        # Record start time for uptime/heartbeat calculations.
        self.stats.started_at = time.time()

        agent = self._agent
        data_dir = _data_dir()

        # ── 1. Safety engine (full modes) ──────────────────────────
        self._safety_engine = EncreSafetyEngine()
        logger.info("Safety engine initialized")

        # ── 2. Hook system ─────────────────────────────────────────
        if self._enable_hooks:
            self._hook_system = EncreHookSystem()
            self._register_default_hooks()
            logger.info("Hook system initialized")

        # ── 3. Plugin registry ─────────────────────────────────────
        self._plugin_registry = PluginRegistry()
        logger.info("Plugin registry initialized")

        # ── 4. Learning engine ─────────────────────────────────────
        self._learning_engine = LearningEngine(agent)
        await self._learning_engine.start()

        # ── 6. Evolution learner ───────────────────────────────────
        if self._enable_evolution:
            evo_path = data_dir / "evolution" / "state.json"
            evo_path.parent.mkdir(parents=True, exist_ok=True)
            self._evolution_learner = EncreEvolutionLearner(storage_path=str(evo_path))
            logger.info("Evolution learner initialized")

        # ── 7. Reflex loop ─────────────────────────────────────────
        if self._enable_reflex:
            self._reflex_loop = EncreReflexLoop(enabled=True)
            self._reflex_scan_task = asyncio.create_task(self._reflex_scan_loop())
            logger.info("Reflex loop initialized")

        # ── 8. Metacognition ───────────────────────────────────────
        if self._enable_metacognition:
            self._meta_cognition = EncreMetaCognition()
            logger.info("Metacognition initialized")

        # ── 9. Feedback learner ────────────────────────────────────
        if self._enable_feedback:
            fb_path = data_dir / "feedback" / "corrections.json"
            fb_path.parent.mkdir(parents=True, exist_ok=True)
            self._feedback_learner = EncreFeedbackLearner(storage_path=str(fb_path))
            logger.info("Feedback learner initialized")

        # ── 10. Compact engine ────────────────────────────────────
        if self._enable_compact:
            self._compact_engine = EncreCompactEngine(
                strategy=EncreMultiStagePipeline(),
            )
            logger.info("Compact engine initialized (multi-stage pipeline)")

        # ── 11. Session manager ───────────────────────────────────
        from encre.server.session_manager import SessionManager
        self._session_manager = SessionManager(
            max_concurrent=self._max_concurrent,
            sessions_dir=str(data_dir / "iclaw" / "sessions"),
        )

        # ── 12. Event router ──────────────────────────────────────
        self._router = EventRouter(
            session_manager=self._session_manager,
            default_config=agent.config,
        )

        # ── 13. WebSocket channel ─────────────────────────────────
        self._ws_channel = WebSocketChannel(host=ws_host, port=ws_port)
        await self._ws_channel.start(self._router)

        # ── 14. Gateway server ─────────────────────────────────────
        self._gateway = WsBridgeServer(
            runner=self,
            host=ws_host,
            port=18792,
            max_connections=32,
        )
        await self._gateway.start()
        logger.info("Gateway server started on ws://%s:%s", ws_host, 18792)

        # ── 15. Scheduler ─────────────────────────────────────────
        self._scheduler = EncreScheduler(
            poll_interval_seconds=self._scheduler_poll_interval,
        )
        self._scheduler.on_job_complete(self._on_job_complete)
        await self._scheduler.start(self._make_agent_factory())

        # ── 16. Memory consolidator ───────────────────────────────
        if self._consolidation_interval > 0:
            self._consolidator = MemoryConsolidator(
                agent,
                interval=self._consolidation_interval,
            )
            await self._consolidator.start()

        # ── 17. Goal runner ───────────────────────────────────────
        self._goal_runner = EncreGoalRunner(
            config=agent.config,
            tool_registry=agent.tool_registry,
            hook_system=agent.hook_system,
            safety=agent.safety,
            memory_system=getattr(agent, "memory_system", None),
            skill_registry=getattr(agent, "skill_registry", None),
            telemetry=getattr(agent, "telemetry", None),
        )

        # ── 18. Swarm subsystems ──────────────────────────────────
        if self._enable_swarm:
            self._blackboard = EncreBlackboard()
            self._consensus = EncreConsensus()
            self._task_planner = EncreTaskPlanner()
            self._role_registry = RoleRegistry()
            self._swarm_session = EncreSwarmSession(
                agent=agent,
                max_concurrent=min(10, self._max_concurrent),
            )
            logger.info("Swarm subsystems initialized (blackboard + consensus + planner + roles)")

        # ── 19. Post-run self-improvement pipeline ─────────────────
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
        logger.info("Post-run pipeline initialized (self-improvement loop)")

        # ── 20. Background housekeeping ─────────────────────────────
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            "iClaw engine ready -- sessions=%d consolidation=%ds ws=ws://%s:%d "
            "compact=%s evolution=%s reflex=%s metacognition=%s feedback=%s swarm=%s hooks=%s",
            self._max_concurrent, self._consolidation_interval,
            ws_host, ws_port,
            self._enable_compact, self._enable_evolution, self._enable_reflex,
            self._enable_metacognition, self._enable_feedback, self._enable_swarm,
            self._enable_hooks,
        )

    async def stop(self) -> None:
        """Shut down all subsystems and cancel background tasks."""
        if not self._running:
            return
        self._running = False
        logger.info("Shutting down iClaw engine...")

        if self._shutdown_event:
            self._shutdown_event.set()

        background_tasks = [self._cleanup_task, self._heartbeat_task, self._reflex_scan_task]
        for task in background_tasks:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        if self._scheduler:
            await self._scheduler.stop()
        if self._consolidator:
            await self._consolidator.stop()
            self._consolidator = None
        if self._learning_engine:
            await self._learning_engine.stop()
            self._learning_engine = None
        if self._ws_channel:
            await self._ws_channel.stop()
            self._ws_channel = None
        if self._gateway:
            await self._gateway.stop()
            self._gateway = None
        if self._router:
            await self._router.shutdown()
            self._router = None
        if self._session_manager:
            await self._session_manager.shutdown()
            self._session_manager = None

        logger.info("iClaw engine stopped")

    # ── Default hooks ──────────────────────────────────────────────────

    def _register_default_hooks(self) -> None:
        """Register the engine's built-in post-tool and post-turn hooks."""
        hs = self._hook_system
        if hs is None:
            return

        async def _on_tool_complete(_name: str, _context: dict[str, Any], _extra: dict[str, Any] | None) -> dict[str, Any] | None:
            return None

        async def _on_turn_end(_name: str, _context: dict[str, Any], _extra: dict[str, Any] | None) -> dict[str, Any] | None:
            return None

        try:
            hs.register_handler("post_tool_exec", _on_tool_complete)
            hs.register_handler("post_turn", _on_turn_end)
        except Exception as e:
            logger.warning("Hook registration incomplete: %s", e)

    # ── Submit pipeline ────────────────────────────────────────────────

    async def submit(
        self,
        channel_name: str,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Submit a one-shot prompt to a channel and return a session id.

        Increments the sessions-created stat. Requires the engine to be
        started (a ready router); otherwise returns an error string.
        """
        if self._router is None:
            return "Error: Engine not ready"
        # Delegate the one-shot submission to the event router.
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
        """Stream an agent run for a prompt, yielding model/tool events.

        Runs pre-turn hooks, optionally compacts oversized prompts, streams
        events (while feeding the learning engine), then runs the post-run
        self-improvement pipeline and post-turn hooks.
        """
        if self._router is None:
            yield Finish(reason="error", error="Engine not ready")
            return

        self.stats.sessions_created += 1

        # ── Hook: pre-turn ──────────────────────────────────────────
        # Fire the pre-turn hook (best effort) before any model work.
        if self._hook_system:
            with contextlib.suppress(Exception):
                await self._hook_system.emit_turn_start(turn=0, prompt=prompt)

        # ── Compact: check if context needs compaction ──────────────
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

        # ── Stream agent events ─────────────────────────────────────
        collected_events: list[AgentEvent] = []
        tool_names: list[str] = []
        stream_start = time.monotonic()
        async for event in self._router.submit_stream(
            channel_name, prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        ):
            # Track tool usage for learning engine
            if isinstance(event, ToolResult):
                tool_names.append(getattr(event, "id", "unknown"))
                # Evolution learning
                if self._evolution_learner:
                    self.stats.evolution_observations += 1
            elif isinstance(event, Finish):
                self.stats.sessions_completed += 1

            collected_events.append(event)
            yield event

        stream_duration = time.monotonic() - stream_start

        # ── Post-run self-improvement pipeline ──────────────────────
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

        # ── Hook: post-turn ─────────────────────────────────────────
        if self._hook_system:
            with contextlib.suppress(Exception):
                await self._hook_system.emit_turn_end(turn=0, event_count=len(tool_names))

    # ── Goal execution ─────────────────────────────────────────────────

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

    # ── Swarm / multi-agent operations ────────────────────────────────

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
        from encre.swarm.session import SwarmResult
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
        from encre.swarm.session import SwarmEvent
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
        """Create a swarm consensus proposal if the consensus subsystem is on."""
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

    # ── Plugin operations ──────────────────────────────────────────────

    def plugin_list(self) -> list[str]:
        """Return the names of all registered plugins."""
        if self._plugin_registry is None:
            return []
        try:
            return list(getattr(self._plugin_registry, "_plugins", {}).keys())
        except Exception:
            return []

    def plugin_load(self, path: str) -> bool:
        """Activate the plugin at *path*; return ``True`` on success."""
        if self._plugin_registry is None:
            return False
        try:
            self._plugin_registry.activate(path)
            return True
        except Exception:
            return False

    # ── Scheduled job operations ───────────────────────────────────────

    def schedule_job(
        self,
        name: str,
        prompt: str,
        cron: str = "",
        fire_at: float | None = None,
        max_failures: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Schedule a recurring/one-shot job via the cron scheduler."""
        if self._scheduler is None:
            return ""
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
        """Cancel a scheduled job by id; return ``True`` if handled."""
        if self._scheduler is None:
            return False
        return self._scheduler.cancel(job_id)

    def list_jobs(self) -> list[ScheduledJob]:
        """Return all currently scheduled jobs."""
        if self._scheduler is None:
            return []
        return self._scheduler.list_jobs()

    # ── Stats / Health ─────────────────────────────────────────────────

    def get_gateway_status(self) -> dict[str, Any]:
        """Return the gateway server status, or ``{"running": False}``."""
        if self._gateway is None:
            return {"running": False}
        return self._gateway.get_status()

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of running counters and uptime/health stats."""
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
            "active_channels": list(self.get_gateway_status().get("adapters", {}).keys()),
            "gateway": self.get_gateway_status(),
            "active_sessions": self._session_manager.active_count if self._session_manager else 0,
            "compact_enabled": self._enable_compact,
            "evolution_enabled": self._enable_evolution,
            "reflex_enabled": self._enable_reflex,
            "swarm_enabled": self._enable_swarm,
            "hooks_enabled": self._enable_hooks,
        }

    def get_health(self) -> dict[str, Any]:
        """Return a lightweight health/status summary of the daemon."""
        return {
            "status": "ok" if self._running else "stopped",
            "running": self._running,
            "uptime_seconds": time.time() - self.stats.started_at if self.stats.started_at > 0 else 0,
            "active_sessions": self._session_manager.active_count if self._session_manager else 0,
            "scheduled_jobs": len(self.list_jobs()),
            "adapters": list(self.get_gateway_status().get("adapters", {}).keys()),
            "subsystems": {
                "compact": self._compact_engine is not None,
                "evolution": self._evolution_learner is not None,
                "reflex": self._reflex_loop is not None,
                "metacognition": self._meta_cognition is not None,
                "feedback": self._feedback_learner is not None,
                "swarm": self._swarm_session is not None,
                "hooks": self._hook_system is not None,
                "plugins": self._plugin_registry is not None,
                "scheduler": self._scheduler is not None,
                "learning": self._learning_engine is not None,
                "consolidator": self._consolidator is not None,
                "goals": self._goal_runner is not None,
            },
        }

    # ── Internal callbacks ─────────────────────────────────────────────

    def _on_job_complete(self, job: ScheduledJob) -> None:
        """Callback fired by the scheduler when a job finishes."""
        self.stats.sessions_completed += 1
        logger.info("Scheduled job completed: %s (state=%s)", job.name, job.state.name)

    def _make_agent_factory(self) -> Callable[[dict[str, Any] | None], EncreAgent]:
        """Build a factory that spawns agents sharing the main agent's config."""
        main_agent = self._agent

        def _factory(agent_config: dict[str, Any] | None = None) -> EncreAgent:
            # Start from the main agent's config (preserves workspace, tools, etc.)
            config = replace(main_agent.config)

            if agent_config:
                # Apply model-specific overrides from the automation job
                if agent_config.get("backend_type"):
                    config.backend_type = agent_config["backend_type"]
                if agent_config.get("api_key"):
                    config.api_key = agent_config["api_key"]
                if agent_config.get("base_url"):
                    config.base_url = agent_config["base_url"]
                if agent_config.get("model_id"):
                    config.model = agent_config["model_id"]
                    # Pin the job's model so the loop's unified fallback tries
                    # it first, then the indicator, then a random enabled model.
                    config.target_model_ids = [agent_config["model_id"]]
                if agent_config.get("max_tokens"):
                    config.max_tokens = agent_config["max_tokens"]
                # Apply workspace path if stored with the job
                if agent_config.get("workspace"):
                    config.workspace = agent_config["workspace"]

            agent = EncreAgent(
                config=config,
                tool_registry=main_agent.tool_registry,
                hook_system=main_agent.hook_system,
                memory_system=main_agent.memory_system,
                safety=main_agent.safety,
                plugin_registry=main_agent.plugin_registry,
            )
            return agent

        return _factory

    async def _reflex_scan_loop(self) -> None:
        """Background loop that periodically marks reflex evaluation runs."""
        while self._running and self._reflex_loop:
            await asyncio.sleep(900)
            if not self._running:
                break
            if self._evolution_learner:
                self.stats.reflex_evaluations += 1

    async def _cleanup_loop(self) -> None:
        """Background loop that periodically evicts idle sessions."""
        while self._running:
            await asyncio.sleep(600)
            if not self._running:
                break
            if self._session_manager:
                try:
                    removed = await self._session_manager.cleanup_idle()
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
                "iClaw heartbeat -- sessions=%d jobs=%d adapters=%s compact=%d evolution=%d",
                self._session_manager.active_count if self._session_manager else 0,
                len(self.list_jobs()),
                list(self.get_gateway_status().get("adapters", {}).keys()),
                self.stats.compact_runs,
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

    # ── LLM-powered run analysis ─────────────────────────────────

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


class IClawDaemon:
    """Headless background daemon managed by the desktop application.

    Wraps ``iClawEngine`` with PID lifecycle management and top-level
    start/wait/stop orchestration.

    The desktop app spawns this as a child process, parses the
    ``ICLAW_READY`` line from stdout, and connects to the WebSocket endpoint.

    Parameters
    ----------
    agent : EncreAgent
        Pre-configured agent instance. Its config provides defaults for new
        sessions (model, tools, permissions, etc.).
    host : str
        Bind address (default: 127.0.0.1).
    port : int
        WebSocket port.
    max_concurrent : int
        Maximum concurrent agent sessions.
    consolidation_interval : int
        Seconds between memory consolidation cycles (0 = disabled).
    scheduler_poll_interval : float
        Seconds between scheduler polling cycles.
    enable_compact : bool
        Enable context compaction engine.
    enable_evolution : bool
        Enable evolution learning engine.
    enable_reflex : bool
        Enable reflex loop.
    enable_metacognition : bool
        Enable metacognition.
    enable_feedback : bool
        Enable feedback learning.
    enable_swarm : bool
        Enable swarm / multi-agent subsystems.
    enable_hooks : bool
        Enable hook system.
    compact_max_tokens : int
        Max tokens before compaction triggers.
    """

    def __init__(
        self,
        agent: EncreAgent,
        *,
        host: str = "127.0.0.1",
        port: int = 18791,
        max_concurrent: int = 20,
        consolidation_interval: int = 3600,
        scheduler_poll_interval: float = 30.0,
        enable_compact: bool = True,
        enable_evolution: bool = True,
        enable_reflex: bool = True,
        enable_metacognition: bool = True,
        enable_feedback: bool = True,
        enable_swarm: bool = True,
        enable_hooks: bool = True,
        compact_max_tokens: int = 128000,
    ) -> None:
        """Construct the daemon wrapper around an :class:`IClawEngine`.

        Stores configuration flags and creates the engine lazily on
        :meth:`start`. The daemon is managed by the desktop app via PID file
        and the ``ICLAW_READY`` stdout line.
        """
        self._agent = agent
        self._host = host
        self._port = port
        self._max_concurrent = max_concurrent
        self._consolidation_interval = consolidation_interval
        self._scheduler_poll_interval = scheduler_poll_interval

        # Flags
        self._enable_compact = enable_compact
        self._enable_evolution = enable_evolution
        self._enable_reflex = enable_reflex
        self._enable_metacognition = enable_metacognition
        self._enable_feedback = enable_feedback
        self._enable_swarm = enable_swarm
        self._enable_hooks = enable_hooks
        self._compact_max_tokens = compact_max_tokens

        self._engine: IClawEngine | None = None
        self._running = False
        self._shutdown_event: asyncio.Event | None = None

    @property
    def engine(self) -> IClawEngine | None:
        """The underlying engine instance, or ``None`` before start."""
        return self._engine

    @property
    def ws_url(self) -> str:
        """Return the WebSocket URL the daemon listens on."""
        return f"ws://{self._host}:{self._port}"

    @property
    def is_running(self) -> bool:
        """Return ``True`` while the daemon is running."""
        return self._running

    async def start(self) -> None:
        """Create and start the engine, write the PID file, print ready line."""
        if self._running:
            return
        self._running = True

        self._engine = IClawEngine(
            self._agent,
            max_concurrent=self._max_concurrent,
            consolidation_interval=self._consolidation_interval,
            scheduler_poll_interval=self._scheduler_poll_interval,
            enable_compact=self._enable_compact,
            enable_evolution=self._enable_evolution,
            enable_reflex=self._enable_reflex,
            enable_metacognition=self._enable_metacognition,
            enable_feedback=self._enable_feedback,
            enable_swarm=self._enable_swarm,
            enable_hooks=self._enable_hooks,
            compact_max_tokens=self._compact_max_tokens,
        )

        await self._engine.start(
            ws_host=self._host,
            ws_port=self._port,
        )

        _write_pid(os.getpid())
        print(f"ICLAW_READY {self.ws_url}", flush=True)

        logger.info(
            "iClaw daemon ready -- ws=%s max_concurrent=%d consolidation=%ds "
            "compact=%s evolution=%s reflex=%s swarm=%s hooks=%s pid=%d",
            self.ws_url, self._max_concurrent,
            self._consolidation_interval,
            self._enable_compact, self._enable_evolution, self._enable_reflex,
            self._enable_swarm, self._enable_hooks,
            os.getpid(),
        )

    async def wait(self) -> None:
        """Block until a SIGINT/SIGTERM sets the shutdown event."""
        self._shutdown_event = asyncio.Event()
        loop = asyncio.get_event_loop()

        def _handle_signal() -> None:
            if self._shutdown_event:
                self._shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, _handle_signal)

        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop the engine, clear the PID file, and exit."""
        if not self._running:
            return
        self._running = False
        logger.info("Shutting down iClaw daemon...")
        if self._shutdown_event:
            self._shutdown_event.set()
        if self._engine:
            await self._engine.stop()
            self._engine = None
        _clear_pid()
        logger.info("iClaw daemon stopped")


async def run_iclaw(
    agent: EncreAgent | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 18791,
    max_concurrent: int = 20,
    consolidation_interval: int = 3600,
    scheduler_poll_interval: float = 30.0,
    enable_compact: bool = True,
    enable_evolution: bool = True,
    enable_reflex: bool = True,
    enable_metacognition: bool = True,
    enable_feedback: bool = True,
    enable_swarm: bool = True,
    enable_hooks: bool = True,
    compact_max_tokens: int = 128000,
) -> None:
    """Entry point for ``python -m encre.iclaw``.

    Builds a default agent when none is supplied, wraps it in an
    :class:`IClawDaemon`, then starts it, blocks until a termination signal
    arrives, and performs a clean shutdown. Registers an ``atexit`` handler so
    the PID file is always cleared even on unexpected exit.

    Args:
        agent: A pre-configured :class:`EncreAgent`, or ``None`` to construct a
            default one.
        host: Bind address for the WebSocket server.
        port: WebSocket port.
        max_concurrent: Maximum concurrent agent sessions.
        consolidation_interval: Seconds between memory consolidation cycles
            (``0`` disables it).
        scheduler_poll_interval: Seconds between scheduler polling cycles.
        enable_compact/evolution/reflex/metacognition/feedback/swarm/hooks:
            Subsystem enable flags forwarded to the engine/daemon.
        compact_max_tokens: Token budget that triggers compaction.

    Returns:
        None.
    """
    # Build a default agent when the caller did not supply one.
    if agent is None:
        agent = _create_default_agent()

    daemon = IClawDaemon(
        agent,
        host=host,
        port=port,
        max_concurrent=max_concurrent,
        consolidation_interval=consolidation_interval,
        scheduler_poll_interval=scheduler_poll_interval,
        enable_compact=enable_compact,
        enable_evolution=enable_evolution,
        enable_reflex=enable_reflex,
        enable_metacognition=enable_metacognition,
        enable_feedback=enable_feedback,
        enable_swarm=enable_swarm,
        enable_hooks=enable_hooks,
        compact_max_tokens=compact_max_tokens,
    )

    atexit.register(_clear_pid)

    await daemon.start()
    await daemon.wait()
    await daemon.stop()
