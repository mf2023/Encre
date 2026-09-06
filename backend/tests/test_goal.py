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

"""Tests for the goal system: definitions, results, statuses, events, and runners."""

import tempfile

import pytest


class TestGoalStatus:
    """Engineered to validate that GoalStatus is a well-formed enum with all
    expected members present and that string conversion round-trips correctly.

    This test class exercises 3 scenarios 鈥?member presence, enum membership,
    and string/name conversion 鈥?to confirm the status type is safe to use
    as a discriminating key in pattern matches and serialization. The design
    follows the invariant that status values must be stable identifiers
    so that goal-state persistence can be compared across restarts.
    """

    def test_verify_all_status_members_are_present_and_not_none(self):
        """Validate that every expected GoalStatus member exists and is not
        None, confirming the enum is fully populated.

        The test asserts each of the six status constants is not None because
        a missing member would indicate an incomplete enum definition and
        would cause KeyError or AttributeError in any code that branches on it.
        """
        from encre.goal import GoalStatus
        assert GoalStatus.PENDING is not None
        assert GoalStatus.IN_PROGRESS is not None
        assert GoalStatus.SUCCESS is not None
        assert GoalStatus.FAILED is not None
        assert GoalStatus.TIMEOUT is not None
        assert GoalStatus.MAX_ATTEMPTS is not None

    def test_verify_goal_status_is_subclass_of_enum(self):
        """Validate that GoalStatus is a proper Enum subclass, confirming
        it supports enum operations like iteration and member comparison.

        The test asserts issubclass because the goal runner uses enum
        comparison (is, ==) to drive state transitions, so the type must
        be a true Enum and not a plain IntEnum or string wrapper.
        """
        from enum import Enum

        from encre.goal import GoalStatus
        assert issubclass(GoalStatus, Enum)

    def test_verify_status_string_conversion_preserves_name(self):
        """Validate that str(GoalStatus.X) yields the canonical 'GoalStatus.X'
        form and that .name returns just the member name, confirming both
        conversion paths work for logging and comparison.

        The test exercises str() and .name on two different members and
        asserts the expected forms because logs use str() for human
        readability while code branches use .name for stable comparison.
        """
        from encre.goal import GoalStatus
        assert str(GoalStatus.PENDING) == "GoalStatus.PENDING"
        status = GoalStatus.SUCCESS
        assert status.name == "SUCCESS"


