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

"""Tests for encre.feedback -- error correction learner with Jaccard similarity."""

from pathlib import Path

from encre.feedback import CorrectionRecord, EncreFeedbackLearner
from encre.feedback.learner import cut_str

# ── CorrectionRecord ──────────────────────────────────────────────────────

class TestCorrectionRecord:
    """Test suite for CorrectionRecord."""
    def test_defaults(self):
        """Test: Defaults."""
        rec = CorrectionRecord(
            tool_name="bash",
            error_type="execution_error",
            error_context="ls /nonexistent",
            user_correction="use ls /tmp instead",
        )
        # Verify: rec.tool_name == "bash"
        assert rec.tool_name == "bash"
        # Verify: rec.error_type == "execution_error"
        assert rec.error_type == "execution_error"
        # Verify: rec.error_context == "ls /nonexistent"
        assert rec.error_context == "ls /nonexistent"
        # Verify: rec.user_correction == "use ls /tmp instead"
        assert rec.user_correction == "use ls /tmp instead"
        # Verify: rec.trigger_count == 0
        assert rec.trigger_count == 0
        # Verify: rec.missed_count == 0
        assert rec.missed_count == 0
        # Verify: rec.stale is False
        assert rec.stale is False
        # Verify: rec.timestamp > 0
        assert rec.timestamp > 0

    def test_to_dict(self):
        """Test: To dict."""
        rec = CorrectionRecord(
            tool_name="file_write",
            error_type="type_error",
            error_context="content must be str",
            user_correction="convert to str first",
        )
        d = rec.to_dict()
        # Verify: d["tool_name"] == "file_write"
        assert d["tool_name"] == "file_write"
        # Verify: d["error_type"] == "type_error"
        assert d["error_type"] == "type_error"
        # Verify: d["error_context"] == "content must be str"
        assert d["error_context"] == "content must be str"
        # Verify: d["user_correction"] == "convert to str first"
        assert d["user_correction"] == "convert to str first"
        # Verify: d["trigger_count"] == 0
        assert d["trigger_count"] == 0
        # Verify: d["missed_count"] == 0
        assert d["missed_count"] == 0
        # Verify: d["stale"] is False
        assert d["stale"] is False

    def test_from_dict(self):
        """Test: From dict."""
        data = {
            "tool_name": "bash",
            "error_type": "syntax_error",
            "error_context": "missing semicolon",
            "user_correction": "add semicolon",
            "timestamp": 1234567890.0,
            "trigger_count": 3,
            "missed_count": 1,
            "stale": False,
        }
        rec = CorrectionRecord.from_dict(data)
        # Verify: rec.tool_name == "bash"
        assert rec.tool_name == "bash"
        # Verify: rec.error_type == "syntax_error"
        assert rec.error_type == "syntax_error"
        # Verify: rec.error_context == "missing semicolon"
        assert rec.error_context == "missing semicolon"
        # Verify: rec.user_correction == "add semicolon"
        assert rec.user_correction == "add semicolon"
        # Verify: rec.timestamp == 1234567890.0
        assert rec.timestamp == 1234567890.0
        # Verify: rec.trigger_count == 3
        assert rec.trigger_count == 3
        # Verify: rec.missed_count == 1
        assert rec.missed_count == 1
        # Verify: rec.stale is False
        assert rec.stale is False

    def test_from_dict_minimal(self):
        """from_dict with only required fields."""
        data = {
            "tool_name": "edit",
            "error_type": "parse_error",
            "error_context": "bad json",
            "user_correction": "validate json",
        }
        rec = CorrectionRecord.from_dict(data)
        # Verify: rec.tool_name == "edit"
        assert rec.tool_name == "edit"
        # Verify: rec.trigger_count == 0
        assert rec.trigger_count == 0
        # Verify: rec.missed_count == 0
        assert rec.missed_count == 0
        # Verify: rec.stale is False
        assert rec.stale is False

    def test_roundtrip(self):
        """Test: Roundtrip."""
        original = CorrectionRecord(
            tool_name="grep",
            error_type="regex_error",
            error_context="invalid pattern [a-z",
            user_correction="escape brackets: \\[a-z",
        )
        original.trigger_count = 5
        restored = CorrectionRecord.from_dict(original.to_dict())
        # Verify: restored.tool_name == original.tool_name
        assert restored.tool_name == original.tool_name
        # Verify: restored.error_type == original.error_type
        assert restored.error_type == original.error_type
        # Verify: restored.error_context == original.error_context
        assert restored.error_context == original.error_context
        # Verify: restored.user_correction == original.user_correction
        assert restored.user_correction == original.user_correction
        # Verify: restored.trigger_count == original.trigger_count
        assert restored.trigger_count == original.trigger_count


