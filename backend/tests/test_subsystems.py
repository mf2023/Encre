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

"""Tests for task subsystem, browser, auto-safety, feedback, skills, thinking."""



# ===========================================================================
# Task System
# ===========================================================================

class TestTaskSystem:
    """Test cases covering task system.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_encre_task(self):
        """Verifies that encre task."""
        from encre.task.types import EncreTask
        task = EncreTask(
            id="task_1",
            name="Test task",
            description="A test task",
            task_type="bash",
            prompt="run tests",
            status="pending",
        )
        # Confirm the expected result for this scenario: encre task.
        assert task.id == "task_1"
        assert task.name == "Test task"
        assert task.task_type == "bash"
        assert task.status == "pending"

    def test_encre_task_with_id(self):
        """Verifies that encre task with id."""
        from encre.task.types import EncreTask
        task = EncreTask(
            id="task_custom",
            name="Custom id task",
            description="Custom id",
            task_type="agent",
            prompt="do something",
        )
        # Confirm the expected result for this scenario: encre task with id.
        assert task.id == "task_custom"
        assert task.name == "Custom id task"

    def test_task_manager_create(self):
        """Verifies that task manager create."""
        from encre.task.manager import EncreTaskManager
        tm = EncreTaskManager()
        # Confirm the expected result for this scenario: task manager create.
        assert tm is not None

    def test_task_executor_create(self):
        """Verifies that task executor create."""
        from encre.task.executor import EncreTaskExecutor
        te = EncreTaskExecutor()
        # Confirm the expected result for this scenario: task executor create.
        assert te is not None


# ===========================================================================
# Browser Session
# ===========================================================================

class TestBrowser:
    """Test cases covering browser.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_browser_state(self):
        """Verifies that browser state."""
        from encre.computer.browser import BrowserState
        state = BrowserState(url="https://example.com", title="Example")
        # Confirm the expected result for this scenario: browser state.
        assert state.url == "https://example.com"
        assert state.title == "Example"
        assert state.html == ""
        assert state.text == ""

    def test_browser_session_create(self):
        """Verifies that browser session create."""
        from encre.computer.browser import EncreBrowserSession
        bs = EncreBrowserSession()
        # Confirm the expected result for this scenario: browser session create.
        assert bs is not None
        assert bs.headless is True


# ===========================================================================
# Auto Safety
# ===========================================================================

class TestAutoSafety:
    """Test cases covering auto safety.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_auto_decision(self):
        """Verifies that auto decision."""
        from encre.autosafety import AutoDecision
        # Confirm the expected result for this scenario: auto decision.
        assert AutoDecision.SAFE is not None
        assert AutoDecision.LOW_RISK is not None
        assert AutoDecision.ASK_USER is not None
        assert AutoDecision.HIGH_RISK is not None
        assert AutoDecision.BLOCK is not None

    def test_classification_result(self):
        """Verifies that classification result."""
        from encre.autosafety import AutoDecision, ClassificationResult
        cr = ClassificationResult(
            decision=AutoDecision.SAFE,
            confidence=0.95,
            reasoning="safe command",
        )
        # Confirm the expected result for this scenario: classification result.
        assert cr.decision == AutoDecision.SAFE
        assert cr.confidence == 0.95

    def test_user_decision_record(self):
        """Verifies that user decision record."""
        from encre.autosafety import UserDecisionRecord
        udr = UserDecisionRecord(
            tool_name="bash",
            tool_args_summary="cmd=ls",
            user_approved=True,
        )
        # Confirm the expected result for this scenario: user decision record.
        assert udr.tool_name == "bash"
        assert udr.user_approved is True

    def test_classifier_create(self):
        """Verifies that classifier create."""
        from encre.autosafety import EncreAutoSafetyClassifier
        classifier = EncreAutoSafetyClassifier()
        # Confirm the expected result for this scenario: classifier create.
        assert classifier is not None


# ===========================================================================
# Feedback Learner
# ===========================================================================

class TestFeedback:
    """Test cases covering feedback.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_correction_record(self):
        """Verifies that correction record."""
        from encre.feedback.learner import CorrectionRecord
        cr = CorrectionRecord(
            tool_name="bash",
            error_type="command_not_found",
            error_context="command not found: pyth",
            user_correction="use correct path: python",
        )
        # Confirm the expected result for this scenario: correction record.
        assert cr.tool_name == "bash"
        assert cr.error_type == "command_not_found"
        assert cr.user_correction == "use correct path: python"

    def test_learner_create(self):
        """Verifies that learner create."""
        from encre.feedback.learner import EncreFeedbackLearner
        learner = EncreFeedbackLearner()
        # Confirm the expected result for this scenario: learner create.
        assert learner is not None


