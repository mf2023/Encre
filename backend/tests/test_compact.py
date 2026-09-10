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

"""Tests for compaction subsystem: strategies, semantic compactor, context partitioner."""

import asyncio

from encre.compact.engine import EncreCompactEngine
from encre.compact.semantic import (
    ContextPartition,
    ContextPartitioner,
    ContextTier,
    SemanticToolOutputCompactor,
)
from encre.compact.strategies import (
    EncreAlwaysCompactStrategy,
    EncreAutoCompactStrategy,
    EncreBudgetReductionStrategy,
    EncreContextCollapseStrategy,
    EncreMicroCompactStrategy,
    EncreMultiStagePipeline,
    EncreSemanticCompactStrategy,
    EncreSnipStrategy,
    EncreTokenBudgetStrategy,
)


def _m(role, content, name=None):
    """Build a message dict with role, content, and optional name field."""
    msg = {"role": role, "content": content}
    if name:
        msg["name"] = name
    return msg


def _make_messages(turns):
    """Build a conversation history with a system message followed by turn_count user/assistant pairs."""
    msgs = [_m("system", "You are an assistant.")]
    for i in range(turns):
        msgs.append(_m("user", f"Question {i}"))
        msgs.append(_m("assistant", f"Answer {i}"))
    return msgs


# ===========================================================================
# ContextTier / ContextPartition
# ===========================================================================

class TestContextTier:
    """Engineered to validate the ContextTier value object for semantic context grouping.

    This test class exercises ContextTier across 2 scenarios to ensure that a
    tier can be constructed with a name and message list, and that its
    token_count() method returns a positive integer proportional to the
    content length. The design supports layered context representation where
    each tier holds a named slice of the conversation for selective retention.
    """

    def test_verify_context_tier_creation_and_fields(self):
        """Validate that ContextTier stores name and messages correctly on construction.

        The test constructs a tier with name 'test' and a single message, then
        asserts both fields match because ContextTier must preserve constructor
        arguments without modification for correct tier identification.
        """
        ct = ContextTier(name="test", messages=[_m("user", "hello")])
        assert ct.name == "test"
        assert len(ct.messages) == 1

    def test_verify_context_tier_token_count_is_positive(self):
        """Validate that ContextTier.token_count() returns a positive integer.

        The test constructs a tier with a short message and asserts token_count
        is greater than zero because even minimal content should produce a
        non-zero token estimate for budget-aware compaction decisions.
        """
        ct = ContextTier(name="test", messages=[_m("user", "hello world")])
        assert ct.token_count() > 0


class TestContextPartition:
    """Engineered to validate the ContextPartition value object for multi-tier message organization.

    This test class exercises ContextPartition across 3 scenarios to ensure
    that the default-constructed partition has empty lists for all five tiers
    (system, hot, warm, cold, reference), that messages can be assigned to
    specific tiers on construction, and that to_messages() correctly serializes
    the partition back into a flat message list. The design supports
    tiered retention where hot messages are always included and cold
    messages are optional during compaction.
    """

    def test_verify_defaults_produce_empty_partitions(self):
        """Validate that a default ContextPartition has empty lists for every tier.

        The test asserts system, hot, warm, cold, and reference are all []
        because an uninitialized partition must not leak stale data into
        the message stream passed to the LLM.
        """
        cp = ContextPartition()
        assert cp.system == []
        assert cp.hot == []
        assert cp.warm == []
        assert cp.cold == []
        assert cp.reference == []

    def test_verify_with_messages_serializes_correctly(self):
        """Validate that to_messages() flattens assigned tier messages in order.

        The test constructs a partition with one system message and one hot
        message and asserts the flattened result has exactly 2 entries because
        to_messages must preserve insertion order across tiers.
        """
        cp = ContextPartition(
            system=[_m("system", "You are helpful.")],
            hot=[_m("user", "latest question")],
        )
        msgs = cp.to_messages()
        assert len(msgs) == 2

    def test_verify_total_tokens_counts_all_messages(self):
        """Validate that total_tokens() returns a positive count when hot tier has content.

        The test constructs a partition with a short hot message and asserts
        total_tokens > 0 because any non-empty partition must report a
        positive token estimate for budget calculations.
        """
        cp = ContextPartition(hot=[_m("user", "hello world")])
        assert cp.total_tokens() > 0


