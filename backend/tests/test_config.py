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

"""Tests for EncreConfig: defaults, overrides, to_dict, factory methods."""


from encre.config import EncreConfig


class TestEncreConfigDefaults:
    """Engineered to validate that :class:`EncreConfig` initializes with correct default values.

    Every field has a documented default that controls agent behavior
    (model selection, token budget, permission policy, sandboxing,
    telemetry, logging, checkpoint limits, session TTL). Tests verify
    the defaults match the product specification so regressions that
    silently shift behavior are caught at construction time.
    """

    def test_verify_default_model_is_empty_string(self):
        """Validate that the default model field is empty, not a hardcoded vendor name.

        An empty default forces the caller to select a model explicitly,
        preventing the agent from defaulting to a single vendor without
        configuration and keeping the product vendor-agnostic.
        """
        config = EncreConfig()
        # Verify: config.model == "" (flat field empty until a ModelConfig is selected)
        assert config.model == ""

    def test_verify_default_backend_type_is_empty_string(self):
        """Validate that the default backend_type is empty, derived from the active ModelConfig.

        backend_type is a denormalized convenience field; it starts empty
        and is populated only after a model is chosen so the config object
        remains consistent without requiring a separate init phase.
        """
        config = EncreConfig()
        # Verify: config.backend_type == "" (derived from active ModelConfig)
        assert config.backend_type == ""

    def test_verify_default_max_tokens_is_four_thousand_ninety_six(self):
        """Validate that the default max_tokens is 4096, a conservative context-budget starting point.

        4096 tokens is small enough to avoid excessive API cost on default
        runs while still accommodating short tool-call chains; tests confirm
        the budget is not accidentally raised or lowered by a refactor.
        """
        config = EncreConfig()
        # Verify: config.max_tokens == 4096
        assert config.max_tokens == 4096

    def test_verify_temperature_field_is_not_present_on_default_config(self):
        """Validate that temperature is absent from the default EncreConfig instance.

        Temperature is handled by the backend-specific model config, not the
        top-level EncreConfig; asserting its absence prevents callers from
        depending on a field that lives in a different config layer.
        """
        config = EncreConfig()
        # Verify: not hasattr(config, "temperature")
        assert not hasattr(config, "temperature")

    def test_verify_default_permission_mode_is_bypass(self):
        """Validate that the default permission_mode is 'bypass', allowing tools without prompting.

        The bypass default matches the developer-oriented posture of the
        agent; tests must confirm it so integration tests do not block on
        missing permission responses.
        """
        config = EncreConfig()
        # Verify: config.permission_mode == "bypass"
        assert config.permission_mode == "bypass"

    def test_verify_default_max_turns_is_zero_for_unlimited(self):
        """Validate that max_turns defaults to 0, representing an unlimited turn budget.

        Zero is the sentinel for 'no limit'; tests confirm the value rather
        than an arbitrary positive integer, so quota enforcement code can
        rely on the sentinel consistently.
        """
        config = EncreConfig()
        # Verify: config.max_turns == 0 (0 = unlimited)
        assert config.max_turns == 0

    def test_verify_default_sandbox_enabled_is_true(self):
        """Validate that sandbox_enabled defaults to True, enabling the execution sandbox.

        Sandboxing is a security requirement; the default must be on so
        unconfigured deployments do not accidentally run arbitrary commands
        without containment.
        """
        config = EncreConfig()
        # Verify: config.sandbox_enabled is True
        assert config.sandbox_enabled is True

    def test_verify_default_telemetry_enabled_is_true(self):
        """Validate that telemetry_enabled defaults to True for usage observation.

        Telemetry drives product metrics and error tracking; the default
        must be on so deployment environments collect data unless explicitly
        disabled by the operator.
        """
        config = EncreConfig()
        # Verify: config.telemetry_enabled is True
        assert config.telemetry_enabled is True

    def test_verify_default_log_level_is_info(self):
        """Validate that log_level defaults to 'INFO' for balanced observability.

        INFO captures enough structure for debugging without the noise of
        DEBUG; tests confirm the default sits at this midpoint.
        """
        config = EncreConfig()
        # Verify: config.log_level == "INFO"
        assert config.log_level == "INFO"

    def test_verify_default_enable_prompt_caching_is_true(self):
        """Validate that enable_prompt_caching defaults to True for cost optimization.

        Prompt caching reduces API cost on repeated prefixes; the default
        must be on so users get the cost benefit unless they opt out.
        """
        config = EncreConfig()
        # Verify: config.enable_prompt_caching is True
        assert config.enable_prompt_caching is True

    def test_verify_default_checkpoint_max_count_is_ten(self):
        """Validate that checkpoint_max_count defaults to 10, capping stored snapshots.

        The cap prevents unbounded memory growth in long-running sessions;
        ten checkpoints provides enough rollback depth for typical workflows.
        """
        config = EncreConfig()
        # Verify: config.checkpoint_max_count == 10
        assert config.checkpoint_max_count == 10

    def test_verify_default_tool_result_max_chars_is_eighty_thousand(self):
        """Validate that tool_result_max_chars defaults to 80000, capping tool output size.

        Truncating oversized tool results prevents context-window exhaustion;
        80KB is a balance between usefulness and budget safety.
        """
        config = EncreConfig()
        # Verify: config.tool_result_max_chars == 80000
        assert config.tool_result_max_chars == 80000

    def test_verify_default_session_max_age_hours_is_twenty_four(self):
        """Validate that session_max_age_hours defaults to 24.0, the session TTL.

        A 24-hour TTL balances persistent context against stale-session
        resource leakage; tests confirm the duration is exactly 24.0.
        """
        config = EncreConfig()
        # Verify: config.session_max_age_hours == 24.0
        assert config.session_max_age_hours == 24.0

    def test_verify_default_api_key_is_empty_string(self):
        """Validate that api_key defaults to an empty string, requiring explicit configuration.

        An empty default prevents accidental use of a developer's local key
        when the config is instantiated without arguments; tests confirm the
        field is blank so credential-leak regressions are caught.
        """
        config = EncreConfig()
        # Verify: config.api_key == ""
        assert config.api_key == ""

    def test_verify_default_base_url_is_empty_string(self):
        """Validate that base_url defaults to an empty string, requiring explicit configuration.

        An empty base_url lets the backend select its own canonical endpoint;
            tests confirm the field is blank so unintended proxy routing is prevented.
        """
        config = EncreConfig()
        # Verify: config.base_url == ""
        assert config.base_url == ""

    def test_verify_default_workspace_is_empty_string(self):
        """Validate that workspace defaults to an empty string, requiring explicit configuration.

        Workspace defines the root directory the agent operates in; leaving
        it empty forces the caller to set it explicitly, preventing the
        agent from silently operating in an unintended directory.
        """
        config = EncreConfig()
        # Verify: config.workspace == ""
        assert config.workspace == ""


