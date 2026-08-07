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

"""Tests for encre.telemetry -- agent event recording and session summaries.

Note: test_security_config.py already covers basic ToolCallRecord, TurnRecord,
RetryRecord, record_tool_call, record_turn, record_retry, get_summary, flush,
reset, and disabled telemetry. This file adds edge case and comprehensive tests.
"""

import os
import tempfile
import time

from encre.telemetry import EncreTelemetry, RetryRecord, ToolCallRecord, TurnRecord

# Redirect telemetry data to a temp directory so tests never pollute
# the real production telemetry directory (~/.dunimd/encre/telemetry/).
_test_telemetry_dir = tempfile.mkdtemp(prefix="encre_test_telemetry_")
os.environ["ENCRE_DATA_DIR"] = _test_telemetry_dir

# ── Edge Cases: Empty Telemetry ──────────────────────────────────────────

class TestEmptyTelemetry:
    """Test cases covering empty telemetry.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_get_summary_with_no_data(self):
        """Verifies that get summary with no data."""
        tel = EncreTelemetry()
        summary = tel.get_summary()
        # Confirm the expected result for this scenario: get summary with no data.
        assert summary["total_tool_calls"] == 0
        assert summary["total_turns"] == 0
        assert summary["successful_tool_calls"] == 0
        assert summary["failed_tool_calls"] == 0
        assert summary["avg_tool_latency_ms"] == 0.0
        assert summary["avg_turn_latency_ms"] == 0.0
        assert summary["total_events"] == 0
        assert summary["compactions"] == 0
        assert summary["tool_usage"] == {}
        assert summary["total_retries"] == 0
        assert summary["retry_by_error"] == {}

    def test_flush_with_no_data(self):
        """Verifies that flush with no data."""
        tel = EncreTelemetry()
        result = tel.flush()
        # Confirm the expected result for this scenario: flush with no data.
        assert isinstance(result, dict)
        assert result["total_tool_calls"] == 0


# ── Tool Call Records ────────────────────────────────────────────────────

class TestToolCallRecordFields:
    """Test cases covering tool call record fields.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_default_tokens_used(self):
        """Verifies that default tokens used."""
        rec = ToolCallRecord(tool_name="test", latency_ms=100.0, success=True)
        # Confirm the expected result for this scenario: default tokens used.
        assert rec.tokens_used == 0

    def test_default_error_message(self):
        """Verifies that default error message."""
        rec = ToolCallRecord(tool_name="test", latency_ms=100.0, success=True)
        # Confirm the expected result for this scenario: default error message.
        assert rec.error_message == ""

    def test_timestamp_auto_generated(self):
        """Verifies that timestamp auto generated."""
        before = time.time()
        rec = ToolCallRecord(tool_name="test", latency_ms=100.0, success=True)
        after = time.time()
        # Confirm the expected result for this scenario: timestamp auto generated.
        assert before <= rec.timestamp <= after

    def test_with_error_message(self):
        """Verifies that with error message."""
        rec = ToolCallRecord(
            tool_name="bash",
            latency_ms=0.0,
            success=False,
            error_message="command not found",
        )
        # Confirm the expected result for this scenario: with error message.
        assert rec.error_message == "command not found"
        assert rec.success is False


# ── Turn Records ─────────────────────────────────────────────────────────

