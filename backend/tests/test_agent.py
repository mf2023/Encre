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

"""Tests for EncreAgent: construction, properties, run, lifecycle."""

import asyncio
import inspect

import pytest

from encre.agent import EncreAgent
from encre.config import EncreConfig


class TestEncreAgentConstruction:
    """Engineered to validate :class:`EncreAgent` construction under varied configurations.

    The agent accepts an optional EncreConfig and must produce a valid
    instance with sensible defaults when none is supplied. Tests confirm
    that default construction yields a non-None agent with a config whose
    model and backend_type are empty strings 鈥?proving no vendor is
    implicitly hardcoded at the constructor level.
    """

    def test_verify_creation_with_no_args_produces_a_valid_agent(self):
        """Validate that EncreAgent() instantiates without arguments and yields a non-None agent.

        Default construction is the common path; a crash or None return
        here breaks every test that does not explicitly pass a config.
        """
        agent = EncreAgent()
        # Verify: agent is not None
        assert agent is not None
        # Verify: isinstance(agent.config, EncreConfig)
        assert isinstance(agent.config, EncreConfig)

    def test_verify_creation_with_explicit_config_stores_that_config(self):
        """Validate that passing an explicit EncreConfig makes it available as agent.config with the expected model.

        The config reference must be stored, not copied, so runtime changes
        to the config object propagate to the agent without reassignment.
        """
        config = EncreConfig(model="gpt-5.6-luna", max_tokens=1000)
        agent = EncreAgent(config=config)
        # Verify: agent.config is config
        assert agent.config is config
        # Verify: agent.config.model == "gpt-5.6-luna"
        assert agent.config.model == "gpt-5.6-luna"

    def test_verify_creation_with_defaults_leaves_model_and_backend_type_empty(self):
        """Validate that the default config leaves model and backend_type as empty strings.

        Hardcoding a vendor default in the constructor would bias the agent
        toward one provider; keeping these empty forces the caller to
        select a backend explicitly before running.
        """
        agent = EncreAgent()
        # Verify: agent.config.model is empty (no hardcoded vendor default)
        assert agent.config.model == ""
        # Verify: agent.config.backend_type is empty (no hardcoded vendor default)
        assert agent.config.backend_type == ""


class TestEncreAgentProperties:
    """Engineered to validate that :class:`EncreAgent` exposes all expected subsystem attributes after construction.

    The agent composes several subsystems (config, tool registry, hook
    system, safety, memory, skill registry, session, telemetry, evolution,
    recovery, and loop). Tests assert the presence of each attribute so
    that removing or renaming a subsystem is caught as a regression.
    """

    def test_verify_agent_has_config_attribute(self):
        """Validate that the agent exposes a config attribute of type EncreConfig.

        Config is the top-level knob for model, permission, and quota
        settings; every subsystem reads from it, so its presence is mandatory.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "config")
        assert hasattr(agent, "config")
        # Verify: isinstance(agent.config, EncreConfig)
        assert isinstance(agent.config, EncreConfig)

    def test_verify_agent_has_tool_registry_attribute(self):
        """Validate that the agent exposes a tool_registry attribute.

        The tool registry is the dispatch table for all builtin and custom
        tools; its absence would make tool invocation impossible.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "tool_registry")
        assert hasattr(agent, "tool_registry")

    def test_verify_agent_has_hook_system_attribute(self):
        """Validate that the agent exposes a hook_system attribute.

        Hooks provide lifecycle callbacks (pre-turn, post-tool, on-error);
        their presence is required for the extensibility layer to function.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "hook_system")
        assert hasattr(agent, "hook_system")

    def test_verify_agent_has_safety_attribute(self):
        """Validate that the agent exposes a safety attribute.

        The safety subsystem enforces permission prompts and action
        restrictions; its presence is required before any tool can run.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "safety")
        assert hasattr(agent, "safety")

    def test_verify_agent_has_memory_system_attribute(self):
        """Validate that the agent exposes a memory_system attribute.

        Memory provides long-term context across sessions; the subsystem
        must exist even when unused so callers can attach handlers uniformly.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "memory_system")
        assert hasattr(agent, "memory_system")

    def test_verify_agent_has_skill_registry_attribute_and_it_is_not_none(self):
        """Validate that the agent exposes a non-None skill_registry attribute.

        Skills are reusable capability modules; the registry must be
        instantiated (not None) so the agent can activate skills at runtime.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "skill_registry")
        assert hasattr(agent, "skill_registry")
        # Verify: agent.skill_registry is not None
        assert agent.skill_registry is not None

    def test_verify_agent_has_session_attribute(self):
        """Validate that the agent exposes a session attribute.

        The session holds the conversation history and is the primary
        I/O surface between the agent loop and the model backend.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "session")
        assert hasattr(agent, "session")

    def test_verify_agent_has_telemetry_attribute(self):
        """Validate that the agent exposes a telemetry attribute.

        Telemetry tracks usage, latency, and errors; the attribute must
        exist so the metrics pipeline can be attached uniformly.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "telemetry")
        assert hasattr(agent, "telemetry")

    def test_verify_agent_has_evolution_attribute(self):
        """Validate that the agent exposes an evolution attribute.

        Evolution drives self-improvement loops (reflection, replay); its
        presence is required even when disabled so the API surface stays stable.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "evolution")
        assert hasattr(agent, "evolution")

    def test_verify_agent_has_recovery_attribute(self):
        """Validate that the agent exposes a recovery attribute.

        Recovery handles checkpoint restoration and crash retry; the
        attribute must exist so the main loop can invoke it on failure.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "recovery")
        assert hasattr(agent, "recovery")

    def test_verify_agent_has_loop_attribute(self):
        """Validate that the agent exposes a loop attribute.

        The loop is the main execution engine; its presence is required
        for goal-oriented and swarm sub-agent modes that run independently.
        """
        agent = EncreAgent()
        # Verify: hasattr(agent, "loop")
        assert hasattr(agent, "loop")