class TestEncreConfigKeywordOverrides:
    """Engineered to validate that keyword arguments properly override default values on :class:`EncreConfig`.

    Each test constructs a config with one or more overrides and asserts
    the field matches the supplied value. Multi-field overrides confirm
    that combinations do not interfere with each other.
    """

    def test_verify_model_override_applies_correctly(self):
        """Validate that passing model='gpt-4o-mini' sets config.model to that value.

        Model selection is the most fundamental config override; tests
        confirm the keyword route reaches the field without intermediate transformation.
        """
        config = EncreConfig(model="gpt-4o-mini")
        # Verify: config.model == "gpt-4o-mini"
        assert config.model == "gpt-4o-mini"

    def test_verify_max_tokens_override_applies_correctly(self):
        """Validate that passing max_tokens=8192 sets config.max_tokens to that value.

        Doubling the default budget tests that the override path handles
        values above the default without capping or clamping unexpectedly.
        """
        config = EncreConfig(max_tokens=8192)
        # Verify: config.max_tokens == 8192
        assert config.max_tokens == 8192

    def test_verify_max_turns_override_applies_correctly(self):
        """Validate that passing max_turns=5 sets config.max_turns to that value.

        A finite turn limit replaces the default unlimited (0); tests confirm
        the override is stored so the loop's termination check sees the new value.
        """
        config = EncreConfig(max_turns=5)
        # Verify: config.max_turns == 5
        assert config.max_turns == 5

    def test_verify_permission_mode_override_applies_correctly(self):
        """Validate that passing permission_mode='bypass' sets config.permission_mode to that value.

        Permission mode controls whether the agent prompts before tool
        execution; overriding it must reach the field so the safety layer
        adopts the caller's intent.
        """
        config = EncreConfig(permission_mode="bypass")
        # Verify: config.permission_mode == "bypass"
        assert config.permission_mode == "bypass"

    def test_verify_backend_type_override_applies_correctly(self):
        """Validate that passing backend_type='anthropic' sets config.backend_type to that value.

        Backend type selects the function-calling protocol and message
        format; the override must propagate so the routing layer picks the
        correct backend implementation.
        """
        config = EncreConfig(backend_type="anthropic")
        # Verify: config.backend_type == "anthropic"
        assert config.backend_type == "anthropic"

    def test_verify_log_level_override_applies_correctly(self):
        """Validate that passing log_level='DEBUG' sets config.log_level to that value.

        DEBUG-level logging is useful in tests to observe internal state;
        the override must reach the logger configuration path.
        """
        config = EncreConfig(log_level="DEBUG")
        # Verify: config.log_level == "DEBUG"
        assert config.log_level == "DEBUG"

    def test_verify_sandbox_enabled_override_applies_correctly(self):
        """Validate that passing sandbox_enabled=False disables the sandbox.

        Tests running in a trusted environment may disable sandboxing; the
        override must flip the boolean flag so the execution wrapper skips
        the containment layer.
        """
        config = EncreConfig(sandbox_enabled=False)
        # Verify: config.sandbox_enabled is False
        assert config.sandbox_enabled is False

    def test_verify_telemetry_enabled_override_applies_correctly(self):
        """Validate that passing telemetry_enabled=False disables telemetry collection.

        Privacy-sensitive test runs must be able to suppress metrics; the
        override must flip the flag so the telemetry client skips reporting.
        """
        config = EncreConfig(telemetry_enabled=False)
        # Verify: config.telemetry_enabled is False
        assert config.telemetry_enabled is False

    def test_verify_session_max_age_hours_override_applies_correctly(self):
        """Validate that passing session_max_age_hours=48.0 extends the session TTL.

        Doubling the default TTL tests that floating-point overrides are
        preserved through the config boundary without integer truncation.
        """
        config = EncreConfig(session_max_age_hours=48.0)
        # Verify: config.session_max_age_hours == 48.0
        assert config.session_max_age_hours == 48.0

    def test_verify_multiple_overrides_apply_simultaneously(self):
        """Validate that multiple keyword overrides coexist without interfering with each other.

        Combined overrides are the common production path; the test asserts
        three independent fields retain their supplied values in a single
        constructor call, confirming no field clobbering occurs.
        """
        config = EncreConfig(model="deepseek-chat", max_tokens=32000, permission_mode="accept_edits")  # noqa: E501
        # Verify: config.model == "deepseek-chat"
        assert config.model == "deepseek-chat"
        # Verify: config.max_tokens == 32000
        assert config.max_tokens == 32000
        # Verify: config.permission_mode == "accept_edits"
        assert config.permission_mode == "accept_edits"


