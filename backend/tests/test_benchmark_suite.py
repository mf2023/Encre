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

"""Tests for the benchmark evaluation suite: scoring, diagnosis, and summarization.

These tests validate how raw benchmark task results are scored against required
tokens, classified into failure buckets, and aggregated into summaries/analyses.
"""

from encre.eval.benchmark_suite import (
    analyze_benchmark_results,
    classify_benchmark_result,
    normalize_task,
    score_task_output,
    summarize_benchmark_results,
)


class TestBenchmarkScoring:
    """Verify task-output scoring (must_include/any_of/must_exclude coverage)."""
    def test_score_task_output_supports_any_of_and_excludes(self):
        """A passing task must include all required tokens, satisfy any_of, and exclude forbidden text."""
        task = normalize_task({
            "id": "research-1",
            "must_include": ["python", "release"],
            "any_of": ["october", "2024"],
            "must_exclude": ["hallucinated"],
        })
        result = score_task_output(task, "Python 3.13 release landed in October 2024.")
        # All required tokens present, any_of satisfied, nothing forbidden found
        assert result["passed"] is True
        # Verify: result["coverage"] == 1.0
        assert result["coverage"] == 1.0
        # Verify: result["forbidden_found"] == []
        assert result["forbidden_found"] == []

    def test_score_task_output_marks_missing_tokens(self):
        """Tasks with missing required tokens must be marked failed and list the missing ones."""
        task = normalize_task({
            "id": "coding-1",
            "must_include": ["loop", "retry", "test"],
        })
        result = score_task_output(task, "Loop behavior is described, but verification is absent.")
        # Output is missing the "retry" and "test" required tokens -> failure
        assert result["passed"] is False
        # Verify: "retry" in result["missing"]
        assert "retry" in result["missing"]
        # Verify: "test" in result["missing"]
        assert "test" in result["missing"]


class TestBenchmarkDiagnosis:
    """Verify benchmark-result classification into failure buckets."""
    def test_classify_benchmark_result_detects_tool_selection_gap(self):
        """Zero tool calls despite preferred tools is diagnosed as a tool_selection_gap."""
        task = normalize_task({
            "id": "coding-2",
            "preferred_tools": ["file_read", "grep"],
            "must_include": ["file", "function"],
        })
        result = {
            "passed": False,
            "finish_reason": "stop",
            "final_text": "You should inspect the project.",
            "tool_calls": 0,
            "tool_error_count": 0,
            "turn_count": 2,
            "stuck_event_count": 0,
            "score": {"coverage": 0.25, "missing": ["file", "function"]},
            "tool_names": [],
            "task_stage": "discover",
            "task_stage_history": ["discover"],
        }
        diagnosis = classify_benchmark_result(task, result)
        # Zero tool calls despite preferred tools -> the agent never selected the right tools
        assert diagnosis["bucket"] == "tool_selection_gap"

    def test_classify_benchmark_result_detects_long_horizon_drift(self):
        """Exceeding max turns with low coverage is diagnosed as long_horizon_drift."""
        task = normalize_task({
            "id": "long-1",
            "max_turn_count": 8,
            "must_include": ["summary"],
        })
        result = {
            "passed": False,
            "finish_reason": "stop",
            "final_text": "Partial notes only.",
            "tool_calls": 6,
            "tool_error_count": 0,
            "turn_count": 11,
            "stuck_event_count": 1,
            "score": {"coverage": 0.5, "missing": ["summary"]},
            "tool_names": ["file_read"],
            "task_stage": "report",
            "task_stage_history": ["discover", "plan", "execute"],
        }
        diagnosis = classify_benchmark_result(task, result)
        # Verify: diagnosis["bucket"] == "long_horizon_drift"
        assert diagnosis["bucket"] == "long_horizon_drift"