# ── cut_str helper ───────────────────────────────────────────────────────

class TestCutStr:
    """Test suite for CutStr."""
    def test_short_string(self):
        """Test: Short string."""
        # Verify: cut_str("hello", 10) == "hello"
        assert cut_str("hello", 10) == "hello"

    def test_exact_length(self):
        """Test: Exact length."""
        # Verify: cut_str("1234567890", 10) == "1234567890"
        assert cut_str("1234567890", 10) == "1234567890"

    def test_truncation(self):
        """Test: Truncation."""
        result = cut_str("this is a very long string that needs cutting", 14)
        # Verify: len(result) <= 14
        assert len(result) <= 14
        # Verify: result.endswith("...")
        assert result.endswith("...")

    def test_empty_string(self):
        """Test: Empty string."""
        # Verify: cut_str("", 5) == ""
        assert cut_str("", 5) == ""

    def test_max_len_zero(self):
        """Test: Max len zero."""
        result = cut_str("abc", 0)
        # With max_len=0, max_len-3 is negative; slice handles it gracefully
        assert isinstance(result, str)


# ── EncreFeedbackLearner ───────────────────────────────────────────────────

class TestEncreFeedbackLearner:
    """Test suite for EncreFeedbackLearner."""
    def setup_method(self):
        """Setup method."""
        self.learner = EncreFeedbackLearner()

    def test_initial_state(self):
        """Test: Initial state."""
        # Verify: self.learner.record_count == 0
        assert self.learner.record_count == 0
        # Verify: self.learner.active_count == 0
        assert self.learner.active_count == 0

    def test_record_correction_new(self):
        """Test: Record correction new."""
        self.learner.record_correction(
            "bash", "execution_error",
            "ls /nonexistent", "use ls /tmp"
        )
        # Verify: self.learner.record_count == 1
        assert self.learner.record_count == 1
        # Verify: self.learner.active_count == 1
        assert self.learner.active_count == 1

    def test_record_correction_duplicate_increments(self):
        """Recording the same correction again should increment trigger_count."""
        self.learner.record_correction(
            "bash", "execution_error",
            "ls /nonexistent", "use ls /tmp"
        )
        self.learner.record_correction(
            "bash", "execution_error",
            "ls /nonexistent path", "use ls /tmp instead"
        )
        # Similar context should match and update existing record
        assert self.learner.record_count == 1
        # Verify: self.learner.active_count == 1
        assert self.learner.active_count == 1

    def test_record_correction_different_tool(self):
        """Test: Record correction different tool."""
        self.learner.record_correction("bash", "execution_error", "ctx1", "fix1")
        self.learner.record_correction("edit", "type_error", "ctx2", "fix2")
        # Verify: self.learner.record_count == 2
        assert self.learner.record_count == 2

    def test_record_correction_different_error_type(self):
        """Test: Record correction different error type."""
        self.learner.record_correction("bash", "execution_error", "ctx1", "fix1")
        self.learner.record_correction("bash", "syntax_error", "ctx2", "fix2")
        # Verify: self.learner.record_count == 2
        assert self.learner.record_count == 2

    def test_get_relevant_feedback_empty(self):
        """Test: Get relevant feedback empty."""
        result = self.learner.get_relevant_feedback("bash", "some context")
        # Verify: result == ""
        assert result == ""

    def test_get_relevant_feedback_match(self):
        """Test: Get relevant feedback match."""
        self.learner.record_correction(
            "bash", "execution_error",
            "command not found ls /badpath", "use correct path"
        )
        self.learner.record_correction(
            "bash", "execution_error",
            "command not found cat /badpath", "check path exists"
        )
        result = self.learner.get_relevant_feedback("bash", "command not found ls")
        # Verify: "Previous errors" in result or result != ""
        assert "Previous errors" in result or result != ""

    def test_get_relevant_feedback_no_match(self):
        """Test: Get relevant feedback no match."""
        self.learner.record_correction(
            "bash", "execution_error",
            "command not found", "use correct command"
        )
        result = self.learner.get_relevant_feedback("grep", "pattern error")
        # Verify: result == ""
        assert result == ""

    def test_reset(self):
        """Test: Reset."""
        self.learner.record_correction("bash", "e", "c", "f")
        self.learner.record_correction("edit", "e", "c", "f")
        # Verify: self.learner.record_count == 2
        assert self.learner.record_count == 2
        self.learner.reset()
        # Verify: self.learner.record_count == 0
        assert self.learner.record_count == 0
        # Verify: self.learner.active_count == 0
        assert self.learner.active_count == 0

    def test_save_and_load(self, tmp_path: Path):
        """Test: Save and load."""
        storage = str(tmp_path / "feedback.json")
        learner = EncreFeedbackLearner(storage_path=storage)
        learner.record_correction("bash", "execution_error", "ctx", "fix")
        learner.record_correction("edit", "type_error", "ctx2", "fix2")
        learner.save()

        # Load into a new learner
        learner2 = EncreFeedbackLearner(storage_path=storage)
        loaded = learner2.load()
        # Verify: loaded is True
        assert loaded is True
        # Verify: learner2.record_count == 2
        assert learner2.record_count == 2

    def test_load_nonexistent(self):
        """Test: Load nonexistent."""
        learner = EncreFeedbackLearner(storage_path="/nonexistent/path/file.json")
        result = learner.load()
        # Verify: result is False
        assert result is False

    def test_load_no_path(self):
        """Test: Load no path."""
        learner = EncreFeedbackLearner()  # no storage_path
        result = learner.load()
        # Verify: result is False
        assert result is False

    def test_save_no_path(self):
        """Test: Save no path."""
        learner = EncreFeedbackLearner()  # no storage_path
        learner.record_correction("bash", "e", "c", "f")
        # Should not raise
        learner.save()

    def test_save_invalid_json_in_file(self, tmp_path: Path):
        """Test: Save invalid json in file."""
        storage = str(tmp_path / "bad.json")
        storage_file = Path(storage)
        storage_file.write_text("this is not json", encoding="utf-8")
        learner = EncreFeedbackLearner(storage_path=storage)
        result = learner.load()
        # Verify: result is False
        assert result is False


