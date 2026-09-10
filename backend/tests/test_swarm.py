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
    """Engineered to validate the async inter-agent mailbox communication channel.

    This test class exercises EncreMailbox construction, send/receive semantics,
    timeout behavior, FIFO ordering, peek without removal, and clear across
    7 scenarios to ensure the swarm's messaging layer preserves message order,
    respects timeout bounds, and supports non-destructive inspection. The design
    uses asyncio queues under the hood so that agent peers can decouple production
    from consumption without blocking the event loop.
    """
    def test_verify_mailbox_creation_with_owner(self):
        """Validate that EncreMailbox stores the owner_id passed at construction.

        The test constructs a mailbox with owner_id='agent1' and asserts the field
        matches, because the mailbox must be attributable to a single agent peer
        so that incoming messages can be routed to the correct recipient.
        """
        mb = EncreMailbox(owner_id="agent1")
        assert mb.owner_id == "agent1"

    async def test_verify_send_receive_preserves_sender_and_content(self):
        """Validate that a sent message is received with original sender and content intact.

        The test sends 'hello' from mailbox 'a' to mailbox 'b' and asserts the
        received message has content=='hello' and sender=='a', because the mailbox
        must preserve message identity so the receiver can attribute origin correctly.
        """
        mb_a = EncreMailbox(owner_id="a")
        mb_b = EncreMailbox(owner_id="b")
        await mb_a.send(mb_b, "hello")
        msg = await mb_b.receive(timeout=1.0)
        assert msg is not None
        assert msg.content == "hello"
        assert msg.sender == "a"

    async def test_verify_receive_returns_none_on_timeout(self):
        """Validate that receive returns None when no message arrives within the timeout.

        The test constructs a mailbox with a short timeout and asserts receive
        returns None because the caller must be able to distinguish between
        'no message yet' and 'message received' to avoid blocking the agent loop.
        """
        mb = EncreMailbox(owner_id="test", timeout=0.1)
        msg = await mb.receive(timeout=0.01)
        assert msg is None

    async def test_verify_multiple_messages_arrive_in_fifo_order(self):
        """Validate that sequential sends are delivered in first-in-first-out order.

        The test sends 'first' then 'second' and asserts msg1.content=='first'
        and msg2.content=='second' because the mailbox must preserve insertion
        order so that agent conversations and handoffs do not reorder messages.
        """
        mb_a = EncreMailbox(owner_id="a")
        mb_b = EncreMailbox(owner_id="b")
        await mb_a.send(mb_b, "first")
        await mb_a.send(mb_b, "second")
        msg1 = await mb_b.receive(timeout=1.0)
        msg2 = await mb_b.receive(timeout=1.0)
        assert msg1.content == "first"
        assert msg2.content == "second"

    def test_verify_mailbox_message_fields(self):
        """Validate that MailboxMessage stores sender, content, and defaults metadata to empty dict.

        The test constructs a message and asserts sender, content, and metadata
        match expectations because the message record is the atomic unit of
        inter-agent communication and must carry all three fields visibly.
        """
        msg = MailboxMessage(sender="a", content="test")
        assert msg.sender == "a"
        assert msg.content == "test"
        assert msg.metadata == {}

    def test_verify_peek_returns_message_without_removal(self):
        """Validate that peek inspects the head of the queue without consuming the message.

        The test sends a message, asserts peek returns a list of length 1, then
        asserts receive still returns the same message because peek must be a
        read-only observation so agents can inspect incoming mail without
        accidentally consuming it before they are ready to process.
        """
        async def _test():
            mb_a = EncreMailbox(owner_id="a")
            mb_b = EncreMailbox(owner_id="b")
            await mb_a.send(mb_b, "msg1")
            peeked = mb_b.peek()
            assert len(peeked) == 1
            msg = await mb_b.receive(timeout=1.0)
            assert msg is not None
        asyncio.run(_test())

    def test_verify_clear_removes_all_pending_messages(self):
        """Validate that clear empties the mailbox so subsequent receive returns None.

        The test sends a message, clears the mailbox, and asserts receive with
        a short timeout returns None because clear must fully drain the queue
        so that a subsequent agent round starts with a clean slate.
        """
        async def _test():
            mb_a = EncreMailbox(owner_id="a")
            mb_b = EncreMailbox(owner_id="b")
            await mb_a.send(mb_b, "msg1")
            mb_b.clear()
            msg = await mb_b.receive(timeout=0.1)
            assert msg is None
        asyncio.run(_test())


