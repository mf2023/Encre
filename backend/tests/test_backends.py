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

"""Tests for backends: model registry, backend factory, BaseBackend ABC,
and retry configuration.
"""

import asyncio

import pytest
from encre.backend import create_backend
from encre.backends.base import BaseBackend
from encre.backends.registry import (
    REGISTRY,
    BackendRegistry,
    ModelInfo,
    resolve_model_info,
)
from encre.backends.retry import DEFAULT_RETRY_CONFIG, RetryConfig

# ===========================================================================
# ModelInfo dataclass
# ===========================================================================

class TestModelInfo:
    """Test suite for ModelInfo."""
    def test_create_default(self):
        """Test: Create default."""
        mi = ModelInfo(name="test-model", provider="openai")
        # Verify: mi.name == "test-model"
        assert mi.name == "test-model"
        # Verify: mi.provider == "openai"
        assert mi.provider == "openai"
        # Verify: mi.context_window == 128000
        assert mi.context_window == 128000
        # Verify: mi.max_output_tokens == 8192
        assert mi.max_output_tokens == 8192
        # Verify: mi.supports_tools is True
        assert mi.supports_tools is True
        # Verify: mi.supports_streaming is True
        assert mi.supports_streaming is True

    def test_create_with_aliases(self):
        """Test: Create with aliases."""
        mi = ModelInfo(
            name="gpt-5.6",
            provider="openai",
            aliases=["gpt4o", "4o"],
        )
        # Verify: mi.aliases == ["gpt4o", "4o"]
        assert mi.aliases == ["gpt4o", "4o"]

    def test_equality(self):
        """Test: Equality."""
        a = ModelInfo(name="m1", provider="openai")
        b = ModelInfo(name="m1", provider="openai")
        # Verify: a == b
        assert a == b

    def test_different_names_not_equal(self):
        """Test: Different names not equal."""
        a = ModelInfo(name="m1", provider="openai")
        b = ModelInfo(name="m2", provider="openai")
        # Verify: a != b
        assert a != b


# ===========================================================================
# BackendRegistry: register / unregister / resolve
# ===========================================================================

class TestBackendRegistryRegistration:
    """Test suite for BackendRegistryRegistration."""
    def test_register_and_resolve_exact(self):
        """Test: Register and resolve exact."""
        registry = BackendRegistry()
        mi = ModelInfo(name="my-model", provider="anthropic", context_window=300000)
        registry.register(mi)
        resolved = registry.resolve("my-model")
        # Verify: resolved is not None
        assert resolved is not None
        # Verify: resolved.name == "my-model"
        assert resolved.name == "my-model"
        # Verify: resolved.context_window == 300000
        assert resolved.context_window == 300000

    def test_register_with_aliases_resolve_alias(self):
        """Test: Register with aliases resolve alias."""
        registry = BackendRegistry()
        mi = ModelInfo(name="my-model-2", provider="openai", aliases=["mm2", "alias2"])
        registry.register(mi)
        r1 = registry.resolve("mm2")
        # Verify: r1 is not None
        assert r1 is not None
        # Verify: r1.name == "my-model-2"
        assert r1.name == "my-model-2"
        r2 = registry.resolve("alias2")
        # Verify: r2 is not None
        assert r2 is not None
        # Verify: r2.name == "my-model-2"
        assert r2.name == "my-model-2"

    def test_unregister_removes_entry(self):
        """Test: Unregister removes entry."""
        registry = BackendRegistry()
        mi = ModelInfo(name="temp-model", provider="openai", aliases=["tm"])
        registry.register(mi)
        # Verify: registry.resolve("temp-model") is not None
        assert registry.resolve("temp-model") is not None
        registry.unregister("temp-model")
        # Verify: registry.resolve("temp-model") is None
        assert registry.resolve("temp-model") is None

    def test_resolve_nonexistent(self):
        """Test: Resolve nonexistent."""
        registry = BackendRegistry()
        # Verify: registry.resolve("nonexistent-model-xyz") is None
        assert registry.resolve("nonexistent-model-xyz") is None

    def test_register_overwrite(self):
        """Test: Register overwrite."""
        registry = BackendRegistry()
        mi1 = ModelInfo(name="overwrite-test", provider="openai", context_window=1000)
        mi2 = ModelInfo(name="overwrite-test", provider="openai", context_window=2000)
        registry.register(mi1)
        registry.register(mi2)
        r = registry.resolve("overwrite-test")
        # Verify: r.context_window == 2000
        assert r.context_window == 2000

    def test_list_models(self):
        """Test: List models."""
        registry = BackendRegistry()
        mi = ModelInfo(name="list-all-test", provider="groq")
        registry.register(mi)
        all_models = registry.list_models()
        # Verify: any(m.name == "list-all-test" for m in all_models)
        assert any(m.name == "list-all-test" for m in all_models)


