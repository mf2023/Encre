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

"""Integration tests: cross-subsystem wiring, agent composition, safety -> tool flow."""

import asyncio

from encre.agent import EncreAgent
from encre.config import EncreConfig
from encre.safety import DangerLevel, EncreSafetyEngine, analyze_bash_command
from encre.tools.builtin import EncreBashTool, EncreFileReadTool, EncreFileWriteTool
from encre.tools.registry import ToolRegistry

# ===========================================================================
# SafetyEngine + Tool integration
# ===========================================================================


class TestSafetyToolIntegration:
    """Test cases covering safety tool integration.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.config = EncreConfig(permission_mode="default")
        self.safety = EncreSafetyEngine(config=self.config)

    def test_analyze_safe_bash(self):
        """Verifies that analyze safe bash."""
        result = self.safety.analyze_bash("ls -la")
        # Confirm the expected result for this scenario: analyze safe bash.
        assert result is not None
        assert result.danger_level == DangerLevel.SAFE

    def test_analyze_dangerous_rm(self):
        """Verifies that analyze dangerous rm."""
        result = self.safety.analyze_bash("rm -rf /")
        # Confirm the expected result for this scenario: analyze dangerous rm.
        assert result is not None
        assert result.danger_level in (DangerLevel.HIGH, DangerLevel.CRITICAL)

    def test_analyze_pipe(self):
        """Verifies that analyze pipe."""
        result = self.safety.analyze_bash("cat /etc/passwd | grep root")
        # Confirm the expected result for this scenario: analyze pipe.
        assert result is not None
        assert result.contains_pipe is True

    def test_permission_check_allow(self):
        """Verifies that permission check allow."""
        async def _test():
            """Verifies that test."""
            decision = await self.safety.check_tool_permission(
                "file_read", {"path": "test.py"}
            )
            # Confirm the expected result for this scenario: permission check allow.
            # Confirm the expected result for this scenario: test.
            assert decision is not None

        asyncio.run(_test())

    def test_permission_mode_bypass(self):
        """Verifies that permission mode bypass."""
        async def _test():
            """Verifies that test."""
            safety = EncreSafetyEngine(
                config=EncreConfig(permission_mode="bypass")
            )
            decision = await safety.check_tool_permission(
                "bash", {"cmd": "rm -rf /"}
            )
            # Confirm the expected result for this scenario: permission mode bypass.
            # Confirm the expected result for this scenario: test.
            assert decision is not None
            assert decision.behavior == "allow"

        asyncio.run(_test())

    def test_validate_tool_output_truncates(self):
        """Verifies that validate tool output truncates."""
        result = self.safety.validate_tool_output("bash", "some output")
        # Confirm the expected result for this scenario: validate tool output truncates.
        assert isinstance(result, str)
        assert "some output" in result

    def test_validate_tool_output_truncates_long(self):
        """Verifies that validate tool output truncates long."""
        long_output = "x" * 200000
        result = self.safety.validate_tool_output("bash", long_output)
        # Confirm the expected result for this scenario: validate tool output truncates long.
        assert len(result) <= self.config.tool_result_max_chars + 50

    def test_danger_level_enum(self):
        """Verifies that danger level enum."""
        # Confirm the expected result for this scenario: danger level enum.
        assert DangerLevel.SAFE is not None
        assert DangerLevel.LOW is not None
        assert DangerLevel.MEDIUM is not None
        assert DangerLevel.HIGH is not None
        assert DangerLevel.CRITICAL is not None

    def test_analyze_bash_command_function(self):
        """Verifies that analyze bash command function."""
        result = analyze_bash_command("echo hello")
        # Confirm the expected result for this scenario: analyze bash command function.
        assert result is not None
        assert result.danger_level == DangerLevel.SAFE

    def test_is_bash_safe(self):
        """Verifies that is bash safe."""
        is_safe, reason = self.safety.is_bash_safe("echo hello")
        # Confirm the expected result for this scenario: is bash safe.
        assert is_safe is True
        assert reason == ""

    def test_is_bash_safe_dangerous(self):
        """Verifies that is bash safe dangerous."""
        is_safe, reason = self.safety.is_bash_safe("rm -rf /")
        # Confirm the expected result for this scenario: is bash safe dangerous.
        assert is_safe is False
        assert len(reason) > 0


# ===========================================================================
# Agent creation and composition
# ===========================================================================


class TestAgentComposition:
    """Test cases covering agent composition.
    
    Covers the expected behavior and relevant edge cases.
    """
    def _make_config(self):
        """Verifies that make config."""
        return EncreConfig(
            model="gpt-5.6",
            backend_type="local",
            permission_mode="bypass",
            max_turns=1,
            max_tokens=1024,
        )

    def test_minimal_agent(self):
        """Verifies that minimal agent."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: minimal agent.
        assert agent is not None
        assert agent.config is not None

    def test_agent_reset(self):
        """Verifies that agent reset."""
        agent = EncreAgent(config=self._make_config())
        agent.reset()
        # Confirm the expected result for this scenario: agent reset.
        assert agent is not None

    def test_agent_has_tool_registry(self):
        """Verifies that agent has tool registry."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has tool registry.
        assert agent.tool_registry is not None

    def test_agent_has_memory_system(self):
        """Verifies that agent has memory system."""
        # memory_system is None by default (not auto-created)
        # but can be explicitly provided with required auto_memory_path
        import tempfile

        from encre.memdir.system import EncreMemorySystem
        mem = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
        agent = EncreAgent(config=self._make_config(), memory_system=mem)
        # Confirm the expected result for this scenario: agent has memory system.
        assert agent.memory_system is not None

    def test_agent_has_safety_engine(self):
        """Verifies that agent has safety engine."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has safety engine.
        assert agent.safety is not None

    def test_agent_has_hook_system(self):
        """Verifies that agent has hook system."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has hook system.
        assert agent.hook_system is not None

    def test_agent_has_skill_registry(self):
        """Verifies that agent has skill registry."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has skill registry.
        assert agent.skill_registry is not None

    def test_agent_has_plugin_registry(self):
        """Verifies that agent has plugin registry."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has plugin registry.
        assert agent.plugin_registry is not None

    def test_agent_has_evolution(self):
        """Verifies that agent has evolution."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has evolution.
        assert agent.evolution is not None

    def test_agent_has_telemetry(self):
        """Verifies that agent has telemetry."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has telemetry.
        assert agent.telemetry is not None

    def test_agent_has_recovery(self):
        """Verifies that agent has recovery."""
        agent = EncreAgent(config=self._make_config())
        # Confirm the expected result for this scenario: agent has recovery.
        assert agent.recovery is not None

    def test_agent_swarm_method(self):
        """Verifies that agent swarm method."""
        agent = EncreAgent(config=self._make_config())
        session = agent.swarm(goal="Test", max_concurrent=2)
        # Confirm the expected result for this scenario: agent swarm method.
        assert session is not None

    def test_agent_load_plugins(self):
        """Verifies that agent load plugins."""
        agent = EncreAgent(config=self._make_config())
        count = agent.load_plugins()
        # Confirm the expected result for this scenario: agent load plugins.
        assert isinstance(count, int)


# ===========================================================================
# ToolRegistry + Tool integration
# ===========================================================================


class TestToolRegistryIntegration:
    """Test cases covering tool registry integration.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        """Verifies that register and get."""
        tool = EncreFileReadTool()
        self.registry.register(tool)
        retrieved = self.registry.get("file_read")
        # Confirm the expected result for this scenario: register and get.
        assert retrieved is not None

    def test_register_many(self):
        """Verifies that register many."""
        tools = [EncreFileReadTool(), EncreFileWriteTool(), EncreBashTool()]
        self.registry.register_many(tools)
        # Confirm the expected result for this scenario: register many.
        assert self.registry.get("file_read") is not None
        assert self.registry.get("file_write") is not None
        assert self.registry.get("bash") is not None

    def test_get_nonexistent(self):
        """Verifies that get nonexistent."""
        # Confirm the expected result for this scenario: get nonexistent.
        assert self.registry.get("nonexistent_tool") is None

    def test_remove_tool(self):
        """Verifies that remove tool."""
        tool = EncreFileReadTool()
        self.registry.register(tool)
        del self.registry._tools["file_read"]
        # Confirm the expected result for this scenario: remove tool.
        assert self.registry.get("file_read") is None

    def test_all_tools(self):
        """Verifies that all tools."""
        self.registry.register(EncreFileReadTool())
        tools = self.registry.all()
        names = [t.name for t in tools]
        # Confirm the expected result for this scenario: all tools.
        assert "file_read" in names

    def test_get_openai_tools(self):
        """Verifies that get openai tools."""
        self.registry.register(EncreFileReadTool())
        self.registry.register(EncreBashTool())
        tools_json = self.registry.get_openai_tools()
        # Confirm the expected result for this scenario: get openai tools.
        assert len(tools_json) >= 2

    def test_get_anthropic_tools(self):
        """Verifies that get anthropic tools."""
        self.registry.register(EncreFileReadTool())
        tools_json = self.registry.get_anthropic_tools()
        # Confirm the expected result for this scenario: get anthropic tools.
        assert len(tools_json) >= 1

    def test_clear_tools(self):
        """Verifies that clear tools."""
        self.registry.register(EncreFileReadTool())
        self.registry._tools.clear()
        # Confirm the expected result for this scenario: clear tools.
        assert self.registry.all() == []