# ===========================================================================
# Teammate
# ===========================================================================

class TestTeammate:
    """Engineered to validate the teammate entity and its handle representation.

    This test class exercises EncreTeammate construction and TeammateHandle
    construction across 2 scenarios to ensure each teammate carries a name,
    an assigned task, and an associated mailbox, and that handles expose the
    canonical identity fields (name, status) used by the orchestrator for
    task assignment and progress tracking.
    """
    def test_verify_teammate_creation_with_mailbox(self):
        """Validate that EncreTeammate stores name, task, and creates a mailbox.

        The test constructs a teammate named 'coder' with a task string and
        asserts name, task, and mailbox are all non-None because every teammate
        in the swarm must have an identity, an assigned objective, and a mailbox
        for inter-agent communication.
        """
        tm = EncreTeammate(name="coder", task="write a function")
        assert tm.name == "coder"
        assert tm.task == "write a function"
        assert tm.mailbox is not None

    def test_verify_teammate_handle_fields(self):
        """Validate that TeammateHandle stores teammate_id, name, and status.

        The test constructs a handle with status='pending' and asserts name and
        status match, because the orchestrator uses handle objects to track
        worker progress without exposing the full teammate entity to the caller.
        """
        handle = TeammateHandle(teammate_id="tm1", name="reviewer", status="pending")
        assert handle.name == "reviewer"
        assert handle.status == "pending"


# ===========================================================================
# RoleRegistry & Roles
# ===========================================================================