# ===========================================================================
# Global REGISTRY and resolve_model_info
# ===========================================================================

class TestResolveModelInfo:
    """Test suite for ResolveModelInfo."""
    def test_resolve_known_model(self):
        """Test: Resolve known model."""
        info = resolve_model_info("gpt-4.1")
        # Verify: info.name == "gpt-4.1"
        assert info.name == "gpt-4.1"
        # Verify: info.provider == "openai"
        assert info.provider == "openai"
        # Verify: info.context_window == 1048576
        assert info.context_window == 1048576

    def test_resolve_registered_custom_model(self):
        """Test: Resolve registered custom model."""
        mi = ModelInfo(name="known-model", provider="anthropic", context_window=999000)
        REGISTRY.register(mi)
        info = resolve_model_info("known-model")
        # Verify: info.context_window == 999000
        assert info.context_window == 999000
        REGISTRY.unregister("known-model")

    def test_resolve_unregistered_openai(self):
        """Test: Resolve unregistered openai."""
        info = resolve_model_info("gpt-5-imaginary")
        # Verify: info.provider == "openai"
        assert info.provider == "openai"
        # Verify: info.context_window == 1048576
        assert info.context_window == 1048576
        # Verify: info.supports_tools is True
        assert info.supports_tools is True

    def test_resolve_unregistered_anthropic(self):
        """Test: Resolve unregistered anthropic."""
        info = resolve_model_info("claude-opus-5-imaginary")
        # Verify: info.provider == "anthropic"
        assert info.provider == "anthropic"
        # Verify: info.context_window == 200000
        assert info.context_window == 200000
        # Verify: info.supports_thinking is True
        assert info.supports_thinking is True
        # Verify: info.supports_prompt_caching is True
        assert info.supports_prompt_caching is True

    def test_resolve_unregistered_google(self):
        """Test: Resolve unregistered google."""
        info = resolve_model_info("gemini-3-imaginary")
        # Verify: info.provider == "google"
        assert info.provider == "google"
        # Verify: info.context_window == 1048576
        assert info.context_window == 1048576

    def test_resolve_unregistered_deepseek(self):
        """Test: Resolve unregistered deepseek."""
        info = resolve_model_info("deepseek-v4-imaginary")
        # Verify: info.provider == "deepseek"
        assert info.provider == "deepseek"
        # Verify: info.context_window == 1048576
        assert info.context_window == 1048576

    def test_resolve_unregistered_groq(self):
        """Test: Resolve unregistered groq."""
        info = resolve_model_info("groq-model-imaginary", provider="groq")
        # Verify: info.provider == "groq"
        assert info.provider == "groq"
        # Verify: info.context_window == 131072
        assert info.context_window == 131072

    def test_resolve_unregistered_ollama(self):
        """Test: Resolve unregistered ollama."""
        info = resolve_model_info("some-ollama-model", provider="ollama")
        # Verify: info.provider == "ollama"
        assert info.provider == "ollama"
        # Verify: info.context_window == 8192
        assert info.context_window == 8192

    def test_resolve_unregistered_local(self):
        """Test: Resolve unregistered local."""
        info = resolve_model_info("my-local-model", provider="local")
        # Verify: info.provider == "local"
        assert info.provider == "local"
        # Verify: info.context_window == 4096
        assert info.context_window == 4096
        # Verify: info.max_output_tokens == 2048
        assert info.max_output_tokens == 2048

    def test_resolve_honors_explicit_provider(self):
        """Test: Resolve honors explicit provider."""
        info = resolve_model_info("some-unknown-model", provider="bedrock")
        # Verify: info.provider == "bedrock"
        assert info.provider == "bedrock"
        # Verify: info.context_window == 200000
        assert info.context_window == 200000

    def test_global_registry_has_known_models(self):
        """Test: Global registry has known models."""
        info = REGISTRY.resolve("gpt-4.1")
        # Verify: info is not None
        assert info is not None
        info2 = REGISTRY.resolve("claude-sonnet-4.6")
        # Verify: info2 is not None
        assert info2 is not None


