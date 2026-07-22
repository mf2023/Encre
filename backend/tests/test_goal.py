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

"""Tests for the goal system: definitions, results, statuses, events, and runners."""

import tempfile

import pytest


class TestGoalStatus:
    """Test suite for GoalStatus."""
    def test_all_status_values(self):
        """Test: All status values."""
        from encre.goal import GoalStatus
        # Verify: GoalStatus.PENDING is not None
        assert GoalStatus.PENDING is not None
        # Verify: GoalStatus.IN_PROGRESS is not None
        assert GoalStatus.IN_PROGRESS is not None
        # Verify: GoalStatus.SUCCESS is not None
        assert GoalStatus.SUCCESS is not None
        # Verify: GoalStatus.FAILED is not None
        assert GoalStatus.FAILED is not None
        # Verify: GoalStatus.TIMEOUT is not None
        assert GoalStatus.TIMEOUT is not None
        # Verify: GoalStatus.MAX_ATTEMPTS is not None
        assert GoalStatus.MAX_ATTEMPTS is not None

    def test_status_is_enum(self):
        """Test: Status is enum."""
        from enum import Enum

        from encre.goal import GoalStatus
        # Verify: issubclass(GoalStatus, Enum)
        assert issubclass(GoalStatus, Enum)

    def test_status_string_conversion(self):
        """Test: Status string conversion."""
        from encre.goal import GoalStatus
        # Verify: str(GoalStatus.PENDING) == "GoalStatus.PENDING"
        assert str(GoalStatus.PENDING) == "GoalStatus.PENDING"
        status = GoalStatus.SUCCESS
        # Verify: status.name == "SUCCESS"
        assert status.name == "SUCCESS"


class TestGoalDefinition:
    """Test suite for GoalDefinition."""
    def test_minimal_construction(self):
        """Test: Minimal construction."""
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Test goal",
            success_criteria="Tests pass",
        )
        # Verify: goal.description == "Test goal"
        assert goal.description == "Test goal"
        # Verify: goal.success_criteria == "Tests pass"
        assert goal.success_criteria == "Tests pass"

    def test_default_values(self):
        """Test: Default values."""
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Default test",
            success_criteria="All good",
        )
        # Verify: goal.max_attempts == 20
        assert goal.max_attempts == 20
        # Verify: goal.timeout_seconds == 3600
        assert goal.timeout_seconds == 3600
        # Verify: goal.evaluator_model == ""
        assert goal.evaluator_model == ""
        # Verify: goal.evaluator_provider == ""
        assert goal.evaluator_provider == ""

    def test_full_construction(self):
        """Test: Full construction."""
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Complex task",
            success_criteria="Zero errors, all features work",
            max_attempts=10,
            timeout_seconds=1800,
            evaluator_model="gpt-4o-mini",
            evaluator_provider="openai",
        )
        # Verify: goal.description == "Complex task"
        assert goal.description == "Complex task"
        # Verify: goal.success_criteria == "Zero errors, all features work"
        assert goal.success_criteria == "Zero errors, all features work"
        # Verify: goal.max_attempts == 10
        assert goal.max_attempts == 10
        # Verify: goal.timeout_seconds == 1800
        assert goal.timeout_seconds == 1800
        # Verify: goal.evaluator_model == "gpt-4o-mini"
        assert goal.evaluator_model == "gpt-4o-mini"
        # Verify: goal.evaluator_provider == "openai"
        assert goal.evaluator_provider == "openai"

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.goal import GoalDefinition
        # Verify: is_dataclass(GoalDefinition)
        assert is_dataclass(GoalDefinition)

    def test_non_default_timeout(self):
        """Test: Non default timeout."""
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Quick task",
            success_criteria="Done",
            timeout_seconds=300,
        )
        # Verify: goal.timeout_seconds == 300
        assert goal.timeout_seconds == 300

    def test_non_default_max_attempts(self):
        """Test: Non default max attempts."""
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Many attempts",
            success_criteria="Eventually",
            max_attempts=100,
        )
        # Verify: goal.max_attempts == 100
        assert goal.max_attempts == 100