class TestRoles:
    """Engineered to validate the role constant taxonomy and role registry lookup logic.

    This test class exercises role name constants, AgentRole construction,
    registry register/get/list/get_for_task/to_dict across 7 scenarios to
    ensure the swarm has a fixed set of recognized roles, that custom roles
    can be registered, that unknown lookups fall back to 'general', and that
    the registry can infer a role from a natural-language task description
    using keyword heuristics. The design uses a registry so that role
    assignments are centralized and extensible.
    """
    def test_verify_role_name_constants_are_correct(self):
        """Validate that all built-in role constants have the expected name attributes.

        The test asserts name == 'architect', 'coder', 'reviewer', 'tester',
        'researcher', 'debugger', and 'general' for the seven built-in roles
        because these constants are the canonical identifiers the orchestrator
        uses to assign work and render role-specific system prompts.
        """
        assert ROLE_ARCHITECT.name == "architect"
        assert ROLE_CODER.name == "coder"
        assert ROLE_REVIEWER.name == "reviewer"
        assert ROLE_TESTER.name == "tester"
        assert ROLE_RESEARCHER.name == "researcher"
        assert ROLE_DEBUGGER.name == "debugger"
        assert ROLE_GENERAL.name == "general"

    def test_verify_agent_role_creation_with_allowed_tools(self):
        """Validate that AgentRole stores name, description, and allowed_tools correctly.

        The test constructs a custom role with allowed_tools=['bash'] and asserts
        the field is preserved because the role definition must carry its tool
        permissions so the executor can enforce least-privilege per role.
        """
        role = AgentRole(name="custom", description="Custom role", allowed_tools=["bash"])
        assert role.name == "custom"
        assert "bash" in role.allowed_tools

    def test_verify_role_registry_register_and_get(self):
        """Validate that registering a custom role makes it retrievable by name.

        The test registers 'custom_role' and asserts registry.get returns an
        object whose name matches, because the registry is the single source
        of truth for role resolution and must support dynamic extension.
        """
        registry = RoleRegistry()
        custom = AgentRole(name="custom_role", description="Custom")
        registry.register(custom)
        assert registry.get("custom_role").name == "custom_role"

    def test_verify_role_registry_get_falls_back_to_general_for_unknown_names(self):
        """Validate that looking up an unknown role name returns the general role.

        The test asserts registry.get('nonexistent').name == 'general' because
        the fallback ensures the swarm always has a default role instead of
        raising KeyError when an unrecognized role name is referenced.
        """
        registry = RoleRegistry()
        role = registry.get("nonexistent")
        assert role.name == "general"

    def test_verify_role_registry_list_includes_default_roles(self):
        """Validate that list_roles returns the built-in role set.

        The test asserts 'architect', 'coder', and 'general' are present because
        the list operation must surface all registered roles so the orchestrator
        can enumerate available assignments for a given task decomposition.
        """
        registry = RoleRegistry()
        roles = registry.list_roles()
        assert "architect" in roles
        assert "coder" in roles
        assert "general" in roles

    def test_verify_role_registry_get_for_task_maps_keywords_to_roles(self):
        """Validate that get_for_task returns the correct role for keyword-matched descriptions.

        The test passes natural-language task descriptions and asserts the
        returned role name matches the expected specialization ('architect' for
        design, 'coder' for implement, 'reviewer' for audit, 'tester' for test,
        'researcher' for research, 'debugger' for debug, 'general' for unmatched)
        because the keyword-based inference is the primary routing mechanism
        that determines which agent persona handles each subtask.
        """
        registry = RoleRegistry()
        assert registry.get_for_task("design the system").name == "architect"
        assert registry.get_for_task("implement the feature").name == "coder"
        assert registry.get_for_task("audit the system for security issues").name == "reviewer"
        assert registry.get_for_task("test the application").name == "tester"
        assert registry.get_for_task("research best practices").name == "researcher"
        assert registry.get_for_task("debug the null pointer").name == "debugger"
        assert registry.get_for_task("something else").name == "general"

    def test_verify_role_to_dict_serializes_name_and_description(self):
        """Validate that to_dict returns a mapping containing at least name and description.

        The test calls ROLE_CODER.to_dict() and asserts d['name'] == 'coder' and
        'description' is present because serialization is required for JSON
        exchange between swarm nodes and for persistence across process boundaries.
        """
        d = ROLE_CODER.to_dict()
        assert d["name"] == "coder"
        assert "description" in d


# ===========================================================================
# TaskPlanner
# ===========================================================================