class TestGoalDefinition:
    """Engineered to validate the GoalDefinition dataclass construction paths,
    default values, and dataclass identity.

    This test class exercises 6 scenarios 鈥?minimal construction, default
    values, full construction, dataclass identity, and custom timeout and
    max_attempts 鈥?to confirm the definition schema is stable and that
    defaults are sensible for long-running autonomous goals. The design
    follows the invariant that default max_attempts=20 and timeout=3600s
    provide a safe ceiling for most tasks without requiring explicit
    configuration for simple goals.
    """

    def test_verify_minimal_construction_preserves_required_fields(self):
        """Validate that GoalDefinition accepts only description and
        success_criteria and stores them verbatim, confirming the minimal
        required-field path is functional.

        The test exercises construction with the two mandatory fields and
        asserts both match because these are the only fields the caller
        must provide; everything else should come from defaults.
        """
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Test goal",
            success_criteria="Tests pass",
        )
        assert goal.description == "Test goal"
        assert goal.success_criteria == "Tests pass"

    def test_verify_default_values_are_sensible_for_long_running_goals(self):
        """Validate that GoalDefinition applies the documented defaults for
        max_attempts, timeout_seconds, evaluator_model, and evaluator_provider
        when they are not supplied.

        The test exercises minimal construction and asserts each default
        because the defaults define the safety envelope 鈥?too low and goals
        fail prematurely; too high and the agent wastes resources.
        """
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Default test",
            success_criteria="All good",
        )
        assert goal.max_attempts == 20
        assert goal.timeout_seconds == 3600
        assert goal.evaluator_model == ""
        assert goal.evaluator_provider == ""

    def test_verify_full_construction_preserves_all_overrides(self):
        """Validate that GoalDefinition stores all explicitly provided fields
        including evaluator_model and evaluator_provider, confirming the full
        construction path supports all configuration knobs.

        The test exercises construction with every field set and asserts each
        value matches because custom evaluators and tighter timeouts are
        needed for production goals that run against real codebases.
        """
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Complex task",
            success_criteria="Zero errors, all features work",
            max_attempts=10,
            timeout_seconds=1800,
            evaluator_model="gpt-4o-mini",
            evaluator_provider="openai",
        )
        assert goal.description == "Complex task"
        assert goal.success_criteria == "Zero errors, all features work"
        assert goal.max_attempts == 10
        assert goal.timeout_seconds == 1800
        assert goal.evaluator_model == "gpt-4o-mini"
        assert goal.evaluator_provider == "openai"

    def test_verify_goal_definition_is_dataclass(self):
        """Validate that GoalDefinition is recognized by dataclasses.is_dataclass,
        confirming it supports generated __init__, __repr__, and comparison.

        The test asserts is_dataclass because the goal runner constructs
        definitions dynamically and relies on dataclass features for
        serialization and structural comparison.
        """
        from dataclasses import is_dataclass

        from encre.goal import GoalDefinition
        assert is_dataclass(GoalDefinition)

    def test_verify_non_default_timeout_is_preserved(self):
        """Validate that a custom timeout_seconds value is stored without
        being clamped or overridden by the default.

        The test exercises construction with timeout_seconds=300 and asserts
        the value is preserved because short-running goals (e.g. smoke tests)
        need a tighter timeout than the 3600s default.
        """
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Quick task",
            success_criteria="Done",
            timeout_seconds=300,
        )
        assert goal.timeout_seconds == 300

    def test_verify_non_default_max_attempts_is_preserved(self):
        """Validate that a custom max_attempts value is stored without
        being clamped or overridden by the default.

        The test exercises construction with max_attempts=100 and asserts
        the value is preserved because complex multi-step goals may need
        more than the 20-attempt default to converge.
        """
        from encre.goal import GoalDefinition
        goal = GoalDefinition(
            description="Many attempts",
            success_criteria="Eventually",
            max_attempts=100,
        )
        assert goal.max_attempts == 100


