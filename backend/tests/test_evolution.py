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

"""Tests for evolution subsystem: learner, optimizer, reflex, meta-cognition."""


from encre.evolution.config import EvolutionConfig
from encre.evolution.learner import EncreEvolutionLearner, ErrorRecord, SuccessRecord
from encre.evolution.meta import CapabilityProfile, EncreMetaCognition
from encre.evolution.optimizer import EncreStrategyOptimizer
from encre.evolution.reflex import EncreReflexLoop, ReflexResult


class TestEvolutionConfig:
    """Test suite for EvolutionConfig."""
    def test_defaults(self):
        """Test: Defaults."""
        cfg = EvolutionConfig()
        # Verify: cfg.learner_enabled is True
        assert cfg.learner_enabled is True
        # Verify: cfg.optimizer_enabled is True
        assert cfg.optimizer_enabled is True
        # Verify: cfg.reflex_enabled is True
        assert cfg.reflex_enabled is True
        # Verify: cfg.meta_enabled is True
        assert cfg.meta_enabled is True

    def test_custom(self):
        """Test: Custom."""
        cfg = EvolutionConfig(learner_enabled=False, optimizer_enabled=False)
        # Verify: cfg.learner_enabled is False
        assert cfg.learner_enabled is False
        # Verify: cfg.optimizer_enabled is False
        assert cfg.optimizer_enabled is False

    def test_create_default(self):
        """Test: Create default."""
        cfg = EvolutionConfig.create_default()
        # Verify: cfg.learner is not None
        assert cfg.learner is not None
        # Verify: cfg.optimizer is not None
        assert cfg.optimizer is not None
        # Verify: cfg.reflex is not None
        assert cfg.reflex is not None
        # Verify: cfg.meta is not None
        assert cfg.meta is not None

    def test_create_disabled(self):
        """Test: Create disabled."""
        cfg = EvolutionConfig.create_disabled()
        # Verify: cfg.learner_enabled is False
        assert cfg.learner_enabled is False
        # Verify: cfg.meta_enabled is False
        assert cfg.meta_enabled is False


class TestRecords:
    """Test suite for Records."""
    def test_success_record(self):
        """Test: Success record."""
        sr = SuccessRecord(tool_name="bash", intent_signature="run tests", param_pattern='{"cmd": "pytest"}', outcome="passed")  # noqa: E501
        # Verify: sr.tool_name == "bash"
        assert sr.tool_name == "bash"
        # Verify: sr.intent_signature == "run tests"
        assert sr.intent_signature == "run tests"
        # Verify: sr.reuse_count == 0
        assert sr.reuse_count == 0

    def test_error_record(self):
        """Test: Error record."""
        er = ErrorRecord(tool_name="grep", error_type="no_match", error_context="no matches found", correction="use broader pattern")  # noqa: E501
        # Verify: er.tool_name == "grep"
        assert er.tool_name == "grep"
        # Verify: er.error_type == "no_match"
        assert er.error_type == "no_match"
        # Verify: er.correction == "use broader pattern"
        assert er.correction == "use broader pattern"
        # Verify: er.resolved is False
        assert er.resolved is False

    def test_record_serialization(self):
        """Test: Record serialization."""
        sr = SuccessRecord(tool_name="bash", intent_signature="run", param_pattern="{}", outcome="ok")  # noqa: E501
        d = sr.to_dict()
        # Verify: d["tool_name"] == "bash"
        assert d["tool_name"] == "bash"
        sr2 = SuccessRecord.from_dict(d)
        # Verify: sr2.tool_name == sr.tool_name
        assert sr2.tool_name == sr.tool_name