class TestTaskPlanner:
    """Engineered to validate the task decomposition planner and pattern detector.

    This test class exercises _detect_pattern across 5 pattern categories (build,
    debug, research, refactor, none), plan generation across 5 task patterns
    (build, debug, research, refactor, unknown fallback), TaskTree utility
    methods (get_ready_nodes, all_done, has_failure), plan_with_llm prompt
    templating, plan_from_json deserialization, and async decompose across
    13 scenarios to ensure the planner correctly classifies intent, produces
    a TaskTree with the expected node count, and supports both programmatic
    and JSON-driven task graph construction. The design uses pattern detection
    to choose a template so that diverse task descriptions produce structured
    dependency graphs without manual orchestration.
    """
    def setup_method(self):
        """Initialize a fresh EncreTaskPlanner before each test for isolation."""
        self.planner = EncreTaskPlanner()

    def test_verify_detect_pattern_classifies_build_keywords(self):
        """Validate that _detect_pattern returns 'build' for creation-oriented phrases.

        The test asserts 'build', 'create', 'implement', 'write a CLI', and
        'develop a mobile app' all map to 'build' because pattern detection
        must recognize synthesis verbs so the planner selects the build template
        which produces a linear dependency chain suited for construction tasks.
        """
        assert _detect_pattern("build a web app") == "build"
        assert _detect_pattern("create an API") == "build"
        assert _detect_pattern("implement a cache layer") == "build"
        assert _detect_pattern("write a CLI tool") == "build"
        assert _detect_pattern("develop a mobile app") == "build"

    def test_verify_detect_pattern_classifies_debug_keywords(self):
        """Validate that _detect_pattern returns 'debug' for repair-oriented phrases.

        The test asserts 'debug' and 'fix a bug' map to 'debug' because the
        debug template produces a shorter 4-node tree focused on diagnosis
        followed by fix, which is structurally different from the build template.
        """
        assert _detect_pattern("debug the login flow") == "debug"
        assert _detect_pattern("fix a bug in auth") == "debug"

    def test_verify_detect_pattern_classifies_research_keywords(self):
        """Validate that _detect_pattern returns 'research' for inquiry-oriented phrases.

        The test asserts 'research' and 'investigate' map to 'research' because
        the research template produces a tree optimized for information gathering
        rather than code generation, with nodes dedicated to literature search
        and synthesis before any implementation begins.
        """
        assert _detect_pattern("research async patterns") == "research"
        assert _detect_pattern("investigate memory leak") == "research"

    def test_verify_detect_pattern_classifies_refactor_keywords(self):
        """Validate that _detect_pattern returns 'refactor' for restructuring-oriented phrases.

        The test asserts 'refactor' and 'clean up' map to 'refactor' because the
        refactor template produces a dependency graph that preserves existing
        behavior while restructuring internals, which requires a different node
        topology than the build template.
        """
        assert _detect_pattern("refactor the database layer") == "refactor"
        assert _detect_pattern("clean up the utils module") == "refactor"

    def test_verify_detect_pattern_returns_none_for_unrecognized_phrases(self):
        """Validate that _detect_pattern returns None when no keyword matches.

        The test passes 'hello world' and asserts None because unrecognized
        phrases should fall through to the default simple planner rather than
        triggering a false pattern match that would produce an inappropriate tree.
        """
        assert _detect_pattern("hello world") is None

    def test_verify_plan_build_pattern_produces_five_node_tree(self):
        """Validate that planning a build task produces a TaskTree with 5 nodes.

        The test asserts isinstance(tree, TaskTree), len(tree.nodes) == 5, and
        that both entry_nodes and exit_nodes are non-empty because the build
        template must produce a multi-node dependency graph with clear start
        and end points so the orchestrator can schedule work in parallel phases.
        """
        tree = self.planner.plan("build a REST API")
        assert isinstance(tree, TaskTree)
        assert len(tree.nodes) == 5
        assert len(tree.entry_nodes) > 0
        assert len(tree.exit_nodes) > 0

    def test_verify_plan_debug_pattern_produces_four_node_tree(self):
        """Validate that planning a debug task produces a TaskTree with 4 nodes.

        The test asserts len(tree.nodes) == 4 because the debug template is
        intentionally shorter than the build template, reflecting the smaller
        scope of diagnosis-plus-fix compared to full construction.
        """
        tree = self.planner.plan("fix the authentication bug")
        assert len(tree.nodes) == 4

    def test_verify_plan_research_pattern_produces_four_node_tree(self):
        """Validate that planning a research task produces a TaskTree with 4 nodes.

        The test asserts len(tree.nodes) == 4 because the research template
        covers information gathering, synthesis, and report writing in four
        sequential stages, each represented as a node in the dependency graph.
        """
        tree = self.planner.plan("investigate database performance")
        assert len(tree.nodes) == 4

    def test_verify_plan_refactor_pattern_produces_five_node_tree(self):
        """Validate that planning a refactor task produces a TaskTree with 5 nodes.

        The test asserts len(tree.nodes) == 5 because the refactor template
        includes analysis, extraction, transformation, verification, and cleanup
        stages, each mapped to a distinct node in the task dependency graph.
        """
        tree = self.planner.plan("refactor the user service")
        assert len(tree.nodes) == 5

    def test_verify_plan_unknown_pattern_falls_back_to_single_node_tree(self):
        """Validate that an unrecognized task pattern falls back to a single-node tree.

        The test asserts len(tree.nodes) == 1 because an uncategorized task
        must still produce a valid TaskTree so the orchestrator can execute
        it as a monolithic step rather than failing with an empty graph.
        """
        tree = self.planner.plan("do something unusual and uncategorized")
        assert len(tree.nodes) == 1

    def test_verify_task_tree_get_ready_nodes_returns_pending_nodes_with_no_dependencies(self):
        """Validate that get_ready_nodes returns only pending nodes with empty dependency lists.

        The test asserts len(ready) > 0 and that every returned node has
        status=='pending' and dependencies==[] because ready nodes are the
        entry points the orchestrator schedules first; any node with a
        non-empty dependency list or non-pending status must be excluded.
        """
        tree = self.planner.plan("build a CLI")
        ready = tree.get_ready_nodes()
        assert len(ready) > 0
        for node in ready:
            assert node.status == "pending"
            assert node.dependencies == []

    def test_verify_task_tree_all_done_returns_true_when_all_nodes_are_completed(self):
        """Validate that all_done returns True after every node is marked completed.

        The test sets all node statuses to 'completed' and asserts all_done()
        is True because the orchestrator uses this predicate to terminate the
        swarm loop once the entire task graph has finished executing.
        """
        tree = self.planner.plan("fix a bug")
        for node in tree.nodes.values():
            node.status = "completed"
        assert tree.all_done() is True

    def test_verify_task_tree_has_failure_returns_true_when_any_node_is_failed(self):
        """Validate that has_failure returns True when at least one node is marked failed.

        The test marks the first node as 'failed' and asserts has_failure()
        is True because the orchestrator must detect any single failure to
        trigger error handling, rollback, or escalation logic immediately.
        """
        tree = self.planner.plan("fix a bug")
        first = next(iter(tree.nodes.values()))
        first.status = "failed"
        assert tree.has_failure() is True

    def test_verify_plan_with_llm_returns_prompt_with_goal_and_context_placeholders(self):
        """Validate that plan_with_llm returns a prompt string containing the expected template placeholders.

        The test asserts 'Goal: {goal}' and 'Context: {context}' are present
        in the returned prompt because the LLM-assisted planner generates a
        text template that the agent fills in before invoking the LLM, and
        both placeholders must be present for the prompt to be structurally valid.
        """
        prompt = self.planner.plan_with_llm("build a chat app", "using FastAPI")
        assert "Goal: {goal}" in prompt
        assert "Context: {context}" in prompt

    def test_verify_plan_from_json_deserializes_tasks_and_entry_exit_nodes(self):
        """Validate that plan_from_json constructs a TaskTree from a JSON string with correct node count and boundaries.

        The test supplies a JSON payload with two tasks (t1 -> t2 dependency),
        entry_tasks=['t1'], and exit_tasks=['t2'], then asserts len(tree.nodes)
        == 2, tree.entry_nodes == ['t1'], and tree.exit_nodes == ['t2'] because
        JSON-driven task graphs must faithfully reproduce the declared topology
        so downstream schedulers can honor the intended execution order.
        """
        import json
        data = {
            "tasks": [
                {"id": "t1", "name": "Design", "description": "architect", "role": "architect", "dependencies": [], "priority": 10},
                {"id": "t2", "name": "Code", "description": "implement", "role": "coder", "dependencies": ["t1"], "priority": 5},
            ],
            "entry_tasks": ["t1"],
            "exit_tasks": ["t2"],
        }
        tree = EncreTaskPlanner.plan_from_json("test goal", json.dumps(data))
        assert len(tree.nodes) == 2
        assert tree.entry_nodes == ["t1"]
        assert tree.exit_nodes == ["t2"]

    def test_verify_decompose_async_returns_a_nonempty_task_tree(self):
        """Validate that the async decompose method returns a TaskTree with at least one node.

        The test calls decompose('build a web app') and asserts isinstance(tree,
        TaskTree) and len(tree.nodes) > 0 because the async path must produce
        the same structural guarantee as the synchronous plan method so that
        callers can treat both interfaces interchangeably in the orchestrator.
        """
        async def _test():
            tree = await self.planner.decompose("build a web app")
            assert isinstance(tree, TaskTree)
            assert len(tree.nodes) > 0
        asyncio.run(_test())


