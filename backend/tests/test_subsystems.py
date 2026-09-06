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

"""Tests for task subsystem, browser, auto-safety, feedback, skills, thinking."""



# ===========================================================================
# Task System
# ===========================================================================

class TestTaskSystem:
    """Engineered to validate the core task data model and subsystem instantiation.

    This test class exercises EncreTask construction, EncreTaskManager creation,
    and EncreTaskExecutor creation across 4 scenarios to ensure the task system's
    foundational types initialize with correct fields and that the manager and
    executor singletons are constructible. The design follows the principle that
    task types must carry id, name, description, task_type, prompt, and status
    as first-class fields so downstream schedulers and executors can route work
    without additional mapping layers.
    """
    def test_verify_encre_task_basic_fields(self):
        """Validate that EncreTask stores all required construction fields correctly.

        The test constructs a bash-type task and asserts id, name, task_type, and
        status match the supplied values because the dataclass must faithfully
        persist constructor arguments for the scheduler to route and track work.
        """
        from encre.task.types import EncreTask
        task = EncreTask(
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

    def test_verify_encre_task_custom_id(self):
        """Validate that EncreTask accepts a caller-supplied custom id.

        The test constructs an agent-type task with id='task_custom' and asserts
        the id field is preserved, because the task system must support explicit
        ids for parent-child relationships and deterministic test lookups.
        """
        from encre.task.types import EncreTask
        task = EncreTask(
            id="task_custom",
            name="Custom id task",
            description="Custom id",
            task_type="agent",
            prompt="do something",
        )
        assert task.id == "task_custom"
        assert task.name == "Custom id task"

    def test_verify_task_manager_instantiation(self):
        """Validate that EncreTaskManager constructs without raising.

        The test asserts the manager instance is not None because the task system
        requires a persistent store object; a failed construction would indicate
        a dependency or configuration error in the backend initialization path.
        """
        from encre.task.manager import EncreTaskManager
        tm = EncreTaskManager()
        assert tm is not None

    def test_verify_task_executor_instantiation(self):
        """Validate that EncreTaskExecutor constructs without raising.

        The test asserts the executor instance is not None because the executor
        is the runtime component that translates task records into shell or
        agent invocations; construction failure would block the entire pipeline.
        """
        from encre.task.executor import EncreTaskExecutor
        te = EncreTaskExecutor()
        assert te is not None


# ===========================================================================
# Browser Session
# ===========================================================================

class TestBrowser:
    """Engineered to validate the browser state model and session factory.

    This test class exercises BrowserState field population and EncreBrowserSession
    construction across 2 scenarios to ensure the browser subsystem exposes a
    clean state contract (url, title, html, text) and a headless-default session
    object. The design separates state representation from session management
    so that screenshot and navigation tests can mock state without spinning up
    a real browser process.
    """
    def test_verify_browser_state_fields(self):
        """Validate that BrowserState stores url, title, and defaults html/text to empty.

        The test constructs a state object and asserts url and title match the
        supplied values while html and text default to empty strings, because
        the browser state record is a snapshot that starts empty until a page
        load or navigation populates it.
        """
        from encre.computer.browser import BrowserState
        state = BrowserState(url="https://example.com", title="Example")
        assert state.url == "https://example.com"
        assert state.title == "Example"
        assert state.html == ""
        assert state.text == ""

    def test_verify_browser_session_defaults(self):
        """Validate that EncreBrowserSession constructs with headless=True by default.

        The test asserts the session is not None and headless is True because the
        default execution mode for automated browser interactions in agent loops
        is headless to avoid GUI dependencies in CI and server environments.
        """
        from encre.computer.browser import EncreBrowserSession
        bs = EncreBrowserSession()
        assert bs is not None
        assert bs.headless is True


# ===========================================================================
# Auto Safety
# ===========================================================================

class TestAutoSafety:
    """Engineered to validate the auto-safety decision taxonomy and classifier.

    This test class exercises AutoDecision enum completeness, ClassificationResult
    and UserDecisionRecord field integrity, and EncreAutoSafetyClassifier
    construction across 4 scenarios to ensure the safety layer exposes a
    five-tier risk scale (SAFE through BLOCK) and can record both automated
    and human decisions with confidence scores. The design uses an enum so
    that downstream tool calls can branch on a closed set of outcomes.
    """
    def test_verify_auto_decision_enum_values(self):
        """Validate that all five AutoDecision levels are defined and non-None.

        The test asserts SAFE, LOW_RISK, ASK_USER, HIGH_RISK, and BLOCK are all
        not None because the classifier must be able to emit every risk tier
        without a missing case that would cause a silent default branch.
        """
        from encre.autosafety import AutoDecision
        assert AutoDecision.SAFE is not None
        assert AutoDecision.LOW_RISK is not None
        assert AutoDecision.ASK_USER is not None
        assert AutoDecision.HIGH_RISK is not None
        assert AutoDecision.BLOCK is not None

    def test_verify_classification_result_fields(self):
        """Validate that ClassificationResult stores decision and confidence accurately.

        The test constructs a result with SAFE decision and 0.95 confidence and
        asserts both fields match, because the decision record is the primary
        artifact that tools and auditors inspect to understand why a command
        was allowed or rejected.
        """
        from encre.autosafety import AutoDecision, ClassificationResult
        cr = ClassificationResult(
            decision=AutoDecision.SAFE,
            confidence=0.95,
            reasoning="safe command",
        )
        assert cr.decision == AutoDecision.SAFE
        assert cr.confidence == 0.95

    def test_verify_user_decision_record_fields(self):
        """Validate that UserDecisionRecord captures tool name and approval status.

        The test constructs a record for a bash tool approved by the user and
        asserts tool_name and user_approved are preserved, because the feedback
        loop stores these records to learn from human corrections over time.
        """
        from encre.autosafety import UserDecisionRecord
        udr = UserDecisionRecord(
            tool_name="bash",
            tool_args_summary="cmd=ls",
            user_approved=True,
        )
        assert udr.tool_name == "bash"
        assert udr.user_approved is True

    def test_verify_classifier_instantiation(self):
        """Validate that EncreAutoSafetyClassifier constructs without error.

        The test asserts the classifier is not None because the safety layer
        must be available before any tool dispatch; a None classifier would
        bypass all risk assessment and create an unchecked execution path.
        """
        from encre.autosafety import EncreAutoSafetyClassifier
        classifier = EncreAutoSafetyClassifier()
        assert classifier is not None


# ===========================================================================
# Feedback Learner
# ===========================================================================

class TestFeedback:
    """Engineered to validate the correction record model and learner factory.

    This test class exercises CorrectionRecord field integrity and
    EncreFeedbackLearner construction across 2 scenarios to ensure the feedback
    subsystem can store tool-name, error-type, error-context, and user-supplied
    correction tuples for later replay. The design isolates correction records
    from live execution so they can be serialized and re-injected during
    subsequent training or policy-update cycles.
    """
    def test_verify_correction_record_fields(self):
        """Validate that CorrectionRecord stores tool, error, and user correction.

        The test constructs a record for a command-not-found error and asserts
        tool_name, error_type, and user_correction match the supplied values,
        because the feedback learner relies on these fields to generate corrected
        prompts for future LLM invocations.
        """
        from encre.feedback.learner import CorrectionRecord
        cr = CorrectionRecord(
            tool_name="bash",
            error_type="command_not_found",
            error_context="command not found: pyth",
            user_correction="use correct path: python",
        )
        assert cr.tool_name == "bash"
        assert cr.error_type == "command_not_found"
        assert cr.user_correction == "use correct path: python"

    def test_verify_feedback_learner_instantiation(self):
        """Validate that EncreFeedbackLearner constructs without error.

        The test asserts the learner is not None because the feedback system
        must be present for the agent loop to register corrections; a missing
        learner would silently drop all user-intervention signals.
        """
        from encre.feedback.learner import EncreFeedbackLearner
        learner = EncreFeedbackLearner()
        assert learner is not None


# ===========================================================================
# Skills
# ===========================================================================

class TestSkills:
    """Engineered to validate the skill definition model, registry, and bundled-load path.

    This test class exercises BundledSkillDefinition construction,
    EncreSkillRegistry instantiation, and the create_bundled_skills +
    load_from_dir pipeline across 3 scenarios to ensure skills can be defined
    with a name, description, and async prompt factory, registered in a
    lookup-capable registry, and loaded from the builtin directory so that
    agents can resolve skill names like 'loop' and 'debug' at runtime.
    The design separates skill metadata from execution to allow discovery
    without side effects.
    """
    def test_verify_skill_definition_fields(self):
        """Validate that BundledSkillDefinition stores name and description.

        The test constructs a skill with an async prompt factory and asserts
        name and description match, because the registry uses these fields for
        lookup and display; an empty or mismatched name would break skill
        resolution in the tool dispatcher.
        """
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "debugging prompt"

        skill = BundledSkillDefinition(
            name="debug",
            description="Debugging skill",
            get_prompt_for_command=_prompt_fn,
        )
        assert skill.name == "debug"
        assert skill.description == "Debugging skill"

    def test_verify_skill_registry_instantiation(self):
        """Validate that EncreSkillRegistry constructs without error.

        The test asserts the registry is not None because the skill lookup
        table must exist before the agent can resolve any skill tool call;
        a None registry would cause an AttributeError on every skill dispatch.
        """
        from encre.skills.registry import EncreSkillRegistry
        registry = EncreSkillRegistry()
        assert registry is not None

    def test_verify_bundled_skills_loaded_into_registry(self):
        """Validate that create_bundled_skills populates the registry with builtin skills.

        The test invokes create_bundled_skills followed by load_from_dir with
        SkillSource.BUNDLED, then asserts that both 'loop' and 'debug' are
        resolvable via registry.lookup, because these two skills represent the
        programmatic loop registration and the static SKILL.md registration
        paths that must both succeed for the agent to function.
        """
        from encre.skills.bundled import create_bundled_skills
        from encre.skills.builtin import builtin_skills_dir
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import SkillSource
        registry = EncreSkillRegistry()
        create_bundled_skills(registry)
        registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)
        loop = registry.lookup("loop")
        assert loop is not None
        assert loop.name == "loop"
        skill = registry.lookup("debug")
        assert skill is not None
        assert skill.name == "debug"


