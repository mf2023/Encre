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

"""Tests for SSRF guard, rate limiter, config, telemetry, sandbox types."""


from encre.config import EncreConfig
from encre.logging_config import get_logger, setup_logging
from encre.ratelimit import EncreRateLimiter, RateLimitResult
from encre.ssrf import EncreSSRFGuard
from encre.telemetry import EncreTelemetry, RetryRecord, ToolCallRecord, TurnRecord


class TestSSRFGuard:
    """Test cases covering s s r f guard.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.guard = EncreSSRFGuard()

    def test_validate_url_allows_public(self):
        """Verifies that validate url allows public."""
        result = self.guard.validate_url("https://example.com/resource")
        # Confirm the expected result for this scenario: validate url allows public.
        assert result is True

    def test_validate_url_blocks_private_ip(self):
        """Verifies that validate url blocks private ip."""
        result = self.guard.validate_url("http://127.0.0.1/admin")
        # Confirm the expected result for this scenario: validate url blocks private ip.
        assert result is False

    def test_validate_url_blocks_metadata(self):
        """Verifies that validate url blocks metadata."""
        result = self.guard.validate_url("http://169.254.169.254/metadata")
        # Confirm the expected result for this scenario: validate url blocks metadata.
        assert result is False

    def test_validate_url_rejects_non_http(self):
        """Verifies that validate url rejects non http."""
        # Confirm the expected result for this scenario: validate url rejects non http.
        assert self.guard.validate_url("ftp://example.com/file") is False

    def test_validate_url_rejects_invalid(self):
        """Verifies that validate url rejects invalid."""
        # Confirm the expected result for this scenario: validate url rejects invalid.
        assert self.guard.validate_url("not-a-url") is False

    def test_is_blocked_hostname_private(self):
        """Verifies that is blocked hostname private."""
        # Confirm the expected result for this scenario: is blocked hostname private.
        assert self.guard.is_blocked_hostname("127.0.0.1") is True
        assert self.guard.is_blocked_hostname("10.0.0.1") is True
        assert self.guard.is_blocked_hostname("192.168.1.1") is True

    def test_is_blocked_hostname_public(self):
        """Verifies that is blocked hostname public."""
        # Confirm the expected result for this scenario: is blocked hostname public.
        assert self.guard.is_blocked_hostname("8.8.8.8") is False

    def test_extract_safe_hostname(self):
        """Verifies that extract safe hostname."""
        hostname = self.guard.extract_safe_hostname("https://example.com/path")
        # Confirm the expected result for this scenario: extract safe hostname.
        assert hostname == "example.com"

    def test_extract_safe_hostname_blocked(self):
        """Verifies that extract safe hostname blocked."""
        hostname = self.guard.extract_safe_hostname("http://127.0.0.1/admin")
        # Confirm the expected result for this scenario: extract safe hostname blocked.
        assert hostname is None

    def test_clear_dns_cache(self):
        """Verifies that clear dns cache."""
        self.guard.clear_dns_cache()
        # Confirm the expected result for this scenario: clear dns cache.
        assert len(self.guard._dns_cache) == 0


class TestRateLimiter:
    """Test cases covering rate limiter.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        rl = EncreRateLimiter(per_minute=60)
        # Confirm the expected result for this scenario: create.
        assert rl.per_minute == 60

    def test_defaults(self):
        """Verifies that defaults."""
        rl = EncreRateLimiter()
        # Confirm the expected result for this scenario: defaults.
        assert rl.per_minute == 60
        assert rl.per_hour == 500
        assert rl.max_concurrent == 10

    def test_rate_limit_result(self):
        """Verifies that rate limit result."""
        rr = RateLimitResult(allowed=True, remaining=5)
        # Confirm the expected result for this scenario: rate limit result.
        assert rr.allowed is True
        assert rr.remaining == 5

    def test_rate_limit_result_denied(self):
        """Verifies that rate limit result denied."""
        rr = RateLimitResult(allowed=False, remaining=0, retry_after=10.0)
        # Confirm the expected result for this scenario: rate limit result denied.
        assert rr.allowed is False
        assert rr.retry_after == 10.0

    def test_first_request_allowed(self):
        """Verifies that first request allowed."""
        rl = EncreRateLimiter(per_minute=999)
        result = rl.check("tool_a")
        # Confirm the expected result for this scenario: first request allowed.
        assert result.allowed is True

    def test_different_keys_independent(self):
        """Verifies that different keys independent."""
        rl = EncreRateLimiter(per_minute=999)
        rl.check("tool_a")
        result = rl.check("tool_b")
        # Confirm the expected result for this scenario: different keys independent.
        assert result.allowed is True


