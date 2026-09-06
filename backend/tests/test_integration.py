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
    """Engineered to validate safety-to-tool wiring in the agent execution pipeline.

    This test class exercises the EncreSafetyEngine across 11 scenarios to ensure
    that bash command analysis, permission checks, output validation, and the
    DangerLevel enum all behave correctly when integrated with the tool registry.
    The design follows a layered approach: raw command analysis (analyze_bash)
    feeds into permission evaluation (check_tool_permission), which gates tool
    execution. Output truncation guards against token budget overflow.
    """

    def setup_method(self):
        """Initialize safety engine with default permission mode before each test."""
        self.config = EncreConfig(permission_mode="default")
        self.safety = EncreSafetyEngine(config=self.config)

    def test_verify_safe_bash_analysis(self):
        """Validate that analyze_bash classifies harmless commands as SAFE.

        The test exercises a read-only 'ls -la' command through the safety engine
        and asserts the returned DangerLevel is SAFE because non-mutating
        directory listing commands pose no security risk.
        """
        result = self.safety.analyze_bash("ls -la")
        assert result is not None
        # Confirm the returned analysis is not None and classified as SAFE.
        assert result.danger_level == DangerLevel.SAFE

    def test_verify_dangerous_rm_analysis(self):
        """Validate that analyze_bash flags recursive destructive removal as HIGH/CRITICAL.

        The test exercises 'rm -rf /' through the safety engine and asserts the
        danger level falls in the HIGH or CRITICAL range because forced recursive
        deletion is an irreversible destructive operation.
        """
        result = self.safety.analyze_bash("rm -rf /")
        assert result is not None
        # Confirm the analysis flags recursive force-delete as high-danger.
        assert result.danger_level in (DangerLevel.HIGH, DangerLevel.CRITICAL)

    def test_verify_pipe_detection(self):
        """Validate that analyze_bash detects shell pipe operators in commands.

        The test exercises a command containing a pipe ('|') and asserts
        contains_pipe is True because piping output between processes is a
        recognized attack vector for information leakage.
        """
        result = self.safety.analyze_bash("cat /etc/passwd | grep root")
        assert result is not None
        # Confirm the safety engine identified the pipe operator.
        assert result.contains_pipe is True

    def test_verify_permission_check_allows_file_read(self):
        """Validate that check_tool_permission returns a decision for allowed tools.

        The test exercises the file_read tool with a benign path in default
        permission mode and asserts a non-None decision is returned because
        the permission engine should always produce an evaluation result.
        """
        async def _test():
            decision = await self.safety.check_tool_permission(
                "file_read", {"path": "test.py"}
            )
            assert decision is not None

        asyncio.run(_test())

    def test_verify_permission_mode_bypass_allows_dangerous_commands(self):
        """Validate that bypass mode permits dangerous operations without restriction.

        The test creates a safety engine in 'bypass' mode, requests permission
        for 'rm -rf /', and asserts behavior == 'allow' because bypass mode
        is designed to disable all permission gating for development use.
        """
        async def _test():
            safety = EncreSafetyEngine(
                config=EncreConfig(permission_mode="bypass")
            )
            decision = await safety.check_tool_permission(
                "bash", {"cmd": "rm -rf /"}
            )
            assert decision is not None
            # Confirm bypass mode results in an explicit allow decision.
            assert decision.behavior == "allow"

        asyncio.run(_test())

    def test_verify_tool_output_preserves_content(self):
        """Validate that validate_tool_output retains the original content string.

        The test exercises output validation on a short bash result and asserts
        the return type is str and the original text is preserved because
        validation must not alter tool output for short responses.
        """
        result = self.safety.validate_tool_output("bash", "some output")
        assert isinstance(result, str)
        assert "some output" in result

    def test_verify_tool_output_truncates_long_responses(self):
        """Validate that validate_tool_output enforces a maximum character ceiling.

        The test exercises a 200K-character output through validation and asserts
        the result fits within tool_result_max_chars + 50 because long tool
        outputs must be truncated to protect the context window from overflow.
        """
        long_output = "x" * 200000
        result = self.safety.validate_tool_output("bash", long_output)
        assert len(result) <= self.config.tool_result_max_chars + 50

    def test_verify_danger_level_enum_completeness(self):
        """Validate that all DangerLevel enum members are defined and non-None.

        The test asserts each enum member exists because the safety engine
        depends on a complete ordered set of danger levels for consistent
        classification across all analysis paths.
        """
        assert DangerLevel.SAFE is not None
        assert DangerLevel.LOW is not None
        assert DangerLevel.MEDIUM is not None
        assert DangerLevel.HIGH is not None
        assert DangerLevel.CRITICAL is not None

    def test_verify_analyze_bash_command_function(self):
        """Validate that the standalone analyze_bash_command returns a safe classification.

        The test exercises the module-level convenience function with 'echo hello'
        and asserts the result is SAFE because echo is a non-mutating output
        operation with no security implications.
        """
        result = analyze_bash_command("echo hello")
        assert result is not None
        assert result.danger_level == DangerLevel.SAFE

    def test_verify_is_bash_safe_positive(self):
        """Validate that is_bash_safe returns (True, '') for harmless commands.

        The test exercises 'echo hello' and asserts is_safe is True with an
        empty reason string because safe commands should produce no warning.
        """
        is_safe, reason = self.safety.is_bash_safe("echo hello")
        assert is_safe is True
        assert reason == ""

    def test_verify_is_bash_safe_rejects_destructive(self):
        """Validate that is_bash_safe returns (False, reason) for dangerous commands.

        The test exercises 'rm -rf /' and asserts is_safe is False with a
        non-empty reason because destructive operations must be explicitly
        rejected with an explanatory message.
        """
        is_safe, reason = self.safety.is_bash_safe("rm -rf /")
        assert is_safe is False
        assert len(reason) > 0