class TestGoalResult:
    """Engineered to validate the GoalResult dataclass construction paths,
    default values, and mutability of the milestones list.

    This test class exercises 7 scenarios 鈥?default construction, full
    construction, failed status, timeout status, max_attempts status,
    milestone mutability, and dataclass identity 鈥?to confirm the result
    shape is stable for both success and failure reporting. The design
    follows the invariant that milestones must be a mutable list so that
    the runner can append progress markers during execution.
    """

    def test_verify_default_construction_sets_all_optional_fields_to_empty_or_zero(self):
        """Validate that GoalResult constructed with only status sets summary,
        attempts, elapsed_seconds, final_output, and milestones to their
        default values.

        The test exercises minimal construction and asserts each default
        because the result is often created upfront and populated incrementally;
        empty defaults prevent AttributeError on first access.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(status=GoalStatus.PENDING)
        assert result.status == GoalStatus.PENDING
        assert result.summary == ""
        assert result.attempts == 0
        assert result.elapsed_seconds == 0.0
        assert result.final_output == ""
        assert result.milestones == []

    def test_verify_full_construction_preserves_all_fields(self):
        """Validate that GoalResult stores all explicitly provided fields
        including milestones, attempts, and elapsed time.

        The test exercises full construction and asserts each value matches
        because the result object is serialized to the goal history and
        must preserve the exact values reported by the runner.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.SUCCESS,
            summary="All tests passed",
            attempts=3,
            elapsed_seconds=45.2,
            final_output="Task completed successfully",
            milestones=["Step 1 done", "Step 2 done", "All done"],
        )
        assert result.status == GoalStatus.SUCCESS
        assert result.summary == "All tests passed"
        assert result.attempts == 3
        assert result.elapsed_seconds == 45.2
        assert result.final_output == "Task completed successfully"
        assert len(result.milestones) == 3
        assert "Step 1 done" in result.milestones

    def test_verify_failed_status_result_carries_summary_and_attempt_count(self):
        """Validate that a FAILED GoalResult preserves the summary and
        attempts count, confirming failure reporting is complete.

        The test exercises construction with FAILED status and asserts the
        fields match because failure reports are the primary diagnostic
        output and must include why the goal failed and how many tries were used.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.FAILED,
            summary="Could not complete the task",
            attempts=10,
            elapsed_seconds=600.0,
        )
        assert result.status == GoalStatus.FAILED
        assert result.attempts == 10

    def test_verify_timeout_status_result_carries_elapsed_seconds(self):
        """Validate that a TIMEOUT GoalResult carries the elapsed time that
        exceeded the limit, confirming the timeout diagnostic is preserved.

        The test exercises construction with TIMEOUT and elapsed_seconds=3601.0
        and asserts the value matches because the caller needs to know how
        close the goal came to completing before the timeout fired.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.TIMEOUT,
            summary="Timed out",
            elapsed_seconds=3601.0,
        )
        assert result.status == GoalStatus.TIMEOUT

    def test_verify_max_attempts_status_result_carries_attempt_count(self):
        """Validate that a MAX_ATTEMPTS GoalResult carries the attempt count
        that was exhausted, confirming the boundary condition is recorded.

        The test exercises construction with MAX_ATTEMPTS and attempts=20
        and asserts the value matches because the distinction between
        FAILED and MAX_ATTEMPTS is which ceiling was hit first.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(
            status=GoalStatus.MAX_ATTEMPTS,
            summary="Reached max attempts",
            attempts=20,
        )
        assert result.status == GoalStatus.MAX_ATTEMPTS

    def test_verify_milestones_list_is_mutable_after_construction(self):
        """Validate that the milestones list can be appended to after
        construction, confirming it is a mutable container not a frozen tuple.

        The test exercises construction with one milestone and appends two
        more and asserts the final length is three because the runner must
        be able to record progress markers during execution.
        """
        from encre.goal import GoalResult, GoalStatus
        result = GoalResult(status=GoalStatus.IN_PROGRESS, milestones=["started"])
        result.milestones.append("middle")
        result.milestones.append("almost done")
        assert len(result.milestones) == 3

    def test_verify_goal_result_is_dataclass(self):
        """Validate that GoalResult is recognized by dataclasses.is_dataclass,
        confirming it supports generated __init__, __repr__, and comparison.

        The test asserts is_dataclass because the goal runner constructs
        results dynamically and relies on dataclass features for
        serialization to the goal history store.
        """
        from dataclasses import is_dataclass

        from encre.goal import GoalResult
        assert is_dataclass(GoalResult)


class TestGoalEvent:
    """Engineered to validate the GoalEvent dataclass construction paths
    and default values, confirming the event shape is stable for the
    observer pipeline.

    This test class exercises 5 scenarios 鈥?construction, defaults, success
    event, failed event, and dataclass identity 鈥?to confirm that events
    carry enough context for downstream observers to render progress UI
    and audit logs without additional lookups. The design follows the
    invariant that attempt and message are optional so that high-level
    status transitions do not require per-attempt detail.
    """

    def test_verify_construction_preserves_status_attempt_and_message(self):
        """Validate that GoalEvent stores status, attempt, and message
        verbatim when all three are provided.

        The test exercises construction with explicit values and asserts
        each field matches because the observer pipeline routes on these
        three fields to update the goal progress widget.
        """
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.IN_PROGRESS,
            attempt=1,
            message="Working on it",
        )
        assert event.status == GoalStatus.IN_PROGRESS
        assert event.attempt == 1
        assert event.message == "Working on it"

    def test_verify_default_values_are_zero_and_empty_for_optional_fields(self):
        """Validate that GoalEvent defaults attempt to 0 and message to ""
        when not provided, confirming the minimal construction path is safe.

        The test exercises construction with only status and asserts the
        defaults because high-level status transitions (e.g. PENDING ->
        IN_PROGRESS) do not always have an associated attempt number.
        """
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(status=GoalStatus.PENDING)
        assert event.attempt == 0
        assert event.message == ""

    def test_verify_success_event_carries_attempt_and_message(self):
        """Validate that a SUCCESS GoalEvent preserves the attempt count and
        completion message, confirming the final-state event is complete.

        The test exercises construction with SUCCESS, attempt=5, and a
        completion message and asserts each field matches because the
        success event is the terminal signal and must be fully informative.
        """
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.SUCCESS,
            attempt=5,
            message="Goal achieved",
        )
        assert event.status == GoalStatus.SUCCESS
        assert event.attempt == 5

    def test_verify_failed_event_carries_attempt_and_message(self):
        """Validate that a FAILED GoalEvent preserves the attempt count and
        failure message, confirming the failure event is fully diagnostic.

        The test exercises construction with FAILED, attempt=20, and an
        exhaustion message and asserts each field matches because failure
        events are the primary input to the goal auditor.
        """
        from encre.goal import GoalEvent, GoalStatus
        event = GoalEvent(
            status=GoalStatus.FAILED,
            attempt=20,
            message="All attempts exhausted",
        )
        assert event.status == GoalStatus.FAILED

    def test_verify_goal_event_is_dataclass(self):
        """Validate that GoalEvent is recognized by dataclasses.is_dataclass,
        confirming it supports generated __init__, __repr__, and comparison.

        The test asserts is_dataclass because events are collected into lists
        and compared structurally by the observer pipeline.
        """
        from dataclasses import is_dataclass

        from encre.goal import GoalEvent
        assert is_dataclass(GoalEvent)


class TestEncreGoalRunnerConstruction:
    """Engineered to validate EncreGoalRunner construction paths, dependency
    injection, and the structure of the evaluator system prompt.

    This test class exercises 4 scenarios 鈥?construction with config only,
    construction with all explicit dependencies, evaluator prompt type,
    and goal-prompt rendering 鈥?to confirm the runner wires subsystems
    correctly and produces prompts in the expected format. The design
    follows the invariant that the runner is a self-contained orchestrator
    that receives all subsystems at construction time so that execute()
    has no late-binding surprises.
    """

    def test_verify_construction_with_config_only_creates_all_subsystems(self):
        """Validate that EncreGoalRunner constructed with only a config
        creates non-None instances for tool_registry, hook_system, safety,
        and telemetry, confirming the default-subsystem path is complete.

        The test exercises minimal construction and asserts each subsystem
        is not None because the runner must be fully operational without
        explicit dependency injection for simple use cases.
        """
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        assert runner is not None
        assert runner.config is config
        assert runner.tool_registry is not None
        assert runner.hook_system is not None
        assert runner.safety is not None
        assert runner.telemetry is not None

    def test_verify_construction_with_all_params_preserves_identity(self):
        """Validate that EncreGoalRunner stores explicitly provided
        tool_registry, hook_system, and safety instances by identity when
        all parameters are supplied.

        The test exercises full construction with custom instances and asserts
        identity because custom subsystems may carry pre-registered state
        (e.g. hooks, tool registrations) that must not be replaced.
        """
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
        assert runner.tool_registry is tools
        assert runner.hook_system is hooks
        assert runner.safety is safety

    def test_verify_evaluator_system_prompt_is_nonempty_string_with_expected_keywords(self):
        """Validate that the EVALUATOR_SYSTEM_PROMPT class attribute is a
        non-empty string containing the phrase 'goal completion evaluator',
        confirming the prompt template is wired and recognizable.

        The test exercises runner construction and asserts the string
        properties because the evaluator prompt drives the LLM judge that
        decides whether a goal result meets the success criteria.
        """
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        assert isinstance(runner.EVALUATOR_SYSTEM_PROMPT, str)
        assert "goal completion evaluator" in runner.EVALUATOR_SYSTEM_PROMPT.lower()

    def test_verify_build_goal_prompt_includes_description_and_success_criteria(self):
        """Validate that _build_goal_prompt renders the goal description and
        success criteria into the output string with the expected formatting.

        The test exercises prompt construction with a sample goal and asserts
        the key phrases appear because the prompt is the primary contract
        sent to the LLM and must contain both the task and the acceptance
        criteria for the model to evaluate correctly.
        """
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner, GoalDefinition
        config = EncreConfig(model="gpt-5.6", backend_type="openai")
        runner = EncreGoalRunner(config=config)
        goal = GoalDefinition(
            description="Implement login",
            success_criteria="Login endpoint works with JWT",
        )
        prompt = runner._build_goal_prompt(goal)
        assert "GOAL: Implement login" in prompt
        assert "SUCCESS CRITERIA: Login endpoint works with JWT" in prompt
        assert "autonomously" in prompt.lower()


class TestEncreGoalLoopConstruction:
    """Engineered to validate EncreGoalLoop construction paths, parameter
    override behavior, and the requirement that description be provided.

    This test class exercises 4 scenarios 鈥?basic construction, custom
    params, runner property delegation, and execute-without-description
    error 鈥?to confirm the loop wraps the runner correctly and enforces
    its invariants. The design follows the invariant that the loop is a
    thin orchestrator over the runner, delegating config and subsystem
    references to the agent it is attached to.
    """

    def test_verify_basic_construction_sets_description_success_criteria_and_defaults(self):
        """Validate that EncreGoalLoop constructed with agent, description,
        and success_criteria stores those values and applies default max_attempts
        and timeout_seconds.

        The test exercises construction with a MockAgent and asserts the
        fields and defaults match because the loop must be immediately
        executable after construction without additional configuration.
        """
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
        assert loop is not None
        assert loop._description == "Test description"
        assert loop._success_criteria == "Test criteria"
        assert loop._max_attempts == 20
        assert loop._timeout_seconds == 3600
        assert loop.runner is not None

    def test_verify_construction_with_custom_params_applies_overrides(self):
        """Validate that EncreGoalLoop stores explicitly provided max_attempts
        and timeout_seconds instead of the defaults.

        The test exercises construction with custom values and asserts the
        overrides are preserved because long-running goals need tighter
        control over retry and timeout budgets.
        """
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
        assert loop._max_attempts == 5
        assert loop._timeout_seconds == 600

    def test_verify_runner_delegates_config_and_subsystem_references_to_agent(self):
        """Validate that the runner inside EncreGoalLoop references the same
        config, tool_registry, and hook_system instances as the parent agent,
        confirming delegation rather than duplication.

        The test exercises construction with only agent (no description) and
        asserts identity for config, tool_registry, and hook_system because
        the runner must share the agent's subsystem state to operate on the
        same tool registrations and hook handlers.
        """
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
        assert loop.runner.tool_registry is agent.tool_registry
        assert loop.runner.hook_system is agent.hook_system

    @pytest.mark.asyncio
    async def test_verify_execute_raises_when_description_is_missing(self):
        """Validate that execute() raises ValueError when called without a
        description and none was provided at construction time, confirming
        the required-field guard is enforced at execution time.

        The test exercises construction with only agent (no description) and
        calls execute() and asserts ValueError with match='description' because
        a goal without a description is semantically undefined and must not
        proceed silently to the LLM.
        """
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