class TestEvolutionLearner:
    """Test suite for EvolutionLearner."""
    def setup_method(self):
        """Setup method."""
        self.learner = EncreEvolutionLearner()

    def test_record_error(self):
        """Test: Record error."""
        self.learner.record_error("bash", "timeout", "command timed out", "retry with backoff")
        # Verify: len(self.learner._errors) == 1
        assert len(self.learner._errors) == 1
        # Verify: self.learner._errors[0].tool_name == "bash"
        assert self.learner._errors[0].tool_name == "bash"

    def test_record_success(self):
        """Test: Record success."""
        self.learner.record_success("bash", "run tests", {"cmd": "pytest"}, "passed")
        # Verify: len(self.learner._successes) == 1
        assert len(self.learner._successes) == 1
        # Verify: self.learner._successes[0].tool_name == "bash"
        assert self.learner._successes[0].tool_name == "bash"

    def test_record_correction_matches_open_error(self):
        """Test: Record correction matches open error."""
        self.learner.record_error("bash", "timeout", "command timed out when running git status", "")  # noqa: E501
        self.learner.record_correction("bash", "command timed out when running", "use timeout flag")
        # Verify: self.learner._errors[0].resolved is True
        assert self.learner._errors[0].resolved is True

    def test_record_correction_no_match(self):
        """Test: Record correction no match."""
        self.learner.record_error("bash", "timeout", "command timed out running git", "")
        self.learner.record_correction("bash", "completely different error about permissions", "fix perms")  # noqa: E501
        # Verify: self.learner._errors[0].resolved is False
        assert self.learner._errors[0].resolved is False

    def test_similar_error_reuse(self):
        """Test: Similar error reuse."""
        self.learner.record_error("bash", "timeout", "command timed out", "")
        self.learner.record_error("bash", "timeout", "command timed out running git", "use timeout")
        # Second call should reuse the first record (similar context)
        assert len(self.learner._errors) == 1
        # Verify: self.learner._errors[0].trigger_count == 1
        assert self.learner._errors[0].trigger_count == 1

    def test_mark_error_resolved(self):
        """Test: Mark error resolved."""
        self.learner.record_error("bash", "timeout", "command timed out", "")
        self.learner.mark_error_resolved("bash", "command timed out")
        # Verify: self.learner._errors[0].resolved is True
        assert self.learner._errors[0].resolved is True

    def test_get_guidance(self):
        """Test: Get guidance."""
        self.learner.record_error("bash", "timeout", "command timed out", "use timeout flag")
        self.learner.record_success("bash", "run tests", {"cmd": "pytest"}, "tests passed")
        guidance = self.learner.get_guidance("bash", "run tests with timeout")
        # Verify: isinstance(guidance, str)
        assert isinstance(guidance, str)

    def test_get_guidance_unknown_tool(self):
        """Test: Get guidance unknown tool."""
        guidance = self.learner.get_guidance("unknown_tool", "some context")
        # Verify: guidance == ""
        assert guidance == ""

    def test_get_tool_best_params(self):
        """Test: Get tool best params."""
        self.learner.record_success("bash", "run tests", {"cmd": "pytest -v"}, "passed")
        params = self.learner.get_tool_best_params("bash", "run tests")
        # Verify: params is not None
        assert params is not None
        # Verify: params["cmd"] == "pytest -v"
        assert params["cmd"] == "pytest -v"

    def test_get_tool_best_params_none(self):
        """Test: Get tool best params none."""
        params = self.learner.get_tool_best_params("nonexistent", "test")
        # Verify: params is None
        assert params is None

    def test_get_statistics(self):
        """Test: Get statistics."""
        self.learner.record_error("bash", "timeout", "err1", "fix1")
        self.learner.record_success("bash", "run", {}, "ok")
        stats = self.learner.get_statistics()
        # Verify: stats["total_errors"] >= 1
        assert stats["total_errors"] >= 1
        # Verify: stats["total_successes"] >= 1
        assert stats["total_successes"] >= 1

    def test_save_load(self):
        """Test: Save load."""
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "learner.json")
        self.learner._storage_path = path
        self.learner.record_error("bash", "timeout", "err", "fix")
        self.learner.save()
        learner2 = EncreEvolutionLearner(storage_path=path)
        # Verify: learner2.load() is True
        assert learner2.load() is True
        # Verify: len(learner2._errors) == 1
        assert len(learner2._errors) == 1
        import shutil
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    def test_load_nonexistent(self):
        """Test: Load nonexistent."""
        learner = EncreEvolutionLearner(storage_path="/nonexistent/path/file.json")
        # Verify: learner.load() is False
        assert learner.load() is False

    def test_reset(self):
        """Test: Reset."""
        self.learner.record_error("bash", "timeout", "err", "fix")
        self.learner.record_success("bash", "run", {}, "ok")
        self.learner.reset()
        # Verify: len(self.learner._errors) == 0
        assert len(self.learner._errors) == 0
        # Verify: len(self.learner._successes) == 0
        assert len(self.learner._successes) == 0


