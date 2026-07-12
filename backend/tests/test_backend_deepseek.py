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

"""Tests for DeepSeekBackend -- construction, capabilities, context window, tokens."""

import asyncio

from encre.backends.deepseek import DeepSeekBackend

# ===========================================================================
# Construction
# ===========================================================================

class TestDeepSeekBackendConstruction:
    """Test DeepSeekBackend instantiation with various parameters."""

    def test_create_default(self):
        """Default model is V4-Flash, base URL is api.deepseek.com."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.model == "deepseek-v4-flash"
        assert be.model == "deepseek-v4-flash"
        # Verify: be.api_key == "sk-test"
        assert be.api_key == "sk-test"
        # Verify: be.api_base_url == "https://api.deepseek.com"
        assert be.api_base_url == "https://api.deepseek.com"

    def test_create_with_custom_model(self):
        """Explicit model is stored correctly."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-flash")
        # Verify: be.model == "deepseek-v4-flash"
        assert be.model == "deepseek-v4-flash"

    def test_create_with_v4_pro_model(self):
        """DeepSeek V4-Pro model."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-pro")
        # Verify: be.model == "deepseek-v4-pro"
        assert be.model == "deepseek-v4-pro"

    def test_legacy_chat_model_is_mapped_to_v4_flash(self):
        """Deprecated deepseek-chat is mapped to deepseek-v4-flash."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-chat")
        # Verify: be.model == "deepseek-v4-flash"
        assert be.model == "deepseek-v4-flash"

    def test_legacy_reasoner_model_is_mapped_to_v4_pro(self):
        """Deprecated deepseek-reasoner is mapped to deepseek-v4-pro."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-reasoner")
        # Verify: be.model == "deepseek-v4-pro"
        assert be.model == "deepseek-v4-pro"

    def test_create_with_custom_base_url(self):
        """Custom base_url overrides the default."""
        be = DeepSeekBackend(
            api_key="sk-test",
            base_url="https://custom.deepseek.example.com/v1",
        )
        # Verify: be.api_base_url == "https://custom.deepseek.example.com/v1"
        assert be.api_base_url == "https://custom.deepseek.example.com/v1"

    def test_create_with_empty_api_key(self):
        """Empty API key is allowed."""
        be = DeepSeekBackend()
        # Verify: be.api_key == ""
        assert be.api_key == ""
        # Verify: be.model == "deepseek-v4-flash"
        assert be.model == "deepseek-v4-flash"

    def test_create_with_http_timeout(self):
        """http_timeout is forwarded to OpenAISSEBackend."""
        be = DeepSeekBackend(api_key="sk-test", http_timeout=90.0)
        # Verify: be.http_timeout == 90.0
        assert be.http_timeout == 90.0


# ===========================================================================
# Capability checks
# ===========================================================================

class TestDeepSeekBackendCapabilities:
    """Test supports_tool_calling, supports_thinking, supports_prompt_caching."""

    def test_supports_tool_calling(self):
        """DeepSeek V4 models support tool calling."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.supports_tool_calling() is True
        assert be.supports_tool_calling() is True

    def test_supports_tool_calling_different_models(self):
        """Tool calling is True for all DeepSeek V4 models."""
        models = ["deepseek-chat", "deepseek-v4-flash", "deepseek-v4-pro"]
        for m in models:
            be = DeepSeekBackend(api_key="sk-test", model=m)
            # Verify: be.supports_tool_calling() is True, f"model={m}"
            assert be.supports_tool_calling() is True, f"model={m}"

    def test_supports_thinking(self):
        """DeepSeek V4 models support reasoning/thinking tokens."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.supports_thinking() is True
        assert be.supports_thinking() is True

    def test_supports_thinking_different_models(self):
        """Thinking is supported by all V4 models."""
        models = ["deepseek-chat", "deepseek-v4-flash", "deepseek-v4-pro"]
        for m in models:
            be = DeepSeekBackend(api_key="sk-test", model=m)
            # Verify: be.supports_thinking() is True, f"model={m}"
            assert be.supports_thinking() is True, f"model={m}"

    def test_supports_prompt_caching(self):
        """DeepSeek V4 supports prompt caching (80-92% discount)."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.supports_prompt_caching() is True
        assert be.supports_prompt_caching() is True


# ===========================================================================
# Context window size
# ===========================================================================

class TestDeepSeekBackendContextWindow:
    """Test context_window_size() for DeepSeek models."""

    def test_context_window_size_default(self):
        """All DeepSeek V4 models: 1,048,576 tokens (1M)."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_window_size_v4_flash(self):
        """V4-Flash: 1M tokens."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-flash")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_window_size_v4_pro(self):
        """V4-Pro: 1M tokens."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-pro")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_window_size_chat(self):
        """Legacy deepseek-chat: 1M tokens (maps to V4)."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-chat")
        # Verify: be.context_window_size() == 1048576
        assert be.context_window_size() == 1048576

    def test_context_window_positive(self):
        """Context window is always positive."""
        be = DeepSeekBackend(api_key="sk-test")
        # Verify: be.context_window_size() > 0
        assert be.context_window_size() > 0
        # Verify: isinstance(be.context_window_size(), int)
        assert isinstance(be.context_window_size(), int)