class TestTurnRecordFields:
    """Test cases covering turn record fields.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_default_compact_triggered(self):
        """Verifies that default compact triggered."""
        rec = TurnRecord(turn_number=1, event_count=5, latency_ms=3000.0)
        # Confirm the expected result for this scenario: default compact triggered.
        assert rec.compact_triggered is False

    def test_default_token_usage(self):
        """Verifies that default token usage."""
        rec = TurnRecord(turn_number=1, event_count=5, latency_ms=3000.0)
        # Confirm the expected result for this scenario: default token usage.
        assert rec.token_usage == {}

    def test_with_token_usage(self):
        """Verifies that with token usage."""
        rec = TurnRecord(
            turn_number=2,
            event_count=10,
            latency_ms=5000.0,
            token_usage={"prompt": 1000, "completion": 200},
        )
        # Confirm the expected result for this scenario: with token usage.
        assert rec.token_usage["prompt"] == 1000
        assert rec.token_usage["completion"] == 200

    def test_with_compact_triggered(self):
        """Verifies that with compact triggered."""
        rec = TurnRecord(
            turn_number=3,
            event_count=8,
            latency_ms=4000.0,
            compact_triggered=True,
        )
        # Confirm the expected result for this scenario: with compact triggered.
        assert rec.compact_triggered is True


# ── Retry Records ────────────────────────────────────────────────────────

class TestRetryRecordFields:
    """Test cases covering retry record fields.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_timestamp_auto_generated(self):
        """Verifies that timestamp auto generated."""
        before = time.time()
        rec = RetryRecord(attempt=1, error_type="exception", error_detail="timeout", delay_s=2.0)
        after = time.time()
        # Confirm the expected result for this scenario: timestamp auto generated.
        assert before <= rec.timestamp <= after

    def test_full_record(self):
        """Verifies that full record."""
        rec = RetryRecord(
            attempt=3,
            error_type="http_status",
            error_detail="503 Service Unavailable",
            delay_s=5.0,
        )
        # Confirm the expected result for this scenario: full record.
        assert rec.attempt == 3
        assert rec.error_type == "http_status"
        assert rec.error_detail == "503 Service Unavailable"
        assert rec.delay_s == 5.0


# ── Comprehensive Summary Tests ──────────────────────────────────────────

class TestSummaryComprehensive:
    """Test cases covering summary comprehensive.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.tel = EncreTelemetry()

    def test_tool_usage_counts_unique(self):
        """Verifies that tool usage counts unique."""
        self.tel.record_tool_call("bash", 100.0, True)
        self.tel.record_tool_call("bash", 200.0, True)
        self.tel.record_tool_call("edit", 150.0, True)
        self.tel.record_tool_call("grep", 50.0, True)
        self.tel.record_tool_call("bash", 300.0, True)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: tool usage counts unique.
        assert summary["tool_usage"]["bash"] == 3
        assert summary["tool_usage"]["edit"] == 1
        assert summary["tool_usage"]["grep"] == 1

    def test_successful_vs_failed_counts(self):
        """Verifies that successful vs failed counts."""
        self.tel.record_tool_call("bash", 100.0, True)
        self.tel.record_tool_call("bash", 100.0, False, error_message="fail")
        self.tel.record_tool_call("edit", 100.0, True)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: successful vs failed counts.
        assert summary["total_tool_calls"] == 3
        assert summary["successful_tool_calls"] == 2
        assert summary["failed_tool_calls"] == 1

    def test_avg_latencies(self):
        """Verifies that avg latencies."""
        self.tel.record_tool_call("a", 100.0, True)
        self.tel.record_tool_call("b", 200.0, True)
        self.tel.record_tool_call("c", 300.0, True)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: avg latencies.
        assert summary["avg_tool_latency_ms"] == 200.0

    def test_avg_turn_latencies(self):
        """Verifies that avg turn latencies."""
        self.tel.record_turn(1, 5, 1000.0)
        self.tel.record_turn(2, 3, 3000.0)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: avg turn latencies.
        assert summary["avg_turn_latency_ms"] == 2000.0

    def test_total_events(self):
        """Verifies that total events."""
        self.tel.record_turn(1, 5, 1000.0)
        self.tel.record_turn(2, 3, 2000.0)
        self.tel.record_turn(3, 7, 1500.0)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: total events.
        assert summary["total_events"] == 15

    def test_compactions_count(self):
        """Verifies that compactions count."""
        self.tel.record_turn(1, 5, 1000.0, compact_triggered=False)
        self.tel.record_turn(2, 3, 2000.0, compact_triggered=True)
        self.tel.record_turn(3, 7, 1500.0, compact_triggered=True)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: compactions count.
        assert summary["compactions"] == 2

    def test_session_duration(self):
        """Verifies that session duration."""
        tel = EncreTelemetry()
        # Session started at _session_started_at
        summary = tel.get_summary()
        # Confirm the expected result for this scenario: session duration.
        assert summary["session_duration_s"] >= 0.0

    def test_retry_summary(self):
        """Verifies that retry summary."""
        self.tel.record_retry(1, "http_status", "429", 1.0)
        self.tel.record_retry(2, "http_status", "503", 2.0)
        self.tel.record_retry(1, "exception", "timeout", 3.0)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: retry summary.
        assert summary["total_retries"] == 3


# ── Reset Behavior ───────────────────────────────────────────────────────

class TestReset:
    """Test cases covering reset.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_reset_clears_all_lists(self):
        """Verifies that reset clears all lists."""
        tel = EncreTelemetry()
        tel.record_tool_call("bash", 100.0, True)
        tel.record_turn(1, 2, 1000.0)
        tel.record_retry(1, "e", "d", 1.0)
        # Confirm the expected result for this scenario: reset clears all lists.
        assert len(tel.tool_calls) == 1
        assert len(tel.turns) == 1
        assert len(tel.retries) == 1

        tel.reset()
        assert len(tel.tool_calls) == 0
        assert len(tel.turns) == 0
        assert len(tel.retries) == 0

    def test_reset_resets_session_start(self):
        """Verifies that reset resets session start."""
        tel = EncreTelemetry()
        old_start = tel._session_started_at
        tel.reset()
        # Confirm the expected result for this scenario: reset resets session start.
        assert tel._session_started_at >= old_start

    def test_summary_after_reset_is_empty(self):
        """Verifies that summary after reset is empty."""
        tel = EncreTelemetry()
        tel.record_tool_call("bash", 100.0, True)
        tel.reset()
        summary = tel.get_summary()
        # Confirm the expected result for this scenario: summary after reset is empty.
        assert summary["total_tool_calls"] == 0
        assert summary["total_turns"] == 0
        assert summary["total_retries"] == 0


