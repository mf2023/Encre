#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for task subsystem, browser, auto-safety, feedback, skills, thinking."""

import pytest


# ===========================================================================
# Task System
# ===========================================================================

class TestTaskSystem:
    def test_ymi_task(self):
        from yim.task.types import YmiTask
        task = YmiTask(
            id="task_1",
            name="Test task",
            description="A test task",
            task_type="bash",
            prompt="run tests",
            status="pending",
        )
        assert task.id == "task_1"
        assert task.name == "Test task"
        assert task.task_type == "bash"
        assert task.status == "pending"

    def test_ymi_task_with_id(self):
        from yim.task.types import YmiTask
        task = YmiTask(
            id="task_custom",
            name="Custom id task",
            description="Custom id",
            task_type="agent",
            prompt="do something",
        )
        assert task.id == "task_custom"
        assert task.name == "Custom id task"

    def test_task_manager_create(self):
        from yim.task.manager import YmiTaskManager
        tm = YmiTaskManager()
        assert tm is not None

    def test_task_executor_create(self):
        from yim.task.executor import YmiTaskExecutor
        te = YmiTaskExecutor()
        assert te is not None


# ===========================================================================
# Browser Session
# ===========================================================================

class TestBrowser:
    def test_browser_state(self):
        from yim.computer.browser import BrowserState
        state = BrowserState(url="https://example.com", title="Example")
        assert state.url == "https://example.com"
        assert state.title == "Example"
        assert state.html == ""
        assert state.text == ""

    def test_browser_session_create(self):
        from yim.computer.browser import YmiBrowserSession
        bs = YmiBrowserSession()
        assert bs is not None
        assert bs.headless is True


# ===========================================================================
# Auto Safety
# ===========================================================================

class TestAutoSafety:
    def test_auto_decision(self):
        from yim.autosafety import AutoDecision
        assert AutoDecision.SAFE is not None
        assert AutoDecision.LOW_RISK is not None
        assert AutoDecision.ASK_USER is not None
        assert AutoDecision.HIGH_RISK is not None
        assert AutoDecision.BLOCK is not None

    def test_classification_result(self):
        from yim.autosafety import ClassificationResult, AutoDecision
        cr = ClassificationResult(
            decision=AutoDecision.SAFE,
            confidence=0.95,
            reasoning="safe command",
        )
        assert cr.decision == AutoDecision.SAFE
        assert cr.confidence == 0.95

    def test_user_decision_record(self):
        from yim.autosafety import UserDecisionRecord
        udr = UserDecisionRecord(
            tool_name="bash",
            tool_args_summary="cmd=ls",
            user_approved=True,
        )
        assert udr.tool_name == "bash"
        assert udr.user_approved is True

    def test_classifier_create(self):
        from yim.autosafety import YmiAutoSafetyClassifier
        classifier = YmiAutoSafetyClassifier()
        assert classifier is not None


# ===========================================================================
# Feedback Learner
# ===========================================================================

class TestFeedback:
    def test_correction_record(self):
        from yim.feedback.learner import CorrectionRecord
        cr = CorrectionRecord(
            tool_name="bash",
            error_type="command_not_found",
            error_context="command not found: pyth",
            user_correction="use correct path: python",
        )
        assert cr.tool_name == "bash"
        assert cr.error_type == "command_not_found"
        assert cr.user_correction == "use correct path: python"

    def test_learner_create(self):
        from yim.feedback.learner import YmiFeedbackLearner
        learner = YmiFeedbackLearner()
        assert learner is not None


# ===========================================================================
# Skills
# ===========================================================================

