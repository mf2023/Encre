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
    """Helper: M."""
    msg = {"role": role, "content": content}
    if name:
        msg["name"] = name
    return msg


def _make_messages(turns):
    """Helper: Make messages."""
    msgs = [_m("system", "You are an assistant.")]
    for i in range(turns):
        msgs.append(_m("user", f"Question {i}"))
        msgs.append(_m("assistant", f"Answer {i}"))
    return msgs


# ===========================================================================
# ContextTier / ContextPartition
# ===========================================================================

class TestContextTier:
    """Test suite for ContextTier."""
    def test_create(self):
        """Test: Create."""
        ct = ContextTier(name="test", messages=[_m("user", "hello")])
        # Verify: ct.name == "test"
        assert ct.name == "test"
        # Verify: len(ct.messages) == 1
        assert len(ct.messages) == 1

    def test_token_count(self):
        """Test: Token count."""
        ct = ContextTier(name="test", messages=[_m("user", "hello world")])
        # Verify: ct.token_count() > 0
        assert ct.token_count() > 0


class TestContextPartition:
    """Test suite for ContextPartition."""
    def test_defaults(self):
        """Test: Defaults."""
        cp = ContextPartition()
        # Verify: cp.system == []
        assert cp.system == []
        # Verify: cp.hot == []
        assert cp.hot == []
        # Verify: cp.warm == []
        assert cp.warm == []
        # Verify: cp.cold == []
        assert cp.cold == []
        # Verify: cp.reference == []
        assert cp.reference == []

    def test_with_messages(self):
        """Test: With messages."""
        cp = ContextPartition(
            system=[_m("system", "You are helpful.")],
            hot=[_m("user", "latest question")],
        )
        msgs = cp.to_messages()
        # Verify: len(msgs) == 2
        assert len(msgs) == 2

    def test_total_tokens(self):
        """Test: Total tokens."""
        cp = ContextPartition(hot=[_m("user", "hello world")])
        # Verify: cp.total_tokens() > 0
        assert cp.total_tokens() > 0


class TestContextPartitioner:
    """Test suite for ContextPartitioner."""
    def test_partition(self):
        """Test: Partition."""
        partitioner = ContextPartitioner()
        messages = [
            _m("system", "You are an assistant."),
            _m("user", "Hello"),
            _m("assistant", "Hi there"),
            _m("user", "Can you help me?"),
            _m("assistant", "Sure, what do you need?"),
        ]
        result = partitioner.partition(messages)
        # Verify: isinstance(result, ContextPartition)
        assert isinstance(result, ContextPartition)
        # Verify: len(result.hot) > 0
        assert len(result.hot) > 0
        # Verify: len(result.system) == 1
        assert len(result.system) == 1


# ===========================================================================
# SemanticToolOutputCompactor
# ===========================================================================

class TestSemanticToolOutputCompactor:
    """Test suite for SemanticToolOutputCompactor."""
    def setup_method(self):
        """Setup method."""
        self.compactor = SemanticToolOutputCompactor()

    def test_compact_grep(self):
        """Test: Compact grep."""
        big = "file.py:1:line1\nfile.py:2:line2\n" * 600
        result = self.compactor.compact_tool_output("grep", big)
        # Verify: len(result) < len(big)
        assert len(result) < len(big)

    def test_compact_glob(self):
        """Test: Compact glob."""
        big = "\n".join(f"/path/to/file{i}.py" for i in range(800))
        result = self.compactor.compact_tool_output("glob", big)
        # Verify: "files" in result.lower() or "glob" in result.lower()
        assert "files" in result.lower() or "glob" in result.lower()

    def test_compact_bash(self):
        """Test: Compact bash."""
        big = "error line 1\n" * 700
        result = self.compactor.compact_tool_output("bash", big)
        # Verify: len(result) < len(big)
        assert len(result) < len(big)

    def test_compact_file_read(self):
        """Test: Compact file read."""
        big = "def foo():\n    pass\n" * 500
        result = self.compactor.compact_tool_output("file_read", big)
        # Verify: len(result) < len(big)
        assert len(result) < len(big)

    def test_compact_web_fetch(self):
        """Test: Compact web fetch."""
        html = "<html><head><title>Test</title></head><body>" + "<p>content</p>" * 600 + "</body></html>"  # noqa: E501
        result = self.compactor.compact_tool_output("web_fetch", html)
        # Verify: len(result) < len(html)
        assert len(result) < len(html)

    def test_compact_task_list(self):
        """Test: Compact task list."""
        big = '{"id": "1", "subject": "test"}\n' * 20
        result = self.compactor.compact_tool_output("task_list", big)
        # Verify: len(result) < 700
        assert len(result) < 700

    def test_compact_unknown_truncates(self):
        """Test: Compact unknown truncates."""
        big = "x" * 10000
        result = self.compactor.compact_tool_output("unknown_tool", big)
        # Verify: len(result) <= 10000
        assert len(result) <= 10000

    def test_short_output_passthrough(self):
        """Test: Short output passthrough."""
        short = "short output"
        result = self.compactor.compact_tool_output("grep", short)
        # Verify: result == short
        assert result == short


# ===========================================================================
# Compaction Strategies
# ===========================================================================

