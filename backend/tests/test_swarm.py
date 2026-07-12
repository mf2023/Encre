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

"""Tests for swarm subsystem: planner, consensus, blackboard, orchestrator, roles,
teammate, mailbox, swarm session."""

import asyncio

from encre.swarm.blackboard import BlackboardEntry, EncreBlackboard
from encre.swarm.consensus import EncreConsensus
from encre.swarm.mailbox import EncreMailbox, MailboxMessage
from encre.swarm.orchestrator import EncreOrchestrator, OrchestrationEvent
from encre.swarm.planner import EncreTaskPlanner, TaskTree, _detect_pattern
from encre.swarm.roles import (
    ROLE_ARCHITECT,
    ROLE_CODER,
    ROLE_DEBUGGER,
    ROLE_GENERAL,
    ROLE_RESEARCHER,
    ROLE_REVIEWER,
    ROLE_TESTER,
    AgentRole,
    RoleRegistry,
)
from encre.swarm.teammate import EncreTeammate, TeammateHandle

# ===========================================================================
# Mailbox
# ===========================================================================

class TestMailbox:
    """Test cases covering mailbox.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        mb = EncreMailbox(owner_id="agent1")
        # Confirm the expected result for this scenario: create.
        assert mb.owner_id == "agent1"

    async def test_send_receive(self):
        """Verifies that send receive."""
        mb_a = EncreMailbox(owner_id="a")
        mb_b = EncreMailbox(owner_id="b")
        await mb_a.send(mb_b, "hello")
        msg = await mb_b.receive(timeout=1.0)
        # Confirm the expected result for this scenario: send receive.
        assert msg is not None
        assert msg.content == "hello"
        assert msg.sender == "a"

    async def test_receive_timeout(self):
        """Verifies that receive timeout."""
        mb = EncreMailbox(owner_id="test", timeout=0.1)
        msg = await mb.receive(timeout=0.01)
        # Confirm the expected result for this scenario: receive timeout.
        assert msg is None

    async def test_multiple_messages_fifo(self):
        """Verifies that multiple messages fifo."""
        mb_a = EncreMailbox(owner_id="a")
        mb_b = EncreMailbox(owner_id="b")
        await mb_a.send(mb_b, "first")
        await mb_a.send(mb_b, "second")
        msg1 = await mb_b.receive(timeout=1.0)
        msg2 = await mb_b.receive(timeout=1.0)
        # Confirm the expected result for this scenario: multiple messages fifo.
        assert msg1.content == "first"
        assert msg2.content == "second"

    def test_mailbox_message(self):
        """Verifies that mailbox message."""
        msg = MailboxMessage(sender="a", content="test")
        # Confirm the expected result for this scenario: mailbox message.
        assert msg.sender == "a"
        assert msg.content == "test"
        assert msg.metadata == {}

    def test_peek(self):
        """Verifies that peek."""
        async def _test():
            """Verifies that test."""
            mb_a = EncreMailbox(owner_id="a")
            mb_b = EncreMailbox(owner_id="b")
            await mb_a.send(mb_b, "msg1")
            peeked = mb_b.peek()
            # Confirm the expected result for this scenario: peek.
            # Confirm the expected result for this scenario: test.
            assert len(peeked) == 1
            # Message still available after peek
            msg = await mb_b.receive(timeout=1.0)
            assert msg is not None
        asyncio.run(_test())

    def test_clear(self):
        """Verifies that clear."""
        async def _test():
            """Verifies that test."""
            mb_a = EncreMailbox(owner_id="a")
            mb_b = EncreMailbox(owner_id="b")
            await mb_a.send(mb_b, "msg1")
            mb_b.clear()
            msg = await mb_b.receive(timeout=0.1)
            # Confirm the expected result for this scenario: clear.
            # Confirm the expected result for this scenario: test.
            assert msg is None
        asyncio.run(_test())


# ===========================================================================
# Teammate
# ===========================================================================

class TestTeammate:
    """Test cases covering teammate.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create_teammate(self):
        """Verifies that create teammate."""
        tm = EncreTeammate(name="coder", task="write a function")
        # Confirm the expected result for this scenario: create teammate.
        assert tm.name == "coder"
        assert tm.task == "write a function"
        assert tm.mailbox is not None

    def test_teammate_handle(self):
        """Verifies that teammate handle."""
        handle = TeammateHandle(teammate_id="tm1", name="reviewer", status="pending")
        # Confirm the expected result for this scenario: teammate handle.
        assert handle.name == "reviewer"
        assert handle.status == "pending"


# ===========================================================================
# RoleRegistry & Roles
# ===========================================================================

