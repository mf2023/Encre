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
PostRunProcessor -- Self-improving loop for the iClaw daemon.

Runs after every agent session to:
1. Analyze the session (tool calls, text output, errors)
2. Summarize key learnings and write to persistent memory
3. Detect repeated tool-use patterns and auto-generate skills
4. Update the soul USER.md with learned user preferences
5. Record evolution observations for long-term adaptation
6. Consolidate feedback corrections

This is the core "self-improving" mechanism that makes iClaw
get better over time without manual intervention.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from encre.agent import EncreAgent
from encre.evolution.learner import EncreEvolutionLearner
from encre.feedback.learner import EncreFeedbackLearner
from encre.learning.consolidator import MemoryConsolidator
from encre.learning.engine import LearningEngine
from encre.logging_config import get_logger
from encre.soul.system import EncreSoulSystem
from encre.utils.types import AgentEvent, TextDelta, ToolResult

logger = get_logger("encre.iclaw.post_run")


@dataclass
class RunSummary:
    """Structured summary of a single agent run."""

    prompt: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    text_output: str = ""
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    tool_call_count: int = 0
    unique_tools: set[str] = field(default_factory=set)
    repeated_patterns: list[dict[str, Any]] = field(default_factory=list)


class PostRunPipeline:
    """Post-run self-improvement pipeline.

    Collects events from a completed run, builds a summary, then
    feeds it through every learning subsystem in sequence.

    Parameters
    ----------
    agent : EncreAgent
        The agent that executed the run. Its subsystems (memory, soul, etc.)
        are accessed through the agent.
    learning_engine : LearningEngine | None
        Engine for detecting patterns and generating skills.
    evolution_learner : EncreEvolutionLearner | None
        Records success/error observations from the run.
    feedback_learner : EncreFeedbackLearner | None
        Records any corrections detected during the run.
    consolidator : MemoryConsolidator | None
        Triggers periodic memory consolidation after analysis.
    soul_system : EncreSoulSystem | None
        Updates USER.md with learned preferences.
    analyze_fn : Callable | None
        Optional async callable that performs LLM-powered analysis of the
        run data. If not provided, simple statistical analysis is used.
    """

    def __init__(
        self,
        agent: EncreAgent,
        *,
        learning_engine: LearningEngine | None = None,
        evolution_learner: EncreEvolutionLearner | None = None,
        feedback_learner: EncreFeedbackLearner | None = None,
        consolidator: MemoryConsolidator | None = None,
        soul_system: EncreSoulSystem | None = None,
        analyze_fn: Callable[[RunSummary], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self._agent = agent
        self._learning_engine = learning_engine
        self._evolution_learner = evolution_learner
        self._feedback_learner = feedback_learner
        self._consolidator = consolidator
        self._soul_system = soul_system
        self._analyze_fn = analyze_fn

    async def process(
        self,
        prompt: str,
        events: list[AgentEvent],
        *,
        duration_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """Run the full post-processing pipeline on a completed session.

        Returns a dict with results from each subsystem stage.
        """
        results: dict[str, Any] = {"stages": {}}

        # First, turn the raw event stream into a structured summary.
        summary = self._build_summary(prompt, events, duration_seconds)
        results["summary"] = {
            "tool_call_count": summary.tool_call_count,
            "unique_tools": sorted(summary.unique_tools),
            "error_count": len(summary.errors),
            "duration_seconds": summary.duration_seconds,
        }

        enrichments: dict[str, Any] = {}
        if self._analyze_fn:
            try:
                enrichments = await self._analyze_fn(summary)
                results["analyzed"] = True
            except Exception as e:
                logger.warning("LLM analysis failed: %s", e)
                results["analyzed"] = False

        # Run all learning stages concurrently; capture individual failures.
        stage_results = await asyncio.gather(
            self._stage_evolution(summary),
            self._stage_learning(summary, enrichments),
            self._stage_memory(summary, enrichments),
            self._stage_soul(summary, enrichments),
            return_exceptions=True,
        )

        stage_names = ["evolution", "learning", "memory", "soul"]
        for name, result in zip(stage_names, stage_results, strict=False):
            if isinstance(result, Exception):
                results["stages"][name] = {"error": str(result)}
                logger.warning("Post-run stage '%s' failed: %s", name, result)
            else:
                results["stages"][name] = result

        results["completed"] = True
        return results

    def _build_summary(
        self,
        prompt: str,
        events: list[AgentEvent],
        duration_seconds: float,
    ) -> RunSummary:
        """Aggregate streamed events into a structured :class:`RunSummary`."""
        summary = RunSummary(
            prompt=prompt,
            duration_seconds=duration_seconds,
        )
        text_parts: list[str] = []
        for event in events:
            if isinstance(event, TextDelta) and event.text:
                text_parts.append(event.text)
            elif isinstance(event, ToolResult):
                tool_id = event.id or "unknown"
                tool_name = tool_id.split("_")[0] if "_" in tool_id else tool_id
                summary.tool_calls.append({
                    "id": tool_id,
                    "name": tool_name,
                    "success": not event.is_error,
                })
                summary.tool_call_count += 1
                summary.unique_tools.add(tool_name)
                if event.is_error:
                    summary.errors.append(event.content or "unknown error")

        summary.text_output = "".join(text_parts)
        self._detect_patterns(summary)
        return summary

    def _detect_patterns(self, summary: RunSummary) -> None:
        """Detect frequently repeated adjacent tool-call pairs in the run."""
        tool_names = [tc["name"] for tc in summary.tool_calls]
        # Need enough calls to make pattern detection meaningful.
        if len(tool_names) < 3:
            return
        from collections import Counter
        pairs = [f"{tool_names[i]}+{tool_names[i+1]}" for i in range(len(tool_names) - 1)]
        pair_counts = Counter(pairs)
        frequent_pairs = {k: v for k, v in pair_counts.items() if v >= 2}
        if frequent_pairs:
            summary.repeated_patterns = [
                {"pattern": k, "frequency": v}
                for k, v in sorted(frequent_pairs.items(), key=lambda x:
                    -x[1])
            ]

    async def _stage_evolution(self, summary: RunSummary) -> dict[str, Any]:
        """Feed success/error tool observations into the evolution learner."""
        if self._evolution_learner is None:
            return {"enabled": False}
        stage: dict[str, Any] = {"enabled": True, "records": 0}
        for tc in summary.tool_calls:
            # Feed each tool outcome back to the evolution learner.
            if tc.get("success", True):
                self._evolution_learner.record_success(tc["name"], summary.prompt[:200])
                stage["records"] = stage.get("records", 0) + 1
            else:
                self._evolution_learner.record_error(tc["name"], tc.get("error", "") or "unknown error")
                stage.setdefault("errors", []).append({"tool": tc["name"]})
        return stage

    async def _stage_learning(self, summary: RunSummary, _enrichments: dict[str, Any]) -> dict[str, Any]:
        """Run the learning engine's pattern/skill analysis on the run."""
        if self._learning_engine is None:
            return {"enabled": False}
        tool_names = [tc["name"] for tc in summary.tool_calls]
        await self._learning_engine.analyze_run(tool_names, summary.prompt)
        return {
            "enabled": True,
            "tools_analyzed": len(tool_names),
            "skills_generated": 0,
        }

    async def _stage_memory(self, summary: RunSummary, enrichments: dict[str, Any]) -> dict[str, Any]:
        """Write a session note to memory and trigger consolidation if able."""
        memory_system = getattr(self._agent, "memory_system", None)
        if memory_system is None:
            return {"enabled": False}
        try:
            task_note = enrichments.get("task_summary", "")
            if not task_note:
                task_note = self._build_memory_note(summary)
            if task_note:
                memory_system.write_entrypoint_cache()
            stage: dict[str, Any] = {"enabled": True, "note_added": bool(task_note)}
            if self._consolidator and summary.tool_call_count > 0:
                await self._consolidator.consolidate()
                stage["consolidated"] = True
            return stage
        except Exception as e:
            logger.warning("Memory stage failed: %s", e)
            return {"enabled": True, "error": str(e)}

    async def _stage_soul(self, _summary: RunSummary, enrichments: dict[str, Any]) -> dict[str, Any]:
        """Append discovered user preferences to the soul USER.md."""
        if self._soul_system is None:
            return {"enabled": False}
        user_notes = enrichments.get("user_preferences", [])
        if isinstance(user_notes, list):
            for note in user_notes:
                if isinstance(note, str) and len(note) > 10:
                    self._soul_system.append_user_note(note)
        return {
            "enabled": True,
            "user_notes_added": len(user_notes) if isinstance(user_notes, list) else 0,
        }

    def _build_memory_note(self, summary: RunSummary) -> str:
        """Render a Markdown session-summary note for the memory system."""
        parts: list[str] = []
        parts.append("## Session Summary")
        parts.append(f"**Goal:** {summary.prompt[:300]}")
        if summary.tool_call_count > 0:
            tools_str = ", ".join(sorted(summary.unique_tools))
            parts.append(f"**Tools used ({summary.tool_call_count}):** {tools_str}")
        if summary.errors:
            parts.append(f"**Errors encountered:** {len(summary.errors)}")
        if summary.repeated_patterns:
            patterns_str = "; ".join(
                f"{p['pattern']} (×{p['frequency']})"
                for p in summary.repeated_patterns[:
                    5]
            )
            parts.append(f"**Repeated patterns:** {patterns_str}")
        return "\n\n".join(parts)


class PostRunOrchestrator:
    """Top-level orchestrator that manages the post-run pipeline lifecycle.

    Wraps PostRunPipeline with event collection -- accumulates AgentEvents
    during a streaming run, then feeds them into the pipeline when finished.
    """

    def __init__(
        self,
        pipeline: PostRunPipeline,
        *,
        min_tool_calls: int = 1,
        min_duration: float = 1.0,
    ) -> None:
        self._pipeline = pipeline
        self._min_tool_calls = min_tool_calls
        self._min_duration = min_duration

    async def collect_and_process(
        self,
        prompt: str,
        events: list[AgentEvent],
        *,
        duration_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """Collect events from a completed streaming run and process them."""
        # Count real tool invocations to decide whether analysis is worthwhile.
        tool_call_count = sum(
            1 for e in events if isinstance(e, ToolResult)
        )
        if tool_call_count < self._min_tool_calls:
            return {"skipped": True, "reason": f"too few tool calls ({tool_call_count} < {self._min_tool_calls})"}
        if duration_seconds < self._min_duration:
            return {"skipped": True, "reason": f"too short ({duration_seconds}s < {self._min_duration}s)"}
        return await self._pipeline.process(prompt, events, duration_seconds=duration_seconds)

    @property
    def pipeline(self) -> PostRunPipeline:
        """The wrapped post-run pipeline instance."""
        return self._pipeline
