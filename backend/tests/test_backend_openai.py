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

"""Tests for OpenAIBackend -- construction, capabilities, context window, tokens."""

import asyncio

from encre.backends.openai import OpenAIBackend

# ===========================================================================
# Construction
# ===========================================================================

class TestOpenAIBackendConstruction:
    """Test OpenAIBackend instantiation with various parameter combinations."""

    def test_create_default(self):
        """Default model is gpt-4.1, default base_url is api.openai.com/v1."""
        be = OpenAIBackend(api_key="sk-test")
        # Verify: be.model == "gpt-4.1"
        assert be.model == "gpt-4.1"
        # Verify: be.api_key == "sk-test"
        assert be.api_key == "sk-test"
        # Verify: be.api_base_url == "https://api.openai.com/v1"
        assert be.api_base_url == "https://api.openai.com/v1"

    def test_create_with_custom_model(self):
        """Explicit model name is stored correctly."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-mini")
        # Verify: be.model == "gpt-4.1-mini"
        assert be.model == "gpt-4.1-mini"

    def test_create_with_base_url(self):
        """Custom base_url overrides the default OpenAI endpoint."""
        be = OpenAIBackend(
            api_key="sk-test",
            base_url="https://custom.openai.example.com/v1",
        )
        # Verify: be.api_base_url == "https://custom.openai.example.com/v1"
        assert be.api_base_url == "https://custom.openai.example.com/v1"

    def test_create_with_nano_model(self):
        """GPT-4.1 Nano variant."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-nano")
        # Verify: be.model == "gpt-4.1-nano"
        assert be.model == "gpt-4.1-nano"

    def test_create_with_o3_model(self):
        """o3 reasoning model."""
        be = OpenAIBackend(api_key="sk-test", model="o3")
        # Verify: be.model == "o3"
        assert be.model == "o3"

    def test_create_with_gpt5_5_model(self):
        """GPT-5.5 top-tier model."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-5.5")
        # Verify: be.model == "gpt-5.5"
        assert be.model == "gpt-5.5"

    def test_create_with_empty_api_key(self):
        """Empty API key is allowed (caller may use env var)."""
        be = OpenAIBackend()
        # Verify: be.api_key == ""
        assert be.api_key == ""
        # Verify: be.model == "gpt-4.1"
        assert be.model == "gpt-4.1"

    def test_create_passes_http_timeout(self):
        """http_timeout kwarg is forwarded to the parent SSE backend."""
        be = OpenAIBackend(api_key="sk-test", http_timeout=60.0)
        # Verify: be.http_timeout == 60.0
        assert be.http_timeout == 60.0


# ===========================================================================
# Capability checks
# ===========================================================================

class TestOpenAIBackendCapabilities:
    """Test supports_tool_calling, supports_thinking, supports_prompt_caching."""

    def test_supports_tool_calling(self):
        """All OpenAI models support tool calling."""
        be = OpenAIBackend(api_key="sk-test")
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True

    def test_supports_tool_calling_different_models(self):
        """Tool calling is True regardless of model choice."""
        models = ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-5.5", "o3"]
        for m in models:
            be = OpenAIBackend(api_key="sk-test", model=m)
            # Verify: be.supports_tool_calling() is True, f"model={m}"
            assert be.supports_tool_calling() is True, f"model={m}"

    def test_supports_thinking_gpt4_1(self):
        """GPT-4.1 does NOT emit thinking tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1")
        # Verify: be.supports_thinking() is False
        assert be.supports_thinking() is False

    def test_supports_thinking_gpt4_1_mini(self):
        """GPT-4.1 Mini does NOT emit thinking tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-mini")
        # Verify: be.supports_thinking() is False
        assert be.supports_thinking() is False

    def test_supports_thinking_gpt5(self):
        """GPT-5.x models do NOT emit thinking tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-5.2")
        # Verify: be.supports_thinking() is False
        assert be.supports_thinking() is False

    def test_supports_thinking_o3(self):
        """o3 IS a reasoning model -- emits thinking tokens."""
        be = OpenAIBackend(api_key="sk-test", model="o3")
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True

    def test_supports_thinking_o4_mini(self):
        """o4-mini IS a reasoning model -- emits thinking tokens."""
        be = OpenAIBackend(api_key="sk-test", model="o4-mini")
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True

    def test_supports_prompt_caching_returns_bool(self):
        """Prompt caching flag is a boolean."""
        be = OpenAIBackend(api_key="sk-test")
        result = be.supports_prompt_caching()
        # Verify: isinstance(result, bool)
        assert isinstance(result, bool)


# ===========================================================================
# Context window size
# ===========================================================================

