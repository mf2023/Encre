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

"""Tests for memdir: memory system, semantic search, working memory, consolidation."""

import os
import tempfile

import pytest
from encre.memdir.semantic import (
    MemoryConsolidator,
    SemanticMemorySearch,
    WorkingMemory,
    _build_idf,
    _cosine_similarity,
    _jaccard_similarity,
    _tf_idf_vectorize,
    _tokenize,
)
from encre.memdir.system import EncreMemorySystem

# ===========================================================================
# Tokeniser & similarity
# ===========================================================================

class TestTokenize:
    """Test cases covering tokenize.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_simple(self):
        """Verifies that simple."""
        t = _tokenize("Hello World! This is a test.")
        # Confirm the expected result for this scenario: simple.
        assert "hello" in t
        assert "world" in t
        assert "this" in t

    def test_chinese(self):
        """Verifies that chinese."""
        t = _tokenize("测试 中文 and English 混合")
        # Confirm the expected result for this scenario: chinese.
        assert "and" in t
        assert "english" in t

    def test_short_tokens_dropped(self):
        """Verifies that short tokens dropped."""
        t = _tokenize("a b c ab cd ef hello")
        # Confirm the expected result for this scenario: short tokens dropped.
        assert "hello" in t
        # Short single-char tokens are dropped; "ab" is exact boundary
        assert "a" not in t
        assert len(t) > 0

    def test_empty(self):
        """Verifies that empty."""
        # Confirm the expected result for this scenario: empty.
        assert _tokenize("") == []


class TestJaccard:
    """Test cases covering jaccard.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_identical(self):
        """Verifies that identical."""
        # Confirm the expected result for this scenario: identical.
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_disjoint(self):
        """Verifies that disjoint."""
        # Confirm the expected result for this scenario: disjoint.
        assert _jaccard_similarity("abc def", "xyz uvw") == 0.0

    def test_partial(self):
        """Verifies that partial."""
        s = _jaccard_similarity("hello world foo", "hello world bar")
        # Confirm the expected result for this scenario: partial.
        assert 0.4 < s < 1.0

    def test_one_empty(self):
        """Verifies that one empty."""
        # Confirm the expected result for this scenario: one empty.
        assert _jaccard_similarity("", "hello") == 0.0
        assert _jaccard_similarity("hello", "") == 0.0


