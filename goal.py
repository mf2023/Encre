#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, AsyncGenerator, Callable

from yim.backend import create_backend
from yim.backends.base import BaseBackend
from yim.config import YmiConfig
from yim.logging_config import get_logger
from yim.loop import YmiLoop
from yim.session import YmiSession
from yim.tools.registry import ToolRegistry
from yim.hooks.system import YmiHookSystem
from yim.safety import YmiSafetyEngine
from yim.memdir.system import YmiMemorySystem
from yim.skills.registry import YmiSkillRegistry
from yim.telemetry import YmiTelemetry
from yim.utils.types import (
    AgentEvent,
    Finish,
    TextDelta,
    ToolCallStart,
    ToolResult,
    create_finish,
    create_text_delta,
)

logger = get_logger("yim.goal")


class GoalStatus(Enum):
    PENDING = auto()
    IN_PROGRESS = auto()
    SUCCESS = auto()
    FAILED = auto()
    TIMEOUT = auto()
    MAX_ATTEMPTS = auto()


@dataclass
class GoalDefinition:
    """A verifiable goal for autonomous execution."""
    description: str
    success_criteria: str  # e.g. "All tests pass", "Zero TypeScript errors"
    max_attempts: int = 20
    timeout_seconds: int = 3600  # 1 hour
    evaluator_model: str = ""  # Defaults to config model, can use cheaper one
    evaluator_provider: str = ""  # Defaults to config backend_type


@dataclass
class GoalResult:
    status: GoalStatus
    summary: str = ""
    attempts: int = 0
    elapsed_seconds: float = 0.0
    final_output: str = ""
    milestones: list[str] = field(default_factory=list)


@dataclass
class GoalEvent:
    """Events emitted during goal-driven execution."""
    status: GoalStatus
    attempt: int = 0
    message: str = ""


