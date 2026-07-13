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
    """Verify that EncreConfig has correct default values."""

    def test_default_model(self):
        """Test: Default model."""
        config = EncreConfig()
        # Verify: config.model == "" (flat field empty until a ModelConfig is selected)
        assert config.model == ""

    def test_default_backend_type(self):
        """Test: Default backend type."""
        config = EncreConfig()
        # Verify: config.backend_type == "" (derived from active ModelConfig)
        assert config.backend_type == ""

    def test_default_max_tokens(self):
        """Test: Default max tokens."""
        config = EncreConfig()
        # Verify: config.max_tokens == 4096
        assert config.max_tokens == 4096

    def test_default_temperature_not_present(self):
        """Test: Default temperature not present."""
        config = EncreConfig()
        # Verify: not hasattr(config, "temperature")
        assert not hasattr(config, "temperature")

    def test_default_permission_mode(self):
        """Test: Default permission mode."""
        config = EncreConfig()
        # Verify: config.permission_mode == "bypass"
        assert config.permission_mode == "bypass"

    def test_default_max_turns(self):
        """Test: Default max turns."""
        config = EncreConfig()
        # Verify: config.max_turns == 0 (0 = unlimited)
        assert config.max_turns == 0

    def test_default_sandbox_enabled(self):
        """Test: Default sandbox enabled."""
        config = EncreConfig()
        # Verify: config.sandbox_enabled is True
        assert config.sandbox_enabled is True

    def test_default_telemetry_enabled(self):
        """Test: Default telemetry enabled."""
        config = EncreConfig()
        # Verify: config.telemetry_enabled is True
        assert config.telemetry_enabled is True

    def test_default_log_level(self):
        """Test: Default log level."""
        config = EncreConfig()
        # Verify: config.log_level == "INFO"
        assert config.log_level == "INFO"

    def test_default_enable_prompt_caching(self):
        """Test: Default enable prompt caching."""
        config = EncreConfig()
        # Verify: config.enable_prompt_caching is True
        assert config.enable_prompt_caching is True

    def test_default_checkpoint_max_count(self):
        """Test: Default checkpoint max count."""
        config = EncreConfig()
        # Verify: config.checkpoint_max_count == 10
        assert config.checkpoint_max_count == 10

    def test_default_tool_result_max_chars(self):
        """Test: Default tool result max chars."""
        config = EncreConfig()
        # Verify: config.tool_result_max_chars == 80000
        assert config.tool_result_max_chars == 80000

    def test_default_session_max_age_hours(self):
        """Test: Default session max age hours."""
        config = EncreConfig()
        # Verify: config.session_max_age_hours == 24.0
        assert config.session_max_age_hours == 24.0

    def test_default_api_key(self):
        """Test: Default api key."""
        config = EncreConfig()
        # Verify: config.api_key == ""
        assert config.api_key == ""

    def test_default_base_url(self):
        """Test: Default base url."""
        config = EncreConfig()
        # Verify: config.base_url == ""
        assert config.base_url == ""

    def test_default_workspace(self):
        """Test: Default workspace."""
        config = EncreConfig()
        # Verify: config.workspace == ""
        assert config.workspace == ""


class TestEncreConfigKeywordOverrides:
    """Verify that keyword arguments properly override defaults."""

    def test_override_model(self):
        """Test: Override model."""
        config = EncreConfig(model="gpt-4o-mini")
        # Verify: config.model == "gpt-4o-mini"
        assert config.model == "gpt-4o-mini"

    def test_override_max_tokens(self):
        """Test: Override max tokens."""
        config = EncreConfig(max_tokens=8192)
        # Verify: config.max_tokens == 8192
        assert config.max_tokens == 8192

    def test_override_max_turns(self):
        """Test: Override max turns."""
        config = EncreConfig(max_turns=5)
        # Verify: config.max_turns == 5
        assert config.max_turns == 5

    def test_override_permission_mode(self):
        """Test: Override permission mode."""
        config = EncreConfig(permission_mode="bypass")
        # Verify: config.permission_mode == "bypass"
        assert config.permission_mode == "bypass"

    def test_override_backend_type(self):
        """Test: Override backend type."""
        config = EncreConfig(backend_type="anthropic")
        # Verify: config.backend_type == "anthropic"
        assert config.backend_type == "anthropic"

    def test_override_log_level(self):
        """Test: Override log level."""
        config = EncreConfig(log_level="DEBUG")
        # Verify: config.log_level == "DEBUG"
        assert config.log_level == "DEBUG"

    def test_override_sandbox_enabled(self):
        """Test: Override sandbox enabled."""
        config = EncreConfig(sandbox_enabled=False)
        # Verify: config.sandbox_enabled is False
        assert config.sandbox_enabled is False

    def test_override_telemetry_enabled(self):
        """Test: Override telemetry enabled."""
        config = EncreConfig(telemetry_enabled=False)
        # Verify: config.telemetry_enabled is False
        assert config.telemetry_enabled is False

    def test_override_session_max_age_hours(self):
        """Test: Override session max age hours."""
        config = EncreConfig(session_max_age_hours=48.0)
        # Verify: config.session_max_age_hours == 48.0
        assert config.session_max_age_hours == 48.0

    def test_multiple_overrides(self):
        """Test: Multiple overrides."""
        config = EncreConfig(model="deepseek-chat", max_tokens=32000, permission_mode="accept_edits")  # noqa: E501
        # Verify: config.model == "deepseek-chat"
        assert config.model == "deepseek-chat"
        # Verify: config.max_tokens == 32000
        assert config.max_tokens == 32000
        # Verify: config.permission_mode == "accept_edits"
        assert config.permission_mode == "accept_edits"