class TestEncreAgentRun:
    """Engineered to validate the run() and run_with_tools() signatures and return types.

    Both methods are async generators that yield event dicts to the
    caller. Tests use inspect and typing introspection to confirm the
    shape of the API without needing a live model backend.
    """

    def test_verify_run_is_an_async_generator_function(self):
        """Validate that agent.run is an async generator function per inspect.isasyncgenfunction.

        The async generator shape lets the caller iterate events lazily;
        a regular async def would force the caller to await the full run,
        defeating real-time streaming.
        """
        agent = EncreAgent()
        # run() is an async generator function
        assert inspect.isasyncgenfunction(agent.run)

    def test_verify_run_signature_contains_prompt_and_system_prompt_parameters(self):
        """Validate that agent.run's signature includes 'prompt' and 'system_prompt' parameters.

        These two parameters are the primary user-facing inputs; their
        presence in the signature guarantees the public API contract holds.
        """
        agent = EncreAgent()
        sig = inspect.signature(agent.run)
        params = list(sig.parameters.keys())
        # Verify: "prompt" in params
        assert "prompt" in params
        # Verify: "system_prompt" in params
        assert "system_prompt" in params

    def test_verify_run_with_tools_is_an_async_generator_function(self):
        """Validate that agent.run_with_tools is an async generator function.

        run_with_tools extends run with explicit tool injection; it must
        retain the async generator shape so streaming works identically.
        """
        agent = EncreAgent()
        # Verify: inspect.isasyncgenfunction(agent.run_with_tools)
        assert inspect.isasyncgenfunction(agent.run_with_tools)

    def test_verify_run_return_type_hint_is_present(self):
        """Validate that typing.get_type_hints(agent.run) includes a 'return' entry.

        The return hint is consumed by IDE tooling and static checkers; its
        presence confirms the developer did not drop the annotation when
        refactoring the async generator body.
        """
        import typing
        agent = EncreAgent()
        hints = typing.get_type_hints(agent.run)
        # Verify: "return" in hints
        assert "return" in hints


class TestEncreAgentLifecycle:
    """Engineered to validate that lifecycle methods exist and are callable on :class:`EncreAgent`.

    Lifecycle hooks (reset, aclose, add_message, respond_permission,
    activate_skill) are called by the loop and by external orchestrators.
    Tests assert callability so that signature changes do not silently
    break the call sites that depend on them.
    """

    def test_verify_reset_is_callable(self):
        """Validate that agent.reset exists and is callable.

        Reset is invoked between turns to clear transitory state; the test
        only checks callability because actual reset behavior is covered
        by session-level tests.
        """
        agent = EncreAgent()
        # Verify: callable(agent.reset)
        assert callable(agent.reset)

    def test_verify_aclose_is_callable(self):
        """Validate that agent.aclose exists and is callable.

        Aclose cleans up async resources (event loops, network handles);
        its presence is required for graceful shutdown.
        """
        agent = EncreAgent()
        # Verify: callable(agent.aclose)
        assert callable(agent.aclose)

    def test_verify_add_message_is_callable(self):
        """Validate that agent.add_message exists and is callable.

        add_message is the external entry point for injecting messages
        without going through the run loop; callability is required for
        programmatic session manipulation.
        """
        agent = EncreAgent()
        # Verify: callable(agent.add_message)
        assert callable(agent.add_message)

    def test_verify_add_message_appends_to_the_session(self):
        """Validate that calling add_message increases the session message count by one.

        The method must delegate to session.add_message; the test asserts
        the list grows from 0 to 1 and that the injected message's role
        and content match what was passed in.
        """
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

    def test_verify_respond_permission_is_callable(self):
        """Validate that agent.respond_permission exists and is callable.

        respond_permission is the external entry point for answering a
        pending permission request; callability is required for async
        callback wiring in the permission handler.
        """
        agent = EncreAgent()
        # Verify: callable(agent.respond_permission)
        assert callable(agent.respond_permission)

    def test_verify_activate_skill_is_callable(self):
        """Validate that agent.activate_skill exists and is callable.

        activate_skill is the entry point for the skill subsystem; its
        presence is required for the skill registry to be invoked at runtime.
        """
        agent = EncreAgent()
        # Verify: callable(agent.activate_skill)
        assert callable(agent.activate_skill)