# ===========================================================================
# Skills
# ===========================================================================

class TestSkills:
    """Test cases covering skills.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_skill_definition(self):
        """Verifies that skill definition."""
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            """Verifies that prompt fn."""
            return "debugging prompt"

        skill = BundledSkillDefinition(
            name="debug",
            description="Debugging skill",
            get_prompt_for_command=_prompt_fn,
        )
        # Confirm the expected result for this scenario: skill definition.
        assert skill.name == "debug"
        assert skill.description == "Debugging skill"

    def test_skill_registry_create(self):
        """Verifies that skill registry create."""
        from encre.skills.registry import EncreSkillRegistry
        registry = EncreSkillRegistry()
        # Confirm the expected result for this scenario: skill registry create.
        assert registry is not None

    def test_create_bundled_skills(self):
        """Verifies that create bundled skills."""
        from encre.skills.bundled import create_bundled_skills
        from encre.skills.builtin import builtin_skills_dir
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import SkillSource
        registry = EncreSkillRegistry()
        create_bundled_skills(registry)
        registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)
        # After creation, registry should have bundled skills. loop is
        # programmatically registered; debug is a static builtin SKILL.md.
        loop = registry.lookup("loop")
        # Confirm the expected result for this scenario: create bundled skills.
        assert loop is not None
        assert loop.name == "loop"
        skill = registry.lookup("debug")
        assert skill is not None
        assert skill.name == "debug"


# ===========================================================================
# Thinking
# ===========================================================================

class TestThinking:
    """Test cases covering thinking.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_thinking_module_imports(self):
        """Verifies that thinking module imports."""
        from encre.thinking.config import resolve_thinking_config
        result = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        # Confirm the expected result for this scenario: thinking module imports.
        assert result is not None
        assert result.enabled is True

    def test_adaptive_thinking_resolution(self):
        """Verifies that adaptive thinking resolution."""
        from encre.thinking.config import resolve_thinking_config
        from encre.utils.types import AdaptiveThinking, DisabledThinking
        # None config + claude model -> adaptive
        resolved = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        # Confirm the expected result for this scenario: adaptive thinking resolution.
        assert isinstance(resolved, AdaptiveThinking)
        # None config + non-claude model -> disabled
        resolved2 = resolve_thinking_config(None, "gpt-4o")
        assert isinstance(resolved2, DisabledThinking)

    def test_get_thinking_budget(self):
        """Verifies that get thinking budget."""
        from encre.thinking.config import get_thinking_budget_tokens
        from encre.utils.types import DisabledThinking, EnabledThinking
        # Confirm the expected result for this scenario: get thinking budget.
        assert get_thinking_budget_tokens(EnabledThinking(budget_tokens=8000)) == 8000
        assert get_thinking_budget_tokens(DisabledThinking()) == 0


# ===========================================================================
# Scheduler types
# ===========================================================================