# ===========================================================================
# Token counting and model attribute
# ===========================================================================

class TestDeepSeekBackendTokens:
    """Test count_tokens() and model attribute."""

    def test_count_tokens_returns_int(self):
        """count_tokens() returns an integer."""
        be = DeepSeekBackend(api_key="sk-test")
        result = be.count_tokens("hello world")
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_count_tokens_empty_string(self):
        """Empty string should not crash."""
        be = DeepSeekBackend(api_key="sk-test")
        result = be.count_tokens("")
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_count_tokens_long_text(self):
        """Long text should not crash."""
        be = DeepSeekBackend(api_key="sk-test")
        result = be.count_tokens("Test " * 500)
        # Verify: isinstance(result, int)
        assert isinstance(result, int)

    def test_model_attribute(self):
        """model attribute matches constructor argument."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-pro")
        # Verify: be.model == "deepseek-v4-pro"
        assert be.model == "deepseek-v4-pro"
        # Verify: isinstance(be.model, str)
        assert isinstance(be.model, str)


# ===========================================================================
# Request data building
# ===========================================================================

class TestDeepSeekBackendRequestBuilding:
    """Test _build_request_data including DeepSeek-specific sanitization."""

    def test_build_request_includes_max_tokens(self):
        """Request body includes max_tokens parameter."""
        be = DeepSeekBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=512,
        )
        # Verify: data["max_tokens"] == 512
        assert data["max_tokens"] == 512

    def test_build_request_includes_model(self):
        """Request body includes the model name."""
        be = DeepSeekBackend(api_key="sk-test", model="deepseek-v4-flash")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
        )
        # Verify: data["model"] == "deepseek-v4-flash"
        assert data["model"] == "deepseek-v4-flash"

    def test_build_request_includes_temperature(self):
        """Temperature is included in request data."""
        be = DeepSeekBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.7,
        )
        # Verify: data["temperature"] == 0.7
        assert data["temperature"] == 0.7

    def test_build_request_strips_internal_message_fields(self):
        """Encre-internal fields are stripped from messages sent to DeepSeek."""
        be = DeepSeekBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "ls"}'},
                    "_client_id": "call_0_0",
                }],
                "branch_id": "br_0001",
                "seq_in_branch": 5,
                "id": "msg_1",
                "parent_id": "msg_0",
                "usage": {"prompt_tokens": 10},
                "segments": [{"kind": "tool", "tool_id": "call_1"}],
                "reasoning_content": "think",
            }, {
                "role": "tool",
                "content": "ok",
                "tool_call_id": "call_1",
                "_client_id": "call_0_0",
                "branch_id": "br_0001",
            }],
        )
        assistant = data["messages"][0]
        # Verify: internal fields removed
        for bad in ("branch_id", "seq_in_branch", "id", "parent_id", "usage", "segments", "reasoning_content", "_client_id"):
            assert bad not in assistant, bad
        # Verify: content null coerced to empty string
        assert assistant["content"] == ""
        # Verify: tool_calls cleaned
        assert assistant["tool_calls"][0] == {
            "id": "call_1",
            "type": "function",
            "function": {"name": "bash", "arguments": '{"command": "ls"}'},
        }
        tool_msg = data["messages"][1]
        assert tool_msg == {"role": "tool", "content": "ok", "tool_call_id": "call_1"}

    def test_build_request_normalizes_tool_schemas(self):
        """Tool parameter schemas are normalized for DeepSeek validation."""
        be = DeepSeekBackend(api_key="sk-test")
        data = be._build_request_data(
            messages=[{"role": "user", "content": "hi"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "minLength": 1},
                            "cwd": {"type": "string"},
                        },
                    },
                },
            }],
        )
        params = data["tools"][0]["function"]["parameters"]
        # Verify: all properties required
        assert sorted(params["required"]) == ["command", "cwd"]
        # Verify: additionalProperties false
        assert params["additionalProperties"] is False
        # Verify: unsupported keyword stripped
        assert "minLength" not in params["properties"]["command"]


# ===========================================================================
# Lifecycle
# ===========================================================================

class TestDeepSeekBackendLifecycle:
    """Test resource cleanup."""

    def test_aclose_does_not_raise(self):
        """aclose() should work without a prior request (lazy client)."""
        be = DeepSeekBackend(api_key="sk-test")
        asyncio.run(be.aclose())

    def test_aclose_idempotent(self):
        """aclose() called twice should not raise."""

        async def _double():
            """Helper: Double."""
            be = DeepSeekBackend(api_key="sk-test")
            await be.aclose()
            await be.aclose()

        asyncio.run(_double())