# ── Disabled Telemetry ───────────────────────────────────────────────────

class TestDisabledTelemetry:
    """Test cases covering disabled telemetry.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_record_tool_call_noop(self):
        """Verifies that record tool call noop."""
        tel = EncreTelemetry(enabled=False)
        tel.record_tool_call("bash", 100.0, True)
        # Confirm the expected result for this scenario: record tool call noop.
        assert len(tel.tool_calls) == 0

    def test_record_turn_noop(self):
        """Verifies that record turn noop."""
        tel = EncreTelemetry(enabled=False)
        tel.record_turn(1, 2, 1000.0)
        # Confirm the expected result for this scenario: record turn noop.
        assert len(tel.turns) == 0

    def test_record_retry_noop(self):
        """Verifies that record retry noop."""
        tel = EncreTelemetry(enabled=False)
        tel.record_retry(1, "e", "d", 1.0)
        # Confirm the expected result for this scenario: record retry noop.
        assert len(tel.retries) == 0

    def test_constructor_default_enabled(self):
        """Verifies that constructor default enabled."""
        tel = EncreTelemetry()
        # Confirm the expected result for this scenario: constructor default enabled.
        assert tel.enabled is True

    def test_constructor_explicitly_disabled(self):
        """Verifies that constructor explicitly disabled."""
        tel = EncreTelemetry(enabled=False)
        # Confirm the expected result for this scenario: constructor explicitly disabled.
        assert tel.enabled is False

    def test_flush_works_when_disabled(self):
        """Verifies that flush works when disabled."""
        tel = EncreTelemetry(enabled=False)
        result = tel.flush()
        # Confirm the expected result for this scenario: flush works when disabled.
        assert isinstance(result, dict)
        assert result["total_tool_calls"] == 0


# ── Timestamp Consistency ────────────────────────────────────────────────

class TestTimestampConsistency:
    """Test cases covering timestamp consistency.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_records_are_ordered_by_time(self):
        """Verifies that records are ordered by time."""
        tel = EncreTelemetry()
        tel.record_tool_call("first", 100.0, True)
        tel.record_tool_call("second", 200.0, True)
        tel.record_tool_call("third", 300.0, True)
        timestamps = [t.timestamp for t in tel.tool_calls]
        # Confirm the expected result for this scenario: records are ordered by time.
        assert timestamps == sorted(timestamps)

    def test_turn_records_are_ordered(self):
        """Verifies that turn records are ordered."""
        tel = EncreTelemetry()
        for i in range(5):
            tel.record_turn(i + 1, 2, 1000.0)
        # Confirm the expected result for this scenario: turn records are ordered.
        assert len(tel.turns) == 5
        timestamps = [t.timestamp for t in tel.turns]
        assert timestamps == sorted(timestamps)