class TestStrategyOptimizer:
    """Test suite for StrategyOptimizer."""
    def setup_method(self):
        """Setup method."""
        self.optimizer = EncreStrategyOptimizer()

    def test_record_outcome_success(self):
        """Test: Record outcome success."""
        self.optimizer.record_outcome("bash", {"cmd": "ls -la"}, success=True, latency_ms=100)
        stats = self.optimizer.get_statistics()
        # Verify: "bash" in stats
        assert "bash" in stats
        # Verify: stats["bash"]["total_samples"] == 1
        assert stats["bash"]["total_samples"] == 1

    def test_record_outcome_failure(self):
        """Test: Record outcome failure."""
        self.optimizer.record_outcome("bash", {"cmd": "rm -rf /"}, success=False)
        stats = self.optimizer.get_statistics()
        # Verify: stats["bash"]["total_samples"] == 1
        assert stats["bash"]["total_samples"] == 1

    def test_suggest_strategy(self):
        """Test: Suggest strategy."""
        for _ in range(5):
            self.optimizer.record_outcome("bash", {"cmd": "ls -la"}, success=True)
        suggestion = self.optimizer.suggest_strategy("bash", "list files")
        # Verify: suggestion is not None
        assert suggestion is not None
        # Verify: "_strategy_hint" in suggestion
        assert "_strategy_hint" in suggestion

    def test_suggest_strategy_insufficient_samples(self):
        """Test: Suggest strategy insufficient samples."""
        self.optimizer.record_outcome("bash", {"cmd": "ls"}, success=True)
        # Only 1 sample, below MIN_SAMPLES_FOR_RECOMMENDATION
        suggestion = self.optimizer.suggest_strategy("bash", "list")
        # Verify: suggestion is None
        assert suggestion is None

    def test_suggest_strategy_unknown_tool(self):
        """Test: Suggest strategy unknown tool."""
        # Verify: self.optimizer.suggest_strategy("nonexistent", "test") is None
        assert self.optimizer.suggest_strategy("nonexistent", "test") is None

    def test_get_fallback(self):
        """Test: Get fallback."""
        for _ in range(5):
            self.optimizer.record_outcome("bash", {"cmd": "ls -la"}, success=True)
        for _ in range(5):
            self.optimizer.record_outcome("bash", {"cmd": "pwd"}, success=True)
        fallback = self.optimizer.get_fallback("bash", {"cmd": "ls -la"})
        # Verify: fallback is not None
        assert fallback is not None
        # Verify: "_fallback_hint" in fallback
        assert "_fallback_hint" in fallback

    def test_get_statistics(self):
        """Test: Get statistics."""
        self.optimizer.record_outcome("bash", {"cmd": "ls"}, success=True)
        self.optimizer.record_outcome("grep", {"pattern": "foo"}, success=False)
        stats = self.optimizer.get_statistics()
        # Verify: "bash" in stats
        assert "bash" in stats
        # Verify: "grep" in stats
        assert "grep" in stats

    def test_reset(self):
        """Test: Reset."""
        self.optimizer.record_outcome("bash", {"cmd": "ls"}, success=True)
        self.optimizer.reset()
        # Verify: self.optimizer.suggest_strategy("bash", "test") is None
        assert self.optimizer.suggest_strategy("bash", "test") is None


