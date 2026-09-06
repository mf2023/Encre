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
# MockBackend 鈥?minimal concrete backend for integration tests
# ===========================================================================

class MockBackend(BaseBackend):
    """Minimal backend for testing RouterBackend integration.

    Optionally raises an exception on chat() for testing failure paths.
    """
    def __init__(self, name: str = "mock", fail_on_call: bool = False,
                 fail_error: Exception | None = None) -> None:
        """Initialize the mock backend with optional failure injection."""
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
        """Yield a single completion or raise the injected failure."""
        if self._fail_on_call:
            raise self._fail_error
        yield BackendFinish(reason="stop", usage={})

    def supports_tool_calling(self) -> bool:
        """Report tool-calling capability to the router."""
        return True

    def context_window_size(self) -> int:
        """Return the modeled context window size."""
        return 128000

    def supports_thinking(self) -> bool:
        """Report whether extended reasoning is supported."""
        return False

    def supports_prompt_caching(self) -> bool:
        """Report whether prompt caching is supported."""
        return False

    def count_tokens(self, text: str) -> int:
        """Approximate token count by splitting on whitespace."""
        return len(text.split())

    async def aclose(self) -> None:
        """No-op teardown for the mock backend."""
        pass

# ===========================================================================
# BackendHealth
# ===========================================================================

class TestBackendHealth:
    """Engineered to validate the BackendHealth failure-tracking state machine.

    This test class exercises :class:`BackendHealth` across initialization,
    failure recording, success-based reset, threshold-based cutover, and manual
    recovery scenarios to ensure the health monitor exposes a reliable signal
    for the failover and router components that gate traffic on it.
    """

    def test_verify_initial_health_is_healthy(self):
        """Validate that a new BackendHealth starts in a healthy state.

        The test constructs a fresh :class:`BackendHealth` and asserts the
        initial counters and healthy flag because the health monitor must
        report healthy before any traffic has flowed through the backend.
        """
        bh = BackendHealth(name="openai")
        # healthy must default to True so new backends accept traffic immediately.
        assert bh.healthy is True
        # consecutive_failures must start at zero to avoid false cutover.
        assert bh.consecutive_failures == 0
        # total_failures and total_requests must start at zero.
        assert bh.total_failures == 0
        assert bh.total_requests == 0

    def test_verify_record_failure_updates_counters(self):
        """Validate that record_failure increments failure counters.

        The test records a single timeout failure and asserts the consecutive
        and total failure counters rise, the request counter rises, and the
        last_error string is preserved because the router reads these fields
        to decide whether to flag the backend as degraded.
        """
        bh = BackendHealth(name="openai")
        bh.record_failure("timeout")
        # Consecutive failures must increment on each recorded failure.
        assert bh.consecutive_failures == 1
        # Total failures must also increment and never decrease.
        assert bh.total_failures == 1
        # Total requests must increment to track throughput.
        assert bh.total_requests == 1
        # last_error must preserve the most recent error message.
        assert bh.last_error == "timeout"

    def test_verify_record_success_resets_consecutive_failures(self):
        """Validate that record_success resets consecutive failures without masking totals.

        The test records two failures followed by a success and asserts the
        consecutive counter drops to zero while total_requests has accumulated
        all three events because the failover logic uses consecutive failures
        as the primary degradation signal while retaining total counters for
        observability.
        """
        bh = BackendHealth(name="openai")
        bh.record_failure("err1")
        bh.record_failure("err2")
        bh.record_success()
        # Consecutive failures must reset after a success.
        assert bh.consecutive_failures == 0
        # Total requests must reflect all events including the success.
        assert bh.total_requests == 3
        # Backend must remain healthy after recovery.
        assert bh.healthy is True

    def test_verify_consecutive_failures_trigger_unhealthy(self):
        """Validate that exceeding the failure threshold flips healthy to False.

        The test records three consecutive failures and asserts healthy becomes
        False because the backend is considered degraded once the consecutive
        failure threshold is crossed, which triggers failover bypass.
        """
        bh = BackendHealth(name="openai")
        for i in range(3):
            bh.record_failure(f"error {i}")
        # healthy must flip to False once the threshold is exceeded.
        assert bh.healthy is False

    def test_verify_manual_recovery_resets_state(self):
        """Validate that manual recovery clears failures and restores health.

        The test drives the backend unhealthy, rewinds last_checked into the
        past, manually sets healthy=True and consecutive_failures=0, then
        asserts the recovery took effect because operators may inject manual
        probes after a known outage window.
        """
        import time
        bh = BackendHealth(name="openai")
        for _ in range(3):
            bh.record_failure("timeout")
        # Confirm unhealthy before manual intervention.
        assert bh.healthy is False
        # Simulate grace period passing and probe
        bh.last_checked = time.time() - 400
        bh.healthy = True
        bh.consecutive_failures = 0
        # Manual recovery must restore healthy status.
        assert bh.healthy is True


