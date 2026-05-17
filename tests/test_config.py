#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

"""Tests for YmiConfig: defaults, overrides, to_dict, factory methods."""

import pytest

from yim.config import YmiConfig


class TestYmiConfigDefaults:
    """Verify that YmiConfig has correct default values."""

    def test_default_model(self):
        config = YmiConfig()
        assert config.model == "gpt-4o"

    def test_default_backend_type(self):
        config = YmiConfig()
        assert config.backend_type == "openai"

    def test_default_max_tokens(self):
        config = YmiConfig()
        assert config.max_tokens == 4096

    def test_default_temperature_not_present(self):
        config = YmiConfig()
        assert not hasattr(config, "temperature")

    def test_default_permission_mode(self):
        config = YmiConfig()
        assert config.permission_mode == "default"

    def test_default_max_turns(self):
        config = YmiConfig()
        assert config.max_turns == 25

    def test_default_sandbox_enabled(self):
        config = YmiConfig()
        assert config.sandbox_enabled is True

    def test_default_telemetry_enabled(self):
        config = YmiConfig()
        assert config.telemetry_enabled is True

    def test_default_log_level(self):
        config = YmiConfig()
        assert config.log_level == "INFO"

    def test_default_enable_prompt_caching(self):
        config = YmiConfig()
        assert config.enable_prompt_caching is True

    def test_default_checkpoint_max_count(self):
        config = YmiConfig()
        assert config.checkpoint_max_count == 10

    def test_default_tool_result_max_chars(self):
        config = YmiConfig()
        assert config.tool_result_max_chars == 80000

    def test_default_session_max_age_hours(self):
        config = YmiConfig()
        assert config.session_max_age_hours == 24.0

    def test_default_api_key(self):
        config = YmiConfig()
        assert config.api_key == ""

    def test_default_base_url(self):
        config = YmiConfig()
        assert config.base_url == ""

    def test_default_workspace(self):
        config = YmiConfig()
        assert config.workspace == ""


class TestYmiConfigKeywordOverrides:
    """Verify that keyword arguments properly override defaults."""

    def test_override_model(self):
        config = YmiConfig(model="gpt-4o-mini")
        assert config.model == "gpt-4o-mini"

    def test_override_max_tokens(self):
        config = YmiConfig(max_tokens=8192)
        assert config.max_tokens == 8192

    def test_override_max_turns(self):
        config = YmiConfig(max_turns=5)
        assert config.max_turns == 5

    def test_override_permission_mode(self):
        config = YmiConfig(permission_mode="bypass")
        assert config.permission_mode == "bypass"

    def test_override_backend_type(self):
        config = YmiConfig(backend_type="anthropic")
        assert config.backend_type == "anthropic"

    def test_override_log_level(self):
        config = YmiConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"

    def test_override_sandbox_enabled(self):
        config = YmiConfig(sandbox_enabled=False)
        assert config.sandbox_enabled is False

    def test_override_telemetry_enabled(self):
        config = YmiConfig(telemetry_enabled=False)
        assert config.telemetry_enabled is False

    def test_override_session_max_age_hours(self):
        config = YmiConfig(session_max_age_hours=48.0)
        assert config.session_max_age_hours == 48.0

    def test_multiple_overrides(self):
        config = YmiConfig(model="deepseek-chat", max_tokens=32000, permission_mode="accept_edits")
        assert config.model == "deepseek-chat"
        assert config.max_tokens == 32000
        assert config.permission_mode == "accept_edits"


class TestYmiConfigBackendKwargs:
    """Verify backend_kwargs handling."""

    def test_default_backend_kwargs_empty(self):
        config = YmiConfig()
        assert config.backend_kwargs == {}

    def test_backend_kwargs_populated(self):
        config = YmiConfig(backend_kwargs={"temperature": 0.7, "top_p": 0.9})
        assert config.backend_kwargs == {"temperature": 0.7, "top_p": 0.9}

    def test_backend_kwargs_does_not_affect_top_level(self):
        config = YmiConfig(backend_kwargs={"model": "fake"})
        assert config.model == "gpt-4o"  # untouched
        assert config.backend_kwargs["model"] == "fake"


class TestYmiConfigToDict:
    """Verify to_dict() serialization."""

    def test_to_dict_returns_dict(self):
        config = YmiConfig()
        result = config.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_default_values(self):
        config = YmiConfig()
        result = config.to_dict()
        assert result["model"] == "gpt-4o"
        assert result["max_tokens"] == 4096
        assert result["permission_mode"] == "default"
        assert result["backend_type"] == "openai"

    def test_to_dict_reflects_overrides(self):
        config = YmiConfig(model="claude-sonnet-4-20250514", backend_type="anthropic")
        result = config.to_dict()
        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["backend_type"] == "anthropic"

    def test_to_dict_includes_backend_kwargs(self):
        config = YmiConfig(backend_kwargs={"timeout": 60})
        result = config.to_dict()
        assert result["backend_kwargs"] == {"timeout": 60}

    def test_to_dict_roundtrip(self):
        config1 = YmiConfig(model="gemini-pro", max_tokens=10000, permission_mode="dont_ask")
        data = config1.to_dict()
        config2 = YmiConfig(**data)
        assert config2.model == config1.model
        assert config2.max_tokens == config1.max_tokens
        assert config2.permission_mode == config1.permission_mode


class TestYmiConfigSpecialization:
    """Spot-check specialized flags to ensure they exist."""

    def test_thinking_config_default_is_none(self):
        config = YmiConfig()
        assert config.thinking_config is None

    def test_thinking_config_settable(self):
        from yim.utils.types import AdaptiveThinking
        tc = AdaptiveThinking(enabled=True, min_tokens=1024, max_tokens=8192)
        config = YmiConfig(thinking_config=tc)
        assert config.thinking_config is tc
        assert config.thinking_config.enabled is True

    def test_enable_prompt_caching_settable(self):
        config = YmiConfig(enable_prompt_caching=False)
        assert config.enable_prompt_caching is False