# ===========================================================================
# BaseBackend ABC compliance
# ===========================================================================

class TestBaseBackendABC:
    """Test suite for BaseBackendABC."""
    def test_cannot_instantiate_abc(self):
        """Test: Cannot instantiate abc."""
        with pytest.raises(TypeError):
            BaseBackend()

    def test_concrete_subclasses_instantiate(self):
        """Test: Concrete subclasses instantiate."""
        from encre.backends.local import LocalBackend
        be = LocalBackend()
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_supports_tool_calling_is_abstract(self):
        """Test: Supports tool calling is abstract."""
        # Verify: "supports_tool_calling" in BaseBackend.__abstractmethods__
        assert "supports_tool_calling" in BaseBackend.__abstractmethods__

    def test_chat_is_abstract(self):
        """Test: Chat is abstract."""
        # Verify: "chat" in BaseBackend.__abstractmethods__
        assert "chat" in BaseBackend.__abstractmethods__

    def test_context_window_size_is_abstract(self):
        """Test: Context window size is abstract."""
        # Verify: "context_window_size" in BaseBackend.__abstractmethods__
        assert "context_window_size" in BaseBackend.__abstractmethods__

    def test_default_supports_thinking(self):
        """Test: Default supports thinking."""
        from encre.backends.local import LocalBackend
        be = LocalBackend()
        # Verify: hasattr(be, "supports_thinking")
        assert hasattr(be, "supports_thinking")
        # Verify: isinstance(be.supports_thinking(), bool)
        assert isinstance(be.supports_thinking(), bool)

    def test_default_supports_prompt_caching(self):
        """Test: Default supports prompt caching."""
        from encre.backends.local import LocalBackend
        be = LocalBackend()
        # Verify: hasattr(be, "supports_prompt_caching")
        assert hasattr(be, "supports_prompt_caching")
        # Verify: isinstance(be.supports_prompt_caching(), bool)
        assert isinstance(be.supports_prompt_caching(), bool)

    def test_default_count_tokens(self):
        """Test: Default count tokens."""
        from encre.backends.local import LocalBackend
        be = LocalBackend()
        # Verify: be.count_tokens("hello") == -1
        assert be.count_tokens("hello") == -1

    def test_aclose_noop(self):
        """Test: Aclose noop."""
        from encre.backends.local import LocalBackend
        be = LocalBackend()
        asyncio.run(be.aclose())


# ===========================================================================
# Backend factory: create_backend()
# ===========================================================================

class TestCreateBackend:
    """Test suite for CreateBackend."""
    def test_create_openai(self):
        """Test: Create openai."""
        be = create_backend("openai")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_anthropic(self):
        """Test: Create anthropic."""
        be = create_backend("anthropic")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_ollama(self):
        """Test: Create ollama."""
        be = create_backend("ollama")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_deepseek(self):
        """Test: Create deepseek."""
        be = create_backend("deepseek")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_google(self):
        """Test: Create google."""
        be = create_backend("google")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_groq(self):
        """Test: Create groq."""
        be = create_backend("groq")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_local(self):
        """Test: Create local."""
        be = create_backend("local")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_bedrock(self):
        """Test: Create bedrock."""
        be = create_backend("bedrock")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_openai_compatible(self):
        """Test: Create openai compatible."""
        be = create_backend("openai_compatible", base_url="https://api.example.com/v1")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_create_unknown_type_raises(self):
        """Test: Create unknown type raises."""
        with pytest.raises(ValueError, match="Unknown backend type"):
            create_backend("nonexistent_backend")

    def test_create_backend_passes_kwargs(self):
        """Test: Create backend passes kwargs."""
        be = create_backend("openai", model="gpt-4o-mini", api_key="sk-test")
        # Verify: be.model == "gpt-4o-mini"
        assert be.model == "gpt-4o-mini"


# ===========================================================================
# RetryConfig
# ===========================================================================