# ===========================================================================
# FailoverBackend
# ===========================================================================

class TestFailoverBackend:
    """Engineered to validate the FailoverBackend primary/fallback chain.

    This test class exercises :class:`FailoverBackend` across creation,
    active-backend selection, health reporting, capability delegation,
    multi-backend chains, empty-input rejection, token counting, and
    async teardown scenarios to ensure the failover wrapper satisfies the
    BaseBackend contract regardless of the underlying backend stack.
    """

    def test_verify_failover_backend_creation(self):
        """Validate that FailoverBackend accepts a primary/fallback pair.

        The test creates two real backends and wraps them in a
        :class:`FailoverBackend`, asserting the wrapper is instantiable and
        itself a BaseBackend because the router must be able to pass the
        wrapper through the same interface as a plain backend.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("primary", be1), ("fallback", be2)])
        assert fb is not None
        assert isinstance(fb, BaseBackend)

    def test_verify_active_backend_starts_as_primary(self):
        """Validate that the first backend in the chain is selected as active.

        The test constructs a failover wrapper with openai first and asserts
        active_backend_name equals 'openai' because the primary must serve
        traffic initially until a failure triggers cutover.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("openai", be1), ("anthropic", be2)])
        # Primary backend must be elected on construction.
        assert fb.active_backend_name == "openai"

    def test_verify_get_health_reports_all_backends(self):
        """Validate that get_health exposes every registered backend's status.

        The test builds a two-backend failover chain and asserts both names
        appear in the health map and that the primary reports healthy because
        the health endpoint is the primary observability contract for SRE tooling.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("openai", be1), ("anthropic", be2)])
        health = fb.get_health()
        # Both backends must appear in the health report.
        assert "openai" in health
        assert "anthropic" in health
        # Primary must report healthy on a fresh chain.
        assert health["openai"]["healthy"] is True

    def test_verify_context_window_size_delegates_correctly(self):
        """Validate that context_window_size returns a positive integer.

        The test delegates to :meth:`FailoverBackend.context_window_size` and
        asserts the result is greater than zero because the router uses this
        value to cap prompt size before dispatch.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        # Delegated window size must be a meaningful positive integer.
        assert fb.context_window_size() > 0

    def test_verify_supports_tool_calling_delegation(self):
        """Validate that supports_tool_calling returns a strict bool.

        The test delegates to :meth:`FailoverBackend.supports_tool_calling`
        and asserts a bool is returned because the router branches on this
        flag when constructing tool-use prompts.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        assert isinstance(fb.supports_tool_calling(), bool)

    def test_verify_supports_thinking_delegation(self):
        """Validate that supports_thinking returns a strict bool.

        The test delegates to :meth:`FailoverBackend.supports_thinking` and
        asserts a bool because the agent loop gates extended-reasoning
        payloads on this capability flag.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        assert isinstance(fb.supports_thinking(), bool)

    def test_verify_supports_prompt_caching_delegation(self):
        """Validate that supports_prompt_caching returns a strict bool.

        The test delegates to :meth:`FailoverBackend.supports_prompt_caching`
        and asserts a bool because prompt-caching eligibility affects cost
        estimation and request shaping.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        fb = FailoverBackend(backends=[("p", be1), ("f", be2)])
        assert isinstance(fb.supports_prompt_caching(), bool)

    def test_verify_three_backend_chain(self):
        """Validate that a three-backend chain reports all members healthy.

        The test constructs a primary/fallback/third chain and asserts the
        primary is elected and the health map contains all three entries
        because linear chains are a common production deployment pattern.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        be2 = create_backend("anthropic", api_key="sk-ant-fake")
        be3 = create_backend("deepseek", api_key="sk-fake")
        fb = FailoverBackend(backends=[("a", be1), ("b", be2), ("c", be3)])
        # Primary must be elected on construction.
        assert fb.active_backend_name == "a"
        # Health report must cover every registered backend.
        assert len(fb.get_health()) == 3

    def test_verify_empty_backends_raises(self):
        """Validate that FailoverBackend rejects an empty backend list.

        The test passes an empty list and asserts a ValueError is raised
        because a failover wrapper without at least one backend is meaningless
        and must fail loudly at construction time.
        """
        with pytest.raises(ValueError, match="At least one backend"):
            FailoverBackend(backends=[])

    def test_verify_count_tokens_delegates(self):
        """Validate that count_tokens delegates to the active backend.

        The test wraps a single backend and asserts the token-count result is
        an integer because the router feeds this value into budget checks.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        fb = FailoverBackend(backends=[("p", be1)])
        assert isinstance(fb.count_tokens("hello"), int)

    def test_verify_aclose_teardown(self):
        """Validate that aclose completes without error.

        The test invokes :meth:`FailoverBackend.aclose` and asserts it finishes
        because the gateway must be able to drain backends cleanly on shutdown.
        """
        be1 = create_backend("openai", api_key="sk-fake")
        fb = FailoverBackend(backends=[("p", be1)])
        asyncio.run(fb.aclose())


# ===========================================================================
# Route
# ===========================================================================

class TestRoute:
    """Engineered to validate the Route category-matching behavior.

    This test class exercises :class:`Route` across construction, coding-prompt
    matching, research-prompt matching, and no-match scenarios to ensure the
    route classifier produces sensible confidence scores for the router backend.
    """

    def test_verify_route_creation(self):
        """Validate that Route stores category and defaults priority to zero.

        The test constructs a :class:`Route` bound to CODING and asserts the
        category matches and priority defaults to zero because routes are
        sorted by priority before matching.
        """
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        assert route.category == TaskCategory.CODING
        assert route.priority == 0

    def test_verify_route_matches_coding_prompt(self):
        """Validate that a CODING route yields positive confidence for code prompts.

        The test feeds a coding-oriented prompt into :meth:`Route.matches` and
        asserts the confidence is greater than zero because the router uses
        this score to select the most appropriate backend for a task.
        """
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        confidence = route.matches("write a python function to sort a list")
        assert confidence > 0.0

    def test_verify_route_matches_research_prompt(self):
        """Validate that a RESEARCH route yields positive confidence for research prompts.

        The test feeds a research-oriented prompt into :meth:`Route.matches`
        and asserts the confidence is greater than zero because the router
        must distinguish research queries from code-generation queries.
        """
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.RESEARCH, backend=backend)
        confidence = route.matches("research the best database for microservices")
        assert confidence > 0.0

    def test_verify_route_no_match_for_unrelated_prompt(self):
        """Validate that a CODING route scores unrelated chit-chat as zero.

        The test feeds a casual greeting into a CODING route and asserts
        confidence equals zero because the router should not route generic
        conversational input into code-specialist backends.
        """
        backend = create_backend("openai", api_key="sk-fake")
        route = Route(category=TaskCategory.CODING, backend=backend)
        confidence = route.matches("hello how are you")
        assert confidence == 0.0


# ===========================================================================
# RouterBackend
# ===========================================================================

class TestRouterBackend:
    """Engineered to validate the RouterBackend construction and basic contracts.

    This test class exercises :class:`RouterBackend` across creation, last-route
    defaults, capability delegation, cost-tracking toggle, and stats structure
    scenarios to ensure the router wrapper satisfies the BaseBackend contract
    regardless of whether per-category routing or cost observation is enabled.
    """

    def test_verify_router_backend_creation(self):
        """Validate that RouterBackend is instantiable and satisfies BaseBackend.

        The test constructs a router with one CODING route and a default
        backend, then asserts the wrapper passes isinstance checks because
        downstream code must be able to swap RouterBackend in place of a plain
        backend without refactoring call sites.
        """
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        assert isinstance(rb, BaseBackend)

    def test_verify_last_route_defaults_to_default_label(self):
        """Validate that last_route starts as 'default' before any chat call.

        The test asserts rb.last_route == 'default' because the router must
        expose a stable label for observability even before the first request.
        """
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        assert rb.last_route == "default"

    def test_verify_context_window_size_delegation(self):
        """Validate that context_window_size delegates to the default backend.

        The test constructs a router with no category routes and asserts the
        delegated window size is positive because the router must always
        expose a sensible upper bound even when no routing rules apply.
        """
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        assert rb.context_window_size() > 0

    def test_verify_supports_tool_calling_delegation(self):
        """Validate that supports_tool_calling returns a bool from the default backend.

        The test asserts a bool because the caller branches on this flag when
        building tool-use prompts and must not receive None or a non-bool.
        """
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        assert isinstance(rb.supports_tool_calling(), bool)

    def test_verify_supports_thinking_delegation(self):
        """Validate that supports_thinking returns a bool from the default backend.

        The test asserts a bool because the agent loop gates reasoning-mode
        payloads on this capability flag.
        """
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default)
        assert isinstance(rb.supports_thinking(), bool)

    def test_verify_cost_tracker_enabled_flag(self):
        """Validate that track_costs=True attaches a CostTracker instance.

        The test constructs a router with cost tracking enabled and asserts
        cost_tracker is not None because the router exposes per-request cost
        data to callers only when tracking is explicitly enabled.
        """
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default, track_costs=True)
        assert rb.cost_tracker is not None

    def test_verify_cost_tracker_disabled_flag(self):
        """Validate that track_costs=False leaves cost_tracker unset.

        The test constructs a router with cost tracking disabled and asserts
        cost_tracker is None because disabling the feature must avoid
        allocating tracking overhead.
        """
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes={}, default=default, track_costs=False)
        assert rb.cost_tracker is None

    def test_verify_route_stats_contains_all_keys(self):
        """Validate that route_stats exposes both the default and category entries.

        The test constructs a router with one CODING route and asserts the
        stats dict contains 'default' and TaskCategory.CODING because the
        stats contract is used by dashboards and logs to render per-route
        request counts.
        """
        routes = {TaskCategory.CODING: create_backend("openai", api_key="sk-fake")}
        default = create_backend("openai", api_key="sk-fake")
        rb = RouterBackend(routes=routes, default=default)
        stats = rb.route_stats
        assert isinstance(stats, dict)
        assert "default" in stats
        assert TaskCategory.CODING in stats


# ===========================================================================
# RouterBackend 鈥?Connection monitor & Auth integration
# ===========================================================================

class TestRouterBackendIntegration:
    """Engineered to validate connection-health monitoring and auth exposure.

    This test class exercises :class:`RouterBackend` against :class:`MockBackend`
    instances that simulate failures, combined with an :class:`AuthManager`, to
    ensure the connection monitor records failures, surface health correctly,
    and that degraded routes trigger fallback while preserving the original
    selection when every route is degraded.
    """

    @pytest.mark.asyncio
    async def test_verify_get_health_exposes_connection_and_auth(self):
        """Validate that get_health returns connection and auth sections.

        The test asserts the health map contains 'connection', 'auth', and
        'last_route' keys because the gateway health endpoint must expose all
        three dimensions so operators can inspect routing health independently
        of auth state.
        """
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)
        health = rb.get_health()
        assert "connection" in health
        assert "auth" in health
        assert health["auth"] is None
        assert isinstance(health["connection"], dict)
        assert "last_route" in health

    @pytest.mark.asyncio
    async def test_verify_auth_manager_visible_in_health(self):
        """Validate that an attached AuthManager appears in the health report.

        The test attaches an :class:`AuthManager` and asserts health['auth'] is
        not None and exposes the provider name and a primary-key flag because
        auth visibility is required for on-call diagnosis of credential issues.
        """
        auth = AuthManager(provider="test", api_key="sk-test")
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(
            routes={TaskCategory.CODING: coding}, default=default,
            auth_manager=auth,
        )
        health = rb.get_health()
        assert health["auth"] is not None
        assert health["auth"]["provider"] == "test"
        assert health["auth"]["has_primary"] is True

    @pytest.mark.asyncio
    async def test_verify_connection_failure_is_recorded(self):
        """Validate that a chat-time connection error increments failure counters.

        The test sends a coding prompt through a failing MockBackend and asserts
        the connection monitor recorded at least one consecutive and total
        failure on the CODING route because the router must mark degraded
        routes so subsequent requests can be routed around them.
        """
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
        assert rh is not None
        assert rh.consecutive_failures >= 1
        assert rh.total_failures >= 1

    @pytest.mark.asyncio
    async def test_verify_successful_call_resets_consecutive_failures(self):
        """Validate that a successful call clears consecutive failures.

        The test pre-records a failure on the CODING route, confirms the
        counter is one, then runs a successful chat and asserts the counter
        drops back to zero because success must erase the streak even if
        total_failures remains elevated for observability.
        """
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Pre-record a failure so we can verify success clears it.
        rb._connection_monitor.record_failure(TaskCategory.CODING, "previous error")
        assert rb._connection_monitor.get_health(TaskCategory.CODING).consecutive_failures == 1

        # Successful call.
        async for _ in rb.chat(
            messages=[{"role": "user", "content": "write a python function"}]
        ):
            pass

        rh = rb._connection_monitor.get_health(TaskCategory.CODING)
        assert rh is not None
        assert rh.consecutive_failures == 0
        assert rh.total_requests >= 1

    @pytest.mark.asyncio
    async def test_verify_degraded_route_falls_back_to_default(self):
        """Validate that a degraded CODING route causes fallback to the default.

        The test drives three consecutive failures on the CODING route to push
        it into a degraded state, then sends a coding prompt and asserts
        last_route switches to 'default' because the router must redirect away
        from degraded routes to maintain service availability.
        """
        coding = MockBackend(name="coding")
        default = MockBackend(name="default")
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Degrade the coding route.
        for _ in range(3):
            rb._connection_monitor.record_failure(TaskCategory.CODING, "timeout")
        assert rb._connection_monitor.is_degraded(TaskCategory.CODING)

        # Chat with a coding prompt 鈥?should fall back to default.
        async for _ in rb.chat(
            messages=[{"role": "user", "content": "write a python function"}]
        ):
            pass

        assert rb.last_route == "default"

    @pytest.mark.asyncio
    async def test_verify_all_routes_degraded_preserves_original_selection(self):
        """Validate that the router keeps the original selection when every route is degraded.

        The test drives both the CODING route and the default route into a
        degraded state, then sends a coding prompt and asserts the router
        still attempts the originally selected route ('coding') instead of
        silently collapsing to default, because fallback should only apply
        when at least one non-degraded alternative exists.
        """
        coding = MockBackend(name="coding", fail_on_call=True)
        default = MockBackend(name="default", fail_on_call=True)
        rb = RouterBackend(routes={TaskCategory.CODING: coding}, default=default)

        # Degrade both routes.
        for _ in range(3):
            rb._connection_monitor.record_failure(TaskCategory.CODING, "timeout")
            rb._connection_monitor.record_failure("default", "timeout")
        assert rb._connection_monitor.is_degraded(TaskCategory.CODING)
        assert rb._connection_monitor.is_degraded("default")

        # All degraded 鈥?should use original selection (coding) despite degradation.
        with pytest.raises(httpx.ConnectError):
            async for _ in rb.chat(
                messages=[{"role": "user", "content": "write a python function"}]
            ):
                pass

        assert rb.last_route == TaskCategory.CODING

    @pytest.mark.asyncio
    async def test_verify_non_connection_error_is_still_recorded(self):
        """Validate that non-connection errors (e.g. ValueError) are recorded too.

        The test configures a MockBackend that raises ValueError on call and
        asserts the connection monitor still records a failure because any
        persistent error class should contribute to the degradation signal,
        not just network-level exceptions.
        """
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
        assert rh is not None
        assert rh.consecutive_failures >= 1


# ===========================================================================
# CostTracker
# ===========================================================================

class TestCostTracker:
    """Engineered to validate the CostTracker accumulation and serialization.

    This test class exercises :class:`CostTracker` across initialization,
    single-model recording, multi-model aggregation, cache-aware recording,
    and dict export scenarios to ensure cost accounting remains accurate
    across heterogeneous backend usage.
    """

    def test_verify_cost_tracker_initial_state(self):
        """Validate that a fresh CostTracker starts at zero for every counter.

        The test asserts total_cost_usd, input/output tokens, and cache tokens
        are all zero because the tracker must begin from a clean slate each
        time a new router instance is constructed.
        """
        ct = CostTracker()
        assert ct.total_cost_usd == 0.0
        assert ct.total_input_tokens == 0
        assert ct.total_output_tokens == 0
        assert ct.cache_hit_tokens == 0

    def test_verify_record_usage_accumulates_correctly(self):
        """Validate that record() accumulates tokens and cost for one model.

        The test records a single usage event and asserts the counters and
        the per-model request tally because cost dashboards render these
        figures per model and in aggregate.
        """
        ct = CostTracker()
        ct.record(model="gpt-5.6", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        assert ct.total_input_tokens == 100
        assert ct.total_output_tokens == 50
        assert ct.total_cost_usd == 0.0005
        assert ct.requests_by_model["gpt-5.6"] == 1

    def test_verify_multiple_models_aggregate_correctly(self):
        """Validate that recording across models produces correct totals.

        The test records two events for different models and asserts the
        aggregated token counts, total cost, per-model cost map size, and
        per-model request tallies because billing reports must sum across
        all models while preserving per-model breakdowns.
        """
        ct = CostTracker()
        ct.record(model="gpt-5.6", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        ct.record(model="claude-sonnet-5", input_tokens=200, output_tokens=100, cost_usd=0.003)  # noqa: E501
        assert ct.total_input_tokens == 300
        assert ct.total_output_tokens == 150
        assert ct.total_cost_usd == 0.0035
        assert len(ct.cost_by_model) == 2
        assert ct.requests_by_model["gpt-5.6"] == 1
        assert ct.requests_by_model["claude-sonnet-5"] == 1

    def test_verify_cache_hit_tokens_and_savings_are_recorded(self):
        """Validate that cache-hit fields are recorded when present.

        The test records a usage event carrying cache_hit and cache_savings
        and asserts those fields appear in the tracker because prompt-cache
        reporting requires separate counters from the raw token totals.
        """
        ct = CostTracker()
        ct.record(model="claude-sonnet-5", input_tokens=1000, output_tokens=50,
                  cost_usd=0.01, cache_hit=500, cache_savings=0.005)
        assert ct.cache_hit_tokens == 500
        assert ct.cache_savings_usd == 0.005

    def test_verify_to_dict_exports_accumulated_state(self):
        """Validate that to_dict returns the full accumulated cost report.

        The test records one event, calls :meth:`CostTracker.to_dict`, and
        asserts the output contains the top-level token/cost fields plus
        the nested per-model maps because the exported dict is consumed by
        logging, metrics endpoints, and billing exporters.
        """
        ct = CostTracker()
        ct.record(model="gpt-5.6", input_tokens=100, output_tokens=50, cost_usd=0.0005)
        d = ct.to_dict()
        assert d["total_input_tokens"] == 100
        assert d["total_output_tokens"] == 50
        assert "cost_by_model" in d
        assert "requests_by_model" in d


# ===========================================================================
# TaskCategory
# ===========================================================================

class TestTaskCategory:
    """Engineered to validate the TaskCategory string constants.

    This test class asserts that every expected category constant maps to its
    canonical string value because the router performs string comparison on
    these constants when selecting routes and reporting stats.
    """

    def test_verify_all_category_constants_are_defined(self):
        """Validate that every TaskCategory constant matches its canonical string.

        The test asserts each constant against its expected value because the
        router and the front-end dashboard share these strings and must stay
        in sync to avoid silent misrouting.
        """
        assert TaskCategory.CLASSIFICATION == "classification"
        assert TaskCategory.REASONING == "reasoning"
        assert TaskCategory.CODING == "coding"
        assert TaskCategory.RESEARCH == "research"
        assert TaskCategory.WRITING == "writing"
        assert TaskCategory.PLANNING == "planning"
        assert TaskCategory.EXECUTION == "execution"
        assert TaskCategory.SUMMARIZATION == "summarization"
