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

"""Tests for EncreAgent: construction, properties, run, lifecycle."""

import inspect

import pytest

from encre.agent import EncreAgent
from encre.config import EncreConfig


class TestEncreAgentConstruction:
    """Verify EncreAgent can be constructed with various configurations."""

    def test_creation_with_no_args(self):
        """Test: Creation with no args."""
        agent = EncreAgent()
        # Verify: agent is not None
        assert agent is not None
        # Verify: isinstance(agent.config, EncreConfig)
        assert isinstance(agent.config, EncreConfig)

    def test_creation_with_explicit_config(self):
        """Test: Creation with explicit config."""
        config = EncreConfig(model="gpt-5.6-luna", max_tokens=1000)
        agent = EncreAgent(config=config)
        # Verify: agent.config is config
        assert agent.config is config
        # Verify: agent.config.model == "gpt-5.6-luna"
        assert agent.config.model == "gpt-5.6-luna"

    def test_creation_with_config_defaults(self):
        """Test: Creation with config defaults."""
        agent = EncreAgent()
        # Verify: agent.config.model is empty (no hardcoded vendor default)
        assert agent.config.model == ""
        # Verify: agent.config.backend_type is empty (no hardcoded vendor default)
        assert agent.config.backend_type == ""


class TestEncreAgentProperties:
    """Verify EncreAgent exposes expected attributes after construction."""

    def test_has_config(self):
        """Test: Has config."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "config")
        assert hasattr(agent, "config")
        # Verify: isinstance(agent.config, EncreConfig)
        assert isinstance(agent.config, EncreConfig)

    def test_has_tool_registry(self):
        """Test: Has tool registry."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "tool_registry")
        assert hasattr(agent, "tool_registry")

    def test_has_hook_system(self):
        """Test: Has hook system."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "hook_system")
        assert hasattr(agent, "hook_system")

    def test_has_safety(self):
        """Test: Has safety."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "safety")
        assert hasattr(agent, "safety")

    def test_has_memory_system(self):
        """Test: Has memory system."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "memory_system")
        assert hasattr(agent, "memory_system")

    def test_has_skill_registry(self):
        """Test: Has skill registry."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "skill_registry")
        assert hasattr(agent, "skill_registry")
        # Verify: agent.skill_registry is not None
        assert agent.skill_registry is not None

    def test_has_session(self):
        """Test: Has session."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "session")
        assert hasattr(agent, "session")

    def test_has_telemetry(self):
        """Test: Has telemetry."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "telemetry")
        assert hasattr(agent, "telemetry")

    def test_has_evolution(self):
        """Test: Has evolution."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "evolution")
        assert hasattr(agent, "evolution")

    def test_has_recovery(self):
        """Test: Has recovery."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "recovery")
        assert hasattr(agent, "recovery")

    def test_has_loop(self):
        """Test: Has loop."""
        agent = EncreAgent()
        # Verify: hasattr(agent, "loop")
        assert hasattr(agent, "loop")


class TestEncreAgentRun:
    """Verify run() signature returns an AsyncGenerator."""

    def test_run_returns_async_generator(self):
        """Test: Run returns async generator."""
        agent = EncreAgent()
        # run() is an async generator function
        assert inspect.isasyncgenfunction(agent.run)

    def test_run_signature(self):
        """Test: Run signature."""
        agent = EncreAgent()
        sig = inspect.signature(agent.run)
        params = list(sig.parameters.keys())
        # Verify: "prompt" in params
        assert "prompt" in params
        # Verify: "system_prompt" in params
        assert "system_prompt" in params

    def test_run_with_tools_returns_async_generator(self):
        """Test: Run with tools returns async generator."""
        agent = EncreAgent()
        # Verify: inspect.isasyncgenfunction(agent.run_with_tools)
        assert inspect.isasyncgenfunction(agent.run_with_tools)

    def test_run_return_type_is_async_generator(self):
        """Test: Run return type is async generator."""
        import typing
        agent = EncreAgent()
        hints = typing.get_type_hints(agent.run)
        # Verify: "return" in hints
        assert "return" in hints


class TestEncreAgentLifecycle:
    """Verify EncreAgent lifecycle methods exist."""

    def test_reset_exists(self):
        """Test: Reset exists."""
        agent = EncreAgent()
        # Verify: callable(agent.reset)
        assert callable(agent.reset)

    def test_aclose_exists(self):
        """Test: Aclose exists."""
        agent = EncreAgent()
        # Verify: callable(agent.aclose)
        assert callable(agent.aclose)

    def test_add_message_exists(self):
        """Test: Add message exists."""
        agent = EncreAgent()
        # Verify: callable(agent.add_message)
        assert callable(agent.add_message)

    def test_add_message_adds_to_session(self):
        """Test: Add message adds to session."""
        agent = EncreAgent()
        # Verify: len(agent.session.messages) == 0
        assert len(agent.session.messages) == 0
        agent.add_message("user", "hello")
        # Verify: len(agent.session.messages) == 1
        assert len(agent.session.messages) == 1
        # Verify: agent.session.messages[0]["role"] == "user"
        assert agent.session.messages[0]["role"] == "user"
        # Verify: agent.session.messages[0]["content"] == "hello"
        assert agent.session.messages[0]["content"] == "hello"

    def test_respond_permission_exists(self):
        """Test: Respond permission exists."""
        agent = EncreAgent()
        # Verify: callable(agent.respond_permission)
        assert callable(agent.respond_permission)

    def test_activate_skill_exists(self):
        """Test: Activate skill exists."""
        agent = EncreAgent()
        # Verify: callable(agent.activate_skill)
        assert callable(agent.activate_skill)


