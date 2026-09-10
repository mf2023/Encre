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

import os
import tempfile

from encre.config import EncreConfig
from encre.logging_config import get_logger, setup_logging

# Redirect telemetry data to a temp directory so tests never pollute
# the real production telemetry directory (~/.dunimd/encre/telemetry/).
_test_telemetry_dir = tempfile.mkdtemp(prefix="encre_test_telemetry_")
os.environ["ENCRE_DATA_DIR"] = _test_telemetry_dir
from encre.ratelimit import EncreRateLimiter, RateLimitResult
from encre.ssrf import EncreSSRFGuard
from encre.telemetry import EncreTelemetry, RetryRecord, ToolCallRecord, TurnRecord


class TestSSRFGuard:
    """Engineered to validate the SSRF guard URL validation and hostname blocking logic.

    This test class exercises EncreSSRFGuard across 10 scenarios covering
    public URL acceptance, private-IP blocking, cloud-metadata blocking,
    non-HTTP rejection, invalid-URL rejection, hostname private/public
    classification, safe hostname extraction, blocked hostname extraction,
    and DNS-cache clearing. The design ensures SSRF mitigation is effective
    against both IP-based and hostname-based attack vectors.
    """
    def setup_method(self):
        """Create a fresh EncreSSRFGuard instance before each test method.

        Returns:
            A new EncreSSRFGuard instance assigned to self.guard.
        """
        self.guard = EncreSSRFGuard()

    def test_verify_validate_url_allows_public(self):
        """Validate that validate_url accepts a public HTTPS URL.

        The test exercises validate_url with "https://example.com/resource"
        and asserts True because public HTTPS URLs are the normal case the
        guard must allow through.
        """
        result = self.guard.validate_url("https://example.com/resource")
        assert result is True

    def test_verify_validate_url_blocks_private_ip(self):
        """Validate that validate_url rejects URLs targeting private IP ranges.

        The test exercises validate_url with "http://127.0.0.1/admin" and
        asserts False because localhost addresses are SSRF attack targets
        that must be blocked.
        """
        result = self.guard.validate_url("http://127.0.0.1/admin")
        assert result is False

    def test_verify_validate_url_blocks_metadata(self):
        """Validate that validate_url rejects URLs targeting cloud metadata endpoints.

        The test exercises validate_url with the AWS metadata IP 169.254.169.254
        and asserts False because metadata-service access is a well-known
        SSRF exploitation path.
        """
        result = self.guard.validate_url("http://169.254.169.254/metadata")
        assert result is False

    def test_verify_validate_url_rejects_non_http(self):
        """Validate that validate_url rejects non-HTTP schemes such as FTP.

        The test exercises validate_url with "ftp://example.com/file" and
        asserts False because only HTTP and HTTPS are permitted by the
        SSRF guard policy.
        """
        assert self.guard.validate_url("ftp://example.com/file") is False

    def test_verify_validate_url_rejects_invalid(self):
        """Validate that validate_url rejects syntactically invalid URLs.

        The test exercises validate_url with "not-a-url" and asserts False
        because the parser must reject strings that do not resolve to a
        valid URL structure.
        """
        assert self.guard.validate_url("not-a-url") is False

    def test_verify_is_blocked_hostname_private(self):
        """Validate that is_blocked_hostname returns True for private IP ranges.

        The test exercises is_blocked_hostname against 127.0.0.1, 10.0.0.1,
        and 192.168.1.1 and asserts True for all because RFC 1918 private
        ranges must be blocked to prevent internal-network SSRF.
        """
        assert self.guard.is_blocked_hostname("127.0.0.1") is True
        assert self.guard.is_blocked_hostname("10.0.0.1") is True
        assert self.guard.is_blocked_hostname("192.168.1.1") is True

    def test_verify_is_blocked_hostname_public(self):
        """Validate that is_blocked_hostname returns False for public IPs.

        The test exercises is_blocked_hostname against 8.8.8.8 and asserts
        False because public DNS-server addresses are legitimate targets.
        """
        assert self.guard.is_blocked_hostname("8.8.8.8") is False

    def test_verify_extract_safe_hostname(self):
        """Validate that extract_safe_hostname returns the host component of a URL.

        The test exercises extract_safe_hostname with "https://example.com/path"
        and asserts "example.com" is returned because URL parsing must isolate
        the hostname for subsequent blocking checks.
        """
        hostname = self.guard.extract_safe_hostname("https://example.com/path")
        assert hostname == "example.com"

    def test_verify_extract_safe_hostname_blocked(self):
        """Validate that extract_safe_hostname returns None for blocked hosts.

        The test exercises extract_safe_hostname with "http://127.0.0.1/admin"
        and asserts None because the hostname is a private IP and the guard
        must signal rejection at the extraction stage.
        """
        hostname = self.guard.extract_safe_hostname("http://127.0.0.1/admin")
        assert hostname is None

    def test_verify_clear_dns_cache(self):
        """Validate that clear_dns_cache empties the internal DNS cache.

        The test exercises clear_dns_cache and asserts len(_dns_cache) == 0
        because cache clearing must remove all cached resolutions to force
        fresh DNS lookups on the next request.
        """
        self.guard.clear_dns_cache()
        assert len(self.guard._dns_cache) == 0


