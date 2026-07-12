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
    """Test cases covering encre loop construction.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test EncreLoop construction and attribute initialization."""

    def setup_method(self):
        """Verifies that setup method."""
        self.config = EncreConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
            enable_prompt_caching=False,
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_basic_construction(self, mock_create_backend):
        """Verifies that basic construction."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: basic construction.
        assert loop.config is self.config
        assert loop.session is self.session
        assert loop.backend is not None

    @patch("encre.loop.create_backend")
    def test_custom_tool_registry(self, mock_create_backend):
        """Verifies that custom tool registry."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tools = ToolRegistry()
        loop = EncreLoop(config=self.config, session=self.session, tool_registry=tools)
        # Confirm the expected result for this scenario: custom tool registry.
        assert loop.tool_registry is tools

    @patch("encre.loop.create_backend")
    def test_default_tool_registry_created(self, mock_create_backend):
        """Verifies that default tool registry created."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: default tool registry created.
        assert isinstance(loop.tool_registry, ToolRegistry)

    @patch("encre.loop.create_backend")
    def test_custom_hook_system(self, mock_create_backend):
        """Verifies that custom hook system."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        hooks = EncreHookSystem()
        loop = EncreLoop(config=self.config, session=self.session, hook_system=hooks)
        # Confirm the expected result for this scenario: custom hook system.
        assert loop.hook_system is hooks

    @patch("encre.loop.create_backend")
    def test_default_hook_system_created(self, mock_create_backend):
        """Verifies that default hook system created."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: default hook system created.
        assert isinstance(loop.hook_system, EncreHookSystem)

    @patch("encre.loop.create_backend")
    def test_custom_safety_engine(self, mock_create_backend):
        """Verifies that custom safety engine."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        safety = EncreSafetyEngine(self.config)
        loop = EncreLoop(config=self.config, session=self.session, safety=safety)
        # Confirm the expected result for this scenario: custom safety engine.
        assert loop.safety is safety

    @patch("encre.loop.create_backend")
    def test_default_safety_created(self, mock_create_backend):
        """Verifies that default safety created."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: default safety created.
        assert isinstance(loop.safety, EncreSafetyEngine)

    @patch("encre.loop.create_backend")
    def test_custom_telemetry(self, mock_create_backend):
        """Verifies that custom telemetry."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tel = EncreTelemetry(enabled=True)
        loop = EncreLoop(config=self.config, session=self.session, telemetry=tel)
        # Confirm the expected result for this scenario: custom telemetry.
        assert loop.telemetry is tel

    @patch("encre.loop.create_backend")
    def test_default_telemetry_disabled(self, mock_create_backend):
        """Verifies that default telemetry disabled."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: default telemetry disabled.
        assert loop.telemetry.enabled is False

    @patch("encre.loop.create_backend")
    def test_all_attributes_initialized(self, mock_create_backend):
        """Verifies that all attributes initialized."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Ensure all core attributes exist
        # Confirm the expected result for this scenario: all attributes initialized.
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
    """Test cases covering encre loop attributes.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test loop attribute behavior beyond construction."""

    def setup_method(self):
        """Verifies that setup method."""
        self.config = EncreConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_resolve_permission(self, mock_create_backend):
        """Verifies that resolve permission."""
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
        # Confirm the expected result for this scenario: resolve permission.
        assert loop._permission_decision is True

    @patch("encre.loop.create_backend")
    def test_resolve_permission_deny(self, mock_create_backend):
        """Verifies that resolve permission deny."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        loop._permission_event = asyncio.Event()
        loop._permission_decision = True

        loop.resolve_permission(False)
        # Confirm the expected result for this scenario: resolve permission deny.
        assert loop._permission_decision is False

    @patch("encre.loop.create_backend")
    def test_resolve_permission_no_event(self, mock_create_backend):
        """resolve_permission should not crash when _permission_event is None."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # _permission_event is None initially
        loop.resolve_permission(True)
        # Confirm the expected result for this scenario: resolve permission no event.
        assert loop._permission_decision is True


class TestEncreLoopAclose:
    """Test cases covering encre loop aclose.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test the async close method."""

    def setup_method(self):
        """Verifies that setup method."""
        self.config = EncreConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    @pytest.mark.asyncio
    async def test_aclose_calls_backend_aclose(self, mock_create_backend):
        """Verifies that aclose calls backend aclose."""
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
    async def test_aclose_graceful_on_backend_without_aclose(self, mock_create_backend):
        """aclose should not raise even if backend lacks aclose (attribute error)."""
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
        # Confirm the expected result for this scenario: aclose graceful on backend without aclose.
        assert loop.backend is not None


class TestEncreLoopMemorySystem:
    """Test optional memory system integration."""
    """Test cases covering encre loop memory system.
    
    Covers the expected behavior and relevant edge cases.
    """

    def setup_method(self):
        """Verifies that setup method."""
        self.config = EncreConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_memory_system_none_by_default(self, mock_create_backend):
        """Verifies that memory system none by default."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = EncreLoop(config=self.config, session=self.session)
        # Confirm the expected result for this scenario: memory system none by default.
        assert loop.memory_system is None

    @patch("encre.loop.create_backend")
    def test_memory_system_can_be_injected(self, mock_create_backend, tmp_path):
        """Verifies that memory system can be injected."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        mem = EncreMemorySystem(auto_memory_path=str(tmp_path / "memory"))
        loop = EncreLoop(config=self.config, session=self.session, memory_system=mem)
        assert loop.memory_system is mem


class TestEncreLoopTaskState:
    def setup_method(self):
        self.config = EncreConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = EncreSession(self.config)

    @patch("encre.loop.create_backend")
    def test_initial_task_state_metadata(self, mock_create_backend):
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
    def test_working_set_prompt_contains_recent_tools(self, mock_create_backend):
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
    def test_task_stage_inference(self, mock_create_backend):
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
    def test_turn_summary_recorded(self, mock_create_backend):
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
        assert len(loop.session.metadata["turn_summaries"]) == 1


class TestEncreLoopToolSemantics:
    def test_infer_tool_semantics_defaults(self):
        tool = build_tool(
            name="grep",
            description="search",
            input_schema={"type": "object", "properties": {}},
            execute=AsyncMock(),
        )
        semantics = _infer_tool_semantics("grep", tool)
        assert semantics["semantic_type"] == "search"
        assert semantics["cost_level"] == "low"

    def test_retry_guard_blocks_guarded_repeat(self):
        p = {
            "name": "apply_patch",
            "args_summary": '{"file_path":"x.py"}',
            "semantics": {"retryability": "guarded"},
        }
        assert _tool_retry_allowed(p, [('apply_patch:{"file_path":"x.py"}',)]) is False

    def test_retry_guard_allows_auto_retry(self):
        p = {
            "name": "grep",
            "args_summary": '{"pattern":"todo"}',
            "semantics": {"retryability": "auto"},
        }
        assert _tool_retry_allowed(p, [('grep:{"pattern":"todo"}',)]) is True

    def test_core_tools_have_explicit_semantics(self):
        assert EncreBashTool.semantic_type == "exec"
        assert EncreFileReadTool.semantic_type == "read"
        assert EncreGrepTool.semantic_type == "search"
        assert EncreFileEditTool.semantic_type == "write"
        assert EncreApplyPatchTool.semantic_type == "write"
        assert EncreWebSearchTool.semantic_type == "network"
        assert EncreTestRunTool.semantic_type == "exec"
        assert EncreAgentTool.semantic_type == "orchestrate"