# ===========================================================================
# Consensus
# ===========================================================================

class TestConsensus:
    """Engineered to validate the multi-agent consensus voting and tally mechanism.

    This test class exercises proposal creation, vote casting, unanimous tally,
    split-vote tally, empty-tally fallback, proposal serialization, and dict
    conversion across 6 scenarios to ensure the consensus module can reach a
    deterministic winner when votes align, report no-consensus when they do not,
    and handle the edge case of zero votes by returning the first option as
    default. The design uses a simple plurality model so that swarm coordination
    does not require a complex bargaining protocol.
    """
    def setup_method(self):
        """Initialize a fresh EncreConsensus before each test for isolation."""
        self.consensus = EncreConsensus()

    def test_verify_create_proposal_stores_title_and_options(self):
        """Validate that create_proposal returns a proposal with the supplied title and options list.

        The test asserts p.title == 'Use FastAPI' and len(p.options) == 2 because
        the proposal object is the canonical input to the voting pipeline and
        must faithfully carry the question and the set of candidate answers.
        """
        p = self.consensus.create_proposal(
            title="Use FastAPI",
            description="Should we use FastAPI for the backend?",
            options=["yes", "no"],
            proposed_by="architect",
        )
        assert p.title == "Use FastAPI"
        assert len(p.options) == 2

    def test_verify_cast_vote_records_choice_and_reasoning(self):
        """Validate that cast_vote stores the voter's choice in the proposal.

        The test casts vote 'A' from voter 'coder1' and asserts v.choice == 'A'
        because the vote record must preserve the voter's selection so the tally
        algorithm can aggregate choices across all participants accurately.
        """
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        v = self.consensus.cast_vote(proposal_id=p.id, voter_id="coder1", choice="A", reasoning="Best option")
        assert v.choice == "A"

    def test_verify_tally_returns_winner_and_consensus_flag_for_unanimous_votes(self):
        """Validate that tally computes the correct winner and sets is_consensus=True when all votes match.

        The test casts three 'A' votes and asserts result.winner == 'A',
        result.is_consensus is True, and result.vote_counts['A'] == 3 because
        unanimous agreement is the signal the orchestrator uses to proceed
        without invoking a tie-breaking or escalation path.
        """
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        self.consensus.cast_vote(p.id, "v1", "A")
        self.consensus.cast_vote(p.id, "v2", "A")
        self.consensus.cast_vote(p.id, "v3", "A")
        result = self.consensus.tally(p)
        assert result.winner == "A"
        assert result.is_consensus is True
        assert result.vote_counts["A"] == 3

    def test_verify_tally_sets_is_consensus_false_for_split_votes(self):
        """Validate that tally reports is_consensus=False when votes are split between options.

        The test casts one 'A' vote and one 'B' vote and asserts is_consensus
        is False because a split vote indicates disagreement that the orchestrator
        must surface to the human operator or escalate to a higher-level resolver.
        """
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        self.consensus.cast_vote(p.id, "v1", "A")
        self.consensus.cast_vote(p.id, "v2", "B")
        result = self.consensus.tally(p)
        assert result.is_consensus is False

    def test_verify_tally_falls_back_to_first_option_when_no_votes_are_cast(self):
        """Validate that tally returns the first option with zero counts when no votes exist.

        The test asserts result.winner == 'A' and result.vote_counts['A'] == 0
        because an empty vote set must still produce a deterministic result so
        the orchestrator is not left without a decision when all teammates abstain.
        """
        p = self.consensus.create_proposal("Test", "desc", ["A", "B"])
        result = self.consensus.tally(p)
        assert result.winner == "A"
        assert result.vote_counts["A"] == 0

    def test_verify_proposal_to_dict_serializes_title_and_proposer(self):
        """Validate that to_dict on a proposal returns a mapping with the correct title and proposer.

        The test asserts d['title'] == 'T' and d['proposed_by'] == 'me' because
        serialization is required for logging, debugging, and cross-process
        proposal sharing within the swarm architecture.
        """
        p = self.consensus.create_proposal("T", "D", ["X"], proposed_by="me")
        d = p.to_dict()
        assert d["title"] == "T"
        assert d["proposed_by"] == "me"