# ===========================================================================
# Agent creation and composition
# ===========================================================================


class TestAgentComposition:
    """Engineered to validate the EncreAgent component composition and dependency injection.

    This test class exercises agent construction across 13 scenarios to ensure
    that all subsystems (tool registry, memory, safety, hooks, skills, plugins,
    evolution, telemetry, recovery) are correctly wired into the agent on
    initialization. The design follows a dependency-injection pattern so that
    every critical subsystem is available as an attribute on the agent instance.
    """

    def _make_config(self):
        """Build a minimal bypass-mode config for agent construction tests."""
        return EncreConfig(
            model="gpt-5.6",
            backend_type="local",
            permission_mode="bypass",
            max_turns=1,
            max_tokens=1024,
        )

    def test_verify_minimal_agent_constructs(self):
        """Validate that a minimal EncreAgent initializes with valid config.

        The test constructs an agent with the default bypass config and asserts
        both the agent instance and its config are non-None because a valid
        configuration is the minimum requirement for agent instantiation.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent is not None
        assert agent.config is not None

    def test_verify_agent_reset_preserves_instance(self):
        """Validate that agent.reset() does not destroy the agent instance.

        The test constructs an agent, calls reset(), and asserts the agent
        remains a valid object because reset should clear runtime state but
        not invalidate the agent itself.
        """
        agent = EncreAgent(config=self._make_config())
        agent.reset()
        assert agent is not None

    def test_verify_agent_has_tool_registry(self):
        """Validate that the agent holds a reference to its tool registry.

        The test asserts agent.tool_registry is not None because the tool
        registry is the central dispatch mechanism for all tool invocations
        and must be available immediately after construction.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.tool_registry is not None

    def test_verify_agent_accepts_external_memory_system(self):
        """Validate that the agent accepts and stores an externally-provided memory system.

        The test creates an EncreMemorySystem with a temporary auto-memory path,
        passes it to the agent constructor, and asserts memory_system is not None
        because explicit injection is the primary mechanism for configuring memory.
        """
        import tempfile
        from encre.memdir.system import EncreMemorySystem
        mem = EncreMemorySystem(auto_memory_path=tempfile.mkdtemp())
        agent = EncreAgent(config=self._make_config(), memory_system=mem)
        assert agent.memory_system is not None

    def test_verify_agent_has_safety_engine(self):
        """Validate that the agent holds a reference to its safety engine.

        The test asserts agent.safety is not None because the safety engine
        intercepts all tool calls and must be present on every agent instance.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.safety is not None

    def test_verify_agent_has_hook_system(self):
        """Validate that the agent holds a reference to its hook system.

        The test asserts agent.hook_system is not None because the hook system
        provides lifecycle callbacks (on_turn_start, on_tool_call, etc.) and
        must be available for extension points.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.hook_system is not None

    def test_verify_agent_has_skill_registry(self):
        """Validate that the agent holds a reference to its skill registry.

        The test asserts agent.skill_registry is not None because skills are
        resolved through this registry during tool selection and must be
        accessible from the agent's top-level interface.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.skill_registry is not None

    def test_verify_agent_has_plugin_registry(self):
        """Validate that the agent holds a reference to its plugin registry.

        The test asserts agent.plugin_registry is not None because plugins are
        loaded and managed through this registry, providing the extension
        mechanism for third-party capabilities.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.plugin_registry is not None

    def test_verify_agent_has_evolution_system(self):
        """Validate that the agent holds a reference to its evolution subsystem.

        The test asserts agent.evolution is not None because the evolution
        system tracks agent state transitions and capability growth across
        sessions and must be initialized on every agent instance.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.evolution is not None

    def test_verify_agent_has_telemetry(self):
        """Validate that the agent holds a reference to its telemetry subsystem.

        The test asserts agent.telemetry is not None because telemetry collects
        usage metrics and performance data, which must be available for
        observability and debugging throughout the agent lifecycle.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.telemetry is not None

    def test_verify_agent_has_recovery(self):
        """Validate that the agent holds a reference to its recovery subsystem.

        The test asserts agent.recovery is not None because the recovery system
        handles checkpoint restoration and error recovery, which must be
        available for fault tolerance during long-running sessions.
        """
        agent = EncreAgent(config=self._make_config())
        assert agent.recovery is not None

    def test_verify_agent_swarm_method_returns_session(self):
        """Validate that agent.swarm() returns a valid session object.

        The test invokes the swarm API with a goal and max_concurrent limit,
        and asserts the returned session is not None because swarm mode
        spawns a concurrent multi-agent coordination session.
        """
        agent = EncreAgent(config=self._make_config())
        session = agent.swarm(goal="Test", max_concurrent=2)
        assert session is not None

    def test_verify_agent_load_plugins_returns_count(self):
        """Validate that agent.load_plugins() returns an integer count.

        The test invokes load_plugins and asserts the result is an int because
        the method reports how many plugins were successfully loaded, which
        serves as a confirmation of plugin discovery and registration.
        """
        agent = EncreAgent(config=self._make_config())
        count = agent.load_plugins()
        assert isinstance(count, int)