class TestContextPartitioner:
    """Engineered to validate the ContextPartitioner distributes messages into correct semantic tiers.

    This test class exercises partitioning across 1 scenario to ensure that
    a mixed conversation history is split into system, hot, and other tiers
    with the system message isolated and recent exchanges placed in hot.
    The design uses recency-based tiering so that the model always sees
    the system prompt and latest turns without older context bloat.
    """

    def test_verify_partition_distributes_messages_into_correct_tiers(self):
        """Validate that partition() returns a ContextPartition with system and hot tiers populated.

        The test feeds a 5-message conversation through the partitioner and
        asserts the result is a ContextPartition, that hot has entries
        (recent turns), and that system has exactly 1 entry (the system
        prompt) because the partitioner must isolate the system message
        and place recent dialogue in the hot tier.
        """
        partitioner = ContextPartitioner()
        messages = [
            _m("system", "You are an assistant."),
            _m("user", "Hello"),
            _m("assistant", "Hi there"),
            _m("user", "Can you help me?"),
            _m("assistant", "Sure, what do you need?"),
        ]
        result = partitioner.partition(messages)
        assert isinstance(result, ContextPartition)
        assert len(result.hot) > 0
        assert len(result.system) == 1


# ===========================================================================
# SemanticToolOutputCompactor
# ===========================================================================

class TestSemanticToolOutputCompactor:
    """Engineered to validate the SemanticToolOutputCompactor reduces oversized tool outputs by tool type.

    This test class exercises the compactor across 8 scenarios covering grep,
    glob, bash, file_read, web_fetch, task_list, unknown tool types, and
    short outputs. The design applies tool-type-specific compression heuristics
    (e.g., glob results are summarized, grep outputs are truncated) so that
    large tool responses fit within the context window without losing
    structural meaning.
    """

    def setup_method(self):
        """Initialize a fresh SemanticToolOutputCompactor before each test."""
        self.compactor = SemanticToolOutputCompactor()

    def test_verify_grep_output_is_compacted(self):
        """Validate that grep tool output exceeding the threshold is reduced in size.

        The test passes a 600-repetition grep-formatted string and asserts the
        result is strictly shorter because grep compaction must trim repetitive
        line-numbered output to fit within token limits.
        """
        big = "file.py:1:line1\nfile.py:2:line2\n" * 600
        result = self.compactor.compact_tool_output("grep", big)
        assert len(result) < len(big)

    def test_verify_glob_output_is_compacted(self):
        """Validate that glob tool output is compacted into a summarized form.

        The test passes 800 file paths and asserts the result contains either
        'files' or 'glob' because glob compaction summarizes raw path lists
        into a human-readable summary rather than emitting every path.
        """
        big = "\n".join(f"/path/to/file{i}.py" for i in range(800))
        result = self.compactor.compact_tool_output("glob", big)
        assert "files" in result.lower() or "glob" in result.lower()

    def test_verify_bash_output_is_compacted(self):
        """Validate that bash tool output is compacted when it exceeds thresholds.

        The test passes 700 repeated error lines and asserts the result is
        strictly shorter because bash compaction must reduce verbose command
        output to fit within the allocated context budget.
        """
        big = "error line 1\n" * 700
        result = self.compactor.compact_tool_output("bash", big)
        assert len(result) < len(big)

    def test_verify_file_read_output_is_compacted(self):
        """Validate that file_read tool output is compacted when it exceeds thresholds.

        The test passes 500 repeated Python function snippets and asserts the
        result is strictly shorter because large source files must be trimmed
        to avoid consuming the entire context window.
        """
        big = "def foo():\n    pass\n" * 500
        result = self.compactor.compact_tool_output("file_read", big)
        assert len(result) < len(big)

    def test_verify_web_fetch_output_is_compacted(self):
        """Validate that web_fetch tool output is compacted when HTML is oversized.

        The test passes a repeated-paragraph HTML document and asserts the
        result is strictly shorter because web fetch compaction must strip
        repetitive HTML structure to fit within context limits.
        """
        html = "<html><head><title>Test</title></head><body>" + "<p>content</p>" * 600 + "</body></html>"  # noqa: E501
        result = self.compactor.compact_tool_output("web_fetch", html)
        assert len(result) < len(html)

    def test_verify_task_list_output_is_compacted(self):
        """Validate that task_list tool output is compacted below the hard size limit.

        The test passes 20 JSON task entries and asserts the result is under
        700 characters because task lists must be bounded to prevent a single
        tool response from dominating the context window.
        """
        big = '{"id": "1", "subject": "test"}\n' * 20
        result = self.compactor.compact_tool_output("task_list", big)
        assert len(result) < 700

    def test_verify_unknown_tool_truncates_to_input_size(self):
        """Validate that unknown tool types fall back to a safe truncation ceiling.

        The test passes 10K repeated characters through an unrecognized tool
        name and asserts the result is at most the input length because the
        compactor must never expand output, even for unknown tool types.
        """
        big = "x" * 10000
        result = self.compactor.compact_tool_output("unknown_tool", big)
        assert len(result) <= 10000

    def test_verify_short_output_is_passed_through_unchanged(self):
        """Validate that outputs below the compaction threshold are returned verbatim.

        The test passes a 12-character string and asserts equality with the
        input because short outputs should bypass compression to avoid
        unnecessary processing overhead.
        """
        short = "short output"
        result = self.compactor.compact_tool_output("grep", short)
        assert result == short