class TestRateLimiter:
    """Engineered to validate the EncreRateLimiter construction and per-key rate tracking.

    This test class exercises rate limiter configuration and request checking
    across 6 scenarios covering construction, defaults, result structure,
    allowed requests, and per-key independence. The design ensures the
    limiter isolates rate windows per tool key.
    """
    def test_verify_create(self):
        """Validate that EncreRateLimiter stores the per_minute parameter.

        The test exercises construction with per_minute=60 and asserts
        rl.per_minute == 60 because the constructor must preserve the
        configured rate limit.
        """
        rl = EncreRateLimiter(per_minute=60)
        assert rl.per_minute == 60

    def test_verify_defaults(self):
        """Validate that EncreRateLimiter uses documented default rate limits.

        The test exercises default construction and asserts per_minute=60,
        per_hour=500, and max_concurrent=10 because these are the
        production defaults for the rate-limiting policy.
        """
        rl = EncreRateLimiter()
        assert rl.per_minute == 60
        assert rl.per_hour == 500
        assert rl.max_concurrent == 10

    def test_verify_rate_limit_result(self):
        """Validate that RateLimitResult stores allowed and remaining fields.

        The test exercises construction with allowed=True and remaining=5
        and asserts both fields are preserved because the result object
        is the contract between the limiter and the caller.
        """
        rr = RateLimitResult(allowed=True, remaining=5)
        assert rr.allowed is True
        assert rr.remaining == 5

    def test_verify_rate_limit_result_denied(self):
        """Validate that RateLimitResult stores denied state and retry_after.

        The test exercises construction with allowed=False and retry_after=10.0
        and asserts both fields are preserved because denied results must
        communicate when the caller may retry.
        """
        rr = RateLimitResult(allowed=False, remaining=0, retry_after=10.0)
        assert rr.allowed is False
        assert rr.retry_after == 10.0

    def test_verify_first_request_allowed(self):
        """Validate that the first request within the rate window is allowed.

        The test exercises check("tool_a") on a limiter with a high per_minute
        ceiling and asserts allowed=True because a single request must never
        be blocked by the rate limiter itself.
        """
        rl = EncreRateLimiter(per_minute=999)
        result = rl.check("tool_a")
        assert result.allowed is True

    def test_verify_different_keys_independent(self):
        """Validate that rate limits are tracked independently per key.

        The test exercises check on "tool_a" then on "tool_b" with a high
        ceiling and asserts the second request is allowed because each key
        has its own sliding window.
        """
        rl = EncreRateLimiter(per_minute=999)
        rl.check("tool_a")
        result = rl.check("tool_b")
        assert result.allowed is True


class TestConfig:
    """Engineered to validate EncreConfig default values and custom construction.

    This test class exercises config construction across 6 scenarios covering
    defaults, custom model/backend/turns/tokens, backend kwargs, permission
    mode, sandbox enabled flag, and tool_result_max_chars. The design ensures
    the config object is the single source of truth for runtime parameters.
    """
    def test_verify_defaults(self):
        """Validate that EncreConfig() initializes with expected default values.

        The test exercises default construction and asserts max_tokens > 0,
        max_turns == 0 (unlimited), and model == "" because these are the
        documented baseline configuration values.
        """
        cfg = EncreConfig()
        # max_turns=0 means unlimited; model="" until a ModelConfig is selected.
        assert cfg.max_tokens > 0
        assert cfg.max_turns == 0
        assert cfg.model == ""

    def test_verify_custom_config(self):
        """Validate that EncreConfig accepts and preserves custom model and backend settings.

        The test exercises construction with explicit model, backend_type,
        max_turns, and max_tokens and asserts each field matches the input
        because custom configuration must not be silently overwritten.
        """
        cfg = EncreConfig(
            model="claude-sonnet-4-20250514",
            backend_type="anthropic",
            max_turns=25,
            max_tokens=32768,
        )
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.backend_type == "anthropic"
        assert cfg.max_turns == 25

    def test_verify_backend_kwargs(self):
        """Validate that EncreConfig stores backend_kwargs dictionary intact.

        The test exercises construction with backend_kwargs={"temperature": 0.7}
        and asserts the temperature value is preserved because backend-specific
        parameters must pass through unchanged to the model provider.
        """
        cfg = EncreConfig(backend_kwargs={"temperature": 0.7})
        assert cfg.backend_kwargs["temperature"] == 0.7

    def test_verify_permission_mode_default(self):
        """Validate that the default permission_mode is 'bypass'.

        The test exercises default construction and asserts permission_mode
        == "bypass" because the default policy allows all tool executions
        without user confirmation.
        """
        cfg = EncreConfig()
        assert cfg.permission_mode == "bypass"

    def test_verify_sandbox_enabled_default(self):
        """Validate that sandbox_enabled defaults to True.

        The test exercises default construction and asserts sandbox_enabled
        is True because sandbox isolation is enabled by default for safety.
        """
        cfg = EncreConfig()
        assert cfg.sandbox_enabled is True

    def test_verify_tool_result_max_chars(self):
        """Validate that tool_result_max_chars is stored and retrievable.

        The test exercises construction with tool_result_max_chars=50000
        and asserts the value is preserved because the truncation threshold
        must be configurable per deployment.
        """
        cfg = EncreConfig(tool_result_max_chars=50000)
        assert cfg.tool_result_max_chars == 50000