class TestSkills:
    def test_skill_definition(self):
        from yim.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "debugging prompt"

        skill = BundledSkillDefinition(
            name="debug",
            description="Debugging skill",
            get_prompt_for_command=_prompt_fn,
        )
        assert skill.name == "debug"
        assert skill.description == "Debugging skill"

    def test_skill_registry_create(self):
        from yim.skills.registry import YmiSkillRegistry
        registry = YmiSkillRegistry()
        assert registry is not None

    def test_create_bundled_skills(self):
        from yim.skills.bundled import create_bundled_skills
        from yim.skills.registry import YmiSkillRegistry
        registry = YmiSkillRegistry()
        create_bundled_skills(registry)
        # After creation, registry should have bundled skills
        skill = registry.lookup("debug")
        assert skill is not None
        assert skill.name == "debug"


# ===========================================================================
# Thinking
# ===========================================================================

class TestThinking:
    def test_thinking_module_imports(self):
        from yim.thinking.config import resolve_thinking_config
        from yim.utils.types import AdaptiveThinking
        result = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        assert result is not None
        assert result.enabled is True

    def test_adaptive_thinking_resolution(self):
        from yim.thinking.config import resolve_thinking_config
        from yim.utils.types import DisabledThinking, AdaptiveThinking
        # None config + claude model → adaptive
        resolved = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        assert isinstance(resolved, AdaptiveThinking)
        # None config + non-claude model → disabled
        resolved2 = resolve_thinking_config(None, "gpt-4o")
        assert isinstance(resolved2, DisabledThinking)

    def test_get_thinking_budget(self):
        from yim.thinking.config import get_thinking_budget_tokens
        from yim.utils.types import EnabledThinking, DisabledThinking
        assert get_thinking_budget_tokens(EnabledThinking(budget_tokens=8000)) == 8000
        assert get_thinking_budget_tokens(DisabledThinking()) == 0


# ===========================================================================
# Scheduler types
# ===========================================================================

class TestSchedulerTypes:
    def test_scheduled_job(self):
        from yim.scheduler import ScheduledJob, ScheduleType
        job = ScheduledJob(
            id="job1",
            name="test job",
            prompt="run tests",
            schedule_type=ScheduleType.RECURRING,
        )
        assert job.id == "job1"
        assert job.name == "test job"
        assert job.prompt == "run tests"

    def test_cron_schedule(self):
        from yim.scheduler import CronSchedule
        cs = CronSchedule(
            minute="*/5", hour="*", day_of_month="*", month="*", day_of_week="*"
        )
        assert cs.minute == "*/5"

    def test_schedule_type(self):
        from yim.scheduler import ScheduleType
        assert ScheduleType.ONE_SHOT is not None
        assert ScheduleType.RECURRING is not None

    def test_job_state(self):
        from yim.scheduler import JobState
        assert JobState.PENDING is not None
        assert JobState.RUNNING is not None
        assert JobState.COMPLETED is not None
        assert JobState.FAILED is not None
        assert JobState.CANCELLED is not None


# ===========================================================================
# Prompt types
# ===========================================================================

class TestPrompts:
    def test_base_prompt(self):
        from yim.prompts.base import YmiBasePrompt
        # YmiBasePrompt is an ABC, can't instantiate directly
        assert YmiBasePrompt is not None

    def test_prompt_template(self):
        from yim.prompts.base import YmiPromptTemplate
        tmpl = YmiPromptTemplate(specialty="coding")
        assert tmpl is not None
        assert tmpl._specialty == "coding"

    def test_prompt_builder(self):
        from yim.prompts.system import YmiPromptBuilder
        builder = YmiPromptBuilder()
        assert builder is not None

    def test_coding_prompt(self):
        from yim.prompts.coding import YmiCodingPrompt
        cp = YmiCodingPrompt()
        assert cp is not None

    def test_general_prompt(self):
        from yim.prompts.general import YmiGeneralPrompt
        gp = YmiGeneralPrompt()
        assert gp is not None

    def test_research_prompt(self):
        from yim.prompts.research import YmiResearchPrompt
        rp = YmiResearchPrompt()
        assert rp is not None

    def test_data_prompt(self):
        from yim.prompts.data import YmiDataPrompt
        dp = YmiDataPrompt()
        assert dp is not None