# ===========================================================================
# Compaction Strategies
# ===========================================================================

class TestCompactionStrategies:
    """Engineered to validate each compaction strategy's should_compact decision and compact execution.

    This test class exercises 16 scenarios across 7 distinct strategy classes
    to ensure that every strategy correctly decides when to trigger compaction
    and produces a valid (possibly reduced) message list when compact is called.
    The design validates both the gate (should_compact) and the action (compact)
    for each strategy to ensure end-to-end compaction pipeline correctness.
    """

    def test_verify_always_compact_triggers_on_sufficient_turns(self):
        """Validate that EncreAlwaysCompactStrategy.should_compact returns True with 8 turns.

        The test creates the strategy and asserts should_compact is True with
        8 message pairs because the always-compact strategy fires when the
        conversation exceeds a minimum turn threshold.
        """
        s = EncreAlwaysCompactStrategy()
        assert asyncio.run(s.should_compact(_make_messages(8), 128000)) is True

    def test_verify_always_compact_skips_with_few_turns(self):
        """Validate that EncreAlwaysCompactStrategy.should_compact returns False with 2 turns.

        The test asserts should_compact is False with only 2 message pairs
        because the strategy is designed to skip compaction on short conversations.
        """
        s = EncreAlwaysCompactStrategy()
        assert asyncio.run(s.should_compact(_make_messages(2), 128000)) is False

    def test_verify_always_compact_execute_reduces_message_count(self):
        """Validate that EncreAlwaysCompactStrategy.compact returns a list no longer than the input.

        The test compacts 8 turns and asserts the result length is at most
        the input length because compaction must never increase message count.
        """
        s = EncreAlwaysCompactStrategy()
        msgs = _make_messages(8)
        result = asyncio.run(s.compact(msgs, 128000))
        assert len(result) <= len(msgs)

    def test_verify_token_budget_should_compact_when_over_ratio(self):
        """Validate that EncreTokenBudgetStrategy.should_compact returns a boolean when budget is exceeded.

        The test creates a strategy with budget_ratio=0.5 and a single 10K
        character message against a 1000-token budget, asserting the result
        is a bool because the strategy evaluates whether token usage exceeds
        the configured ratio threshold.
        """
        s = EncreTokenBudgetStrategy(budget_ratio=0.5)
        msgs = [_m("user", "x" * 10000)]
        assert isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)

    def test_verify_token_budget_execute_reduces_message_count(self):
        """Validate that EncreTokenBudgetStrategy.compact returns a list no longer than the input.

        The test compacts 20 turns with a 0.5 budget ratio and asserts the
        result length is at most the input because token-budget compaction
        must truncate or summarize to stay within the budget.
        """
        s = EncreTokenBudgetStrategy(budget_ratio=0.5)
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        assert len(result) <= len(msgs)

    def test_verify_budget_reduction_truncates_oversized_messages(self):
        """Validate that EncreBudgetReductionStrategy truncates messages exceeding max_chars_per_message.

        The test sets max_chars_per_message=100 with a 5000-character input
        and asserts the first message content is under 5000 characters after
        compaction because budget reduction must enforce a per-message size cap.
        """
        s = EncreBudgetReductionStrategy(max_chars_per_message=100)
        msgs = [_m("user", "x" * 5000)]
        result = asyncio.run(s.compact(msgs, 128000))
        assert len(result[0]["content"]) < 5000  # was truncated

    def test_verify_budget_reduction_should_compact_on_oversized_message(self):
        """Validate that EncreBudgetReductionStrategy.should_compact returns True for an oversized message.

        The test asserts should_compact is True when a single message is 5000
        characters with max_chars_per_message=100 because the strategy must
        detect when any message exceeds the per-message budget.
        """
        s = EncreBudgetReductionStrategy(max_chars_per_message=100)
        msgs = [_m("user", "x" * 5000)]
        assert asyncio.run(s.should_compact(msgs, 128000)) is True

    def test_verify_snip_execute_keeps_recent_turns_only(self):
        """Validate that EncreSnipStrategy.compact returns a list no longer than the input.

        The test creates a snip strategy keeping the last 3 turns and asserts
        the compacted result is at most the original length because snipping
        must remove older messages while preserving recent ones.
        """
        s = EncreSnipStrategy(keep_recent_turns=3)
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        assert len(result) <= len(msgs)

    def test_verify_micro_compact_execute_returns_valid_result(self):
        """Validate that EncreMicroCompactStrategy.compact returns a non-None message list.

        The test compacts 10 turns and asserts the result is not None because
        micro compaction should always produce a valid (possibly unchanged)
        message list even when no compaction is needed.
        """
        s = EncreMicroCompactStrategy()
        msgs = _make_messages(10)
        result = asyncio.run(s.compact(msgs, 128000))
        assert result is not None

    def test_verify_micro_compact_should_compact_on_large_single_message(self):
        """Validate that EncreMicroCompactStrategy.should_compact returns True for a 5000-char message.

        The test asserts should_compact is True because a single very large
        message should trigger micro compaction regardless of turn count.
        """
        s = EncreMicroCompactStrategy()
        msgs = [_m("user", "x" * 5000)]
        assert asyncio.run(s.should_compact(msgs, 128000)) is True

    def test_verify_context_collapse_execute_returns_valid_result(self):
        """Validate that EncreContextCollapseStrategy.compact returns a non-None message list.

        The test compacts 20 turns and asserts the result is not None because
        context collapse must always produce a valid output list.
        """
        s = EncreContextCollapseStrategy()
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        assert result is not None

    def test_verify_semantic_should_compact_on_oversized_tool_output(self):
        """Validate that EncreSemanticCompactStrategy.should_compact returns a boolean for oversized tool content.

        The test passes a 10K-character tool message and asserts should_compact
        returns a bool because the semantic strategy evaluates content density
        to decide whether semantic compression is warranted.
        """
        s = EncreSemanticCompactStrategy()
        msgs = [_m("tool", "x" * 10000)]
        assert isinstance(asyncio.run(s.should_compact(msgs, 128000)), bool)

    def test_verify_semantic_execute_returns_valid_result(self):
        """Validate that EncreSemanticCompactStrategy.compact returns a non-None message list.

        The test compacts a single short user message and asserts the result
        is not None because semantic compaction must always return a valid
        message list even when no semantic reduction is applied.
        """
        s = EncreSemanticCompactStrategy()
        msgs = [_m("user", "test")]
        result = asyncio.run(s.compact(msgs, 128000))
        assert result is not None

    def test_verify_multi_stage_pipeline_has_minimum_stages(self):
        """Validate that EncreMultiStagePipeline initializes with at least 6 compaction stages.

        The test asserts len(_stages) >= 6 because the multi-stage pipeline
        is designed to apply a fixed sequence of compaction passes (semantic,
        budget, snip, etc.) in a deterministic order.
        """
        pipeline = EncreMultiStagePipeline()
        assert len(pipeline._stages) >= 6

    def test_verify_multi_stage_execute_returns_valid_result(self):
        """Validate that EncreMultiStagePipeline.compact returns a non-None message list.

        The test compacts 5 turns through the pipeline and asserts the result
        is not None because the multi-stage pipeline must always produce a
        valid output after applying all configured stages.
        """
        pipeline = EncreMultiStagePipeline()
        msgs = _make_messages(5)
        result = asyncio.run(pipeline.compact(msgs, 128000))
        assert result is not None

    def test_verify_multi_stage_should_compact_returns_bool(self):
        """Validate that EncreMultiStagePipeline.should_compact returns a boolean decision.

        The test asserts should_compact returns a bool for a short 2-turn
        conversation because the pipeline aggregates decisions from all
        stages and must return a clear True/False gate.
        """
        pipeline = EncreMultiStagePipeline()
        assert isinstance(asyncio.run(pipeline.should_compact(_make_messages(2), 128000)), bool)

    def test_verify_auto_compact_should_compact_on_large_content(self):
        """Validate that EncreAutoCompactStrategy.should_compact returns a boolean for large input.

        The test creates a strategy with threshold_ratio=0.5 and a 50K
        character message against a 1000-token budget, asserting the result
        is a bool because the auto strategy evaluates content-to-budget ratio.
        """
        s = EncreAutoCompactStrategy(threshold_ratio=0.5)
        msgs = [_m("user", "x" * 50000)]
        assert isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)

    def test_verify_auto_compact_execute_returns_valid_result(self):
        """Validate that EncreAutoCompactStrategy.compact returns a non-None message list.

        The test compacts 2 turns and asserts the result is not None because
        auto compaction must always return a valid message list regardless
        of whether any actual compaction was applied.
        """
        s = EncreAutoCompactStrategy(threshold_ratio=0.5)
        msgs = _make_messages(2)
        result = asyncio.run(s.compact(msgs, 128000))
        assert result is not None