class TestEncreAgentGoalAndSwarm:
    """Engineered to validate the goal() and swarm() factory methods on :class:`EncreAgent`.

    These class methods construct independent execution loops (goal loop
    for single-objective tasks, swarm session for multi-agent parallelism).
    Tests assert the returned objects are non-None and expose an execute()
    method, confirming the factory contract holds.
    """

    def test_verify_goal_returns_an_executable_goal_loop(self):
        """Validate that agent.goal() returns an object with an execute method.

        The goal loop is the top-level orchestrator for single-agent goal
        resolution; execute() is the entry point the caller invokes to
        start the loop.
        """
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

    def test_verify_swarm_returns_an_executable_swarm_session(self):
        """Validate that agent.swarm() returns an object with an execute method.

        The swarm session orchestrates multiple concurrent sub-agents;
        execute() is the entry point that drives the parallel workflow.
        """
        agent = EncreAgent()
        session = agent.swarm(
            goal="Build a TODO app",
            max_concurrent=2,
        )
        # Verify: session is not None
        assert session is not None
        # Verify: hasattr(session, "execute")
        assert hasattr(session, "execute")

    def test_verify_set_scheduler_is_callable(self):
        """Validate that agent.set_scheduler exists and is callable.

        set_scheduler wires an external cron/ scheduler into the agent so
        goal loops can be triggered on a timetable; callability is required
        for DI wiring in production deployments.
        """
        agent = EncreAgent()
        # Verify: callable(agent.set_scheduler)
        assert callable(agent.set_scheduler)


class _FakeConfig:
    """Minimal stand-in for EncreConfig used by the agent tool."""

    def __init__(self):
        self.sub_agents = []


class _FakeParentLoop:
    """Fake parent loop that records how sub-agents are launched.

    Captures each sub-agent prompt in self.calls and returns a fixed
    transcript shape so the parallel path can be tested without a real
    model backend. The progress_callback is invoked with one snapshot
    message per sub-agent to verify streaming behavior.
    """

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
    """Regression tests for the parallel ``tasks`` path of the agent tool.

    Previously the parallel path passed ``progress_callback=None`` and
    returned ``messages=[]`` -- the UI never rendered a sub-agent view
    and the parent only saw a bare "succeeded" placeholder. These tests
    assert the fixed behavior: real transcripts are aggregated, progress
    is streamed, and the concurrency cap is respected.
    """

    @pytest.mark.asyncio
    async def test_verify_parallel_tasks_aggregate_messages_and_stream_progress(self):
        """Validate that parallel task execution aggregates real transcripts and streams progress callbacks.

        Two sub-agents ('alpha' and 'beta') are launched concurrently; the
        test asserts their prompts appear in parent.calls (proving both
        ran), their final content appears in the aggregated result, and
        the streamed snapshots appear in the joined message stream. The
        sub_results list must contain exactly two entries so callers that
        inspect per-task outcomes do not see a zero-length list.
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
    async def test_verify_parallel_tasks_rejects_non_list_tasks_value(self):
        """Validate that passing a non-list ``tasks`` value returns a clear error message.

        The executor must validate the input shape before spawning any
        sub-agents; a string like 'nope' should produce a readable error
        rather than an unhandled TypeError deep in the concurrency code.
        """
        from encre.tools.builtin import agent as agent_mod

        parent = _FakeParentLoop()
        token = agent_mod.set_active_loop(parent)
        try:
            result = await agent_mod._agent_execute(tasks="nope")
        finally:
            agent_mod.reset_active_loop(token)
        assert "must be an array" in result["content"]

    @pytest.mark.asyncio
    async def test_verify_parallel_tasks_respects_max_parallel_sub_agents_cap(self):
        """Validate that at most MAX_PARALLEL_SUB_AGENTS run concurrently and all tasks eventually complete.

        Six tasks are submitted; the probe loop records active/peak/total
        counters. The test asserts total == 6 (no task is dropped), peak ==
        MAX_PARALLEL_SUB_AGENTS (the semaphore bounds concurrency exactly),
        and peak <= 4 (a defensive upper bound independent of the constant).
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