class TestSchedulerTypes:
    """Test cases covering scheduler types.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_scheduled_job(self):
        """Verifies that scheduled job."""
        from encre.scheduler import ScheduledJob, ScheduleType
        job = ScheduledJob(
            id="job1",
            name="test job",
            prompt="run tests",
            schedule_type=ScheduleType.RECURRING,
        )
        # Confirm the expected result for this scenario: scheduled job.
        assert job.id == "job1"
        assert job.name == "test job"
        assert job.prompt == "run tests"

    def test_cron_schedule(self):
        """Verifies that cron schedule."""
        from encre.scheduler import CronSchedule
        cs = CronSchedule(
            minute="*/5", hour="*", day_of_month="*", month="*", day_of_week="*"
        )
        # Confirm the expected result for this scenario: cron schedule.
        assert cs.minute == "*/5"

    def test_schedule_type(self):
        """Verifies that schedule type."""
        from encre.scheduler import ScheduleType
        # Confirm the expected result for this scenario: schedule type.
        assert ScheduleType.ONE_SHOT is not None
        assert ScheduleType.RECURRING is not None

    def test_job_state(self):
        """Verifies that job state."""
        from encre.scheduler import JobState
        # Confirm the expected result for this scenario: job state.
        assert JobState.PENDING is not None
        assert JobState.RUNNING is not None
        assert JobState.COMPLETED is not None
        assert JobState.FAILED is not None
        assert JobState.CANCELLED is not None


# ===========================================================================
# Prompt types
# ===========================================================================

class TestPrompts:
    """Test cases covering prompts.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_base_prompt(self):
        """Verifies that base prompt."""
        from encre.prompts.base import EncreBasePrompt
        # EncreBasePrompt is an ABC, can't instantiate directly
        # Confirm the expected result for this scenario: base prompt.
        assert EncreBasePrompt is not None

    def test_prompt_template(self):
        """Verifies that prompt template."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="coding")
        # Confirm the expected result for this scenario: prompt template.
        assert tmpl is not None
        assert tmpl._specialty == "coding"

    def test_prompt_builder(self):
        """Verifies that prompt builder."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        # Confirm the expected result for this scenario: prompt builder.
        assert builder is not None

    def test_coding_prompt(self):
        """Verifies that coding prompt."""
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        # Confirm the expected result for this scenario: coding prompt.
        assert cp is not None

    def test_general_prompt(self):
        """Verifies that general prompt."""
        from encre.prompts.general import EncreGeneralPrompt
        gp = EncreGeneralPrompt()
        # Confirm the expected result for this scenario: general prompt.
        assert gp is not None

    def test_research_prompt(self):
        """Verifies that research prompt."""
        from encre.prompts.research import EncreResearchPrompt
        rp = EncreResearchPrompt()
        # Confirm the expected result for this scenario: research prompt.
        assert rp is not None

    def test_data_prompt(self):
        """Verifies that data prompt."""
        from encre.prompts.data import EncreDataPrompt
        dp = EncreDataPrompt()
        # Confirm the expected result for this scenario: data prompt.
        assert dp is not None


class TestSkillTool:
    """Tests for the model-facing skill activation tool."""

    @staticmethod
    def _fake_loop():
        from encre.skills.builtin import builtin_skills_dir
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import SkillSource
        from encre.skills.bundled import create_bundled_skills

        registry = EncreSkillRegistry()
        create_bundled_skills(registry)
        registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)

        class _Loop:
            skill_registry = registry
            class _S:
                id = "test"
            session = _S()
            _active_doc_skills = {}

        loop = _Loop()
        from encre.tools.builtin.find_tool import set_parent_loop
        set_parent_loop(loop)
        return loop

    def test_skill_tool_registered(self):
        """The skill tool is registered in the default tool set."""
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        assert "skill" in tr.list_tools()

    def test_skill_tool_activates_and_caches(self):
        """Activating a skill caches its body on the loop for next-turn injection."""
        import asyncio
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        exe = tr.list_tools()["skill"].execute
        loop = self._fake_loop()
        result = asyncio.run(exe(name="travel-flights", args="Beijing to Shanghai"))
        assert "travel-flights" in result
        assert "travel-flights" in loop._active_doc_skills
        body = loop._active_doc_skills["travel-flights"]
        assert "Flight Search Guidance" in body

    def test_skill_tool_alias_normalises_to_canonical(self):
        """An alias resolves to the canonical skill name in the cache."""
        import asyncio
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        exe = tr.list_tools()["skill"].execute
        loop = self._fake_loop()
        asyncio.run(exe(name="flights"))
        # Alias "flights" must cache under the canonical "travel-flights".
        assert "travel-flights" in loop._active_doc_skills
        assert "flights" not in loop._active_doc_skills

    def test_skill_tool_unknown_name_errors(self):
        """An unknown skill name returns a clear error, not a crash."""
        import asyncio
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        exe = tr.list_tools()["skill"].execute
        self._fake_loop()
        result = asyncio.run(exe(name="does-not-exist"))
        assert result.startswith("Error:")