# ===========================================================================
# Thinking
# ===========================================================================

class TestThinking:
    """Engineered to validate the thinking-config resolution and budget calculation.

    This test class exercises resolve_thinking_config across 3 scenarios 鈥?    module importability, adaptive thinking selection for Claude/GPT models,
    and budget token extraction from EnabledThinking and DisabledThinking
    variants 鈥?to ensure the thinking subsystem returns the correct config
    type based on model capability and that budget tokens are computed
    consistently. The design gates adaptive thinking on model-family heuristics
    so that unsupported models fall back to DisabledThinking rather than
    attempting an unavailable feature.
    """
    def test_verify_thinking_module_imports_correctly(self):
        """Validate that resolve_thinking_config is importable and returns a config for Claude.

        The test calls resolve_thinking_config with None config and a Claude
        model name, asserting the result is not None and enabled is True,
        because the module import path must be stable for the agent loop to
        invoke thinking configuration at startup.
        """
        from encre.thinking.config import resolve_thinking_config
        result = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        assert result is not None
        assert result.enabled is True

    def test_verify_adaptive_thinking_resolution_for_supported_models(self):
        """Validate that adaptive thinking is selected for Claude and GPT model families.

        The test calls resolve_thinking_config with None for both a Claude and a
        GPT model name and asserts isinstance(resolved, AdaptiveThinking) for each,
        because both families declare runtime thinking support and the resolver
        must map them to the adaptive branch rather than DisabledThinking.
        """
        from encre.thinking.config import resolve_thinking_config
        from encre.utils.types import AdaptiveThinking, DisabledThinking
        resolved = resolve_thinking_config(None, "claude-sonnet-4-20250514")
        assert isinstance(resolved, AdaptiveThinking)
        resolved2 = resolve_thinking_config(None, "gpt-5.6")
        assert isinstance(resolved2, AdaptiveThinking)

    def test_verify_thinking_budget_tokens_for_enabled_and_disabled(self):
        """Validate that get_thinking_budget_tokens returns the correct integer for each config type.

        The test passes EnabledThinking(budget_tokens=8000) and DisabledThinking()
        and asserts 8000 and 0 respectively, because the budget calculator must
        read the explicit field from EnabledThinking and return zero for any
        disabled variant so the caller can skip thinking-related token accounting.
        """
        from encre.thinking.config import get_thinking_budget_tokens
        from encre.utils.types import DisabledThinking, EnabledThinking
        assert get_thinking_budget_tokens(EnabledThinking(budget_tokens=8000)) == 8000
        assert get_thinking_budget_tokens(DisabledThinking()) == 0