class TestReflexLoop:
    """Test suite for ReflexLoop."""
    def setup_method(self):
        """Setup method."""
        self.reflex = EncreReflexLoop(enabled=True)

    def test_reflect_empty_tools(self):
        """Test: Reflect empty tools."""
        result = self.reflex.reflect(turn_number=1, tool_results=[], turn_latency_ms=100)
        # Verify: isinstance(result, ReflexResult)
        assert isinstance(result, ReflexResult)
        # Verify: result.turn_number == 1
        assert result.turn_number == 1
        # Verify: result.score < 1.0
        assert result.score < 1.0
        # Verify: len(result.issues) > 0
        assert len(result.issues) > 0

    def test_reflect_all_success(self):
        """Test: Reflect all success."""
        result = self.reflex.reflect(turn_number=2, tool_results=[
            {"tool_name": "file_read", "is_error": False},
            {"tool_name": "grep", "is_error": False},
        ], turn_latency_ms=2000)
        # Verify: result.score > 0.5
        assert result.score > 0.5
        # Verify: result.should_retry is False
        assert result.should_retry is False

    def test_reflect_all_errors(self):
        """Test: Reflect all errors."""
        result = self.reflex.reflect(turn_number=3, tool_results=[
            {"tool_name": "bash", "is_error": True},
            {"tool_name": "bash", "is_error": True},
        ], turn_latency_ms=500)
        # Verify: result.score < 0.5
        assert result.score < 0.5
        # error_rate = 2/2 = 1.0, should_retry = error_rate > 0.5 and total > 1
        assert result.should_retry is True

    def test_consecutive_failures_detected(self):
        """Test: Consecutive failures detected."""
        for i in range(4):
            self.reflex.reflect(turn_number=i, tool_results=[
                {"tool_name": "bash", "is_error": True},
            ], turn_latency_ms=100)
        result = self.reflex.reflect(turn_number=5, tool_results=[
            {"tool_name": "bash", "is_error": True},
        ], turn_latency_ms=100)
        # Verify: any("consecutive" in issue.lower() for issue in result.issues)
        assert any("consecutive" in issue.lower() for issue in result.issues)

    def test_duplicate_calls_detected(self):
        """Test: Duplicate calls detected."""
        result = self.reflex.reflect(turn_number=1, tool_results=[
            {"tool_name": "grep", "is_error": False},
            {"tool_name": "grep", "is_error": False},
            {"tool_name": "grep", "is_error": False},
            {"tool_name": "grep", "is_error": False},
        ], turn_latency_ms=100)
        # Verify: any("repeated" in issue.lower() for issue in result.issues)
        assert any("repeated" in issue.lower() for issue in result.issues)

    def test_slow_turn_detected(self):
        """Test: Slow turn detected."""
        result = self.reflex.reflect(turn_number=1, tool_results=[
            {"tool_name": "bash", "is_error": False},
        ], turn_latency_ms=120000)
        # Verify: any("slow" in issue.lower() for issue in result.issues)
        assert any("slow" in issue.lower() for issue in result.issues)

    def test_get_improvement_context(self):
        """Test: Get improvement context."""
        self.reflex.reflect(turn_number=1, tool_results=[
            {"tool_name": "bash", "is_error": True},
        ], turn_latency_ms=100)
        ctx = self.reflex.get_improvement_context()
        # Verify: isinstance(ctx, str)
        assert isinstance(ctx, str)

    def test_get_improvement_context_empty(self):
        """Test: Get improvement context empty."""
        reflex = EncreReflexLoop(enabled=True)
        # Verify: reflex.get_improvement_context() == ""
        assert reflex.get_improvement_context() == ""

    def test_get_trend_stable(self):
        """Test: Get trend stable."""
        for i in range(5):
            self.reflex.reflect(turn_number=i, tool_results=[
                {"tool_name": "bash", "is_error": False},
            ], turn_latency_ms=100)
        # Verify: self.reflex.get_trend() == "stable"
        assert self.reflex.get_trend() == "stable"

    def test_get_average_score(self):
        """Test: Get average score."""
        self.reflex.reflect(turn_number=1, tool_results=[
            {"tool_name": "bash", "is_error": False},
        ], turn_latency_ms=100)
        avg = self.reflex.get_average_score()
        # Verify: 0.0 <= avg <= 1.0
        assert 0.0 <= avg <= 1.0

    def test_reset(self):
        """Test: Reset."""
        self.reflex.reflect(turn_number=1, tool_results=[
            {"tool_name": "bash", "is_error": False},
        ], turn_latency_ms=100)
        self.reflex.reset()
        # Verify: self.reflex.get_average_score() == 1.0
        assert self.reflex.get_average_score() == 1.0
        # Verify: self.reflex.get_improvement_context() == ""
        assert self.reflex.get_improvement_context() == ""

    def test_disabled_reflex(self):
        """Test: Disabled reflex."""
        reflex = EncreReflexLoop(enabled=False)
        result = reflex.reflect(turn_number=1, tool_results=[], turn_latency_ms=100)
        # Verify: result.score == 1.0
        assert result.score == 1.0
        # Verify: result.issues == []
        assert result.issues == []