class YmiGoalRunner:
    """Autonomous goal-driven agent execution.

    Runs an agent loop with progress evaluation:
    1. Agent works on the goal (standard tool-using loop)
    2. After each turn, an evaluator model checks if the goal is met
    3. If not met, feedback is injected and the agent continues
    4. If met → success. If max attempts → failure.

    The evaluator uses a lightweight model by default (configurable).
    """

    # Prompt for the evaluator model
    EVALUATOR_SYSTEM_PROMPT = """You are a goal completion evaluator. Your job is to check whether a goal has been met based on the agent's execution trace.

Reply with a JSON object:
{
  "met": true or false,
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation of your assessment",
  "feedback": "If not met: specific guidance on what's missing. If met: empty string.",
  "milestone": "If achieved: a short description of what was accomplished."
}

Be strict but fair. The goal is met only if the success criteria are fully satisfied."""

    def __init__(
        self,
        config: YmiConfig,
        tool_registry: ToolRegistry | None = None,
        hook_system: YmiHookSystem | None = None,
        safety: YmiSafetyEngine | None = None,
        memory_system: YmiMemorySystem | None = None,
        skill_registry: YmiSkillRegistry | None = None,
        telemetry: YmiTelemetry | None = None,
    ) -> None:
        self.config = config
        self.tool_registry = tool_registry or ToolRegistry()
        self.hook_system = hook_system or YmiHookSystem()
        self.safety = safety or YmiSafetyEngine(config)
        self.memory_system = memory_system
        self.skill_registry = skill_registry
        self.telemetry = telemetry or YmiTelemetry(enabled=False)

    def _make_evaluator_backend(self, goal: GoalDefinition) -> BaseBackend:
        provider = goal.evaluator_provider or self.config.backend_type
        model = goal.evaluator_model or self.config.model
        if goal.evaluator_provider:
            return create_backend(
                provider,
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                model=model,
                **self.config.backend_kwargs,
            )
        # Use a fast/cheap model for evaluation when possible
        eval_model = model
        if provider == "anthropic":
            eval_model = "claude-haiku-4-5-20251001"
        elif provider == "openai":
            eval_model = "gpt-4o-mini"
        elif provider == "google":
            eval_model = "gemini-2.0-flash"
        return create_backend(
            provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=eval_model,
            **self.config.backend_kwargs,
        )

    async def run(
        self,
        goal: GoalDefinition,
        on_attempt: Callable[[GoalEvent], None] | None = None,
    ) -> GoalResult:
        """Execute a goal-driven autonomous loop and return the result."""
        start_time = time.time()
        result = GoalResult(status=GoalStatus.IN_PROGRESS)

        evaluator = self._make_evaluator_backend(goal)

        # Build the initial prompt with goal context
        goal_prompt = self._build_goal_prompt(goal)

        # Standard agent loop
        session = YmiSession(self.config)
        loop = YmiLoop(
            self.config, session, self.tool_registry,
            self.hook_system, self.safety,
            self.memory_system, self.skill_registry,
            self.telemetry,
        )

        full_trace: list[str] = []
        current_feedback: str = ""

        for attempt in range(1, goal.max_attempts + 1):
            elapsed = time.time() - start_time
            if elapsed > goal.timeout_seconds:
                result.status = GoalStatus.TIMEOUT
                result.elapsed_seconds = elapsed
                result.attempts = attempt
                result.summary = f"Timed out after {elapsed:.0f}s ({attempt} attempts)"
                return result

            # Build the prompt for this attempt
            if attempt == 1:
                prompt = goal_prompt
            else:
                prompt = (
                    f"[CONTINUING]\nGoal not yet met. Feedback: {current_feedback}\n\n"
                    f"Please continue working on the goal. Focus on what's missing.\n"
                    f"Goal: {goal.description}\n"
                    f"Success criteria: {goal.success_criteria}"
                )

            # Run one turn
            turn_output: list[str] = []
            async for event in loop.run(prompt):
                if isinstance(event, TextDelta):
                    turn_output.append(event.text)
                elif isinstance(event, ToolResult):
                    turn_output.append(f"\n[Tool: {event.content[:500]}]")

            turn_text = "".join(turn_output)
            full_trace.append(f"--- Attempt {attempt} ---\n{turn_text}")

            if on_attempt:
                on_attempt(GoalEvent(
                    status=GoalStatus.IN_PROGRESS,
                    attempt=attempt,
                    message=turn_text[:300],
                ))

            # Evaluate: did we achieve the goal?
            eval_result = await self._evaluate(evaluator, goal, full_trace)

            if eval_result.get("met"):
                result.status = GoalStatus.SUCCESS
                result.attempts = attempt
                result.elapsed_seconds = time.time() - start_time
                result.final_output = turn_text
                result.summary = eval_result.get("reasoning", "Goal achieved.")
                if eval_result.get("milestone"):
                    result.milestones.append(eval_result["milestone"])
                if on_attempt:
                    on_attempt(GoalEvent(
                        status=GoalStatus.SUCCESS,
                        attempt=attempt,
                        message=result.summary,
                    ))
                return result

            current_feedback = eval_result.get("feedback", "Goal not yet met. Continue.")

            # If confidence is very low and we're past half attempts, warn
            confidence = eval_result.get("confidence", 0.0)
            if confidence < 0.2 and attempt > goal.max_attempts // 2:
                current_feedback += (
                    f"\nWARNING: Progress confidence is very low ({confidence:.0%}). "
                    "Consider a different approach."
                )

            # Reset session for next attempt
            loop = YmiLoop(
                self.config, YmiSession(self.config), self.tool_registry,
                self.hook_system, self.safety,
                self.memory_system, self.skill_registry,
                self.telemetry,
            )

        result.status = GoalStatus.MAX_ATTEMPTS
        result.attempts = goal.max_attempts
        result.elapsed_seconds = time.time() - start_time
        result.summary = f"Reached max attempts ({goal.max_attempts}) without meeting the goal."
        if on_attempt:
            on_attempt(GoalEvent(
                status=GoalStatus.MAX_ATTEMPTS,
                attempt=goal.max_attempts,
                message=result.summary,
            ))
        return result

    def _build_goal_prompt(self, goal: GoalDefinition) -> str:
        return (
            f"GOAL: {goal.description}\n\n"
            f"SUCCESS CRITERIA: {goal.success_criteria}\n\n"
            f"Work autonomously to achieve this goal. After each action, check your "
            f"progress against the success criteria. When you believe the goal is met, "
            f"state the results clearly.\n\n"
            f"You have up to {goal.max_attempts} attempts. Be thorough but efficient."
        )

    async def _evaluate(
        self,
        evaluator: BaseBackend,
        goal: GoalDefinition,
        trace: list[str],
    ) -> dict[str, Any]:
        """Ask the evaluator model to check if the goal has been met."""
        trace_text = "\n".join(trace[-5:])  # Last 5 attempts
        if len(trace_text) > 8000:
            trace_text = trace_text[-8000:]

        eval_prompt = (
            f"Goal: {goal.description}\n\n"
            f"Success Criteria: {goal.success_criteria}\n\n"
            f"Agent Execution Trace:\n{trace_text}\n\n"
            f"Has the goal been met according to the success criteria? Reply with JSON only."
        )

        messages = [
            {"role": "system", "content": self.EVALUATOR_SYSTEM_PROMPT},
            {"role": "user", "content": eval_prompt},
        ]

        try:
            full_response: str = ""
            async for event in evaluator.chat(
                messages=messages,
                max_tokens=1024,
                temperature=0.0,
                enable_caching=False,
            ):
                from yim.utils.types import BackendText
                if isinstance(event, BackendText):
                    full_response += event.text
                elif hasattr(event, "error"):
                    break

            # Parse JSON from response
            json_start = full_response.find("{")
            json_end = full_response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(full_response[json_start:json_end])
            return {"met": False, "confidence": 0.0, "reasoning": "Could not parse evaluator response", "feedback": full_response[:500]}

        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse evaluator JSON response (first 200 chars): {full_response[:200]}")
            return {"met": False, "confidence": 0.0, "reasoning": f"Evaluator JSON parse error: {e}", "feedback": "Continue."}
        except Exception as e:
            logger.error(f"Evaluator request failed: {e}", exc_info=True)
            return {"met": False, "confidence": 0.0, "reasoning": f"Evaluator error: {e}", "feedback": "Continue."}