class TestBenchmarkSummary:
    """Verify benchmark summarization and analysis aggregation."""
    def test_summarize_benchmark_results_groups_tracks_and_buckets(self):
        """Summary aggregates pass rates and failure buckets across tracks/categories/difficulties."""
        results = [
            {
                "id": "a",
                "track": "claude_code",
                "category": "coding_fix",
                "difficulty": "medium",
                "tags": ["coding", "verification"],
                "passed": True,
                "duration_ms": 100,
                "tool_calls": 2,
                "turn_count": 3,
                "prompt_build_ms": 20,
                "first_model_event_ms": 40,
                "model_total_ms": 80,
                "stuck_event_count": 0,
                "delegate_count": 0,
                "tool_error_count": 0,
                "score": {"coverage": 1.0},
                "diagnosis": {"bucket": "passed"},
            },
            {
                "id": "b",
                "track": "manus",
                "category": "research_synthesis",
                "difficulty": "hard",
                "tags": ["research"],
                "passed": False,
                "duration_ms": 200,
                "tool_calls": 0,
                "turn_count": 4,
                "prompt_build_ms": 30,
                "first_model_event_ms": 90,
                "model_total_ms": 150,
                "stuck_event_count": 1,
                "delegate_count": 1,
                "tool_error_count": 1,
                "score": {"coverage": 0.25},
                "diagnosis": {"bucket": "tool_selection_gap"},
            },
        ]
        summary = summarize_benchmark_results(results)
        # Verify: summary["task_count"] == 2
        assert summary["task_count"] == 2
        # Verify: summary["failure_buckets"]["tool_selection_gap"] == 1
        assert summary["failure_buckets"]["tool_selection_gap"] == 1
        # Verify: summary["by_track"]["claude_code"]["pass_rate"] == 1.0
        assert summary["by_track"]["claude_code"]["pass_rate"] == 1.0
        # Verify: summary["by_category"]["research_synthesis"]["failed"] == 1
        assert summary["by_category"]["research_synthesis"]["failed"] == 1
        # Verify: summary["by_difficulty"]["hard"]["failed"] == 1
        assert summary["by_difficulty"]["hard"]["failed"] == 1
        # Verify: summary["by_track"]["manus"]["avg_first_model_event_ms"] == 90.0
        assert summary["by_track"]["manus"]["avg_first_model_event_ms"] == 90.0

    def test_analyze_benchmark_results_surfaces_priorities(self):
        """Analysis surfaces the slowest tasks and prioritized fixes by failure bucket."""
        results = [
            {
                "id": "slow-1",
                "track": "manus",
                "category": "research_synthesis",
                "difficulty": "hard",
                "tags": ["research"],
                "passed": False,
                "duration_ms": 1200,
                "tool_calls": 1,
                "turn_count": 6,
                "first_model_event_ms": 500,
                "stuck_event_count": 2,
                "tool_error_count": 1,
                "delegate_count": 0,
                "score": {"coverage": 0.25},
                "diagnosis": {"bucket": "runtime_or_budget_failure", "signals": ["finish_reason=max_tokens"]},
            },
            {
                "id": "gap-1",
                "track": "claude_code",
                "category": "coding_fix",
                "difficulty": "medium",
                "tags": ["coding"],
                "passed": False,
                "duration_ms": 800,
                "tool_calls": 0,
                "turn_count": 3,
                "first_model_event_ms": 120,
                "stuck_event_count": 0,
                "tool_error_count": 0,
                "delegate_count": 0,
                "score": {"coverage": 0.2},
                "diagnosis": {"bucket": "tool_selection_gap", "signals": ["no tool calls despite preferred tools"]},
            },
        ]
        analysis = analyze_benchmark_results(results, top_n=2)
        # Verify: analysis["top_slowest_tasks"][0]["id"] == "slow-1"
        assert analysis["top_slowest_tasks"][0]["id"] == "slow-1"
        # Verify: analysis["top_first_token_latency_tasks"][0]["id"] == "slow-1"
        assert analysis["top_first_token_latency_tasks"][0]["id"] == "slow-1"
        # Verify: analysis["prioritized_fixes"][0]["bucket"] in {"runtime_or_budget_failure", "tool_selection_gap"}
        assert analysis["prioritized_fixes"][0]["bucket"] in {"runtime_or_budget_failure", "tool_selection_gap"}