class TestOpenAIBackendContextWindow:
    """Test context_window_size() for every model variant."""

    def test_context_gpt4_1(self):
        """GPT-4.1: 1,048,576 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_gpt4_1_mini(self):
        """GPT-4.1 Mini: 1,048,576 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-mini")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_gpt4_1_nano(self):
        """GPT-4.1 Nano: 1,048,576 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-nano")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_o3(self):
        """o3: 200,000 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="o3")
        # Verify: be.context_window_size() == 200000
        assert be.context_window_size() == 200000

    def test_context_o4_mini(self):
        """o4-mini: 1,048,576 tokens ('mini' substring matches first)."""
        be = OpenAIBackend(api_key="sk-test", model="o4-mini")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_gpt5_2(self):
        """GPT-5.2: 128,000 tokens (default fallback)."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-5.2")
        # Verify: be.context_window_size() == 128000
        assert be.context_window_size() == 128000

    def test_context_gpt5_4(self):
        """GPT-5.4: 400,000 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-5.4")
        # Verify: be.context_window_size() == 400000
        assert be.context_window_size() == 400000

    def test_context_gpt5_5(self):
        """GPT-5.5: 1,048,576 tokens."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-5.5")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_always_positive(self):
        """Context window is always a positive integer."""
        models = ["gpt-4.1", "gpt-4.1-mini", "gpt-5.2", "o3", "o4-mini"]
        for m in models:
            be = OpenAIBackend(api_key="sk-test", model=m)
            # Verify: be.context_window_size() > 0, f"model={m}"
            assert be.context_window_size() > 0, f"model={m}"
            # Verify: isinstance(be.context_window_size(), int), f"model={m}"
            assert isinstance(be.context_window_size(), int), f"model={m}"


# ===========================================================================
# Token counting and model attribute
# ===========================================================================

class TestOpenAIBackendTokens:
    """Test count_tokens and model attribute access."""

    def test_count_tokens_returns_int(self):
        """count_tokens() returns an integer (may be -1 without tiktoken)."""
        be = OpenAIBackend(api_key="sk-test")
        result = be.count_tokens("hello world")
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_count_tokens_empty_string(self):
        """Empty string should not crash token counting."""
        be = OpenAIBackend(api_key="sk-test")
        result = be.count_tokens("")
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_count_tokens_long_text(self):
        """Long text should not crash token counting."""
        be = OpenAIBackend(api_key="sk-test")
        result = be.count_tokens("The quick brown fox jumps over the lazy dog. " * 100)
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_model_attribute_access(self):
        """model attribute reflects the constructor argument."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-mini")
        # Verify: be.model == "gpt-4.1-mini"
        assert be.model == "gpt-4.1-mini"
        # Verify: isinstance(be.model, str)
        assert isinstance(be.model, str)

    def test_model_default(self):
        """Default model is gpt-4.1."""
        be = OpenAIBackend(api_key="sk-test")
        # Verify: be.model == "gpt-4.1"
        assert be.model == "gpt-4.1"


# ===========================================================================
# Request data / token parameter construction
# ===========================================================================

class TestOpenAIBackendRequestBuilding:
    """Test _build_request_data and token parameter handling."""

    def test_build_request_includes_max_tokens(self):
        """_build_request_data propagates max_tokens to the request body."""
        be = OpenAIBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=2048,
        )
        # Verify: "max_tokens" in data
        assert "max_tokens" in data
        # Verify: data["max_tokens"] == 2048
        assert data["max_tokens"] == 2048

    def test_build_request_default_max_tokens(self):
        """Default max_tokens is 4096."""
        be = OpenAIBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
        )
        # Verify: data["max_tokens"] == 4096
        assert data["max_tokens"] == 4096

    def test_build_request_includes_model(self):
        """Request body includes the model name."""
        be = OpenAIBackend(api_key="sk-test", model="gpt-4.1-mini")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
        )
        # Verify: data["model"] == "gpt-4.1-mini"
        assert data["model"] == "gpt-4.1-mini"

    def test_build_request_includes_messages(self):
        """Request body includes conversation messages."""
        be = OpenAIBackend(api_key="sk-test")
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        data = be._build_request_data(messages=messages)
        # Verify: data["messages"] == messages
        assert data["messages"] == messages

    def test_build_request_stream_default(self):
        """Streaming is enabled by default."""
        be = OpenAIBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
        )
        # Verify: data["stream"] is True
        assert data["stream"] is True

    def test_build_request_non_stream(self):
        """Non-streaming mode can be requested."""
        be = OpenAIBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )
        # Verify: data["stream"] is False
        assert data["stream"] is False

    def test_build_request_with_tools(self):
        """Tool definitions are included when provided."""
        be = OpenAIBackend(api_key="sk-test")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        data = be._build_request_data(
            messages=[{"role": "user", "content": "search for cats"}],
            tools=tools,
        )
        # Verify: "tools" in data
        assert "tools" in data
        # Verify: data["tools"] == tools
        assert data["tools"] == tools
        # Verify: "tool_choice" in data
        assert "tool_choice" in data

    def test_build_request_without_tools(self):
        """Tools and tool_choice are omitted when no tools provided."""
        be = OpenAIBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
        )
        # Verify: "tools" not in data
        assert "tools" not in data
        # Verify: "tool_choice" not in data
        assert "tool_choice" not in data