class TestCompactionStrategies:
    """Test suite for CompactionStrategies."""
    def test_always_compact_should(self):
        """Test: Always compact should."""
        s = EncreAlwaysCompactStrategy()
        # Verify: asyncio.run(s.should_compact(_make_messages(8), 128000)) is True
        assert asyncio.run(s.should_compact(_make_messages(8), 128000)) is True

    def test_always_compact_few(self):
        """Test: Always compact few."""
        s = EncreAlwaysCompactStrategy()
        # Verify: asyncio.run(s.should_compact(_make_messages(2), 128000)) is False
        assert asyncio.run(s.should_compact(_make_messages(2), 128000)) is False

    def test_always_compact_execute(self):
        """Test: Always compact execute."""
        s = EncreAlwaysCompactStrategy()
        msgs = _make_messages(8)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: len(result) <= len(msgs)
        assert len(result) <= len(msgs)

    def test_token_budget_should(self):
        """Test: Token budget should."""
        s = EncreTokenBudgetStrategy(budget_ratio=0.5)
        msgs = [_m("user", "x" * 10000)]
        # Verify: isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)
        assert isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)

    def test_token_budget_execute(self):
        """Test: Token budget execute."""
        s = EncreTokenBudgetStrategy(budget_ratio=0.5)
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: len(result) <= len(msgs)
        assert len(result) <= len(msgs)

    def test_budget_reduction_execute(self):
        """Test: Budget reduction execute."""
        s = EncreBudgetReductionStrategy(max_chars_per_message=100)
        msgs = [_m("user", "x" * 5000)]
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: len(result[0]["content"]) < 5000  # was truncated
        assert len(result[0]["content"]) < 5000  # was truncated

    def test_budget_reduction_should(self):
        """Test: Budget reduction should."""
        s = EncreBudgetReductionStrategy(max_chars_per_message=100)
        msgs = [_m("user", "x" * 5000)]
        # Verify: asyncio.run(s.should_compact(msgs, 128000)) is True
        assert asyncio.run(s.should_compact(msgs, 128000)) is True

    def test_snip_execute(self):
        """Test: Snip execute."""
        s = EncreSnipStrategy(keep_recent_turns=3)
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: len(result) <= len(msgs)
        assert len(result) <= len(msgs)

    def test_micro_compact_execute(self):
        """Test: Micro compact execute."""
        s = EncreMicroCompactStrategy()
        msgs = _make_messages(10)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None

    def test_micro_compact_large_content(self):
        """Test: Micro compact large content."""
        s = EncreMicroCompactStrategy()
        msgs = [_m("user", "x" * 5000)]
        # Verify: asyncio.run(s.should_compact(msgs, 128000)) is True
        assert asyncio.run(s.should_compact(msgs, 128000)) is True

    def test_context_collapse_execute(self):
        """Test: Context collapse execute."""
        s = EncreContextCollapseStrategy()
        msgs = _make_messages(20)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None

    def test_semantic_should(self):
        """Test: Semantic should."""
        s = EncreSemanticCompactStrategy()
        msgs = [_m("tool", "x" * 10000)]
        # Verify: isinstance(asyncio.run(s.should_compact(msgs, 128000)), bool)
        assert isinstance(asyncio.run(s.should_compact(msgs, 128000)), bool)

    def test_semantic_execute(self):
        """Test: Semantic execute."""
        s = EncreSemanticCompactStrategy()
        msgs = [_m("user", "test")]
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None

    def test_multi_stage_has_six_stages(self):
        """Test: Multi stage has six stages."""
        pipeline = EncreMultiStagePipeline()
        # Verify: len(pipeline._stages) >= 6
        assert len(pipeline._stages) >= 6

    def test_multi_stage_execute(self):
        """Test: Multi stage execute."""
        pipeline = EncreMultiStagePipeline()
        msgs = _make_messages(5)
        result = asyncio.run(pipeline.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None

    def test_multi_stage_should(self):
        """Test: Multi stage should."""
        pipeline = EncreMultiStagePipeline()
        # Verify: isinstance(asyncio.run(pipeline.should_compact(_make_messages(2), 128000)), bool)
        assert isinstance(asyncio.run(pipeline.should_compact(_make_messages(2), 128000)), bool)

    def test_auto_compact_strategy(self):
        """Test: Auto compact strategy."""
        s = EncreAutoCompactStrategy(threshold_ratio=0.5)
        msgs = [_m("user", "x" * 50000)]
        # Verify: isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)
        assert isinstance(asyncio.run(s.should_compact(msgs, 1000)), bool)

    def test_auto_compact_execute(self):
        """Test: Auto compact execute."""
        s = EncreAutoCompactStrategy(threshold_ratio=0.5)
        msgs = _make_messages(2)
        result = asyncio.run(s.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None


# ===========================================================================
# EncreCompactEngine
# ===========================================================================

class TestCompactEngine:
    """Test suite for CompactEngine."""
    def test_create(self):
        """Test: Create."""
        engine = EncreCompactEngine()
        # Verify: engine is not None
        assert engine is not None

    def test_with_strategy(self):
        """Test: With strategy."""
        s = EncreAlwaysCompactStrategy()
        engine = EncreCompactEngine(strategy=s)
        # Verify: engine is not None
        assert engine is not None

    def test_should_compact(self):
        """Test: Should compact."""
        engine = EncreCompactEngine()
        msgs = _make_messages(2)
        # Verify: isinstance(asyncio.run(engine.should_compact(msgs, 128000)), bool)
        assert isinstance(asyncio.run(engine.should_compact(msgs, 128000)), bool)

    def test_compact(self):
        """Test: Compact."""
        engine = EncreCompactEngine()
        msgs = _make_messages(30)
        result = asyncio.run(engine.compact(msgs, 128000))
        # Verify: result is not None
        assert result is not None

    def test_set_strategy(self):
        """Test: Set strategy."""
        engine = EncreCompactEngine()
        s = EncreAlwaysCompactStrategy()
        engine.set_strategy(s)
        # Verify: engine._strategy is s
        assert engine._strategy is s
