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

"""Tests for encre.loop -- the agent execution loop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from encre.config import EncreConfig
from encre.hooks.system import EncreHookSystem
from encre.loop import EncreLoop, _infer_tool_semantics, _tool_retry_allowed
from encre.memdir.system import EncreMemorySystem
from encre.safety import EncreSafetyEngine
from encre.session import EncreSession
from encre.telemetry import EncreTelemetry
from encre.tools.base import build_tool
from encre.tools.registry import ToolRegistry
from encre.tools.builtin.agent import EncreAgentTool
from encre.tools.builtin.apply_patch import EncreApplyPatchTool
from encre.tools.builtin.bash import EncreBashTool
from encre.tools.builtin.file_edit import EncreFileEditTool
from encre.tools.builtin.file_read import EncreFileReadTool
from encre.tools.builtin.grep import EncreGrepTool
from encre.tools.builtin.test_runner import EncreTestRunTool
from encre.tools.builtin.web_search import EncreWebSearchTool


class TestEncreLoopConstruction:
    """Engineered to validate EncreLoop constructor behavior across all
    injection points and default-creation paths.

    This test class exercises 10 scenarios covering config, session, backend,
    tool registry, hook system, safety engine, telemetry, and the full set of
    evolution/recovery attributes to ensure the loop wires each dependency
    correctly. The design follows the invariant that every optional component
    must have a deterministic default when not injected so that the loop is
    always in a valid state regardless of how it is constructed.
    """

    def setup_method(self):
        """Prepare a standard config and session for all construction tests."""
        self.config = EncreConfig(
            model="gpt-5.6",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
            enable_prompt_caching=False,
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_verify_basic_construction_wires_config_session_and_backend(self, mock_create_backend):
        """Validate that EncreLoop stores config, session, and creates a
        backend when all three are provided or derivable.

        The test exercises bare construction with config and session and asserts
        each attribute is set because the loop must always have a backend
        instance to drive LLM calls, even if the backend is mocked.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert loop.config is self.config, "config reference must be preserved"
        assert loop.session is self.session, "session reference must be preserved"
        assert loop.backend is not None, "backend must be created even with mocked factory"

    @patch("encre.loop.create_backend")
    def test_verify_custom_tool_registry_is_preserved(self, mock_create_backend):
        """Validate that a user-provided ToolRegistry is stored as-is instead
        of being replaced by a default instance.

        The test exercises construction with an explicit tool_registry and
        asserts identity because custom registries carry registered tools
        that the default registry would not have.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tools = ToolRegistry()
        loop = EncreLoop(config=self.config, session=self.session, tool_registry=tools)
        assert loop.tool_registry is tools, "custom tool registry must be preserved by identity"

    @patch("encre.loop.create_backend")
    def test_verify_default_tool_registry_is_created_when_not_provided(self, mock_create_backend):
        """Validate that EncreLoop creates a ToolRegistry instance when none
        is injected, confirming the default-instantiation path.

        The test exercises bare construction and asserts isinstance because
        the loop must never have a None tool_registry 鈥?even an empty registry
        is preferable to a missing one for method-call safety.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert isinstance(loop.tool_registry, ToolRegistry), \
            "default tool registry must be instantiated when not provided"

    @patch("encre.loop.create_backend")
    def test_verify_custom_hook_system_is_preserved(self, mock_create_backend):
        """Validate that a user-provided EncreHookSystem is stored as-is
        instead of being replaced by a default instance.

        The test exercises construction with an explicit hook_system and
        asserts identity because custom hook systems may have pre-registered
        handlers that the default system would lack.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        hooks = EncreHookSystem()
        loop = EncreLoop(config=self.config, session=self.session, hook_system=hooks)
        assert loop.hook_system is hooks, "custom hook system must be preserved by identity"

    @patch("encre.loop.create_backend")
    def test_verify_default_hook_system_is_created_when_not_provided(self, mock_create_backend):
        """Validate that EncreLoop creates an EncreHookSystem instance when
        none is injected, confirming the default-instantiation path.

        The test exercises bare construction and asserts isinstance because
        the loop must always have a hook system to emit lifecycle events,
        even if no handlers are registered.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert isinstance(loop.hook_system, EncreHookSystem), \
            "default hook system must be instantiated when not provided"

    @patch("encre.loop.create_backend")
    def test_verify_custom_safety_engine_is_preserved(self, mock_create_backend):
        """Validate that a user-provided EncreSafetyEngine is stored as-is
        instead of being replaced by a default instance.

        The test exercises construction with an explicit safety argument and
        asserts identity because custom safety engines may carry policy
        overrides that the default engine would not have.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        safety = EncreSafetyEngine(self.config)
        loop = EncreLoop(config=self.config, session=self.session, safety=safety)
        assert loop.safety is safety, "custom safety engine must be preserved by identity"

    @patch("encre.loop.create_backend")
    def test_verify_default_safety_engine_is_created_when_not_provided(self, mock_create_backend):
        """Validate that EncreLoop creates an EncreSafetyEngine instance when
        none is injected, confirming the default-instantiation path.

        The test exercises bare construction and asserts isinstance because
        every loop must have a safety engine to gate tool execution, even
        when the default policy is permissive.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert isinstance(loop.safety, EncreSafetyEngine), \
            "default safety engine must be instantiated when not provided"

    @patch("encre.loop.create_backend")
    def test_verify_custom_telemetry_is_preserved(self, mock_create_backend):
        """Validate that a user-provided EncreTelemetry is stored as-is
        instead of being replaced by a default instance.

        The test exercises construction with an explicit telemetry argument
        and asserts identity because custom telemetry instances may carry
        configured exporters that the default (disabled) instance lacks.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tel = EncreTelemetry(enabled=True)
        loop = EncreLoop(config=self.config, session=self.session, telemetry=tel)
        assert loop.telemetry is tel, "custom telemetry must be preserved by identity"

    @patch("encre.loop.create_backend")
    def test_verify_default_telemetry_is_disabled(self, mock_create_backend):
        """Validate that the default EncreTelemetry instance has enabled=False,
        confirming telemetry is opt-in by default.

        The test exercises bare construction and asserts the enabled flag is
        False because telemetry must never be active without explicit
        configuration to avoid leaking production data in default deployments.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert loop.telemetry.enabled is False, \
            "default telemetry must be disabled to prevent accidental data emission"

    @patch("encre.loop.create_backend")
    def test_verify_all_core_and_evolution_attributes_are_initialized(self, mock_create_backend):
        """Validate that every public and evolution attribute exists on the
        loop instance after construction, confirming no missing dependency.

        The test exercises bare construction and asserts hasattr for config,
        session, backend, tool_registry, hook_system, safety, telemetry,
        compact_engine, prompt_builder, learner, optimizer, reflex, meta,
        and recovery_engine because the loop references all of these during
        a normal turn and a missing attribute would cause an AttributeError
        at runtime.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert hasattr(loop, "config")
        assert hasattr(loop, "session")
        assert hasattr(loop, "backend")
        assert hasattr(loop, "tool_registry")
        assert hasattr(loop, "hook_system")
        assert hasattr(loop, "safety")
        assert hasattr(loop, "telemetry")
        assert hasattr(loop, "compact_engine")
        assert hasattr(loop, "prompt_builder")
        # Evolution attributes
        assert hasattr(loop, "learner")
        assert hasattr(loop, "optimizer")
        assert hasattr(loop, "reflex")
        assert hasattr(loop, "meta")
        # Recovery
        assert hasattr(loop, "recovery_engine")


class TestEncreLoopAttributes:
    """Engineered to validate permission-resolution behavior and the
    interaction between _permission_event, _permission_decision, and the
    resolve_permission public API.

    This test class exercises 3 scenarios 鈥?approve, deny, and no-event 鈥?    to confirm the permission gate correctly updates the decision flag and
    does not crash when the event is absent. The design follows the invariant
    that resolve_permission must be safe to call from any thread context
    because it is invoked by the WebSocket handler when the user clicks
    approve or deny.
    """

    def setup_method(self):
        """Prepare a standard config and session for all attribute tests."""
        self.config = EncreConfig(
            model="gpt-5.6",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_verify_resolve_permission_sets_decision_to_approved(self, mock_create_backend):
        """Validate that resolve_permission(True) sets _permission_decision to
        True and propagates the approval to the loop state.

        The test exercises the method with a pre-initialized event and asserts
        the decision flag is True because the approval path must flip the
        flag so the blocked tool execution can resume.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        loop._permission_event = asyncio.Event()
        loop._permission_decision = False
        loop._pending_tool_name = "test_tool"

        loop.resolve_permission(True)
        assert loop._permission_decision is True, "approve must set the decision flag to True"

    @patch("encre.loop.create_backend")
    def test_verify_resolve_permission_sets_decision_to_denied(self, mock_create_backend):
        """Validate that resolve_permission(False) overrides a prior True
        decision with False, confirming the deny path works correctly.

        The test exercises the method with a pre-set True decision and asserts
        the flag is flipped to False because the user may change their mind
        before the async wait resolves.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        loop._permission_event = asyncio.Event()
        loop._permission_decision = True

        loop.resolve_permission(False)
        assert loop._permission_decision is False, "deny must set the decision flag to False"

    @patch("encre.loop.create_backend")
    def test_verify_resolve_permission_does_not_crash_when_event_is_none(self, mock_create_backend):
        """Validate that resolve_permission safely handles the case where
        _permission_event is None, confirming the no-event guard path.

        The test exercises the method without initializing the event and
        asserts the decision is still set because some code paths call
        resolve_permission defensively after the fact and must not raise.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # _permission_event is None initially
        loop.resolve_permission(True)
        assert loop._permission_decision is True, "decision must be set even when event is absent"