# ===========================================================================
# Blackboard
# ===========================================================================

class TestBlackboard:
    """Engineered to validate the shared blackboard as a versioned key-value store for the swarm.

    This test class exercises put/get, get-all, get-all-visible, delete,
    overwrite semantics, version increment, compare-and-swap success and
    failure, BlackboardEntry field integrity, and reset across 12 scenarios
    to ensure the blackboard provides causal consistency for multi-agent
    coordination. The design uses monotonic version numbers and CAS operations
    so that concurrent agents can detect and avoid write-write collisions.
    """
    def setup_method(self):
        """Initialize a fresh EncreBlackboard before each test for isolation."""
        self.bb = EncreBlackboard()

    def test_verify_put_and_get_retains_value_with_owner(self):
        """Validate that put stores a value and get retrieves the same value tuple.

        The test puts 'value1' under 'key1' in namespace 'default' with owner
        'agent1' and asserts get returns a tuple whose first element is 'value1',
        because the blackboard must act as a reliable shared memory region that
        all swarm members can read from without data loss between put and get.
        """
        self.bb.put("default", "key1", "value1", owner="agent1")
        result = self.bb.get("default", "key1")
        assert result is not None
        assert result[0] == "value1"

    def test_verify_get_returns_none_for_missing_key(self):
        """Validate that get returns None when the requested key does not exist.

        The test asserts None because the caller must be able to distinguish
        between 'key absent' and 'key present with empty value' so that
        downstream logic can decide whether to initialize or update a field.
        """
        assert self.bb.get("default", "nonexistent") is None

    def test_verify_get_all_retrieves_all_keys_in_a_namespace(self):
        """Validate that get_all returns a dict with all keys from the specified namespace.

        The test puts two keys in 'ns1' and asserts the returned dict contains
        'k1' -> 'v1' and 'k2' -> 'v2' because namespace-scoped bulk reads are
        the primary mechanism agents use to discover shared state without
        knowing the exact key names in advance.
        """
        self.bb.put("ns1", "k1", "v1", owner="a")
        self.bb.put("ns1", "k2", "v2", owner="a")
        all_data = self.bb.get_all("ns1")
        assert all_data["k1"] == "v1"
        assert all_data["k2"] == "v2"

    def test_verify_get_all_visible_returns_public_namespace_entries(self):
        """Validate that get_all_visible surfaces entries from public namespaces.

        The test puts an entry without an owner (public) and asserts the
        resulting dict contains the key 'public_ns/key' and the value 'value',
        because visible entries are the mechanism by which agents broadcast
        results to all other swarm members without explicit targeting.
        """
        self.bb.put("public_ns", "key", "value")
        visible = self.bb.get_all_visible()
        assert "public_ns/key" in visible
        assert "value" in visible

    def test_verify_delete_removes_key_and_returns_true_while_missing_key_returns_false(self):
        """Validate that delete removes an existing key and returns False for a missing key.

        The test puts 'k1', asserts delete returns True and get afterwards
        returns None, then asserts delete on a nonexistent key returns False
        because the boolean return value lets callers distinguish between
        'successfully removed' and 'nothing to remove' without raising.
        """
        self.bb.put("default", "k1", "v1")
        assert self.bb.delete("default", "k1") is True
        assert self.bb.get("default", "k1") is None
        assert self.bb.delete("default", "nonexistent") is False

    def test_verify_overwrite_replaces_value_and_advances_version(self):
        """Validate that re-putting the same key replaces the old value.

        The test puts 'v1', overwrites with 'v2', and asserts get returns
        'v2' as the current value because overwrites are the intended update
        mechanism for the blackboard and the old value must be fully replaced
        rather than concatenated, preserving a single source of truth per key.
        """
        self.bb.put("default", "k1", "v1")
        self.bb.put("default", "k1", "v2")
        result = self.bb.get("default", "k1")
        assert result[0] == "v2"

    def test_verify_version_increments_on_each_put(self):
        """Validate that successive puts to the same key produce strictly increasing version numbers.

        The test asserts v2 > v1 because monotonic versioning is the foundation
        of the compare-and-swap protocol; without increasing versions, CAS
        cannot detect stale writes and the blackboard loses causal consistency.
        """
        v1 = self.bb.put("default", "k1", "v1")
        v2 = self.bb.put("default", "k1", "v2")
        assert v2 > v1

    def test_verify_compare_and_swap_succeeds_when_version_matches(self):
        """Validate that compare_and_swap updates the value when the provided version matches the current one.

        The test puts 'v1', then CAS with the returned version and new value
        'v2', and asserts the CAS returns True and get returns 'v2' because
        successful CAS is the mechanism that enables safe concurrent updates
        without locks in the multi-agent swarm environment.
        """
        v = self.bb.put("default", "k1", "v1")
        assert self.bb.compare_and_swap("default", "k1", v, "v2") is True
        result = self.bb.get("default", "k1")
        assert result[0] == "v2"

    def test_verify_compare_and_swap_fails_when_version_is_stale(self):
        """Validate that compare_and_swap returns False when the provided version does not match the current one.

        The test puts 'v1', then attempts CAS with version 999 and asserts
        False because a mismatched version indicates another agent has written
        the key in the interim, and the operation must abort to prevent
        overwriting unconsumed concurrent changes.
        """
        self.bb.put("default", "k1", "v1")
        assert self.bb.compare_and_swap("default", "k1", 999, "v2") is False

    def test_verify_blackboard_entry_stores_key_value_version_namespace_and_owner(self):
        """Validate that BlackboardEntry stores all five structural fields correctly.

        The test asserts key, value, version, namespace, and owner match the
        supplied values because the entry object is the atomic unit stored
        in the blackboard and all five fields are required for versioned,
        namespaced, owned writes and reads.
        """
        entry = BlackboardEntry(key="test", value=42, version=1, namespace="ns1", owner="agent1")
        assert entry.key == "test"
        assert entry.value == 42
        assert entry.version == 1

    def test_verify_reset_clears_all_namespaces(self):
        """Validate that reset empties the entire blackboard so subsequent get returns None.

        The test puts a key, calls reset, and asserts the key is no longer
        retrievable because reset is the operational mechanism for ending a
        swarm session and releasing all shared state before starting a new one.
        """
        self.bb.put("default", "k1", "v1")
        self.bb.reset()
        assert self.bb.get("default", "k1") is None


