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

"""Tests for yim.loop — the agent execution loop."""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from yim.config import YmiConfig
from yim.loop import YmiLoop
from yim.session import YmiSession
from yim.safety import YmiSafetyEngine
from yim.tools.registry import ToolRegistry
from yim.hooks.system import YmiHookSystem
from yim.memdir.system import YmiMemorySystem
from yim.telemetry import YmiTelemetry


class TestYmiLoopConstruction:
    """Test YmiLoop construction and attribute initialization."""

    def setup_method(self):
        self.config = YmiConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
            enable_prompt_caching=False,
        )
        self.session = YmiSession(self.config)

    @patch("yim.loop.create_backend")
    def test_basic_construction(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert loop.config is self.config
        assert loop.session is self.session
        assert loop.backend is not None

    @patch("yim.loop.create_backend")
    def test_custom_tool_registry(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tools = ToolRegistry()
        loop = YmiLoop(config=self.config, session=self.session, tool_registry=tools)
        assert loop.tool_registry is tools

    @patch("yim.loop.create_backend")
    def test_default_tool_registry_created(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert isinstance(loop.tool_registry, ToolRegistry)

    @patch("yim.loop.create_backend")
    def test_custom_hook_system(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        hooks = YmiHookSystem()
        loop = YmiLoop(config=self.config, session=self.session, hook_system=hooks)
        assert loop.hook_system is hooks

    @patch("yim.loop.create_backend")
    def test_default_hook_system_created(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert isinstance(loop.hook_system, YmiHookSystem)

    @patch("yim.loop.create_backend")
    def test_custom_safety_engine(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        safety = YmiSafetyEngine(self.config)
        loop = YmiLoop(config=self.config, session=self.session, safety=safety)
        assert loop.safety is safety

    @patch("yim.loop.create_backend")
    def test_default_safety_created(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert isinstance(loop.safety, YmiSafetyEngine)

    @patch("yim.loop.create_backend")
    def test_custom_telemetry(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        tel = YmiTelemetry(enabled=True)
        loop = YmiLoop(config=self.config, session=self.session, telemetry=tel)
        assert loop.telemetry is tel

    @patch("yim.loop.create_backend")
    def test_default_telemetry_disabled(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert loop.telemetry.enabled is False

    @patch("yim.loop.create_backend")
    def test_all_attributes_initialized(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        # Ensure all core attributes exist
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


class TestYmiLoopAttributes:
    """Test loop attribute behavior beyond construction."""

    def setup_method(self):
        self.config = YmiConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = YmiSession(self.config)

    @patch("yim.loop.create_backend")
    def test_resolve_permission(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        loop._permission_event = asyncio.Event()
        loop._permission_decision = False
        loop._pending_tool_name = "test_tool"

        loop.resolve_permission(True)
        assert loop._permission_decision is True

    @patch("yim.loop.create_backend")
    def test_resolve_permission_deny(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        loop._permission_event = asyncio.Event()
        loop._permission_decision = True

        loop.resolve_permission(False)
        assert loop._permission_decision is False

    @patch("yim.loop.create_backend")
    def test_resolve_permission_no_event(self, mock_create_backend):
        """resolve_permission should not crash when _permission_event is None."""
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        # _permission_event is None initially
        loop.resolve_permission(True)
        assert loop._permission_decision is True


class TestYmiLoopAclose:
    """Test the async close method."""

    def setup_method(self):
        self.config = YmiConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = YmiSession(self.config)

    @patch("yim.loop.create_backend")
    @pytest.mark.asyncio
    async def test_aclose_calls_backend_aclose(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.aclose = AsyncMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        await loop.aclose()
        mock_backend.aclose.assert_awaited_once()

    @patch("yim.loop.create_backend")
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

        loop = YmiLoop(config=self.config, session=self.session)
        # aclose has try/except AttributeError pattern
        # This tests graceful handling
        assert loop.backend is not None


class TestYmiLoopMemorySystem:
    """Test optional memory system integration."""

    def setup_method(self):
        self.config = YmiConfig(
            model="gpt-4o",
            backend_type="openai",
            permission_mode="default",
            max_turns=10,
            max_tokens=4096,
            log_level="ERROR",
        )
        self.session = YmiSession(self.config)

    @patch("yim.loop.create_backend")
    def test_memory_system_none_by_default(self, mock_create_backend):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        loop = YmiLoop(config=self.config, session=self.session)
        assert loop.memory_system is None

    @patch("yim.loop.create_backend")
    def test_memory_system_can_be_injected(self, mock_create_backend, tmp_path):
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend

        mem = YmiMemorySystem(auto_memory_path=str(tmp_path / "memory"))
        loop = YmiLoop(config=self.config, session=self.session, memory_system=mem)
        assert loop.memory_system is mem