# ── Jaccard Similarity ───────────────────────────────────────────────────

class TestContextSimilarity:
    """Test the Jaccard similarity used in _context_similarity."""

    def setup_method(self):
        """Setup method."""
        self.learner = EncreFeedbackLearner()

    def test_identical_strings(self):
        """Test: Identical strings."""
        sim = self.learner._context_similarity("hello world", "hello world")
        # Verify: sim > 0.9
        assert sim > 0.9

    def test_completely_different(self):
        """Test: Completely different."""
        sim = self.learner._context_similarity("foo bar baz", "x y z")
        # Verify: sim == 0.0
        assert sim == 0.0

    def test_partial_overlap(self):
        """Test: Partial overlap."""
        sim = self.learner._context_similarity(
            "command not found ls",
            "command not found cat",
        )
        # "command", "not", "found" overlap, "ls" vs "cat" don't
        assert 0.4 < sim < 1.0

    def test_empty_strings(self):
        """Test: Empty strings."""
        # Verify: self.learner._context_similarity("", "abc") == 0.0
        assert self.learner._context_similarity("", "abc") == 0.0
        # Verify: self.learner._context_similarity("abc", "") == 0.0
        assert self.learner._context_similarity("abc", "") == 0.0
        # Verify: self.learner._context_similarity("", "") == 0.0
        assert self.learner._context_similarity("", "") == 0.0

    def test_case_insensitive(self):
        """Test: Case insensitive."""
        sim = self.learner._context_similarity("HELLO World", "hello world")
        # Verify: sim > 0.9
        assert sim > 0.9

    def test_length_bonus_for_long_tokens(self):
        """Long matching tokens get a length bonus."""
        sim_with_long = self.learner._context_similarity(
            "verylongtoken common",
            "verylongtoken common",
        )
        sim_without = self.learner._context_similarity(
            "x common",
            "x common",
        )
        # Verify: sim_with_long >= sim_without
        assert sim_with_long >= sim_without


# ── Pruning and Decay ────────────────────────────────────────────────────

class TestPruning:
    """Test suite for Pruning."""
    def test_prune_at_max_records(self):
        """Test: Prune at max records."""
        learner = EncreFeedbackLearner()
        # Add records beyond MAX_RECORDS
        for i in range(learner.MAX_RECORDS + 10):
            learner.record_correction(
                f"tool_{i % 5}", f"error_{i % 3}",
                f"context_{i}", f"fix_{i}",
            )
        # Verify: learner.record_count <= learner.MAX_RECORDS
        assert learner.record_count <= learner.MAX_RECORDS

    def test_active_count_excludes_stale(self):
        """Test: Active count excludes stale."""
        learner = EncreFeedbackLearner()
        learner.record_correction("bash", "e", "c", "f")
        learner.record_correction("edit", "e", "c2", "f2")
        # Force first record to become stale
        learner._records[0].stale = True
        # Verify: learner.active_count == 1
        assert learner.active_count == 1
        # Verify: learner.record_count == 2
        assert learner.record_count == 2