# ===========================================================================
# Lifecycle
# ===========================================================================

# ===========================================================================
# Prompt caching
# ===========================================================================

class TestOpenAIBackendPromptCaching:
    """Test the _apply_prompt_caching_openai static method."""

    def test_splits_system_at_boundary(self):
        """System message is split into prefix and suffix at __PROMPT_CACHE_BOUNDARY__."""
        messages = [
            {"role": "system", "content": "You are helpful.__PROMPT_CACHE_BOUNDARY__\nMemory: foo"},
            {"role": "user", "content": "Hello"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert "You are helpful." in result[0]["content"]
        assert result[1]["role"] == "system"
        assert "Memory: foo" in result[1]["content"]
        assert result[2]["role"] == "user"

    def test_no_boundary_unchanged(self):
        """Messages without boundary marker are left unchanged."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 2
        assert result[0]["content"] == "You are helpful."

    def test_only_user_messages(self):
        """No system messages means no splitting occurs."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 2

    def test_multiple_system_messages(self):
        """Only the system message with boundary is split."""
        messages = [
            {"role": "system", "content": "Static rules.__PROMPT_CACHE_BOUNDARY__\nDynamic rules"},
            {"role": "system", "content": "Extra system"},
            {"role": "user", "content": "Hi"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 4
        assert result[0]["role"] == "system" and "Static rules" in result[0]["content"]
        assert result[1]["role"] == "system" and "Dynamic rules" in result[1]["content"]
        assert result[2]["role"] == "system"
        assert result[3]["role"] == "user"

    def test_empty_prefix_or_suffix(self):
        """Empty parts after splitting are dropped."""
        messages = [
            {"role": "system", "content": "__PROMPT_CACHE_BOUNDARY__\nOnly suffix"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 1
        assert "Only suffix" in result[0]["content"]

        messages2 = [
            {"role": "system", "content": "Only prefix\n__PROMPT_CACHE_BOUNDARY__"},
        ]
        result2 = OpenAIBackend._apply_prompt_caching_openai(messages2)
        assert len(result2) == 1
        assert "Only prefix" in result2[0]["content"]

    def test_non_string_content_unchanged(self):
        """List content (e.g. multimodal) is not modified."""
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": "Hello"}],
            },
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert len(result) == 1
        assert isinstance(result[0]["content"], list)

    def test_mixed_message_order_preserved(self):
        """Non-system messages keep their order relative to split system parts."""
        messages = [
            {"role": "system", "content": "A.__PROMPT_CACHE_BOUNDARY__\nB."},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        roles = [m["role"] for m in result]
        assert roles == ["system", "system", "user", "assistant", "user"]

    def test_boundary_removed_from_system(self):
        """The boundary marker text is removed from all system message contents."""
        messages = [
            {"role": "system", "content": "A.__PROMPT_CACHE_BOUNDARY__\nB."},
            {"role": "system", "content": "C.__PROMPT_CACHE_BOUNDARY__\nD."},
        ]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        for m in result:
            assert "__PROMPT_CACHE_BOUNDARY__" not in m["content"]

    def test_chat_without_caching_no_split(self):
        """enable_caching=False leaves messages unchanged."""
        messages = [{"role": "user", "content": "Hello"}]
        result = OpenAIBackend._apply_prompt_caching_openai(messages)
        assert result == messages


class TestOpenAIBackendLifecycle:
    """Test resource cleanup and lifecycle."""

    def test_aclose_does_not_raise(self):
        """aclose() should work even without a prior request (lazy client)."""
        be = OpenAIBackend(api_key="sk-test")
        # Should not raise -- _client may be None (lazy init).
        asyncio.run(be.aclose())

    def test_aclose_idempotent(self):
        """Calling aclose() twice should not raise."""
        be = OpenAIBackend(api_key="sk-test")

        async def _double_close():
            """Helper: Double close."""
            await be.aclose()
            await be.aclose()

        asyncio.run(_double_close())