# ===========================================================================
# Scheduler types
# ===========================================================================

class TestSchedulerTypes:
    """Engineered to validate the scheduler domain models and state machine.

    This test class exercises ScheduledJob construction, CronSchedule field
    population, ScheduleType enum values, and JobState enum values across
    4 scenarios to ensure the scheduler's type system is complete and that
    every state in the job lifecycle (PENDING through CANCELLED) is representable.
    The design uses enums for schedule_type and job_state so that pattern
    matching and serialization can rely on a closed set of valid values.
    """
    def test_verify_scheduled_job_fields(self):
        """Validate that ScheduledJob stores id, name, prompt, and schedule type.

        The test constructs a recurring job and asserts id, name, and prompt
        match the supplied values because the scheduler uses these fields to
        render job listings and to dispatch the correct prompt at trigger time.
        """
        from encre.scheduler import ScheduledJob, ScheduleType
        job = ScheduledJob(
            id="job1",
            name="test job",
            prompt="run tests",
            schedule_type=ScheduleType.RECURRING,
        )
        assert job.id == "job1"
        assert job.name == "test job"
        assert job.prompt == "run tests"

    def test_verify_cron_schedule_field_population(self):
        """Validate that CronSchedule stores all five cron expression fields.

        The test constructs a every-5-minutes schedule and asserts minute == '*/5'
        because the cron parser consumes these five string fields to compute
        the next fire time; any missing or mis-typed field would break scheduling.
        """
        from encre.scheduler import CronSchedule
        cs = CronSchedule(
            minute="*/5", hour="*", day_of_month="*", month="*", day_of_week="*"
        )
        assert cs.minute == "*/5"

    def test_verify_schedule_type_enum_values(self):
        """Validate that ScheduleType exposes ONE_SHOT and RECURRING.

        The test asserts both values are not None because the scheduler must
        support both execution modes; a missing variant would collapse the
        job dispatch path into a single behavior and lose scheduling flexibility.
        """
        from encre.scheduler import ScheduleType
        assert ScheduleType.ONE_SHOT is not None
        assert ScheduleType.RECURRING is not None

    def test_verify_job_state_enum_values(self):
        """Validate that JobState exposes all five lifecycle states.

        The test asserts PENDING, RUNNING, COMPLETED, FAILED, and CANCELLED
        are all not None because the state machine must be able to represent
        every terminal and intermediate state so the UI and scheduler can
        render accurate job progress without unhandled transitions.
        """
        from encre.scheduler import JobState
        assert JobState.PENDING is not None
        assert JobState.RUNNING is not None
        assert JobState.COMPLETED is not None
        assert JobState.FAILED is not None
        assert JobState.CANCELLED is not None