class TestTelemetry:
    """Engineered to validate the EncreTelemetry recording and summary pipeline.

    This test class exercises telemetry records and methods across 10 scenarios
    covering ToolCallRecord, TurnRecord, RetryRecord construction, recording,
    summary generation, flush, reset, and disabled-mode behavior. The design
    ensures telemetry data is accurately accumulated and reportable.
    """
    def setup_method(self):
        """Create a fresh EncreTelemetry instance before each test method.

        Returns:
            A new EncreTelemetry instance assigned to self.tel.
        """
        self.tel = EncreTelemetry()

    def test_verify_tool_call_record(self):
        """Validate that ToolCallRecord stores all fields correctly.

        The test exercises construction with tool_name="bash", latency_ms=1500.0,
        success=True, and tokens_used=100 and asserts each field is preserved
        because the record object is the atomic unit of telemetry data.
        """
        tcr = ToolCallRecord(
            tool_name="bash", latency_ms=1500.0, success=True, tokens_used=100
        )
        assert tcr.tool_name == "bash"
        assert tcr.latency_ms == 1500.0
        assert tcr.success is True
        assert tcr.tokens_used == 100

    def test_verify_turn_record(self):
        """Validate that TurnRecord stores turn_number, event_count, and latency_ms.

        The test exercises construction with turn_number=1, event_count=2,
        and latency_ms=3000.0 and asserts each field is preserved because
        turn-level aggregation depends on accurate counting.
        """
        tr = TurnRecord(turn_number=1, event_count=2, latency_ms=3000.0)
        assert tr.turn_number == 1
        assert tr.event_count == 2
        assert tr.latency_ms == 3000.0

    def test_verify_retry_record(self):
        """Validate that RetryRecord stores attempt, error_type, error_detail, and delay_s.

        The test exercises construction with attempt=2, error_type="http_status",
        error_detail="429", and delay_s=1.0 and asserts all fields are
        preserved because retry records must capture the full error context.
        """
        rr = RetryRecord(
            attempt=2, error_type="http_status", error_detail="429", delay_s=1.0
        )
        assert rr.attempt == 2
        assert rr.error_type == "http_status"
        assert rr.error_detail == "429"
        assert rr.delay_s == 1.0

    def test_verify_record_tool_call(self):
        """Validate that record_tool_call appends to the tool_calls list.

        The test exercises record_tool_call("bash", 2000.0, True, 100) and
        asserts len(tool_calls) == 1 because each recorded call must be
        appended to the accumulator list.
        """
        self.tel.record_tool_call("bash", 2000.0, True, 100)
        assert len(self.tel.tool_calls) == 1

    def test_verify_record_turn(self):
        """Validate that record_turn appends to the turns list.

        The test exercises record_turn(1, 2, 3000.0) and asserts len(turns)
        == 1 because each turn must be recorded for latency and event-count
        aggregation.
        """
        self.tel.record_turn(1, 2, 3000.0)
        assert len(self.tel.turns) == 1

    def test_verify_record_retry(self):
        """Validate that record_retry appends to the retries list.

        The test exercises record_retry(1, "http_status", "429", 1.0) and
        asserts len(retries) == 1 because retry events must be captured
        for error-rate analysis.
        """
        self.tel.record_retry(1, "http_status", "429", 1.0)
        assert len(self.tel.retries) == 1

    def test_verify_get_summary(self):
        """Validate that get_summary returns a dict with total_tool_calls count.

        The test exercises record_tool_call followed by get_summary and
        asserts the result is a dict with total_tool_calls == 1 because
        the summary must aggregate recorded calls into a reportable format.
        """
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        summary = self.tel.get_summary()
        assert isinstance(summary, dict)
        assert summary["total_tool_calls"] == 1

    def test_verify_flush(self):
        """Validate that flush persists recorded data and returns a summary dict.

        The test exercises record_tool_call followed by flush and asserts
        the result is a dict with total_tool_calls == 1 because flush must
        serialize the in-memory buffer into an external store.
        """
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        result = self.tel.flush()
        assert isinstance(result, dict)
        assert result["total_tool_calls"] == 1

    def test_verify_reset(self):
        """Validate that reset clears all recorded telemetry data.

        The test exercises record_tool_call followed by reset and asserts
        len(tool_calls) == 0 because reset must provide a clean slate
        for a new session without restarting the process.
        """
        self.tel.record_tool_call("bash", 1000.0, True, 100)
        self.tel.reset()
        assert len(self.tel.tool_calls) == 0

    def test_verify_disabled_telemetry(self):
        """Validate that telemetry is discarded when enabled=False.

        The test exercises record_tool_call on a telemetry instance with
        enabled=False and asserts len(tool_calls) == 0 because disabled
        telemetry must not accumulate any data.
        """
        tel = EncreTelemetry(enabled=False)
        tel.record_tool_call("bash", 1000.0, True, 100)
        assert len(tel.tool_calls) == 0