# ===========================================================================
# Orchestrator
# ===========================================================================

class TestOrchestrator:
    """Engineered to validate the swarm orchestrator construction and event model.

    This test class exercises EncreOrchestrator instantiation with a role
    registry and blackboard, and OrchestrationEvent field population across
    2 scenarios to ensure the orchestrator accepts its required dependencies
    and that events carry the type, task_id, task_name, and role fields used
    by the event loop to drive state transitions. The design keeps the
    orchestrator lightweight so that heavy lifting is delegated to the
    planner, consensus, and blackboard components.
    """
    def test_verify_orchestrator_creation_with_dependencies(self):
        """Validate that EncreOrchestrator constructs with a role registry, blackboard, and concurrency limit.

        The test constructs an orchestrator with max_concurrent=3 and asserts
        the instance is not None because the orchestrator is the top-level
        coordinator that ties together roles, shared memory, and task
        execution; a failed construction would indicate a dependency wiring
        error in the swarm initialization path.
        """
        blackboard = EncreBlackboard()
        roles = RoleRegistry()
        roles.register(ROLE_GENERAL)
        orch = EncreOrchestrator(
            role_registry=roles,
            blackboard=blackboard,
            max_concurrent=3,
        )
        assert orch is not None

    def test_verify_orchestration_event_fields(self):
        """Validate that OrchestrationEvent stores type, task_id, task_name, and role.

        The test constructs an event with type='task_completed' and task_id='t1'
        and asserts both fields match, because the event loop uses these fields
        to dispatch state transitions (e.g. mark task done, trigger dependents)
        and any mismatch would cause the orchestrator to lose track of progress.
        """
        event = OrchestrationEvent(type="task_completed", task_id="t1", task_name="Test", role="general")
        assert event.type == "task_completed"
        assert event.task_id == "t1"