class TestGoalResult:
    """Test suite for GoalResult."""
    def test_default_construction(self):
        """Test: Default construction."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(status=GoalStatus.PENDING)
        # Verify: result.status == GoalStatus.PENDING
        assert result.status == GoalStatus.PENDING
        # Verify: result.summary == ""
        assert result.summary == ""
        # Verify: result.attempts == 0
        assert result.attempts == 0
        # Verify: result.elapsed_seconds == 0.0
        assert result.elapsed_seconds == 0.0
        # Verify: result.final_output == ""
        assert result.final_output == ""
        # Verify: result.milestones == []
        assert result.milestones == []

    def test_full_construction(self):
        """Test: Full construction."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.SUCCESS,
            summary="All tests passed",
            attempts=3,
            elapsed_seconds=45.2,
            final_output="Task completed successfully",
            milestones=["Step 1 done", "Step 2 done", "All done"],
        )
        # Verify: result.status == GoalStatus.SUCCESS
        assert result.status == GoalStatus.SUCCESS
        # Verify: result.summary == "All tests passed"
        assert result.summary == "All tests passed"
        # Verify: result.attempts == 3
        assert result.attempts == 3
        # Verify: result.elapsed_seconds == 45.2
        assert result.elapsed_seconds == 45.2
        # Verify: result.final_output == "Task completed successfully"
        assert result.final_output == "Task completed successfully"
        # Verify: len(result.milestones) == 3
        assert len(result.milestones) == 3
        # Verify: "Step 1 done" in result.milestones
        assert "Step 1 done" in result.milestones

    def test_failed_status(self):
        """Test: Failed status."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.FAILED,
            summary="Could not complete the task",
            attempts=10,
            elapsed_seconds=600.0,
        )
        # Verify: result.status == GoalStatus.FAILED
        assert result.status == GoalStatus.FAILED
        # Verify: result.attempts == 10
        assert result.attempts == 10

    def test_timeout_status(self):
        """Test: Timeout status."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.TIMEOUT,
            summary="Timed out",
            elapsed_seconds=3601.0,
        )
        # Verify: result.status == GoalStatus.TIMEOUT
        assert result.status == GoalStatus.TIMEOUT

    def test_max_attempts_status(self):
        """Test: Max attempts status."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.MAX_ATTEMPTS,
            summary="Reached max attempts",
            attempts=20,
        )
        # Verify: result.status == GoalStatus.MAX_ATTEMPTS
        assert result.status == GoalStatus.MAX_ATTEMPTS

    def test_milestones_are_mutable_list(self):
        """Test: Milestones are mutable list."""
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(status=GoalStatus.IN_PROGRESS, milestones=["started"])
        result.milestones.append("middle")
        result.milestones.append("almost done")
        # Verify: len(result.milestones) == 3
        assert len(result.milestones) == 3

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.goal import GoalResult
        # Verify: is_dataclass(GoalResult)
        assert is_dataclass(GoalResult)


class TestGoalEvent:
    """Test suite for GoalEvent."""
    def test_construction(self):
        """Test: Construction."""
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.IN_PROGRESS,
            attempt=1,
            message="Working on it",
        )
        # Verify: event.status == GoalStatus.IN_PROGRESS
        assert event.status == GoalStatus.IN_PROGRESS
        # Verify: event.attempt == 1
        assert event.attempt == 1
        # Verify: event.message == "Working on it"
        assert event.message == "Working on it"

    def test_default_values(self):
        """Test: Default values."""
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(status=GoalStatus.PENDING)
        # Verify: event.attempt == 0
        assert event.attempt == 0
        # Verify: event.message == ""
        assert event.message == ""

    def test_success_event(self):
        """Test: Success event."""
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.SUCCESS,
            attempt=5,
            message="Goal achieved",
        )
        # Verify: event.status == GoalStatus.SUCCESS
        assert event.status == GoalStatus.SUCCESS
        # Verify: event.attempt == 5
        assert event.attempt == 5

    def test_failed_event(self):
        """Test: Failed event."""
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.FAILED,
            attempt=20,
            message="All attempts exhausted",
        )
        # Verify: event.status == GoalStatus.FAILED
        assert event.status == GoalStatus.FAILED

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.goal import GoalEvent
        # Verify: is_dataclass(GoalEvent)
        assert is_dataclass(GoalEvent)


class TestEncreGoalRunnerConstruction:
    """Test suite for EncreGoalRunnerConstruction."""
    def test_construction_with_config(self):
        """Test: Construction with config."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        # Verify: runner is not None
        assert runner is not None
        # Verify: runner.config is config
        assert runner.config is config
        # Verify: runner.tool_registry is not None
        assert runner.tool_registry is not None
        # Verify: runner.hook_system is not None
        assert runner.hook_system is not None
        # Verify: runner.safety is not None
        assert runner.safety is not None
        # Verify: runner.telemetry is not None
        assert runner.telemetry is not None

    def test_construction_with_all_params(self):
        """Test: Construction with all params."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        from encre.hooks.system import EncreHookSystem
        from encre.safety import EncreSafetyEngine
        from encre.tools.registry import ToolRegistry

        config = EncreConfig(model="claude-sonnet-4-20250514", backend_type="anthropic")
        tools = ToolRegistry()
        hooks = EncreHookSystem()
        safety = EncreSafetyEngine(config)

        runner = EncreGoalRunner(
            config=config,
            tool_registry=tools,
            hook_system=hooks,
            safety=safety,
        )
        # Verify: runner.tool_registry is tools
        assert runner.tool_registry is tools
        # Verify: runner.hook_system is hooks
        assert runner.hook_system is hooks
        # Verify: runner.safety is safety
        assert runner.safety is safety

    def test_evulator_system_prompt_is_string(self):
        """Test: Evulator system prompt is string."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        # Verify: isinstance(runner.EVALUATOR_SYSTEM_PROMPT, str)
        assert isinstance(runner.EVALUATOR_SYSTEM_PROMPT, str)
        # Verify: "goal completion evaluator" in runner.EVALUATOR_SYSTEM_PROMPT.lower()
        assert "goal completion evaluator" in runner.EVALUATOR_SYSTEM_PROMPT.lower()

    def test_build_goal_prompt(self):
        """Test: Build goal prompt."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner, GoalDefinition
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        goal = GoalDefinition(
            description="Implement login",
            success_criteria="Login endpoint works with JWT",
        )
        prompt = runner._build_goal_prompt(goal)
        # Verify: "GOAL: Implement login" in prompt
        assert "GOAL: Implement login" in prompt
        # Verify: "SUCCESS CRITERIA: Login endpoint works with JWT" in prompt
        assert "SUCCESS CRITERIA: Login endpoint works with JWT" in prompt
        # Verify: "autonomously" in prompt.lower()
        assert "autonomously" in prompt.lower()


class TestEncreGoalLoopConstruction:
    """Test suite for EncreGoalLoopConstruction."""
    def test_construction_basic(self):
        """Test: Construction basic."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop

        config = EncreConfig(model="gpt-5.6", backend_type="openai")

        # Manually create a minimal mock for EncreAgent
        import tempfile
        class MockAgent:
            """MockAgent."""
            def __init__(self):
                """Helper: Init."""
                self.config = config
                from encre.hooks.system import EncreHookSystem
                from encre.memdir.system import EncreMemorySystem
                from encre.safety import EncreSafetyEngine
                from encre.skills.registry import EncreSkillRegistry
                from encre.telemetry import EncreTelemetry
                from encre.tools.registry import ToolRegistry
                self.tool_registry = ToolRegistry()
                self.hook_system = EncreHookSystem()
                self.safety = EncreSafetyEngine(config)
                self.memory_system = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
                self.skill_registry = EncreSkillRegistry()
                self.telemetry = EncreTelemetry(enabled=False)

        agent = MockAgent()
        loop = EncreGoalLoop(
            agent=agent,
            description="Test description",
            success_criteria="Test criteria",
        )
        # Verify: loop is not None
        assert loop is not None
        # Verify: loop._description == "Test description"
        assert loop._description == "Test description"
        # Verify: loop._success_criteria == "Test criteria"
        assert loop._success_criteria == "Test criteria"
        # Verify: loop._max_attempts == 20
        assert loop._max_attempts == 20
        # Verify: loop._timeout_seconds == 3600
        assert loop._timeout_seconds == 3600
        # Verify: loop.runner is not None
        assert loop.runner is not None

    def test_construction_with_custom_params(self):
        """Test: Construction with custom params."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop

        config = EncreConfig(model="gpt-5.6", backend_type="openai")

        class MockAgent:
            """MockAgent."""
            def __init__(self):
                """Helper: Init."""
                self.config = config
                from encre.hooks.system import EncreHookSystem
                from encre.memdir.system import EncreMemorySystem
                from encre.safety import EncreSafetyEngine
                from encre.skills.registry import EncreSkillRegistry
                from encre.telemetry import EncreTelemetry
                from encre.tools.registry import ToolRegistry
                self.tool_registry = ToolRegistry()
                self.hook_system = EncreHookSystem()
                self.safety = EncreSafetyEngine(config)
                self.memory_system = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
                self.skill_registry = EncreSkillRegistry()
                self.telemetry = EncreTelemetry(enabled=False)

        agent = MockAgent()
        loop = EncreGoalLoop(
            agent=agent,
            description="Custom desc",
            success_criteria="Custom criteria",
            max_attempts=5,
            timeout_seconds=600,
        )
        # Verify: loop._max_attempts == 5
        assert loop._max_attempts == 5
        # Verify: loop._timeout_seconds == 600
        assert loop._timeout_seconds == 600

    def test_runner_uses_agent_properties(self):
        """Test: Runner uses agent properties."""
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop

        config = EncreConfig(model="gpt-5.6", backend_type="openai")

        class MockAgent:
            """MockAgent."""
            def __init__(self):
                """Helper: Init."""
                self.config = config
                from encre.hooks.system import EncreHookSystem
                from encre.memdir.system import EncreMemorySystem
                from encre.safety import EncreSafetyEngine
                from encre.skills.registry import EncreSkillRegistry
                from encre.telemetry import EncreTelemetry
                from encre.tools.registry import ToolRegistry
                self.tool_registry = ToolRegistry()
                self.hook_system = EncreHookSystem()
                self.safety = EncreSafetyEngine(config)
                self.memory_system = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
                self.skill_registry = EncreSkillRegistry()
                self.telemetry = EncreTelemetry(enabled=False)

        agent = MockAgent()
        loop = EncreGoalLoop(agent=agent)
        # The runner should reference the agent's subsystems
        assert loop.runner.config is agent.config
        # Verify: loop.runner.tool_registry is agent.tool_registry
        assert loop.runner.tool_registry is agent.tool_registry
        # Verify: loop.runner.hook_system is agent.hook_system
        assert loop.runner.hook_system is agent.hook_system

    @pytest.mark.asyncio
    async def test_execute_raises_without_description(self):
        """Test: Execute raises without description."""
        import pytest
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop

        config = EncreConfig(model="gpt-5.6", backend_type="openai")

        class MockAgent:
            """MockAgent."""
            def __init__(self):
                """Helper: Init."""
                self.config = config
                from encre.hooks.system import EncreHookSystem
                from encre.memdir.system import EncreMemorySystem
                from encre.safety import EncreSafetyEngine
                from encre.skills.registry import EncreSkillRegistry
                from encre.telemetry import EncreTelemetry
                from encre.tools.registry import ToolRegistry
                self.tool_registry = ToolRegistry()
                self.hook_system = EncreHookSystem()
                self.safety = EncreSafetyEngine(config)
                self.memory_system = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
                self.skill_registry = EncreSkillRegistry()
                self.telemetry = EncreTelemetry(enabled=False)

        agent = MockAgent()
        loop = EncreGoalLoop(agent=agent)

        with pytest.raises(ValueError, match="description"):
            await loop.execute()  # No description provided here or at construction