# ===========================================================================
# ToolRegistry + Tool integration
# ===========================================================================


class TestToolRegistryIntegration:
    """Engineered to validate the ToolRegistry lifecycle: register, resolve, and remove.

    This test class exercises the registry across 8 scenarios to ensure that
    tool registration, lookup by name, bulk registration, OpenAI/Anthropic
    format export, and cleanup all behave correctly. The design follows a
    dictionary-backed resolution model so that get(name) returns O(1) access
    to any registered tool instance.
    """

    def setup_method(self):
        """Initialize a fresh ToolRegistry before each test to prevent cross-test pollution."""
        self.registry = ToolRegistry()

    def test_verify_register_and_retrieve_by_name(self):
        """Validate that a registered tool is retrievable via registry.get().

        The test registers EncreFileReadTool and asserts the lookup returns
        a non-None value because the registry must resolve tools by their
        canonical name string.
        """
        tool = EncreFileReadTool()
        self.registry.register(tool)
        retrieved = self.registry.get("file_read")
        assert retrieved is not None

    def test_verify_bulk_register_exposes_all_tools(self):
        """Validate that register_many adds each tool and all are resolvable.

        The test registers three different tools and asserts each can be
        retrieved by its canonical name because bulk registration must be
        atomic 鈥?all tools must be accessible after the call completes.
        """
        tools = [EncreFileReadTool(), EncreFileWriteTool(), EncreBashTool()]
        self.registry.register_many(tools)
        assert self.registry.get("file_read") is not None
        assert self.registry.get("file_write") is not None
        assert self.registry.get("bash") is not None

    def test_verify_get_nonexistent_returns_none(self):
        """Validate that registry.get() returns None for unregistered tool names.

        The test queries a nonexistent tool name and asserts None because
        missing tools should not raise exceptions 鈥?they should return None
        so callers can gracefully handle absent dependencies.
        """
        assert self.registry.get("nonexistent_tool") is None

    def test_verify_remove_tool_exits_registry(self):
        """Validate that deleting a tool from the internal store removes it from resolution.

        The test registers a tool, manually deletes it from _tools, and asserts
        that subsequent get() returns None because direct mutation of the
        internal store must be reflected in lookups.
        """
        tool = EncreFileReadTool()
        self.registry.register(tool)
        del self.registry._tools["file_read"]
        assert self.registry.get("file_read") is None

    def test_verify_all_returns_registered_names(self):
        """Validate that registry.all() includes the name of every registered tool.

        The test registers a single tool, retrieves the full list, and asserts
        'file_read' appears in the name set because the all() method must
        report every registered tool for discovery and introspection.
        """
        self.registry.register(EncreFileReadTool())
        tools = self.registry.all()
        names = [t.name for t in tools]
        assert "file_read" in names

    def test_verify_get_openai_tools_format(self):
        """Validate that get_openai_tools produces the correct number of tool definitions.

        The test registers two tools and asserts the OpenAI-format list has
        at least 2 entries because the format converter must emit one tool
        definition per registered tool.
        """
        self.registry.register(EncreFileReadTool())
        self.registry.register(EncreBashTool())
        tools_json = self.registry.get_openai_tools()
        assert len(tools_json) >= 2

    def test_verify_get_anthropic_tools_format(self):
        """Validate that get_anthropic_tools produces at least one tool definition.

        The test registers a single tool and asserts the Anthropic-format list
        is non-empty because the format converter must emit at least one tool
        definition when tools are registered.
        """
        self.registry.register(EncreFileReadTool())
        tools_json = self.registry.get_anthropic_tools()
        assert len(tools_json) >= 1

    def test_verify_clear_removes_all_tools(self):
        """Validate that clearing the internal store empties the registry.

        The test registers a tool, directly clears _tools, and asserts all()
        returns an empty list because the registry must reflect manual
        cleanup of its internal storage.
        """
        self.registry.register(EncreFileReadTool())
        self.registry._tools.clear()
        assert self.registry.all() == []