class TestConfig:
    """Test cases covering config.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        cfg = EncreConfig()
        # Confirm the expected result for this scenario: defaults.
        # max_turns=0 means unlimited; model="" until a ModelConfig is selected.
        assert cfg.max_tokens > 0
        assert cfg.max_turns == 0
        assert cfg.model == ""

    def test_custom_config(self):
        """Verifies that custom config."""
        cfg = EncreConfig(
            model="claude-sonnet-4-20250514",
            backend_type="anthropic",
            max_turns=25,
            max_tokens=32768,
        )
        # Confirm the expected result for this scenario: custom config.
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.backend_type == "anthropic"
        assert cfg.max_turns == 25

    def test_backend_kwargs(self):
        """Verifies that backend kwargs."""
        cfg = EncreConfig(backend_kwargs={"temperature": 0.7})
        # Confirm the expected result for this scenario: backend kwargs.
        assert cfg.backend_kwargs["temperature"] == 0.7

    def test_permission_mode_default(self):
        """Verifies that permission mode default."""
        cfg = EncreConfig()
        # Confirm the expected result for this scenario: permission mode default.
        assert cfg.permission_mode == "bypass"

    def test_sandbox_enabled_default(self):
        """Verifies that sandbox enabled default."""
        cfg = EncreConfig()
        # Confirm the expected result for this scenario: sandbox enabled default.
        assert cfg.sandbox_enabled is True

    def test_tool_result_max_chars(self):
        """Verifies that tool result max chars."""
        cfg = EncreConfig(tool_result_max_chars=50000)
        # Confirm the expected result for this scenario: tool result max chars.
        assert cfg.tool_result_max_chars == 50000


class TestTelemetry:
    """Test cases covering telemetry.
    
    Covers the expected behavior and relevant edge cases.
    """
    def setup_method(self):
        """Verifies that setup method."""
        self.tel = EncreTelemetry()

    def test_tool_call_record(self):
        """Verifies that tool call record."""
        tcr = ToolCallRecord(
            tool_name="bash", latency_ms=1500.0, success=True, tokens_used=100
        )
        # Confirm the expected result for this scenario: tool call record.
        assert tcr.tool_name == "bash"
        assert tcr.latency_ms == 1500.0
        assert tcr.success is True
        assert tcr.tokens_used == 100

    def test_turn_record(self):
        """Verifies that turn record."""
        tr = TurnRecord(turn_number=1, event_count=2, latency_ms=3000.0)
        # Confirm the expected result for this scenario: turn record.
        assert tr.turn_number == 1
        assert tr.event_count == 2
        assert tr.latency_ms == 3000.0

    def test_retry_record(self):
        """Verifies that retry record."""
        rr = RetryRecord(
            attempt=2, error_type="http_status", error_detail="429", delay_s=1.0
        )
        # Confirm the expected result for this scenario: retry record.
        assert rr.attempt == 2
        assert rr.error_type == "http_status"
        assert rr.error_detail == "429"
        assert rr.delay_s == 1.0

    def test_record_tool_call(self):
        """Verifies that record tool call."""
        self.tel.record_tool_call("bash", 2000.0, True, 100)
        # Confirm the expected result for this scenario: record tool call.
        assert len(self.tel.tool_calls) == 1

    def test_record_turn(self):
        """Verifies that record turn."""
        self.tel.record_turn(1, 2, 3000.0)
        # Confirm the expected result for this scenario: record turn.
        assert len(self.tel.turns) == 1

    def test_record_retry(self):
        """Verifies that record retry."""
        self.tel.record_retry(1, "http_status", "429", 1.0)
        # Confirm the expected result for this scenario: record retry.
        assert len(self.tel.retries) == 1

    def test_get_summary(self):
        """Verifies that get summary."""
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        summary = self.tel.get_summary()
        # Confirm the expected result for this scenario: get summary.
        assert isinstance(summary, dict)
        assert summary["total_tool_calls"] == 1

    def test_flush(self):
        """Verifies that flush."""
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        result = self.tel.flush()
        # Confirm the expected result for this scenario: flush.
        assert isinstance(result, dict)
        assert result["total_tool_calls"] == 1

    def test_reset(self):
        """Verifies that reset."""
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        self.tel.reset()
        # Confirm the expected result for this scenario: reset.
        assert len(self.tel.tool_calls) == 0

    def test_disabled_telemetry(self):
        """Verifies that disabled telemetry."""
        tel = EncreTelemetry(enabled=False)
        tel.record_tool_call("bash", 1000.0, True, 100)
        # Confirm the expected result for this scenario: disabled telemetry.
        assert len(tel.tool_calls) == 0


class TestLoggingConfig:
    """Test cases covering logging config.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_setup_logging(self):
        """Verifies that setup logging."""
        setup_logging(level="WARNING")
        # setup_logging returns None (configures global state)

    def test_get_logger(self):
        """Verifies that get logger."""
        logger = get_logger("test.module")
        # Confirm the expected result for this scenario: get logger.
        assert logger is not None


class TestSandboxTypes:
    """Test cases covering sandbox types.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_sandbox_config(self):
        """Verifies that sandbox config."""
        from encre.sandbox.types import SandboxConfig

        cfg = SandboxConfig(image="ubuntu:22.04", timeout=30)
        # Confirm the expected result for this scenario: sandbox config.
        assert cfg.image == "ubuntu:22.04"
        assert cfg.timeout == 30

    def test_sandbox_config_defaults(self):
        """Verifies that sandbox config defaults."""
        from encre.sandbox.types import NetworkPolicy, SandboxConfig

        cfg = SandboxConfig()
        # Confirm the expected result for this scenario: sandbox config defaults.
        assert cfg.image == "python:3.11-slim"
        assert cfg.network.policy is NetworkPolicy.NONE
        assert cfg.resource.memory_limit == "512m"

    def test_sandbox_result(self):
        """Verifies that sandbox result."""
        from encre.sandbox.types import SandboxResult

        sr = SandboxResult(stdout="success", stderr="", exit_code=0, duration_ms=1200.0)
        # Confirm the expected result for this scenario: sandbox result.
        assert sr.exit_code == 0
        assert sr.stdout == "success"

    def test_sandbox_result_error(self):
        """Verifies that sandbox result error."""
        from encre.sandbox.types import SandboxResult

        sr = SandboxResult(
            stdout="", stderr="command not found", exit_code=1, timed_out=True
        )
        # Confirm the expected result for this scenario: sandbox result error.
        assert sr.exit_code == 1
        assert sr.timed_out is True
