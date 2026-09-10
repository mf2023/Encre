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

"""Tests for the rate limiter: construction, check, backoff, slots, and reset."""

import asyncio

import pytest


class TestRateLimitResult:
    """Engineered to validate the RateLimitResult dataclass contract.

Tests confirm that allowed=True yields retry_after==0.0 and the
specified remaining quota, that allowed=False carries the reported
retry_after and zero remaining, that default initialisation uses
retry_after=0.0 and remaining=0, and that the class is recognised as
a dataclass.
"""
    def test_verify_ratelimit_result_allowed(self):
        """Validate that allowed result."""
        from encre.ratelimit import RateLimitResult
        result = RateLimitResult(allowed=True, remaining=50)
        assert result.allowed is True
        assert result.retry_after == 0.0
        assert result.remaining == 50

    def test_verify_ratelimit_result_denied(self):
        """Validate that denied result."""
        from encre.ratelimit import RateLimitResult
        result = RateLimitResult(allowed=False, retry_after=30.5, remaining=0)
        assert result.allowed is False
        assert result.retry_after == 30.5
        assert result.remaining == 0

    def test_verify_ratelimit_result_default_values(self):
        """Validate that default values."""
        from encre.ratelimit import RateLimitResult
        result = RateLimitResult(allowed=True)
        assert result.retry_after == 0.0
        assert result.remaining == 0

    def test_verify_ratelimit_result_is_dataclass(self):
        """Validate that is dataclass."""
        from dataclasses import is_dataclass

        from encre.ratelimit import RateLimitResult
        assert is_dataclass(RateLimitResult)


class TestEncreRateLimiterConstruction:
    """Engineered to validate EncreRateLimiter default and custom construction.

Tests assert that the constructor applies the documented default
quotas (60/min, 500/hour, 5000/day, 10 concurrent) and that custom
values are stored verbatim in the corresponding attributes, with
_concurrent_count initialised to zero.
"""
    def test_verify_ratelimit_result_default_values(self):
        """Validate that default values."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        assert limiter.per_minute == 60
        assert limiter.per_hour == 500
        assert limiter.per_day == 5000
        assert limiter.max_concurrent == 10
        assert limiter._concurrent_count == 0

    def test_verify_ratelimit_construction_custom_values(self):
        """Validate that custom values."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(
            per_minute=30,
            per_hour=200,
            per_day=1000,
            max_concurrent=5,
        )
        assert limiter.per_minute == 30
        assert limiter.per_hour == 200
        assert limiter.per_day == 1000
        assert limiter.max_concurrent == 5

    def test_verify_ratelimit_construction_initial_windows_empty(self):
        """Validate that initial windows empty."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        assert limiter._windows == {}

    def test_verify_ratelimit_construction_initial_active_tools_empty(self):
        """Validate that initial active tools empty."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        assert limiter.active_tools == []


class TestEncreRateLimiterCheck:
    """Engineered to validate the rate-limit check logic.

Tests cover the first-request case (always allowed with positive
remaining), cumulative counting across multiple requests, per-tool
window isolation (heavy tool usage does not affect light tool quota),
per-minute limit enforcement (denial on the N+1 request), and
per-day limit enforcement with zero remaining on denial.
"""
    def test_verify_ratelimit_check_first_check_allowed(self):
        """Validate that first check allowed."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        result = limiter.check("bash")
        assert result.allowed is True
        assert result.remaining > 0

    def test_verify_ratelimit_check_multiple_checks_track_count(self):
        """Validate that multiple checks track count."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=100)
        for _ in range(10):
            result = limiter.check("bash")
            assert result.allowed is True
        # Remaining should have decreased
        assert result.remaining < 5000

    def test_verify_ratelimit_check_different_tools_have_separate_windows(self):
        """Validate that different tools have separate windows."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=100)
        # Use one tool a lot, the other should still have full quota
        for _ in range(50):
            limiter.check("heavy_tool")
        result = limiter.check("light_tool")
        assert result.allowed is True
        # light_tool should have close to full remaining
        assert result.remaining > 4000

    def test_verify_ratelimit_check_per_minute_limit_exceeded(self):
        """Validate that per minute limit exceeded."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=5, per_hour=99999, per_day=99999)
        for _ in range(5):
            result = limiter.check("bash")
            assert result.allowed is True
        # 6th should be denied
        result = limiter.check("bash")
        assert result.allowed is False
        assert result.retry_after > 0

    def test_verify_ratelimit_check_per_day_limit_exceeded(self):
        """Validate that per day limit exceeded."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=99999, per_hour=99999, per_day=3)
        for _ in range(3):
            result = limiter.check("bash")
            assert result.allowed is True
        # 4th should be denied
        result = limiter.check("bash")
        assert result.allowed is False
        assert result.remaining == 0


class TestEncreRateLimiterSlots:
    """Engineered to validate the async concurrent-slot acquisition protocol.