class TestRetryConfig:
    """Test suite for RetryConfig."""
    def test_default_config(self):
        """Test: Default config."""
        rc = RetryConfig()
        # Verify: rc.max_retries == 8
        assert rc.max_retries == 8
        # Verify: rc.base_delay == 2.0
        assert rc.base_delay == 2.0
        # Verify: rc.max_delay == 120.0
        assert rc.max_delay == 120.0
        # Verify: 429 in rc.retryable_status_codes
        assert 429 in rc.retryable_status_codes
        # Verify: 502 in rc.retryable_status_codes
        assert 502 in rc.retryable_status_codes
        # Verify: 503 in rc.retryable_status_codes
        assert 503 in rc.retryable_status_codes
        # Verify: 504 in rc.retryable_status_codes
        assert 504 in rc.retryable_status_codes

    def test_default_retry_config_is_retry_config(self):
        """Test: Default retry config is retry config."""
        # Verify: isinstance(DEFAULT_RETRY_CONFIG, RetryConfig)
        assert isinstance(DEFAULT_RETRY_CONFIG, RetryConfig)

    def test_custom_config(self):
        """Test: Custom config."""
        rc = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            retryable_status_codes={429, 500},
        )
        # Verify: rc.max_retries == 5
        assert rc.max_retries == 5
        # Verify: rc.base_delay == 2.0
        assert rc.base_delay == 2.0
        # Verify: rc.max_delay == 120.0
        assert rc.max_delay == 120.0
        # Verify: rc.retryable_status_codes == {429, 500}
        assert rc.retryable_status_codes == {429, 500}

    def test_zero_retries_disables_retry(self):
        """Test: Zero retries disables retry."""
        rc = RetryConfig(max_retries=0)
        # Verify: rc.max_retries == 0
        assert rc.max_retries == 0

    def test_retry_on_exceptions_default(self):
        """Test: Retry on exceptions default."""
        import httpx
        rc = RetryConfig()
        # Verify: httpx.TimeoutException in rc.retryable_exceptions
        assert httpx.TimeoutException in rc.retryable_exceptions
        # Verify: httpx.ConnectError in rc.retryable_exceptions
        assert httpx.ConnectError in rc.retryable_exceptions


# ===========================================================================
# Backend-specific capability checks
# ===========================================================================

class TestBackendCapabilities:
    """Test suite for BackendCapabilities."""
    def test_openai_capabilities(self):
        """Test: Openai capabilities."""
        be = create_backend("openai", api_key="sk-fake")
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0
        # Verify: isinstance(be.supports_thinking(), bool)
        assert isinstance(be.supports_thinking(), bool)

    def test_anthropic_capabilities(self):
        """Test: Anthropic capabilities."""
        be = create_backend("anthropic", api_key="sk-ant-fake")
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True
        # Verify: be.supports_prompt_caching() is True
        assert be.supports_prompt_caching() is True

    def test_deepseek_capabilities(self):
        """Test: Deepseek capabilities."""
        be = create_backend("deepseek", api_key="sk-fake")
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0

    def test_local_capabilities(self):
        """Test: Local capabilities."""
        be = create_backend("local")
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)

    def test_ollama_capabilities(self):
        """Test: Ollama capabilities."""
        be = create_backend("ollama")
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)


# ===========================================================================
# Config integration with backends
# ===========================================================================

class TestConfigBackendIntegration:
    """Test suite for ConfigBackendIntegration."""
    def test_config_server_backend_type_default(self):
        """Test: Config server backend type default."""
        from encre.config import EncreConfig
        cfg = EncreConfig()
        # Verify: cfg.backend_type == "openai"
        assert cfg.backend_type == "openai"
        be = create_backend(cfg.backend_type, api_key="sk-fake")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)

    def test_config_with_kwargs(self):
        """Test: Config with kwargs."""
        from encre.config import EncreConfig
        cfg = EncreConfig(
            backend_type="anthropic",
            backend_kwargs={"max_tokens": 32768},
        )
        # Verify: cfg.backend_type == "anthropic"
        assert cfg.backend_type == "anthropic"
        # Verify: cfg.backend_kwargs["max_tokens"] == 32768
        assert cfg.backend_kwargs["max_tokens"] == 32768