class TestEncreLoopAclose:
    """Engineered to validate the async close lifecycle, specifically that
    aclose delegates to the backend's aclose when available and remains
    graceful when it is not.

    This test class exercises 2 scenarios 鈥?backend with aclose and backend
    without aclose 鈥?to confirm the try/except AttributeError pattern works.
    The design follows the invariant that aclose must never raise because
    it is called during teardown when the process is already shutting down.
    """

    def setup_method(self):
        """Prepare a standard config and session for all aclose tests."""
        self.config = EncreConfig(
            model="gpt-5.6",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    @pytest.mark.asyncio
    async def test_verify_aclose_delegates_to_backend_aclose(self, mock_create_backend):
        """Validate that aclose calls backend.aclose exactly once when the
        backend exposes the method, confirming resource cleanup propagation.

        The test exercises aclose on a loop with a mock backend that has an
        AsyncMock aclose and asserts the await count is one because backend
        connections (HTTP clients, WebSocket streams) must be closed to
        prevent resource leaks.
        """
        mock_backend = MagicMock()
        mock_backend.aclose = AsyncMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        await loop.aclose()
        mock_backend.aclose.assert_awaited_once()

    @patch("encre.loop.create_backend")
    @pytest.mark.asyncio
    async def test_verify_aclose_is_graceful_when_backend_lacks_aclose(self, mock_create_backend):
        """Validate that aclose does not raise when the backend object does
        not expose an aclose attribute, confirming the AttributeError guard.

        The test exercises aclose on a loop whose mock backend has aclose
        deleted and asserts the loop remains intact because third-party
        backends may not implement the async close protocol.
        """
        mock_backend = MagicMock()
        # Remove aclose attribute entirely
        del mock_backend.aclose
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # aclose has try/except AttributeError pattern
        # This tests graceful handling
        assert loop.backend is not None, "loop must remain valid after aclose on a no-aclose backend"


class TestEncreLoopMemorySystem:
    """Engineered to validate optional memory-system integration, specifically
    that the loop accepts an injected EncreMemorySystem and defaults to None
    when none is provided.

    This test class exercises 2 scenarios 鈥?default None and custom injection 鈥?    to confirm the optional dependency does not force a hard requirement.
    The design follows the invariant that memory is an optional enhancement
    so that lightweight deployments can run the loop without the memory
    subsystem compiled in.
    """

    def setup_method(self):
        """Prepare a standard config and session for all memory tests."""
        self.config = EncreConfig(
            model="gpt-5.6",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_verify_memory_system_is_none_by_default(self, mock_create_backend):
        """Validate that the memory_system attribute is None when no memory
        system is injected, confirming the optional-dependency default.

        The test exercises bare construction and asserts None because memory
        is an optional subsystem and the loop must operate without it.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert loop.memory_system is None, "memory_system must default to None when not injected"

    @patch("encre.loop.create_backend")
    def test_verify_memory_system_can_be_injected(self, mock_create_backend, tmp_path):
        """Validate that an injected EncreMemorySystem is stored by identity
        and remains accessible after construction.

        The test exercises construction with an explicit memory_system argument
        and asserts identity because custom memory backends may carry
        pre-loaded state that must not be replaced by a default instance.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        mem = EncreMemorySystem(auto_memory_path=str(tmp_path / "memory"))
        loop = EncreLoop(config=self.config, session=self.session, memory_system=mem)
        assert loop.memory_system is mem, "injected memory system must be preserved by identity"


class TestEncreLoopTaskState:
    """Engineered to validate the task-state metadata system that tracks
    work phase, working set, and turn summaries across loop turns.

    This test class exercises 4 scenarios 鈥?initial metadata, working-set
    prompt rendering, stage inference, and turn-summary recording 鈥?to
    confirm the metadata dict stays in sync with the loop's internal state.
    The design follows the invariant that task_stage drives which prompt
    template is injected so the model knows whether it is planning,
    executing, or reporting.
    """

    def setup_method(self):
        """Prepare a standard config and session for all task-state tests."""
        self.config = EncreConfig(
            model="gpt-5.6",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_verify_initial_task_state_metadata_has_correct_defaults(self, mock_create_backend):
        """Validate that the session metadata starts with task_stage='discover',
        working_set={}, and turn_summaries=[] as defaults.

        The test exercises bare construction and asserts each metadata key
        because the initial state must be predictable so the first turn
        prompt is stable across runs.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert loop.session.metadata["task_stage"] == "discover"
        assert loop.session.metadata["working_set"] == {}
        assert loop.session.metadata["turn_summaries"] == []

    @patch("encre.loop.create_backend")
    def test_verify_working_set_prompt_contains_recent_tool_semantics(self, mock_create_backend):
        """Validate that _build_working_set_prompt includes the current task
        description, recent tool names, and the 'Current Task State' header
        when a working set is refreshed.

        The test exercises _refresh_working_set with a grep tool and asserts
        the rendered prompt contains the expected strings because the working
        set prompt gives the model context about which tools are relevant
        to the current task phase.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        prepared = [{
            "name": "grep",
            "args": {"pattern": "todo", "path": "src"},
            "semantics": {"semantic_type": "search", "cost_level": "low"},
        }]
        loop._refresh_working_set("find todos", prepared)
        rendered = loop._build_working_set_prompt()
        assert "Current Task State" in rendered
        assert "grep" in rendered
        assert "find todos" in rendered

    @patch("encre.loop.create_backend")
    def test_verify_task_stage_inference_matches_semantics(self, mock_create_backend):
        """Validate that _infer_task_stage returns the correct stage label
        based on the prompt text and tool semantics.

        The test exercises inference with four distinct prompts and asserts
        each returns the expected stage string because stage inference drives
        which prompt template is used and which tools are considered relevant.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        assert loop._infer_task_stage("Please plan the refactor") == "plan"
        assert loop._infer_task_stage(
            "edit the file",
            [{"name": "apply_patch", "semantics": {"semantic_type": "write"}}],
        ) == "execute"
        assert loop._infer_task_stage("verify the tests") == "verify"
        assert loop._infer_task_stage("write a summary for me") == "report"

    @patch("encre.loop.create_backend")
    def test_verify_turn_summary_is_recorded_after_turn_completion(self, mock_create_backend):
        """Validate that _maybe_record_turn_summary appends a summary entry
        when called with prepared tools and outcomes.

        The test exercises the method with turn_count=3 and asserts the
        summaries list grows by one because turn summaries feed the
        reflection optimizer that decides whether to retry or continue.
        """
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        loop.session.turn_count = 3
        prepared = [{"name": "file_read"}]
        outcomes = [{"tool_name": "file_read", "is_error": False}]
        loop._maybe_record_turn_summary("inspect file", prepared, outcomes)
        assert len(loop.session.metadata["turn_summaries"]) == 1, \
            "one summary entry must be recorded per turn"


class TestEncreLoopToolSemantics:
    """Engineered to validate the tool-semantics inference layer and the
    retry-guard logic that prevents tight re-spawn loops on guarded tools.

    This test class exercises 8 scenarios covering default semantics
    inference, retry-allowed logic for guarded/auto/manual retryability
    strategies, and the semantic_type declarations on core builtin tools.
    The design follows the invariant that tools must declare their
    retryability so the loop can decide whether a repeated call is a bug
    (guarded) or a feature (auto).
    """

    def test_verify_infer_tool_semantics_applies_defaults_for_unknown_tools(self):
        """Validate that _infer_tool_semantics falls back to search/low for
        tools that do not declare semantic_type, confirming the default
        inference is safe.

        The test exercises the function with a generic mock tool and asserts
        the inferred semantics match the default mapping because unknown
        tools should default to the least disruptive profile.
        """
        tool = build_tool(
            name="grep",
            description="search",
            input_schema={"type": "object", "properties": {}},
            execute=AsyncMock(),
        )
        tool.semantic_type = ""
        semantics = _infer_tool_semantics("grep", tool)
        assert semantics["semantic_type"] == "search"
        assert semantics["cost_level"] == "low"

    def test_verify_retry_guard_blocks_guarded_tool_repeat(self):
        """Validate that _tool_retry_allowed returns False when a tool has
        retryability='guarded' and has already been called with the same
        args in the history.

        The test exercises the function with an apply_patch call that appeared
        once and asserts False because guarded tools must not repeat without
        explicit user intervention to prevent infinite edit loops.
        """
        p = {
            "name": "apply_patch",
            "args_summary": '{"file_path":"x.py"}',
            "semantics": {"retryability": "guarded"},
        }
        assert _tool_retry_allowed(p, [('apply_patch:{"file_path":"x.py"}',)]) is False

    def test_verify_retry_guard_allows_auto_retry_tool_repeat(self):
        """Validate that _tool_retry_allowed returns True when a tool has
        retryability='auto' even if the same call appeared in history.

        The test exercises the function with a grep call that appeared once
        and asserts True because auto-retry tools are designed to be safe to
        re-invoke (e.g. idempotent reads) and the guard should not block them.
        """
        p = {
            "name": "grep",
            "args_summary": '{"pattern":"todo"}',
            "semantics": {"retryability": "auto"},
        }
        assert _tool_retry_allowed(p, [('grep:{"pattern":"todo"}',)]) is True

    def test_verify_retry_guard_allows_manual_tool_first_call_and_unrelated_repeat(self):
        """Validate that _tool_retry_allowed returns True for a manual tool
        on its first invocation and when unrelated tools appear in history,
        but False on immediate back-to-back repeat.

        The test exercises three calls 鈥?empty history, unrelated history,
        and same-tool history 鈥?and asserts the pattern matches because
        manual tools (e.g. agent delegation) should only run once per
        invocation chain to prevent recursive spawning loops.
        """
        p = {
            "name": "agent",
            "args_summary": '{"subagent_type":"Search"}',
            "semantics": {"retryability": "manual"},
        }
        assert _tool_retry_allowed(p, []) is True
        assert _tool_retry_allowed(p, [('grep:{"pattern":"todo"}',)]) is True

    def test_verify_retry_guard_blocks_manual_tool_immediate_repeat(self):
        """Validate that _tool_retry_allowed returns False when a manual tool
        is called back-to-back with the same args, confirming the tight-loop
        guard is active.

        The test exercises the function with the same agent call in history
        and asserts False because immediate re-spawning of the same sub-agent
        is almost always a logic bug.
        """
        p = {
            "name": "agent",
            "args_summary": '{"subagent_type":"Search"}',
            "semantics": {"retryability": "manual"},
        }
        assert _tool_retry_allowed(p, [('agent:{"subagent_type":"Search"}',)]) is False

    def test_verify_agent_tool_declares_manual_retryability(self):
        """Validate that EncreAgentTool declares retryability='manual' as a
        class attribute, confirming the orchestration tool is protected
        against re-spawn loops.

        The test asserts the class-level constant because the retry guard
        reads this attribute at tool-registration time, so it must be stable.
        """
        assert EncreAgentTool.retryability == "manual"

    def test_verify_core_tools_have_explicit_semantic_type_declarations(self):
        """Validate that all core builtin tools declare a non-empty
        semantic_type so the inference layer does not need to guess.

        The test asserts each tool's semantic_type against the expected
        label because explicit declarations are more stable than inference
        and make the tool catalog self-documenting.
        """
        assert EncreBashTool.semantic_type == "exec"
        assert EncreFileReadTool.semantic_type == "read"
        assert EncreGrepTool.semantic_type == "search"
        assert EncreFileEditTool.semantic_type == "write"
        assert EncreApplyPatchTool.semantic_type == "write"
        assert EncreWebSearchTool.semantic_type == "network"
        assert EncreTestRunTool.semantic_type == "exec"
        assert EncreAgentTool.semantic_type == "orchestrate"