# ===========================================================================
# Prompt types
# ===========================================================================

class TestPrompts:
    """Engineered to validate the prompt base classes and specialty implementations.

    This test class exercises EncreBasePrompt, EncrePromptTemplate,
    EncrePromptBuilder, and the four specialty prompt subclasses (Coding,
    General, Research, Data) across 7 scenarios to ensure the prompt factory
    hierarchy is instantiable and that specialty prompts carry their
    specialization tag. The design uses an ABC base so that all prompt types
    share a common interface while allowing per-specialty template injection.
    """
    def test_verify_base_prompt_class_exists(self):
        """Validate that EncreBasePrompt is importable as an ABC.

        The test asserts the class object is not None because the prompt system
        requires a base type for structural typing; a missing base would break
        isinstance checks throughout the prompt builder chain.
        """
        from encre.prompts.base import EncreBasePrompt
        assert EncreBasePrompt is not None

    def test_verify_prompt_template_with_specialty(self):
        """Validate that EncrePromptTemplate stores the specialty tag.

        The test constructs a template with specialty='coding' and asserts
        _specialty equals 'coding' because the template renderer uses this
        tag to select the correct system prompt variant at generation time.
        """
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="coding")
        assert tmpl is not None
        assert tmpl._specialty == "coding"

    def test_verify_prompt_builder_instantiation(self):
        """Validate that EncrePromptBuilder constructs without error.

        The test asserts the builder is not None because the builder is the
        central orchestrator for assembling system, user, and tool messages
        into a single prompt string; a failed construction would block all
        LLM interaction rounds.
        """
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        assert builder is not None

    def test_verify_coding_prompt_instantiation(self):
        """Validate that EncreCodingPrompt constructs as a specialty prompt.

        The test asserts the instance is not None because the coding prompt
        variant injects code-specific instructions (e.g. output formatting,
        error handling) into the system message and must be available for
        agent routes that specialize in code generation tasks.
        """
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        assert cp is not None

    def test_verify_general_prompt_instantiation(self):
        """Validate that EncreGeneralPrompt constructs as a specialty prompt.

        The test asserts the instance is not None because the general prompt
        variant is the fallback for non-specialized tasks and must be available
        whenever the agent receives a query that does not match a specialty route.
        """
        from encre.prompts.general import EncreGeneralPrompt
        gp = EncreGeneralPrompt()
        assert gp is not None

    def test_verify_research_prompt_instantiation(self):
        """Validate that EncreResearchPrompt constructs as a specialty prompt.

        The test asserts the instance is not None because the research prompt
        variant injects investigation-oriented instructions (e.g. cite sources,
        summarize findings) and must be available for research-task routing.
        """
        from encre.prompts.research import EncreResearchPrompt
        rp = EncreResearchPrompt()
        assert rp is not None

    def test_verify_data_prompt_instantiation(self):
        """Validate that EncreDataPrompt constructs as a specialty prompt.

        The test asserts the instance is not None because the data prompt
        variant injects data-analysis-oriented instructions (e.g. pandas patterns,
        chart guidance) and must be available for data-task routing.
        """
        from encre.prompts.data import EncreDataPrompt
        dp = EncreDataPrompt()
        assert dp is not None