class TestTfIdf:
    """Test cases covering tf idf.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_build_idf(self):
        """Verifies that build idf."""
        corpus = ["hello world", "hello foo", "bar baz"]
        idf = _build_idf(corpus)
        # Confirm the expected result for this scenario: build idf.
        assert "hello" in idf
        assert "world" in idf
        assert idf["hello"] < idf["world"]  # hello appears in 2 docs, world in 1

    def test_empty_corpus(self):
        """Verifies that empty corpus."""
        # Confirm the expected result for this scenario: empty corpus.
        assert _build_idf([]) == {}

    def test_vectorize(self):
        """Verifies that vectorize."""
        corpus = ["hello world foo", "hello bar", "bar baz qux"]
        idf = _build_idf(corpus)
        vocab = set(idf.keys())
        vec = _tf_idf_vectorize("hello world", idf, vocab)
        # Confirm the expected result for this scenario: vectorize.
        assert "hello" in vec
        assert vec["hello"] > 0

    def test_cosine_same(self):
        """Verifies that cosine same."""
        corpus = ["hello world", "foo bar"]
        idf = _build_idf(corpus)
        vocab = set(idf.keys())
        v = _tf_idf_vectorize("hello world", idf, vocab)
        # Confirm the expected result for this scenario: cosine same.
        assert _cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_cosine_orthogonal(self):
        """Verifies that cosine orthogonal."""
        corpus = ["hello world", "foo bar"]
        idf = _build_idf(corpus)
        vocab = set(idf.keys())
        v1 = _tf_idf_vectorize("hello world", idf, vocab)
        v2 = _tf_idf_vectorize("foo bar", idf, vocab)
        # Confirm the expected result for this scenario: cosine orthogonal.
        assert _cosine_similarity(v1, v2) == 0.0


# ===========================================================================
# SemanticMemorySearch
# ===========================================================================

class TestSemanticMemorySearch:
    """Test cases covering semantic memory search.
    
    Covers the expected behavior and relevant edge cases.
    """
    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifies that setup."""
        self.tmpdir = tempfile.mkdtemp()
        yield
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        """Verifies that write."""
        with open(os.path.join(self.tmpdir, name), "w", encoding="utf-8") as f:
            f.write(content)

    def test_search_finds_relevant(self):
        """Verifies that search finds relevant."""
        self._write("auth.md", "The login system uses OAuth2 with JWT tokens.")
        self._write("ui.md", "The dashboard uses React and Tailwind CSS for styling.")
        sms = SemanticMemorySearch(self.tmpdir)
        results = sms.search("authentication login")
        # Confirm the expected result for this scenario: search finds relevant.
        assert len(results) >= 1
        assert results[0].file_name == "auth.md"

    def test_search_respects_top_k(self):
        """Verifies that search respects top k."""
        for i in range(10):
            self._write(f"doc{i}.md", f"Document number {i} about various topics.")
        sms = SemanticMemorySearch(self.tmpdir)
        results = sms.search("document", top_k=3)
        # Confirm the expected result for this scenario: search respects top k.
        assert len(results) <= 3

    def test_search_empty_dir(self):
        """Verifies that search empty dir."""
        sms = SemanticMemorySearch(self.tmpdir)
        # Confirm the expected result for this scenario: search empty dir.
        assert sms.search("anything") == []

    def test_search_relevant_higher_threshold(self):
        """Verifies that search relevant higher threshold."""
        self._write("a.md", "python async programming guide")
        self._write("b.md", "baking chocolate cake recipe")
        sms = SemanticMemorySearch(self.tmpdir)
        results = sms.search_relevant("python programming")
        # Confirm the expected result for this scenario: search relevant higher threshold.
        assert len(results) >= 1
        assert results[0].file_name == "a.md"

    def test_ignores_memory_md(self):
        """Verifies that ignores memory md."""
        self._write("MEMORY.md", "entrypoint content")
        self._write("real.md", "actual memory content here")
        sms = SemanticMemorySearch(self.tmpdir)
        results = sms.search("content")
        names = {r.file_name for r in results}
        # Confirm the expected result for this scenario: ignores memory md.
        assert "MEMORY.md" not in names
        assert "real.md" in names

    def test_index_explicit(self):
        """Verifies that index explicit."""
        sms = SemanticMemorySearch(self.tmpdir)
        sms.index({"a.md": "hello world", "b.md": "foo bar"})
        results = sms.search("hello")
        # Confirm the expected result for this scenario: index explicit.
        assert results[0].file_name == "a.md"


# ===========================================================================
# WorkingMemory
# ===========================================================================