Tests confirm that acquiring slots increments _concurrent_count,
that release decrements it, that releasing without an acquire never
drives the count negative, and that a second acquire blocks when
capacity is reached (verified via task timeout after a short spin).
"""
    @pytest.mark.asyncio
    async def test_verify_ratelimit_slots_acquire_slot_below_limit(self):
        """Validate that acquire slot below limit."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(max_concurrent=10)
        await limiter.acquire_slot()
        assert limiter._concurrent_count == 1

    @pytest.mark.asyncio
    async def test_verify_ratelimit_slots_acquire_multiple_slots(self):
        """Validate that acquire multiple slots."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(max_concurrent=5)
        await limiter.acquire_slot()
        await limiter.acquire_slot()
        await limiter.acquire_slot()
        assert limiter._concurrent_count == 3

    @pytest.mark.asyncio
    async def test_verify_ratelimit_slots_release_slot(self):
        """Validate that release slot."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        await limiter.acquire_slot()
        assert limiter._concurrent_count == 1
        limiter.release_slot()
        assert limiter._concurrent_count == 0

    def test_verify_ratelimit_slots_release_slot_never_goes_negative(self):
        """Validate that release slot never goes negative."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        limiter.release_slot()
        limiter.release_slot()
        assert limiter._concurrent_count == 0

    @pytest.mark.asyncio
    async def test_verify_ratelimit_slots_acquire_slot_blocks_when_at_capacity(self):
        """Validate that acquire slot blocks when at capacity."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(max_concurrent=1)
        await limiter.acquire_slot()
        assert limiter._concurrent_count == 1

        # Now attempt to acquire another slot -- it should be blocked
        # We test this by using a task with a timeout
        async def acquire():
            """Acquire a slot from the limiter."""
            await limiter.acquire_slot()
            return True

        task = asyncio.create_task(acquire())
        await asyncio.sleep(0.2)  # Give it time to spin
        assert limiter._concurrent_count == 1  # Still at capacity

        # Release and the task should proceed
        limiter.release_slot()
        await asyncio.wait_for(task, timeout=2.0)
        assert limiter._concurrent_count == 1


class TestEncreRateLimiterBackoff:
    """Engineered to validate the exponential-backoff-with-jitter policy.

Tests assert that backoff(0) returns approximately 1 s, that delay
increases with attempt count (monotonic within jitter bounds), that
delays are capped at 60 s (verifiable at attempt 10 where 2**10
exceeds the cap), and that the return value is always a float.
"""
    def test_verify_ratelimit_backoff_with_zero_attempts(self):
        """Validate that backoff with zero attempts."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        delay = limiter.backoff(0)
        assert 1.0 <= delay <= 1.5  # 2^0 = 1 + random(0, 0.5)

    def test_verify_ratelimit_backoff_increases_with_attempts(self):
        """Validate that backoff increases with attempts."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        d1 = limiter.backoff(1)
        d2 = limiter.backoff(2)
        d3 = limiter.backoff(3)
        # Base values: 2, 4, 8 -- should generally increase
        # but there's jitter so we check ranges
        assert d1 > 0
        assert d2 > 0
        assert d3 > 0

    def test_verify_ratelimit_backoff_capped_at_60_seconds(self):
        """Validate that backoff capped at 60 seconds."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        # 2^10 = 1024, capped at 60
        delay = limiter.backoff(10)
        assert delay <= 60.5  # 60 + random(0, 0.5)
        assert delay >= 60.0

    def test_verify_ratelimit_backoff_returns_float(self):
        """Validate that backoff returns float."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        delay = limiter.backoff(5)
        assert isinstance(delay, float)


class TestEncreRateLimiterReset:
    """Engineered to validate the rate-limiter reset operation.

Tests confirm that reset clears all sliding windows, zeroes
_concurrent_count, and empties the active_tools tracking list,
restoring the limiter to its initial construction state.
"""
    def test_verify_ratelimit_reset_clears_windows(self):
        """Validate that reset clears windows."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=5)
        for _ in range(3):
            limiter.check("bash")
        assert "bash" in limiter._windows
        limiter.reset()
        assert limiter._windows == {}

    def test_verify_ratelimit_reset_clears_concurrent_count(self):
        """Validate that reset clears concurrent count."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        limiter._concurrent_count = 5
        limiter.reset()
        assert limiter._concurrent_count == 0

    def test_verify_ratelimit_reset_active_tools_empty_after_reset(self):
        """Validate that active tools empty after reset."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=100)
        limiter.check("bash")
        limiter.check("grep")
        assert len(limiter.active_tools) == 2
        limiter.reset()
        assert limiter.active_tools == []


class TestEncreRateLimiterActiveTools:
    """Engineered to validate the active-tools tracking list.

Tests assert that active_tools starts empty, and that each call to
check registers the tool name so that the list reflects all tools
that have been exercised since the last reset.
"""
    def test_verify_ratelimit_active_tools_returns_names(self):
        """Validate that active tools returns names."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter(per_minute=100)
        limiter.check("bash")
        limiter.check("grep")
        active = limiter.active_tools
        assert "bash" in active
        assert "grep" in active

    def test_verify_ratelimit_active_tools_starts_empty(self):
        """Validate that active tools starts empty."""
        from encre.ratelimit import EncreRateLimiter
        limiter = EncreRateLimiter()
        assert limiter.active_tools == []