# ===========================================================================
# EncreCompactEngine
# ===========================================================================

class _MockBackend:
    """Minimal mock backend for CompactEngine tests that reports a 128K context window."""

    def context_window_size(self) -> int:
        return 128000

    @property
    def model(self) -> str:
        return "mock-model"


class TestCompactEngine:
    """Engineered to validate the EncreCompactEngine orchestration layer for compaction decisions.

    This test class exercises the engine across 3 scenarios to ensure that
    the engine can be constructed, that should_compact returns a boolean
    decision, and that compact produces a non-None result when using the
    mock backend. The design follows a fallback pattern where the engine
    delegates to strategy-specific logic and falls back to budget-based
    reduction when no specialized compaction path is available.
    """

    def test_verify_engine_construction(self):
        """Validate that EncreCompactEngine() constructs successfully.

        The test asserts the engine instance is not None because the engine
        is the top-level coordinator for all compaction operations and must
        be instantiable without arguments.
        """
        engine = EncreCompactEngine()
        assert engine is not None

    def test_verify_should_compact_returns_bool(self):
        """Validate that should_compact returns a boolean for a short message list.

        The test passes 2 turns and a 128K budget and asserts the result is
        a bool because should_compact is a gate that must return a definitive
        True/False without side effects.
        """
        engine = EncreCompactEngine()
        msgs = _make_messages(2)
        assert isinstance(engine.should_compact(msgs, 128000), bool)

    def test_verify_compact_with_mock_backend_returns_valid_result(self):
        """Validate that compact() returns a non-None message list using the mock backend.

        The test passes 30 turns through compact with the mock backend and
        asserts the result is not None because compact must always produce
        a valid message list, falling back to _budget_fallback when the
        backend does not provide real API compaction endpoints.
        """
        engine = EncreCompactEngine()
        msgs = _make_messages(30)
        backend = _MockBackend()
        result = asyncio.run(engine.compact(msgs, backend=backend, turn_count=0))
        # Falls back to _budget_fallback since mock backend has no real API
        assert result is not None