class TestEncreConfigBackendKwargs:
    """Engineered to validate backend_kwargs handling on :class:`EncreConfig`.

    backend_kwargs is a free-form dict passed through to the model backend
    client; tests confirm it is stored as-is and does not leak into top-
    level config fields, preserving the separation between structuring
    fields and passthrough transport options.
    """

    def test_verify_default_backend_kwargs_is_an_empty_dict(self):
        """Validate that backend_kwargs defaults to an empty dict when not supplied.

        An empty dict lets backend-specific code skip conditional checks
        and iterate safely; tests confirm the default is not None.
        """
        config = EncreConfig()
        # Verify: config.backend_kwargs == {}
        assert config.backend_kwargs == {}

    def test_verify_backend_kwargs_is_stored_as_supplied(self):
        """Validate that backend_kwargs stores the exact dict passed at construction.

        The dict is forwarded to the HTTP client; any mutation during
        storage would change the effective transport parameters silently.
        """
        config = EncreConfig(backend_kwargs={"temperature": 0.7, "top_p": 0.9})
        # Verify: config.backend_kwargs == {"temperature": 0.7, "top_p": 0.9}
        assert config.backend_kwargs == {"temperature": 0.7, "top_p": 0.9}

    def test_verify_backend_kwargs_does_not_affect_top_level_model_field(self):
        """Validate that placing 'model' inside backend_kwargs does not change config.model.

        backend_kwargs is transport-layer passthrough; putting a model key
        there must not shortcut the explicit model field, which would
        create ambiguity about which path wins during resolution.
        """
        config = EncreConfig(backend_kwargs={"model": "fake"})
        # Verify: config.model == ""  # untouched (flat field stays at default)
        assert config.model == ""  # untouched
        # Verify: config.backend_kwargs["model"] == "fake"
        assert config.backend_kwargs["model"] == "fake"