class TestRoles:
    """Test cases covering roles.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_role_constants(self):
        """Verifies that role constants."""
        # Confirm the expected result for this scenario: role constants.
        assert ROLE_ARCHITECT.name == "architect"
        assert ROLE_CODER.name == "coder"
        assert ROLE_REVIEWER.name == "reviewer"
        assert ROLE_TESTER.name == "tester"
        assert ROLE_RESEARCHER.name == "researcher"
        assert ROLE_DEBUGGER.name == "debugger"
        assert ROLE_GENERAL.name == "general"

    def test_agent_role_creation(self):
        """Verifies that agent role creation."""
        role = AgentRole(name="custom", description="Custom role", allowed_tools=["bash"])
        # Confirm the expected result for this scenario: agent role creation.
        assert role.name == "custom"
        assert "bash" in role.allowed_tools

    def test_role_registry_register(self):
        """Verifies that role registry register."""
        registry = RoleRegistry()
        custom = AgentRole(name="custom_role", description="Custom")
        registry.register(custom)
        # Confirm the expected result for this scenario: role registry register.
        assert registry.get("custom_role").name == "custom_role"

    def test_role_registry_get_defaults_to_general(self):
        """Verifies that role registry get defaults to general."""
        registry = RoleRegistry()
        role = registry.get("nonexistent")
        # Confirm the expected result for this scenario: role registry get defaults to general.
        assert role.name == "general"

    def test_role_registry_list_roles(self):
        """Verifies that role registry list roles."""
        registry = RoleRegistry()
        roles = registry.list_roles()
        # Confirm the expected result for this scenario: role registry list roles.
        assert "architect" in roles
        assert "coder" in roles
        assert "general" in roles

    def test_role_registry_get_for_task(self):
        """Verifies that role registry get for task."""
        registry = RoleRegistry()
        # Confirm the expected result for this scenario: role registry get for task.
        assert registry.get_for_task("design the system").name == "architect"
        assert registry.get_for_task("implement the feature").name == "coder"
        assert registry.get_for_task("audit the system for security issues").name == "reviewer"
        assert registry.get_for_task("test the application").name == "tester"
        assert registry.get_for_task("research best practices").name == "researcher"
        assert registry.get_for_task("debug the null pointer").name == "debugger"
        assert registry.get_for_task("something else").name == "general"

    def test_role_to_dict(self):
        """Verifies that role to dict."""
        d = ROLE_CODER.to_dict()
        # Confirm the expected result for this scenario: role to dict.
        assert d["name"] == "coder"
        assert "description" in d


# ===========================================================================
# TaskPlanner
# ===========================================================================

class TestTaskPlanner:
    """Test cases covering task planner.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.planner = EncreTaskPlanner()

    def test_detect_pattern_build(self):
        """Verifies that detect pattern build."""
        # Confirm the expected result for this scenario: detect pattern build.
        assert _detect_pattern("build a web app") == "build"
        assert _detect_pattern("create an API") == "build"
        assert _detect_pattern("implement a cache layer") == "build"
        assert _detect_pattern("write a CLI tool") == "build"
        assert _detect_pattern("develop a mobile app") == "build"

    def test_detect_pattern_debug(self):
        """Verifies that detect pattern debug."""
        # Confirm the expected result for this scenario: detect pattern debug.
        assert _detect_pattern("debug the login flow") == "debug"
        assert _detect_pattern("fix a bug in auth") == "debug"

    def test_detect_pattern_research(self):
        """Verifies that detect pattern research."""
        # Confirm the expected result for this scenario: detect pattern research.
        assert _detect_pattern("research async patterns") == "research"
        assert _detect_pattern("investigate memory leak") == "research"

    def test_detect_pattern_refactor(self):
        """Verifies that detect pattern refactor."""
        # Confirm the expected result for this scenario: detect pattern refactor.
        assert _detect_pattern("refactor the database layer") == "refactor"
        assert _detect_pattern("clean up the utils module") == "refactor"

    def test_detect_pattern_none(self):
        """Verifies that detect pattern none."""
        # Confirm the expected result for this scenario: detect pattern none.
        assert _detect_pattern("hello world") is None

    def test_plan_build_pattern(self):
        """Verifies that plan build pattern."""
        tree = self.planner.plan("build a REST API")
        # Confirm the expected result for this scenario: plan build pattern.
        assert isinstance(tree, TaskTree)
        assert len(tree.nodes) == 5
        assert len(tree.entry_nodes) > 0
        assert len(tree.exit_nodes) > 0

    def test_plan_debug_pattern(self):
        """Verifies that plan debug pattern."""
        tree = self.planner.plan("fix the authentication bug")
        # Confirm the expected result for this scenario: plan debug pattern.
        assert len(tree.nodes) == 4

    def test_plan_research_pattern(self):
        """Verifies that plan research pattern."""
        tree = self.planner.plan("investigate database performance")
        # Confirm the expected result for this scenario: plan research pattern.
        assert len(tree.nodes) == 4

    def test_plan_refactor_pattern(self):
        """Verifies that plan refactor pattern."""
        tree = self.planner.plan("refactor the user service")
        # Confirm the expected result for this scenario: plan refactor pattern.
        assert len(tree.nodes) == 5

    def test_plan_unknown_falls_back_to_simple(self):
        """Verifies that plan unknown falls back to simple."""
        tree = self.planner.plan("do something unusual and uncategorized")
        # Confirm the expected result for this scenario: plan unknown falls back to simple.
        assert len(tree.nodes) == 1

    def test_task_tree_get_ready_nodes(self):
        """Verifies that task tree get ready nodes."""
        tree = self.planner.plan("build a CLI")
        ready = tree.get_ready_nodes()
        # Confirm the expected result for this scenario: task tree get ready nodes.
        assert len(ready) > 0
        for node in ready:
            assert node.status == "pending"
            assert node.dependencies == []

    def test_task_tree_all_done(self):
        """Verifies that task tree all done."""
        tree = self.planner.plan("fix a bug")
        for node in tree.nodes.values():
            node.status = "completed"
        # Confirm the expected result for this scenario: task tree all done.
        assert tree.all_done() is True

    def test_task_tree_has_failure(self):
        """Verifies that task tree has failure."""
        tree = self.planner.plan("fix a bug")
        first = next(iter(tree.nodes.values()))
        first.status = "failed"
        # Confirm the expected result for this scenario: task tree has failure.
        assert tree.has_failure() is True

    def test_plan_with_llm_returns_prompt(self):
        """Verifies that plan with llm returns prompt."""
        prompt = self.planner.plan_with_llm("build a chat app", "using FastAPI")
        # Confirm the expected result for this scenario: plan with llm returns prompt.
        assert "build a chat app" in prompt
        assert "FastAPI" in prompt

    def test_plan_from_json(self):
        """Verifies that plan from json."""
        import json
        data = {
            "tasks": [
                {"id": "t1", "name": "Design", "description": "architect", "role": "architect", "dependencies": [], "priority": 10},  # noqa: E501
                {"id": "t2", "name": "Code", "description": "implement", "role": "coder", "dependencies": ["t1"], "priority": 5},  # noqa: E501
            ],
            "entry_tasks": ["t1"],
            "exit_tasks": ["t2"],
        }
        tree = EncreTaskPlanner.plan_from_json("test goal", json.dumps(data))
        # Confirm the expected result for this scenario: plan from json.
        assert len(tree.nodes) == 2
        assert tree.entry_nodes == ["t1"]
        assert tree.exit_nodes == ["t2"]

    def test_decompose_async(self):
        """Verifies that decompose async."""
        async def _test():
            """Verifies that test."""
            tree = await self.planner.decompose("build a web app")
            # Confirm the expected result for this scenario: decompose async.
            # Confirm the expected result for this scenario: test.
            assert isinstance(tree, TaskTree)
            assert len(tree.nodes) > 0
        asyncio.run(_test())