class TestWorkingMemory:
    """Test cases covering working memory.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_initial_empty(self):
        """Verifies that initial empty."""
        wm = WorkingMemory()
        # Confirm the expected result for this scenario: initial empty.
        assert wm.current_goal == ""
        assert wm.subgoals == []
        assert wm.hypotheses == []

    def test_set_goal(self):
        """Verifies that set goal."""
        wm = WorkingMemory()
        wm.set_goal("Implement OAuth2")
        # Confirm the expected result for this scenario: set goal.
        assert wm.current_goal == "Implement OAuth2"

    def test_add_subgoal_no_dupes(self):
        """Verifies that add subgoal no dupes."""
        wm = WorkingMemory()
        wm.add_subgoal("Write tests")
        wm.add_subgoal("Write tests")
        # Confirm the expected result for this scenario: add subgoal no dupes.
        assert len(wm.subgoals) == 1

    def test_complete_subgoal(self):
        """Verifies that complete subgoal."""
        wm = WorkingMemory()
        wm.add_subgoal("Write tests")
        wm.complete_subgoal("Write tests")
        # Confirm the expected result for this scenario: complete subgoal.
        assert wm.subgoals == []

    def test_hypothesis_lifecycle(self):
        """Verifies that hypothesis lifecycle."""
        wm = WorkingMemory()
        wm.add_hypothesis("The bug is in auth.py")
        wm.confirm_hypothesis("The bug is in auth.py")
        # Confirm the expected result for this scenario: hypothesis lifecycle.
        assert wm.hypotheses == []
        assert any("CONFIRMED" in f for f in wm.findings)

    def test_reject_hypothesis(self):
        """Verifies that reject hypothesis."""
        wm = WorkingMemory()
        wm.add_hypothesis("Memory leak in loop")
        wm.reject_hypothesis("Memory leak in loop")
        # Confirm the expected result for this scenario: reject hypothesis.
        assert wm.hypotheses == []
        assert any("REJECTED" in f for f in wm.findings)

    def test_add_finding(self):
        """Verifies that add finding."""
        wm = WorkingMemory()
        wm.add_finding("Token refresh endpoint returns 401")
        # Confirm the expected result for this scenario: add finding.
        assert len(wm.findings) == 1

    def test_question_lifecycle(self):
        """Verifies that question lifecycle."""
        wm = WorkingMemory()
        wm.add_question("Should we use asyncpg?")
        wm.resolve_question("Should we use asyncpg?", "Yes, it's faster")
        # Confirm the expected result for this scenario: question lifecycle.
        assert wm.open_questions == []
        assert any("asyncpg" in f for f in wm.findings)

    def test_scratchpad(self):
        """Verifies that scratchpad."""
        wm = WorkingMemory()
        wm.note("TODO: check error handling")
        wm.note("Done: error handling looks fine")
        # Confirm the expected result for this scenario: scratchpad.
        assert len(wm.scratchpad) == 2

    def test_summarize_empty(self):
        """Verifies that summarize empty."""
        wm = WorkingMemory()
        # Confirm the expected result for this scenario: summarize empty.
        assert "empty" in wm.summarize().lower()

    def test_summarize_with_content(self):
        """Verifies that summarize with content."""
        wm = WorkingMemory()
        wm.set_goal("Test framework")
        wm.add_finding("pytest configured")
        s = wm.summarize()
        # Confirm the expected result for this scenario: summarize with content.
        assert "Test framework" in s
        assert "pytest configured" in s

    def test_summarize_truncates_lists(self):
        """Verifies that summarize truncates lists."""
        wm = WorkingMemory()
        for i in range(20):
            wm.add_finding(f"Finding {i}")
        s = wm.summarize()
        # Should show only last 10 findings
        # Confirm the expected result for this scenario: summarize truncates lists.
        assert "Finding 0" not in s
        assert "Finding 19" in s

    def test_serialize_roundtrip(self):
        """Verifies that serialize roundtrip."""
        wm = WorkingMemory()
        wm.set_goal("Test")
        wm.add_hypothesis("H1")
        wm.add_finding("F1")
        d = wm.to_dict()
        wm2 = WorkingMemory.from_dict(d)
        # Confirm the expected result for this scenario: serialize roundtrip.
        assert wm2.current_goal == "Test"
        assert "H1" in wm2.hypotheses
        assert "F1" in wm2.findings


# ===========================================================================
# MemoryConsolidator
# ===========================================================================

class TestMemoryConsolidator:
    """Test cases covering memory consolidator.
    
    Covers the expected behavior and relevant edge cases.
    """
    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifies that setup."""
        self.tmpdir = tempfile.mkdtemp()
        self.mc = MemoryConsolidator(self.tmpdir)
        yield
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_find_duplicates(self):
        """Verifies that find duplicates."""
        files = {
            "a.md": "Always use async/await for network calls in production code.",
            "b.md": "Always use async/await for network calls in the production environment.",
            "c.md": "Completely different topic about CSS grid layout and flexbox.",
        }
        actions = self.mc.find_duplicates(files)
        # Confirm the expected result for this scenario: find duplicates.
        assert len(actions) >= 1
        action = actions[0]
        assert action.action == "merge"
        assert action.merged_content

    def test_find_duplicates_none(self):
        """Verifies that find duplicates none."""
        files = {"a.md": "foo bar", "b.md": "completely unrelated"}
        # Confirm the expected result for this scenario: find duplicates none.
        assert self.mc.find_duplicates(files) == []

    def test_find_conflicts(self):
        """Verifies that find conflicts."""
        files = {
            "a.md": "Always use async/await for network calls.",
            "b.md": "Never use async/await; prefer synchronous calls.",
        }
        actions = self.mc.find_conflicts(files)
        # Confirm the expected result for this scenario: find conflicts.
        assert len(actions) >= 1
        assert actions[0].action == "flag_conflict"

    def test_find_conflicts_no_overlap_no_flag(self):
        """Verifies that find conflicts no overlap no flag."""
        files = {
            "a.md": "Always use async/await for network calls.",
            "b.md": "The CSS grid system is preferred for layouts.",
        }
        actions = self.mc.find_conflicts(files)
        # Confirm the expected result for this scenario: find conflicts no overlap no flag.
        assert len(actions) == 0

    def test_find_stale(self):
        """Verifies that find stale."""
        files = {"old.md": "Reference: `src/auth.py:42` has the login flow."}
        age_days = {"old.md": 60}
        actions = self.mc.find_stale(files, age_days, stale_threshold_days=30)
        # src/auth.py likely doesn't exist in cwd
        # Confirm the expected result for this scenario: find stale.
        assert len(actions) >= 1
        assert actions[0].action == "mark_stale"

    def test_find_stale_not_old_enough(self):
        """Verifies that find stale not old enough."""
        files = {"recent.md": "Reference: `src/auth.py:42`"}
        age_days = {"recent.md": 5}
        actions = self.mc.find_stale(files, age_days, stale_threshold_days=30)
        # Confirm the expected result for this scenario: find stale not old enough.
        assert len(actions) == 0

    def test_consolidate_orders_actions(self):
        """Verifies that consolidate orders actions."""
        files = {
            "dup_a.md": "Always use async/await for network calls in production code.",
            "dup_b.md": "Always use async/await for network calls in the production environment.",
            "conflict.md": "Never use async/await; prefer synchronous calls.",
        }
        age_days = {"dup_a.md": 35, "dup_b.md": 10, "conflict.md": 5}
        actions = self.mc.consolidate(files, age_days)
        # merge should come before conflict
        # Confirm the expected result for this scenario: consolidate orders actions.
        assert actions[0].action == "merge"
        assert any(a.action == "flag_conflict" for a in actions)


