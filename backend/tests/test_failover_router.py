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

"""Tests for failover and router backends."""

import asyncio

import httpx
import pytest
from encre.backend import create_backend
from encre.backends.auth import AuthManager
from encre.backends.base import BaseBackend
from encre.backends.failover import BackendHealth, FailoverBackend
from encre.backends.router import CostTracker, Route, RouterBackend, TaskCategory
from encre.utils.types import BackendFinish


# ===========================================================================
# MockBackend — minimal concrete backend for integration tests
# ===========================================================================

class MockBackend(BaseBackend):
    """Minimal backend for testing RouterBackend integration.

    Optionally raises an exception on chat() for testing failure paths.
    """
    def __init__(self, name: str = "mock", fail_on_call: bool = False,
                 fail_error: Exception | None = None) -> None:
        """Helper: Init."""
        self.model = name
        self._fail_on_call = fail_on_call
        self._fail_error = fail_error or httpx.ConnectError("mock connection error")

    async def chat(
        self,
        messages: list | None = None,
        tools: list | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        stream: bool = True,
        enable_caching: bool = False,
    ):
        """Chat."""
        if self._fail_on_call:
            raise self._fail_error
        yield BackendFinish(reason="stop", usage={})

    def supports_tool_calling(self) -> bool:
        """Supports tool calling."""
        return True

    def context_window_size(self) -> int:
        """Context window size."""
        return 128000

    def supports_thinking(self) -> bool:
        """Supports thinking."""
        return False

    def supports_prompt_caching(self) -> bool:
        """Supports prompt caching."""
        return False

    def count_tokens(self, text: str) -> int:
        """Count tokens."""
        return len(text.split())

    async def aclose(self) -> None:
        """Aclose."""
        pass

# ===========================================================================
# BackendHealth
# ===========================================================================

class TestBackendHealth:
    """Test suite for BackendHealth."""
    def test_initial_healthy(self):
        """Test: Initial healthy."""
        bh = BackendHealth(name="openai")
        # Verify: bh.healthy is True
        assert bh.healthy is True
        # Verify: bh.consecutive_failures == 0
        assert bh.consecutive_failures == 0
        # Verify: bh.total_failures == 0
        assert bh.total_failures == 0
        # Verify: bh.total_requests == 0
        assert bh.total_requests == 0

    def test_record_failure(self):
        """Test: Record failure."""
        bh = BackendHealth(name="openai")
        bh.record_failure("timeout")
        # Verify: bh.consecutive_failures == 1
        assert bh.consecutive_failures == 1
        # Verify: bh.total_failures == 1
        assert bh.total_failures == 1
        # Verify: bh.total_requests == 1
        assert bh.total_requests == 1
        # Verify: bh.last_error == "timeout"
        assert bh.last_error == "timeout"

    def test_record_success_resets_consecutive(self):
        """Test: Record success resets consecutive."""
        bh = BackendHealth(name="openai")
        bh.record_failure("err1")
        bh.record_failure("err2")
        bh.record_success()
        # Verify: bh.consecutive_failures == 0
        assert bh.consecutive_failures == 0
        # Verify: bh.total_requests == 3
        assert bh.total_requests == 3
        # Verify: bh.healthy is True
        assert bh.healthy is True

    def test_consecutive_failures_threshold(self):
        """Test: Consecutive failures threshold."""
        bh = BackendHealth(name="openai")
        for i in range(3):
            bh.record_failure(f"error {i}")
        # Verify: bh.healthy is False
        assert bh.healthy is False

    def test_manual_recovery(self):
        """Test: Manual recovery."""
        import time
        bh = BackendHealth(name="openai")
        for _ in range(3):
            bh.record_failure("timeout")
        # Verify: bh.healthy is False
        assert bh.healthy is False
        # Simulate grace period passing and probe
        bh.last_checked = time.time() - 400
        bh.healthy = True
        bh.consecutive_failures = 0
        # Verify: bh.healthy is True
        assert bh.healthy is True


# ===========================================================================
# FailoverBackend
# ===========================================================================