class YmiGoalLoop:
    """Simplified goal loop that can be attached to an existing YmiAgent.

    Usage:
        agent = YmiAgent(config)
        goal_loop = YmiGoalLoop(agent)
        result = await goal_loop.execute(
            description="Implement user authentication",
            success_criteria="Login endpoint works with JWT tokens, tests pass",
        )
    """

    def __init__(
        self,
        agent: Any,
        description: str = "",
        success_criteria: str = "",
        max_attempts: int = 20,
        timeout_seconds: int = 3600,
    ) -> None:
        self.agent = agent
        self._description = description
        self._success_criteria = success_criteria
        self._max_attempts = max_attempts
        self._timeout_seconds = timeout_seconds
        self.runner = YmiGoalRunner(
            agent.config,
            agent.tool_registry,
            agent.hook_system,
            agent.safety,
            agent.memory_system,
            agent.skill_registry,
            agent.telemetry,
        )

    async def execute(
        self,
        description: str = "",
        success_criteria: str = "",
        max_attempts: int = 20,
        timeout_seconds: int = 3600,
        evaluator_model: str = "",
        evaluator_provider: str = "",
        on_progress: Callable[[GoalEvent], None] | None = None,
    ) -> GoalResult:
        description = description or self._description
        success_criteria = success_criteria or self._success_criteria
        if not description or not success_criteria:
            raise ValueError("description and success_criteria are required.")
        goal = GoalDefinition(
            description=description,
            success_criteria=success_criteria,
            max_attempts=max_attempts or self._max_attempts,
            timeout_seconds=timeout_seconds or self._timeout_seconds,
            evaluator_model=evaluator_model,
            evaluator_provider=evaluator_provider,
        )
        return await self.runner.run(goal, on_attempt=on_progress)
