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

"""Tests for individual backend implementations (no API keys needed)."""

import asyncio

import pytest
from encre.backend import create_backend
from encre.backends.base import BaseBackend

# ===========================================================================
# OpenAI
# ===========================================================================

class TestOpenAIBackend:
    """Test suite for OpenAIBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("openai", api_key="sk-fake")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("openai", model="gpt-4o-mini", api_key="sk-fake")
        # Verify: be.model == "gpt-4o-mini"
        assert be.model == "gpt-4o-mini"

    def test_count_tokens(self):
        """Test: Count tokens."""
        be = create_backend("openai", api_key="sk-fake")
        # May return -1 if tiktoken not installed
        assert isinstance(be.count_tokens("hello"), int)


# ===========================================================================
# Anthropic
# ===========================================================================

class TestAnthropicBackend:
    """Test suite for AnthropicBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("anthropic", api_key="sk-ant-fake")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() == 200000
        assert be.context_window_size() == 200000
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True
        # Verify: be.supports_prompt_caching() is True
        assert be.supports_prompt_caching() is True

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("anthropic", model="claude-sonnet-4-20250514", api_key="sk-ant-fake")
        # Verify: be.model == "claude-sonnet-4-20250514"
        assert be.model == "claude-sonnet-4-20250514"

    def test_max_tokens_override(self):
        """Test: Max tokens override."""
        be = create_backend("anthropic", api_key="sk-ant-fake")
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True


# ===========================================================================
# DeepSeek
# ===========================================================================

class TestDeepSeekBackend:
    """Test suite for DeepSeekBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("deepseek", api_key="sk-fake")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("deepseek", model="deepseek-chat", api_key="sk-fake")
        # Verify: deprecated deepseek-chat is mapped to deepseek-v4-flash
        assert be.model == "deepseek-v4-flash"


# ===========================================================================
# Google
# ===========================================================================

class TestGoogleBackend:
    """Test suite for GoogleBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("google", api_key="fake-key")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("google", model="gemini-2.5-flash", api_key="fake-key")
        # Verify: be.model == "gemini-2.5-flash"
        assert be.model == "gemini-2.5-flash"


# ===========================================================================
# Groq
# ===========================================================================

class TestGroqBackend:
    """Test suite for GroqBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("groq", api_key="gsk-fake")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True
        # Verify: be.context_window_size() == 131072
        assert be.context_window_size() == 131072

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("groq", model="llama-4-maverick", api_key="gsk-fake")
        # Verify: be.model == "llama-4-maverick"
        assert be.model == "llama-4-maverick"


# ===========================================================================
# Ollama
# ===========================================================================

class TestOllamaBackend:
    """Test suite for OllamaBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("ollama", base_url="http://localhost:11434")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.context_window_size() == 8192
        assert be.context_window_size() == 8192
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)


# ===========================================================================
# Local
# ===========================================================================

class TestLocalBackend:
    """Test suite for LocalBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("local")
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.context_window_size() == 4096
        assert be.context_window_size() == 4096
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend("local", model_name="meta-llama/Llama-4-Maverick-17B-128E-Instruct")
        # Verify: be.model_name == "meta-llama/Llama-4-Maverick-17B-128E-Instruct"
        assert be.model_name == "meta-llama/Llama-4-Maverick-17B-128E-Instruct"


# ===========================================================================
# Bedrock
# ===========================================================================

class TestBedrockBackend:
    """Test suite for BedrockBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("bedrock", aws_access_key_id="fake", aws_secret_access_key="fake", region="us-east-1")  # noqa: E501
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: be.context_window_size() == 200000
        assert be.context_window_size() == 200000
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend(
            "bedrock",
            model="anthropic.claude-sonnet-4-20250514-v1:0",
            aws_access_key_id="fake",
            aws_secret_access_key="fake",
        )
        # Verify: be.model == "anthropic.claude-sonnet-4-20250514-v1:0"
        assert be.model == "anthropic.claude-sonnet-4-20250514-v1:0"


# ===========================================================================
# OpenAI Compatible
# ===========================================================================

class TestOpenAICompatibleBackend:
    """Test suite for OpenAICompatibleBackend."""
    def test_create(self):
        """Test: Create."""
        be = create_backend("openai_compatible", base_url="https://api.example.com/v1", api_key="sk-fake")  # noqa: E501
        # Verify: isinstance(be, BaseBackend)
        assert isinstance(be, BaseBackend)
        # Verify: isinstance(be.supports_tool_calling(), bool)
        assert isinstance(be.supports_tool_calling(), bool)
        # Verify: be.context_window_size() == 128000
        assert be.context_window_size() == 128000

    def test_model_override(self):
        """Test: Model override."""
        be = create_backend(
            "openai_compatible",
            model="custom-model",
            base_url="https://api.example.com/v1",
            api_key="sk-fake",
        )
        # Verify: be.model == "custom-model"
        assert be.model == "custom-model"


# ===========================================================================
# Retry integration
# ===========================================================================

class TestRetryIntegration:
    """Test suite for RetryIntegration."""
    def test_retry_with_backoff_handler(self):
        """Test: Retry with backoff handler."""
        import httpx
        from encre.backends.retry import RetryConfig, retry_with_backoff

        async def _test():
            """Helper: Test."""
            config = RetryConfig(max_retries=2, base_delay=0.01)

            @retry_with_backoff(config)
            async def flaky_request():
                """Flaky request."""
                raise httpx.TimeoutException("timeout")

            with pytest.raises(httpx.TimeoutException):
                await flaky_request()

        asyncio.run(_test())

    def test_retry_config_tool_retries(self):
        """Test: Retry config tool retries."""
        from encre.backends.retry import RetryConfig
        rc = RetryConfig()
        # Verify: rc.rate_limit_retries == 8
        assert rc.rate_limit_retries == 8