class TestLoggingConfig:
    """Engineered to validate logging setup and logger retrieval.

    This test class exercises setup_logging and get_logger across 2
    scenarios to ensure the logging subsystem is functional.
    """
    def test_verify_setup_logging(self):
        """Validate that setup_logging completes without raising.

        The test exercises setup_logging(level="WARNING") and asserts nothing
        is raised because the function configures global state and returns
        None on success.
        """
        setup_logging(level="WARNING")
        # setup_logging returns None (configures global state)

    def test_verify_get_logger(self):
        """Validate that get_logger returns a non-None Logger instance.

        The test exercises get_logger("test.module") and asserts the result
        is not None because every module must be able to obtain a logger
        for structured output.
        """
        logger = get_logger("test.module")
        assert logger is not None


class TestSandboxTypes:
    """Engineered to validate SandboxConfig and SandboxResult types imported from encre.sandbox.types.

    This test class exercises these types across 4 scenarios covering
    custom construction, defaults, basic result, and error result to
    ensure the types module provides a stable API surface.
    """
    def test_verify_sandbox_config(self):
        """Validate that SandboxConfig accepts custom image and timeout values.

        The test exercises construction with image="ubuntu:22.04" and
        timeout=30 and asserts both fields are preserved because the
        config types must support deployment-specific overrides.
        """
        from encre.sandbox.types import SandboxConfig

        cfg = SandboxConfig(image="ubuntu:22.04", timeout=30)
        assert cfg.image == "ubuntu:22.04"
        assert cfg.timeout == 30

    def test_verify_sandbox_config_defaults(self):
        """Validate that SandboxConfig() exposes the documented default image and network policy.

        The test exercises default construction and asserts image == "python:3.11-slim",
        network.policy == NetworkPolicy.NONE, and resource.memory_limit == "512m"
        because the defaults define the baseline sandbox configuration.
        """
        from encre.sandbox.types import NetworkPolicy, SandboxConfig

        cfg = SandboxConfig()
        assert cfg.image == "python:3.11-slim"
        assert cfg.network.policy is NetworkPolicy.NONE
        assert cfg.resource.memory_limit == "512m"

    def test_verify_sandbox_result(self):
        """Validate that SandboxResult stores stdout, stderr, exit_code, and duration_ms.

        The test exercises construction with a successful execution and
        asserts exit_code == 0 and stdout == "success" because the result
        object is the primary contract between the sandbox and the caller.
        """
        from encre.sandbox.types import SandboxResult

        sr = SandboxResult(stdout="success", stderr="", exit_code=0, duration_ms=1200.0)
        assert sr.exit_code == 0
        assert sr.stdout == "success"

    def test_verify_sandbox_result_error(self):
        """Validate that SandboxResult stores error diagnostics correctly.

        The test exercises construction with stderr="command not found",
        exit_code=1, and timed_out=True and asserts exit_code == 1 and
        timed_out is True because error results must preserve all
        diagnostic fields for downstream logging and reporting.
        """
        from encre.sandbox.types import SandboxResult

        sr = SandboxResult(
            stdout="", stderr="command not found", exit_code=1, timed_out=True
        )
        assert sr.exit_code == 1
        assert sr.timed_out is True