class TestFailoverBackend:
    """Test suite for FailoverBackend."""
    def test_create(self):
        """Test: Create."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("primary", be1), ("fallback", be2)])
        # Verify: fb is not None
        assert fb is not None
        # Verify: isinstance(fb, BaseBackend)
        assert isinstance(fb, BaseBackend)

    def test_active_name_starts_first(self):
        """Test: Active name starts first."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("openai", be1), ("anthropic", be2)])
        # Verify: fb.active_backend_name == "openai"
        assert fb.active_backend_name == "openai"

    def test_get_health(self):
        """Test: Get health."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("openai", be1), ("anthropic", be2)])
        health = fb.get_health()
        # Verify: "openai" in health
        assert "openai" in health
        # Verify: "anthropic" in health
        assert "anthropic" in health
        # Verify: health["openai"]["healthy"] is True
        assert health["openai"]["healthy"] is True

    def test_context_window_size(self):
        """Test: Context window size."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        # Verify: fb.context_window_size() > 0
        assert fb.context_window_size() > 0

    def test_supports_tool_calling(self):
        """Test: Supports tool calling."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        # Verify: isinstance(fb.supports_tool_calling(), bool)
        assert isinstance(fb.supports_tool_calling(), bool)

    def test_supports_thinking(self):
        """Test: Supports thinking."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        # Verify: isinstance(fb.supports_thinking(), bool)
        assert isinstance(fb.supports_thinking(), bool)

    def test_supports_prompt_caching(self):
        """Test: Supports prompt caching."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        # Verify: isinstance(fb.supports_prompt_caching(), bool)
        assert isinstance(fb.supports_prompt_caching(), bool)

    def test_three_backend_chain(self):
        """Test: Three backend chain."""
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        be3 = create_backend("deepseek", api_key="sk-fake")
        fb = FailoverBackend(backends=[("a", be1), ("b", be2), ("c", be3)])
        # Verify: fb.active_backend_name == "a"
        assert fb.active_backend_name == "a"
        # Verify: len(fb.get_health()) == 3
        assert len(fb.get_health()) == 3

    def test_empty_backends_raises(self):
        """Test: Empty backends raises."""
        with pytest.raises(ValueError, match="At least one backend"):
            FailoverBackend(backends=[])

    def test_count_tokens(self):
        """Test: Count tokens."""
        be1 = create_backend("openai", api_key="sk-fake")
        fb = FailoverBackend(backends=[("p", be1)])
        # Verify: isinstance(fb.count_tokens("hello"), int)
        assert isinstance(fb.count_tokens("hello"), int)

    def test_aclose(self):
        """Test: Aclose."""
        be1 = create_backend("openai", api_key="sk-fake")
        fb = FailoverBackend(backends=[("p", be1)])
        asyncio.run(fb.aclose())


# ===========================================================================
# Route
# ===========================================================================

class TestRoute:
    """Test suite for Route."""
    def test_create(self):
        """Test: Create."""
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        # Verify: route.category == TaskCategory.CODING
        assert route.category == TaskCategory.CODING
        # Verify: route.priority == 0
        assert route.priority == 0

    def test_matches_coding_prompt(self):
        """Test: Matches coding prompt."""
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        confidence = route.matches("write a python function to sort a list")
        # Verify: confidence > 0.0
        assert confidence > 0.0

    def test_matches_research_prompt(self):
        """Test: Matches research prompt."""
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.RESEARCH, backend=backend)
        confidence = route.matches("research the best database for microservices")
        # Verify: confidence > 0.0
        assert confidence > 0.0

    def test_matches_no_match(self):
        """Test: Matches no match."""
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        confidence = route.matches("hello how are you")
        # Verify: confidence == 0.0
        assert confidence == 0.0


# ===========================================================================
# RouterBackend
# ===========================================================================

class TestRouterBackend:
    """Test suite for RouterBackend."""
    def test_create(self):
        """Test: Create."""
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        # Verify: isinstance(rb, BaseBackend)
        assert isinstance(rb, BaseBackend)

    def test_last_route_default(self):
        """Test: Last route default."""
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        # Verify: rb.last_route == "default"
        assert rb.last_route == "default"

    def test_context_window_size(self):
        """Test: Context window size."""
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        # Verify: rb.context_window_size() > 0
        assert rb.context_window_size() > 0

    def test_supports_tool_calling(self):
        """Test: Supports tool calling."""
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        # Verify: isinstance(rb.supports_tool_calling(), bool)
        assert isinstance(rb.supports_tool_calling(), bool)

    def test_supports_thinking(self):
        """Test: Supports thinking."""
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        # Verify: isinstance(rb.supports_thinking(), bool)
        assert isinstance(rb.supports_thinking(), bool)

    def test_cost_tracker_enabled(self):
        """Test: Cost tracker enabled."""
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default, track_costs=True)
        # Verify: rb.cost_tracker is not None
        assert rb.cost_tracker is not None

    def test_cost_tracker_disabled(self):
        """Test: Cost tracker disabled."""
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default, track_costs=False)
        # Verify: rb.cost_tracker is None
        assert rb.cost_tracker is None

    def test_route_stats_defaults(self):
        """Test: Route stats defaults."""
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        stats = rb.route_stats
        # Verify: isinstance(stats, dict)
        assert isinstance(stats, dict)
        # Verify: "default" in stats
        assert "default" in stats
        # Verify: TaskCategory.CODING in stats
        assert TaskCategory.CODING in stats


# ===========================================================================
# RouterBackend — Connection monitor & Auth integration
# ===========================================================================

class TestRouterBackendIntegration:
    """Tests for AuthManager + ConnectionHealthMonitor integration."""

    @pytest.mark.asyncio
    async def test_get_health_returns_connection_info(self):
        """Test: Get health returns connection info."""
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)
        health = rb.get_health()
        # Verify: "connection" in health
        assert "connection" in health
        # Verify: "auth" in health
        assert "auth" in health
        # Verify: health["auth"] is None
        assert health["auth"] is None
        # Verify: isinstance(health["connection"], dict)
        assert isinstance(health["connection"], dict)
        # Verify: "last_route" in health
        assert "last_route" in health

    @pytest.mark.asyncio
    async def test_auth_manager_accepted_and_visible(self):
        """Test: Auth manager accepted and visible."""
        auth = AuthManager(provider="test", api_key="sk-test")
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(
            routes={TaskCategory.CODING: coding}, default=default,
            auth_manager=auth,
        )
        health = rb.get_health()
        # Verify: health["auth"] is not None
        assert health["auth"] is not None
        # Verify: health["auth"]["provider"] == "test"
        assert health["auth"]["provider"] == "test"
        # Verify: health["auth"]["has_primary"] is True
        assert health["auth"]["has_primary"] is True

    @pytest.mark.asyncio
    async def test_connection_failure_recorded(self):
        """Test: Connection failure recorded."""
        coding = MockBackend(name="coding", fail_on_call=True)
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        with pytest.raises(httpx.ConnectError):
            async for _ in rb.chat(
                messages=[{"role": "user", "content": "write a python function"}]
            ):
                pass

        # Verify the coding route got a failure recorded.
        rh = rb._connection_monitor.get_health(TaskCategory.CODING)
        # Verify: rh is not None
        assert rh is not None
        # Verify: rh.consecutive_failures >= 1
        assert rh.consecutive_failures >= 1
        # Verify: rh.total_failures >= 1
        assert rh.total_failures >= 1

    @pytest.mark.asyncio
    async def test_successful_call_records_success(self):
        """Test: Successful call records success."""
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Pre-record a failure so we can verify success clears it.
        rb._connection_monitor.record_failure(TaskCategory.CODING, "previous error")
        # Verify: rb._connection_monitor.get_health(TaskCategory.CODING).consecutive_failures == 1
        assert rb._connection_monitor.get_health(TaskCategory.CODING).consecutive_failures == 1

        # Successful call.
        async for _ in rb.chat(
            messages=[{"role": "user", "content": "write a python function"}]
        ):
            pass

        rh = rb._connection_monitor.get_health(TaskCategory.CODING)
        # Verify: rh is not None
        assert rh is not None
        # Verify: rh.consecutive_failures == 0
        assert rh.consecutive_failures == 0
        # Verify: rh.total_requests >= 1
        assert rh.total_requests >= 1

    @pytest.mark.asyncio
    async def test_degraded_route_falls_back(self):
        """Test: Degraded route falls back."""
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Degrade the coding route.
        for _ in range(3):
            rb._connection_monitor.record_failure(TaskCategory.CODING, "timeout")
        # Verify: rb._connection_monitor.is_degraded(TaskCategory.CODING)
        assert rb._connection_monitor.is_degraded(TaskCategory.CODING)

        # Chat with a coding prompt — should fall back to default.
        async for _ in rb.chat(
            messages=[{"role": "user", "content": "write a python function"}]
        ):
            pass

        # Verify: rb.last_route == "default"
        assert rb.last_route == "default"

    @pytest.mark.asyncio
    async def test_all_routes_degraded_uses_original_selection(self):
        """Test: All routes degraded uses original selection."""
        coding = MockBackend(name="coding", fail_on_call=True)
        default = MockBackend(name="default", fail_on_call=True)
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Degrade both routes.
        for _ in range(3):
            rb._connection_monitor.record_failure(TaskCategory.CODING, "timeout")
            rb._connection_monitor.record_failure("default", "timeout")
        # Verify: rb._connection_monitor.is_degraded(TaskCategory.CODING)
        assert rb._connection_monitor.is_degraded(TaskCategory.CODING)
        # Verify: rb._connection_monitor.is_degraded("default")
        assert rb._connection_monitor.is_degraded("default")

        # All degraded — should use original selection (coding) despite degradation.
        with pytest.raises(httpx.ConnectError):
            async for _ in rb.chat(
                messages=[{"role": "user", "content": "write a python function"}]
            ):
                pass

        # Verify: rb.last_route == TaskCategory.CODING
        assert rb.last_route == TaskCategory.CODING

    @pytest.mark.asyncio
    async def test_non_connection_error_still_recorded(self):
        """Test: Non connection error still recorded."""
        coding = MockBackend(
            name="coding", fail_on_call=True,
            fail_error=ValueError("bad request"),
        )
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        with pytest.raises(ValueError, match="bad request"):
            async for _ in rb.chat(
                messages=[{"role": "user", "content": "write a python function"}]
            ):
                pass

        rh = rb._connection_monitor.get_health(TaskCategory.CODING)
        # Verify: rh is not None
        assert rh is not None
        # Verify: rh.consecutive_failures >= 1
        assert rh.consecutive_failures >= 1


# ===========================================================================
# CostTracker
# ===========================================================================

class TestCostTracker:
    """Test suite for CostTracker."""
    def test_create(self):
        """Test: Create."""
        ct = CostTracker()
        # Verify: ct.total_cost_usd == 0.0
        assert ct.total_cost_usd == 0.0
        # Verify: ct.total_input_tokens == 0
        assert ct.total_input_tokens == 0
        # Verify: ct.total_output_tokens == 0
        assert ct.total_output_tokens == 0
        # Verify: ct.cache_hit_tokens == 0
        assert ct.cache_hit_tokens == 0

    def test_record_usage(self):
        """Test: Record usage."""
        ct = CostTracker()
        ct.record(model="gpt-4o", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        # Verify: ct.total_input_tokens == 100
        assert ct.total_input_tokens == 100
        # Verify: ct.total_output_tokens == 50
        assert ct.total_output_tokens == 50
        # Verify: ct.total_cost_usd == 0.0005
        assert ct.total_cost_usd == 0.0005
        # Verify: ct.requests_by_model["gpt-4o"] == 1
        assert ct.requests_by_model["gpt-4o"] == 1

    def test_multiple_models(self):
        """Test: Multiple models."""
        ct = CostTracker()
        ct.record(model="gpt-4o", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        ct.record(model="claude-sonnet-4-20250514", input_tokens=200, output_tokens=100, cost_usd=0.003)  # noqa: E501
        # Verify: ct.total_input_tokens == 300
        assert ct.total_input_tokens == 300
        # Verify: ct.total_output_tokens == 150
        assert ct.total_output_tokens == 150
        # Verify: ct.total_cost_usd == 0.0035
        assert ct.total_cost_usd == 0.0035
        # Verify: len(ct.cost_by_model) == 2
        assert len(ct.cost_by_model) == 2
        # Verify: ct.requests_by_model["gpt-4o"] == 1
        assert ct.requests_by_model["gpt-4o"] == 1
        # Verify: ct.requests_by_model["claude-sonnet-4-20250514"] == 1
        assert ct.requests_by_model["claude-sonnet-4-20250514"] == 1

    def test_with_cache(self):
        """Test: With cache."""
        ct = CostTracker()
        ct.record(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=50,
                  cost_usd=0.01, cache_hit=500, cache_savings=0.005)
        # Verify: ct.cache_hit_tokens == 500
        assert ct.cache_hit_tokens == 500
        # Verify: ct.cache_savings_usd == 0.005
        assert ct.cache_savings_usd == 0.005

    def test_to_dict(self):
        """Test: To dict."""
        ct = CostTracker()
        ct.record(model="gpt-4o", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        d = ct.to_dict()
        # Verify: d["total_input_tokens"] == 100
        assert d["total_input_tokens"] == 100
        # Verify: d["total_output_tokens"] == 50
        assert d["total_output_tokens"] == 50
        # Verify: "cost_by_model" in d
        assert "cost_by_model" in d
        # Verify: "requests_by_model" in d
        assert "requests_by_model" in d


# ===========================================================================
# TaskCategory
# ===========================================================================

class TestTaskCategory:
    """Test suite for TaskCategory."""
    def test_all_categories_exist(self):
        """Test: All categories exist."""
        # Verify: TaskCategory.CLASSIFICATION == "classification"
        assert TaskCategory.CLASSIFICATION == "classification"
        # Verify: TaskCategory.REASONING == "reasoning"
        assert TaskCategory.REASONING == "reasoning"
        # Verify: TaskCategory.CODING == "coding"
        assert TaskCategory.CODING == "coding"
        # Verify: TaskCategory.RESEARCH == "research"
        assert TaskCategory.RESEARCH == "research"
        # Verify: TaskCategory.WRITING == "writing"
        assert TaskCategory.WRITING == "writing"
        # Verify: TaskCategory.PLANNING == "planning"
        assert TaskCategory.PLANNING == "planning"
        # Verify: TaskCategory.EXECUTION == "execution"
        assert TaskCategory.EXECUTION == "execution"
        # Verify: TaskCategory.SUMMARIZATION == "summarization"
        assert TaskCategory.SUMMARIZATION == "summarization"