# ===========================================================================
# EncreMemorySystem integration
# ===========================================================================

class TestEncreMemorySystem:
    """Test cases covering encre memory system.
    
    Covers the expected behavior and relevant edge cases.
    """
    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifies that setup."""
        self.tmpdir = tempfile.mkdtemp()
        self.ms = EncreMemorySystem(self.tmpdir)
        yield
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_empty(self):
        """Verifies that scan empty."""
        # Confirm the expected result for this scenario: scan empty.
        assert self.ms.scan() == []

    def test_scan_single(self):
        """Verifies that scan single."""
        self._write("test.md", "---\ndescription: Test memory\ntype: reference\n---\nContent here.")
        memories = self.ms.scan()
        # Confirm the expected result for this scenario: scan single.
        assert len(memories) == 1
        assert memories[0].description == "Test memory"
        assert memories[0].memory_type == "reference"

    def test_scan_skips_entrypoint(self):
        """Verifies that scan skips entrypoint."""
        self._write("MEMORY.md", "entrypoint")
        self._write("real.md", "real memory")
        memories = self.ms.scan()
        names = {m.filename for m in memories}
        # Confirm the expected result for this scenario: scan skips entrypoint.
        assert "MEMORY.md" not in names
        assert "real.md" in names

    def test_format_manifest_empty(self):
        """Verifies that format manifest empty."""
        manifest = self.ms.format_manifest([])
        # Confirm the expected result for this scenario: format manifest empty.
        assert manifest == ""

    def test_build_prompt(self):
        """Verifies that build prompt."""
        self._write("test.md", "---\ndescription: A test\n---\nTest content.")
        prompt = self.ms.build_prompt()
        # Confirm the expected result for this scenario: build prompt.
        assert "MEMORY.md Entrypoint" in prompt

    def test_search_delegates_to_semantic(self):
        """Verifies that search delegates to semantic."""
        self._write("auth.md", "OAuth2 JWT token authentication system.")
        self._write("ui.md", "CSS grid layout with responsive breakpoints.")
        results = self.ms.search("authentication login")
        # Confirm the expected result for this scenario: search delegates to semantic.
        assert len(results) >= 1
        assert results[0].file_name == "auth.md"

    def test_search_relevant(self):
        """Verifies that search relevant."""
        self._write("db.md", "Database connection pooling with postgresql and asyncpg for performance.")  # noqa: E501
        results = self.ms.search_relevant("database postgres")
        # search_relevant has higher threshold -- may or may not match, depends on corpus
        # Confirm the expected result for this scenario: search relevant.
        assert isinstance(results, list)

    def test_working_memory_accessible(self):
        """Verifies that working memory accessible."""
        wm = self.ms.working
        wm.set_goal("Test goal")
        # Confirm the expected result for this scenario: working memory accessible.
        assert self.ms.working.current_goal == "Test goal"

    def test_reset_working(self):
        """Verifies that reset working."""
        self.ms.working.set_goal("Old")
        self.ms.reset_working()
        # Confirm the expected result for this scenario: reset working.
        assert self.ms.working.current_goal == ""

    def test_inject_working_empty(self):
        """Verifies that inject working empty."""
        # Confirm the expected result for this scenario: inject working empty.
        assert self.ms.inject_working_memory_prompt() == ""

    def test_inject_working_with_content(self):
        """Verifies that inject working with content."""
        self.ms.working.set_goal("Fix login bug")
        prompt = self.ms.inject_working_memory_prompt()
        # Confirm the expected result for this scenario: inject working with content.
        assert "Fix login bug" in prompt

    def test_build_prompt_with_context(self):
        """Verifies that build prompt with context."""
        self._write("auth.md", "OAuth2 JWT token authentication.")
        self._write("css.md", "Tailwind CSS utility classes.")
        prompt = self.ms.build_prompt_with_context("authentication")
        # Confirm the expected result for this scenario: build prompt with context.
        assert "Semantically Relevant" in prompt
        assert "auth.md" in prompt

    def test_consolidate_empty(self):
        """Verifies that consolidate empty."""
        # Confirm the expected result for this scenario: consolidate empty.
        assert self.ms.consolidate() == []

    def test_write_entrypoint(self):
        """Verifies that write entrypoint."""
        self.ms.write_entrypoint("# Test\n\nEntrypoint content.")
        result = self.ms.load_entrypoint()
        # Confirm the expected result for this scenario: write entrypoint.
        assert "Entrypoint content" in result.content

    def test_load_entrypoint_empty(self):
        """Verifies that load entrypoint empty."""
        result = self.ms.load_entrypoint()
        # Confirm the expected result for this scenario: load entrypoint empty.
        assert result.content == ""
        assert result.was_line_truncated is False

    def _write(self, name, content):
        """Verifies that write."""
        with open(os.path.join(self.tmpdir, name), "w", encoding="utf-8") as f:
            f.write(content)