class TestEncreConfigBackendKwargs:
    """Verify backend_kwargs handling."""

    def test_default_backend_kwargs_empty(self):
        """Test: Default backend kwargs empty."""
        config = EncreConfig()
        # Verify: config.backend_kwargs == {}
        assert config.backend_kwargs == {}

    def test_backend_kwargs_populated(self):
        """Test: Backend kwargs populated."""
        config = EncreConfig(backend_kwargs={"temperature": 0.7, "top_p": 0.9})
        # Verify: config.backend_kwargs == {"temperature": 0.7, "top_p": 0.9}
        assert config.backend_kwargs == {"temperature": 0.7, "top_p": 0.9}

    def test_backend_kwargs_does_not_affect_top_level(self):
        """Test: Backend kwargs does not affect top level."""
        config = EncreConfig(backend_kwargs={"model": "fake"})
        # Verify: config.model == ""  # untouched (flat field stays at default)
        assert config.model == ""  # untouched
        # Verify: config.backend_kwargs["model"] == "fake"
        assert config.backend_kwargs["model"] == "fake"


class TestEncreConfigToDict:
    """Verify to_dict() serialization."""

    def test_to_dict_returns_dict(self):
        """Test: To dict returns dict."""
        config = EncreConfig()
        result = config.to_dict()
        # Verify: isinstance(result, dict)
        assert isinstance(result, dict)

    def test_to_dict_contains_default_values(self):
        """Test: To dict contains default values."""
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

    def test_to_dict_reflects_overrides(self):
        """Test: To dict reflects overrides."""
        config = EncreConfig(model="claude-sonnet-4-20250514", backend_type="anthropic")
        result = config.to_dict()
        # Verify: result["model"] == "claude-sonnet-4-20250514"
        assert result["model"] == "claude-sonnet-4-20250514"
        # Verify: result["backend_type"] == "anthropic"
        assert result["backend_type"] == "anthropic"

    def test_to_dict_includes_backend_kwargs(self):
        """Test: To dict includes backend kwargs."""
        config = EncreConfig(backend_kwargs={"timeout": 60})
        result = config.to_dict()
        # Verify: result["backend_kwargs"] == {"timeout": 60}
        assert result["backend_kwargs"] == {"timeout": 60}

    def test_to_dict_roundtrip(self):
        """Test: To dict roundtrip."""
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
    """Spot-check specialized flags to ensure they exist."""

    def test_thinking_config_default_is_none(self):
        """Test: Thinking config default is none."""
        config = EncreConfig()
        # Verify: config.thinking_config is None
        assert config.thinking_config is None

    def test_thinking_config_settable(self):
        """Test: Thinking config settable."""
        from encre.utils.types import AdaptiveThinking
        tc = AdaptiveThinking(enabled=True, min_tokens=1024, max_tokens=8192)
        config = EncreConfig(thinking_config=tc)
        # Verify: config.thinking_config is tc
        assert config.thinking_config is tc
        # Verify: config.thinking_config.enabled is True
        assert config.thinking_config.enabled is True

    def test_enable_prompt_caching_settable(self):
        """Test: Enable prompt caching settable."""
        config = EncreConfig(enable_prompt_caching=False)
        # Verify: config.enable_prompt_caching is False
        assert config.enable_prompt_caching is False