class TestMetaCognition:
    """Test suite for MetaCognition."""
    def setup_method(self):
        """Setup method."""
        self.meta = EncreMetaCognition()

    def test_capability_profile_default(self):
        """Test: Capability profile default."""
        profile = CapabilityProfile(domain="python")
        # Verify: profile.domain == "python"
        assert profile.domain == "python"
        # Verify: profile.score == 0.5
        assert profile.score == 0.5
        # Verify: profile.confidence == 0.0
        assert profile.confidence == 0.0
        # Verify: profile.sample_count == 0
        assert profile.sample_count == 0

    def test_capability_profile_update(self):
        """Test: Capability profile update."""
        profile = CapabilityProfile(domain="python")
        profile.update(success=True, difficulty=0.5)
        # Verify: profile.sample_count == 1
        assert profile.sample_count == 1
        # Verify: profile.score > 0.5
        assert profile.score > 0.5

    def test_assess_turn(self):
        """Test: Assess turn."""
        self.meta.assess_turn("write a python function to read a file", [
            {"tool_name": "file_read", "is_error": False},
        ])
        profile = self.meta.get_profile("file_operations")
        # Verify: isinstance(profile, dict)
        assert isinstance(profile, dict)
        # Verify: profile["score"] > 0.5
        assert profile["score"] > 0.5

    def test_get_profile_unknown(self):
        """Test: Get profile unknown."""
        result = self.meta.get_profile("unknown_domain")
        # Verify: isinstance(result, dict)
        assert isinstance(result, dict)
        # Verify: result["confidence"] == 0.0
        assert result["confidence"] == 0.0

    def test_get_all_profiles(self):
        """Test: Get all profiles."""
        self.meta.assess_turn("run tests with pytest", [
            {"tool_name": "bash", "is_error": False},
        ])
        all_profiles = self.meta.get_profile()
        # Verify: isinstance(all_profiles, dict)
        assert isinstance(all_profiles, dict)

    def test_get_weakness_report(self):
        # Create low score with high confidence
        """Test: Get weakness report."""
        for _ in range(25):
            self.meta.assess_turn("use bash to run a broken command", [
                {"tool_name": "bash", "is_error": True},
            ])
        report = self.meta.get_weakness_report()
        # Verify: isinstance(report, list)
        assert isinstance(report, list)

    def test_should_delegate(self):
        """Test: Should delegate."""
        should, _reason = self.meta.should_delegate("design a system architecture")
        # No confidence yet, should not delegate
        assert should is False

    def test_get_self_awareness_context(self):
        """Test: Get self awareness context."""
        ctx = self.meta.get_self_awareness_context()
        # Verify: isinstance(ctx, str)
        assert isinstance(ctx, str)

    def test_record_delegation(self):
        """Test: Record delegation."""
        self.meta.record_delegation("complex task", "sub_agent", True)
        # Should not crash

    def test_reset(self):
        """Test: Reset."""
        self.meta.assess_turn("run tests", [{"tool_name": "bash", "is_error": False}])
        self.meta.reset()
        # Verify: self.meta.get_profile() == {}
        assert self.meta.get_profile() == {}