class TestEncreAgentGoalAndSwarm:
    """Verify goal() and swarm() factory methods exist."""

    def test_goal_returns_goal_loop(self):
        """Test: Goal returns goal loop."""
        agent = EncreAgent()
        loop = agent.goal(
            description="Test goal",
            success_criteria="Tests pass",
            max_attempts=3,
        )
        # Verify: loop is not None
        assert loop is not None
        # Verify: hasattr(loop, "execute")
        assert hasattr(loop, "execute")

    def test_swarm_returns_swarm_session(self):
        """Test: Swarm returns swarm session."""
        agent = EncreAgent()
        session = agent.swarm(
            goal="Build a TODO app",
            max_concurrent=2,
        )
        # Verify: session is not None
        assert session is not None
        # Verify: hasattr(session, "execute")
        assert hasattr(session, "execute")

    def test_set_scheduler_exists(self):
        """Test: Set scheduler exists."""
        agent = EncreAgent()
        # Verify: callable(agent.set_scheduler)
        assert callable(agent.set_scheduler)


class _FakeConfig:
    """Minimal stand-in for EncreConfig used by the agent tool."""

    def __init__(self):
        self.sub_agents = []


class _FakeParentLoop:
    """Fake parent loop that records how sub-agents are launched."""

    def __init__(self):
        self.sub_agent_depth = 0
        self.config = _FakeConfig()
        self.calls: list[str] = []

    async def _run_sub_agent(self, prompt, system_prompt="", max_turns=0,
                             tool_policy="all", progress_callback=None, **_kw):
        """Emit one live snapshot then return a real transcript."""
        self.calls.append(prompt)
        msg = {"role": "assistant", "content": f"snapshot for {prompt}"}
        if progress_callback is not None:
            await progress_callback([msg])
        return {
            "content": f"final for {prompt}",
            "messages": [msg],
            "session_id": f"sid-{prompt}",
        }


class TestAgentToolParallel:
    """Regression tests for the parallel ``tasks`` path of the agent tool."""

    @pytest.mark.asyncio
    async def test_parallel_tasks_aggregate_messages_and_stream(self):
        """Parallel tasks must return real transcripts and stream progress.

        Previously the parallel path passed ``progress_callback=None`` and
        returned ``messages=[]`` -- the UI never rendered a sub-agent view
        and the parent only saw a bare "succeeded" placeholder.
        """
        from encre.tools.builtin import agent as agent_mod

        parent = _FakeParentLoop()
        token = agent_mod.set_active_loop(parent)
        streamed: list[list[dict]] = []

        async def _cb(messages):
            streamed.append(messages)

        try:
            result = await agent_mod._agent_execute(
                tasks=[{"prompt": "alpha"}, {"prompt": "beta"}],
                progress_callback=_cb,
            )
        finally:
            agent_mod.reset_active_loop(token)

        # Both sub-agents ran.
        assert parent.calls == ["alpha", "beta"]
        # Aggregated content carries each sub-agent's real output.
        assert "final for alpha" in result["content"]
        assert "final for beta" in result["content"]
        # Messages are aggregated (not empty) so the card renders.
        assert result["messages"], "parallel path must return transcripts"
        joined = " ".join(str(m.get("content", "")) for m in result["messages"])
        assert "snapshot for alpha" in joined
        assert "snapshot for beta" in joined
        # Per-task results are still exposed for callers that want them.
        assert len(result["sub_results"]) == 2
        # Live progress was streamed to the parent callback.
        assert streamed, "parallel path must stream combined progress"

    @pytest.mark.asyncio
    async def test_parallel_tasks_rejects_non_list(self):
        """A non-list ``tasks`` value returns a clear error."""
        from encre.tools.builtin import agent as agent_mod

        parent = _FakeParentLoop()
        token = agent_mod.set_active_loop(parent)
        try:
            result = await agent_mod._agent_execute(tasks="nope")
        finally:
            agent_mod.reset_active_loop(token)
        assert "must be an array" in result["content"]

    @pytest.mark.asyncio
    async def test_parallel_tasks_concurrency_capped_at_four(self):
        """At most MAX_PARALLEL_SUB_AGENTS run at once; extras queue.

        Six tasks in one call must all run, but no more than four may be
        in-flight simultaneously -- the rest wait on the semaphore.
        """
        from encre.tools.builtin import agent as agent_mod

        class _ProbeLoop:
            def __init__(self):
                self.sub_agent_depth = 0
                self.config = _FakeConfig()
                self.active = 0
                self.peak = 0
                self.total = 0

            async def _run_sub_agent(self, prompt, system_prompt="", max_turns=0,
                                     tool_policy="all", progress_callback=None, **_kw):
                self.active += 1
                self.total += 1
                self.peak = max(self.peak, self.active)
                # Yield so other queued tasks get a chance to start; the
                # semaphore must still bound how many overlap here.
                await asyncio.sleep(0.02)
                self.active -= 1
                return {"content": f"final for {prompt}", "messages": [], "session_id": prompt}

        parent = _ProbeLoop()
        token = agent_mod.set_active_loop(parent)
        try:
            result = await agent_mod._agent_execute(
                tasks=[{"prompt": f"t{i}"} for i in range(6)],
            )
        finally:
            agent_mod.reset_active_loop(token)

        assert parent.total == 6, "every task must eventually run"
        assert parent.peak == agent_mod.MAX_PARALLEL_SUB_AGENTS
        assert parent.peak <= 4
        assert len(result["sub_results"]) == 6