class TestEncreConfigToDict:
    """Engineered to validate to_dict() serialization on :class:`EncreConfig`.

    to_dict is the persistence and transmission path; tests confirm the
    output is a plain dict, includes default values, reflects overrides,
    carries backend_kwargs, and round-trips through **data reconstruction.
    """

    def test_verify_to_dict_returns_a_plain_dict(self):
        """Validate that to_dict() returns an instance of dict, not a custom mapping type.

        Callers expect standard dict methods (get, keys, item access); a
        custom mapping would break JSON serialization and keyword unpacking.
        """
        config = EncreConfig()
        result = config.to_dict()
        # Verify: isinstance(result, dict)
        assert isinstance(result, dict)

    def test_verify_to_dict_contains_default_values_for_key_fields(self):
        """Validate that to_dict() emits the expected default values for model, max_tokens, permission_mode, and backend_type.

        Serialization is used for diffs and audits; the default values must
        appear explicitly so the output is self-describing without a
        schema lookup.
        """
        config = EncreConfig()
        result = config.to_dict()
        # Verify: result["model"] == ""
        assert result["model"] == ""
        # Verify: result["max_tokens"] == 4096
        assert result["max_tokens"] == 4096
        # Verify: result["permission_mode"] == "bypass"
        assert result["permission_mode"] == "bypass"
        # Verify: result["backend_type"] == ""
        assert result["backend_type"] == ""

    def test_verify_to_dict_reflects_user_overrides(self):
        """Validate that to_dict() emits overridden values rather than the hard-coded defaults.

        The serialized form is the canonical representation; overrides must
        survive into the dict so persistence and transmission carry the
        caller's intent, not the class defaults.
        """
        config = EncreConfig(model="claude-sonnet-4-20250514", backend_type="anthropic")
        result = config.to_dict()
        # Verify: result["model"] == "claude-sonnet-4-20250514"
        assert result["model"] == "claude-sonnet-4-20250514"
        # Verify: result["backend_type"] == "anthropic"
        assert result["backend_type"] == "anthropic"

    def test_verify_to_dict_includes_backend_kwargs(self):
        """Validate that to_dict() carries the backend_kwargs dict into the output.

        backend_kwargs are transport-layer settings that must travel with
        the config across serialization boundaries; omitting them would
        reset the HTTP client to defaults on reconstruction.
        """
        config = EncreConfig(backend_kwargs={"timeout": 60})
        result = config.to_dict()
        # Verify: result["backend_kwargs"] == {"timeout": 60}
        assert result["backend_kwargs"] == {"timeout": 60}

    def test_verify_to_dict_round_trip_preserves_key_fields(self):
        """Validate that to_dict() output can reconstruct an equivalent config via EncreConfig(**data).

        Round-trip fidelity is the persistence contract; the reconstructed
        config must match the original on model, max_tokens, and permission_mode.
        """
        config1 = EncreConfig(model="gemini-pro", max_tokens=10000, permission_mode="dont_ask")
        data = config1.to_dict()
        config2 = EncreConfig(**data)
        # Verify: config2.model == config1.model
        assert config2.model == config1.model
        # Verify: config2.max_tokens == config1.max_tokens
        assert config2.max_tokens == config1.max_tokens
        # Verify: config2.permission_mode == config1.permission_mode
        assert config2.permission_mode == config1.permission_mode


class TestEncreConfigSpecialization:
    """Spot-check specialized flags on :class:`EncreConfig` to ensure they exist and are settable.

    thinking_config and enable_prompt_caching are optional features that
    must be present on the config object even when not supplied at
    construction time. Tests confirm the default state and the ability to
    override it with a real value.
    """

    def test_verify_thinking_config_defaults_to_none(self):
        """Validate that thinking_config is None by default, indicating reasoning is disabled until configured.

        None is the sentinel for 'no thinking mode selected'; tests confirm
        the field exists and is absent of a default so callers can branch
        on None without an AttributeError.
        """
        config = EncreConfig()
        # Verify: config.thinking_config is None
        assert config.thinking_config is None

    def test_verify_thinking_config_is_settable_to_an_adaptive_thinking_instance(self):
        """Validate that thinking_config accepts an AdaptiveThinking instance and stores it by reference.

        The adaptive mode toggles reasoning on based on input length;
        storing the instance by reference lets the agent inspect enabled,
        min_tokens, and max_tokens at runtime without re-parsing.
        """
        from encre.utils.types import AdaptiveThinking
        tc = AdaptiveThinking(enabled=True, min_tokens=1024, max_tokens=8192)
        config = EncreConfig(thinking_config=tc)
        # Verify: config.thinking_config is tc
        assert config.thinking_config is tc
        # Verify: config.thinking_config.enabled is True
        assert config.thinking_config.enabled is True

    def test_verify_enable_prompt_caching_is_settable_to_false(self):
        """Validate that enable_prompt_caching can be overridden to False at construction time.

        Some deployments disable caching for latency-sensitive or cost-
        sensitive workloads; the test confirms the override path reaches
        the field so operators can tune this without patching the class.
        """
        config = EncreConfig(enable_prompt_caching=False)
        # Verify: config.enable_prompt_caching is False
        assert config.enable_prompt_caching is False