# ===========================================================================
# Consensus
# ===========================================================================

class TestConsensus:
    """Test cases covering consensus.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.consensus = EncreConsensus()

    def test_create_proposal(self):
        """Verifies that create proposal."""
        p = self.consensus.create_proposal(
            title="Use FastAPI",
            description="Should we use FastAPI for the backend?",
            options=["yes", "no"],
            proposed_by="architect",
        )
        # Confirm the expected result for this scenario: create proposal.
        assert p.title == "Use FastAPI"
        assert len(p.options) == 2

    def test_cast_vote(self):
        """Verifies that cast vote."""
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        v = self.consensus.cast_vote(proposal_id=p.id, voter_id="coder1", choice="A", reasoning="Best option")  # noqa: E501
        # Confirm the expected result for this scenario: cast vote.
        assert v.choice == "A"

    def test_tally_unanimous(self):
        """Verifies that tally unanimous."""
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        self.consensus.cast_vote(p.id, "v1", "A")
        self.consensus.cast_vote(p.id, "v2", "A")
        self.consensus.cast_vote(p.id, "v3", "A")
        result = self.consensus.tally(p)
        # Confirm the expected result for this scenario: tally unanimous.
        assert result.winner == "A"
        assert result.is_consensus is True
        assert result.vote_counts["A"] == 3

    def test_tally_no_consensus(self):
        """Verifies that tally no consensus."""
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        self.consensus.cast_vote(p.id, "v1", "A")
        self.consensus.cast_vote(p.id, "v2", "B")
        result = self.consensus.tally(p)
        # Confirm the expected result for this scenario: tally no consensus.
        assert result.is_consensus is False

    def test_tally_empty(self):
        """Verifies that tally empty."""
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        result = self.consensus.tally(p)
        # Confirm the expected result for this scenario: tally empty.
        assert result.winner == "A"
        assert result.vote_counts["A"] == 0

    def test_proposal_to_dict(self):
        """Verifies that proposal to dict."""
        p = self.consensus.create_proposal("T", "D", ["X"], proposed_by="me")
        d = p.to_dict()
        # Confirm the expected result for this scenario: proposal to dict.
        assert d["title"] == "T"
        assert d["proposed_by"] == "me"


# ===========================================================================
# Blackboard
# ===========================================================================

class TestBlackboard:
    """Test cases covering blackboard.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.bb = EncreBlackboard()

    def test_put_get(self):
        """Verifies that put get."""
        self.bb.put("default", "key1", "value1", owner="agent1")
        result = self.bb.get("default", "key1")
        # Confirm the expected result for this scenario: put get.
        assert result is not None
        assert result[0] == "value1"

    def test_get_nonexistent(self):
        """Verifies that get nonexistent."""
        # Confirm the expected result for this scenario: get nonexistent.
        assert self.bb.get("default", "nonexistent") is None

    def test_get_all(self):
        """Verifies that get all."""
        self.bb.put("ns1", "k1", "v1", owner="a")
        self.bb.put("ns1", "k2", "v2", owner="a")
        all_data = self.bb.get_all("ns1")
        # Confirm the expected result for this scenario: get all.
        assert all_data["k1"] == "v1"
        assert all_data["k2"] == "v2"

    def test_get_all_visible(self):
        """Verifies that get all visible."""
        self.bb.put("public_ns", "key", "value")
        visible = self.bb.get_all_visible()
        # Confirm the expected result for this scenario: get all visible.
        assert "public_ns/key" in visible
        assert "value" in visible

    def test_delete(self):
        """Verifies that delete."""
        self.bb.put("default", "k1", "v1")
        # Confirm the expected result for this scenario: delete.
        assert self.bb.delete("default", "k1") is True
        assert self.bb.get("default", "k1") is None

    def test_delete_nonexistent(self):
        """Verifies that delete nonexistent."""
        # Confirm the expected result for this scenario: delete nonexistent.
        assert self.bb.delete("default", "nonexistent") is False

    def test_overwrite(self):
        """Verifies that overwrite."""
        self.bb.put("default", "k1", "v1")
        self.bb.put("default", "k1", "v2")
        result = self.bb.get("default", "k1")
        # Confirm the expected result for this scenario: overwrite.
        assert result[0] == "v2"

    def test_version_increment(self):
        """Verifies that version increment."""
        v1 = self.bb.put("default", "k1", "v1")
        v2 = self.bb.put("default", "k1", "v2")
        # Confirm the expected result for this scenario: version increment.
        assert v2 > v1

    def test_compare_and_swap(self):
        """Verifies that compare and swap."""
        v = self.bb.put("default", "k1", "v1")
        # Confirm the expected result for this scenario: compare and swap.
        assert self.bb.compare_and_swap("default", "k1", v, "v2") is True
        result = self.bb.get("default", "k1")
        assert result[0] == "v2"

    def test_compare_and_swap_wrong_version(self):
        """Verifies that compare and swap wrong version."""
        self.bb.put("default", "k1", "v1")
        # Confirm the expected result for this scenario: compare and swap wrong version.
        assert self.bb.compare_and_swap("default", "k1", 999, "v2") is False

    def test_blackboard_entry(self):
        """Verifies that blackboard entry."""
        entry = BlackboardEntry(key="test", value=42, version=1, namespace="ns1", owner="agent1")
        # Confirm the expected result for this scenario: blackboard entry.
        assert entry.key == "test"
        assert entry.value == 42
        assert entry.version == 1

    def test_reset(self):
        """Verifies that reset."""
        self.bb.put("default", "k1", "v1")
        self.bb.reset()
        # Confirm the expected result for this scenario: reset.
        assert self.bb.get("default", "k1") is None


# ===========================================================================
# Orchestrator
# ===========================================================================

class TestOrchestrator:
    """Test cases covering orchestrator.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        blackboard = EncreBlackboard()
        roles = RoleRegistry()
        roles.register(ROLE_GENERAL)
        orch = EncreOrchestrator(
            role_registry=roles,
            blackboard=blackboard,
            max_concurrent=3,
        )
        # Confirm the expected result for this scenario: create.
        assert orch is not None

    def test_orchestration_event(self):
        """Verifies that orchestration event."""
        event = OrchestrationEvent(type="task_completed", task_id="t1", task_name="Test", role="general")  # noqa: E501
        # Confirm the expected result for this scenario: orchestration event.
        assert event.type == "task_completed"
        assert event.task_id == "t1"