class TestSkillTool:
    """Engineered to validate the model-facing skill activation tool registration and behavior.

    This test class exercises the skill tool registration in the default tool set,
    skill activation with caching on the loop, alias-to-canonical-name normalization,
    and error handling for unknown skill names across 4 scenarios. The design
    ensures the skill tool is discoverable by the agent's tool dispatcher, caches
    activated skill bodies on the loop object for next-turn injection, and returns
    a structured error instead of raising when the requested skill does not exist.
    """

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

    def test_verify_skill_tool_registered_in_default_toolset(self):
        """Validate that the skill tool is present after default tool registration.

        The test registers default tools and asserts 'skill' is in the tool list
        because the agent must be able to discover and invoke the skill activation
        tool without manual registry manipulation at runtime.
        """
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        assert "skill" in tr.list_tools()

    def test_verify_skill_tool_activates_and_caches_body_on_loop(self):
        """Validate that activating a skill caches its body on the loop for next-turn injection.

        The test registers default tools, invokes the skill execute function with
        'travel-flights', and asserts the response contains the skill name, the
        loop's _active_doc_skills dict contains 'travel-flights', and the cached
        body includes the 'Flight Search Guidance' header, because the agent loop
        injects cached skill bodies into subsequent context windows automatically.
        """
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

    def test_verify_skill_tool_alias_normalises_to_canonical_name(self):
        """Validate that an alias resolves to the canonical skill name in the cache.

        The test activates the alias 'flights' and asserts the canonical key
        'travel-flights' is present in _active_doc_skills while 'flights' is not,
        because the skill registry must normalize aliases to their canonical form
        so that subsequent lookups and cache hits use a single consistent key.
        """
        import asyncio
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        exe = tr.list_tools()["skill"].execute
        loop = self._fake_loop()
        asyncio.run(exe(name="flights"))
        assert "travel-flights" in loop._active_doc_skills
        assert "flights" not in loop._active_doc_skills

    def test_verify_skill_tool_unknown_name_returns_error_not_crash(self):
        """Validate that an unknown skill name produces a structured error string.

        The test invokes the skill execute with 'does-not-exist' and asserts the
        result starts with 'Error:' because the tool must never raise an exception
        into the agent loop; a structured error string lets the LLM handle the
        failure gracefully and retry with a corrected skill name.
        """
        import asyncio
        from encre.tools.defaults import register_default_tools
        from encre.tools.registry import ToolRegistry
        tr = ToolRegistry()
        register_default_tools(tr)
        exe = tr.list_tools()["skill"].execute
        self._fake_loop()
        result = asyncio.run(exe(name="does-not-exist"))
        assert result.startswith("Error:")
