#!/usr/bin/env python3

# Copyright 漏 2025-2026 Wenze Wei. All Rights Reserved.
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

from __future__ import annotations

"""Tests for GoogleBackend -- construction, capabilities, context window,
grounding, message conversion, and token counting."""

import asyncio

from encre.backends.google import GoogleBackend

# ===========================================================================
# Construction
# ===========================================================================


class TestGoogleBackendConstruction:
    """Engineered to validate ``GoogleBackend`` instantiation across parameter combinations.

    This test class exercises constructor behavior across 7 scenarios covering
    default model and base URL, Flash model variant, custom base URL override,
    grounding toggle, grounding default, empty API key handling, and HTTP
    client initialization. The design ensures the backend points at Google AI
    Studio by default and correctly propagates user-supplied parameters so
    that downstream requests route to the intended endpoint with the right flags.
    """

    def test_verify_default_model_and_base_url(self):
        """Validate that defaults are ``gemini-3.7-flash`` and the Google AI Studio endpoint.

        The test exercises construction with only an API key and asserts the
        model, api_key, and base_url attributes match the documented defaults
        because the default configuration must target Google's generative-language
        endpoint so that requests succeed out of the box.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.model == "gemini-3.7-flash"
        assert be.api_key == "fake-key"
        assert "generativelanguage.googleapis.com" in be.base_url

    def test_verify_flash_model_variant(self):
        """Validate that the Gemini 2.5 Flash model is accepted and stored correctly.

        The test exercises construction with ``model="gemini-2.5-flash"`` and
        asserts the attribute matches because the Flash tier is a distinct
        model with different latency and cost characteristics than Pro.
        """
        be = GoogleBackend(api_key="fake-key", model="gemini-2.5-flash")
        assert be.model == "gemini-2.5-flash"

    def test_verify_custom_base_url_overrides_default(self):
        """Validate that a custom base_url replaces the default Google endpoint.

        The test exercises construction with a custom ``base_url`` and asserts
        the attribute holds the provided URL because proxy deployments and
        compatible API gateways require redirecting requests to an alternate origin.
        """
        be = GoogleBackend(
            api_key="fake-key",
            base_url="https://custom-google.example.com/v1beta",
        )
        assert be.base_url == "https://custom-google.example.com/v1beta"

    def test_verify_grounding_can_be_enabled_at_construction(self):
        """Validate that ``enable_grounding=True`` is stored on the backend instance.

        The test exercises construction with grounding enabled and asserts the
        flag is ``True`` because Google Search grounding must be opt-in and
        preserved so that the request builder can attach grounding config.
        """
        be = GoogleBackend(api_key="fake-key", enable_grounding=True)
        assert be.enable_grounding is True

    def test_verify_grounding_is_disabled_by_default(self):
        """Validate that grounding defaults to ``False`` so it does not fire unintentionally.

        The test exercises parameterless construction (with API key) and asserts
        ``enable_grounding`` is ``False`` because grounding adds network
        latency and cost and must be explicitly enabled by the caller.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.enable_grounding is False

    def test_verify_empty_api_key_is_allowed(self):
        """Validate that construction without an API key does not raise.

        The test exercises parameterless construction and asserts ``api_key`` is
        empty string and the model defaults to ``gemini-3.7-flash`` because
        some deployments inject credentials via environment variables after
        backend construction.
        """
        be = GoogleBackend()
        assert be.api_key == ""
        assert be.model == "gemini-3.7-flash"

    def test_verify_http_client_is_initialized(self):
        """Validate that construction creates an active httpx.AsyncClient.

        The test exercises construction and asserts ``_client`` is not None
        because the Google backend creates its own HTTP client eagerly so
        that connection pooling is ready immediately for chat requests.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._client is not None


# ===========================================================================
# Capability checks
# ===========================================================================


class TestGoogleBackendCapabilities:
    """Engineered to validate capability flags for Gemini models.

    This test class exercises ``supports_tool_calling``, ``supports_thinking``,
    ``supports_grounding``, and ``supports_prompt_caching`` across 5 scenarios.
    The design ensures each capability flag returns the correct boolean so
    that the agent loop can enable function calling, reasoning modes, Google
    Search grounding, and prompt-caching headers per model correctly.
    """

    def test_verify_supports_tool_calling_default(self):
        """Validate that the default Gemini model supports function calling.

        The test exercises the default backend and asserts ``supports_tool_calling()``
        returns ``True`` because all Gemini 2.5 models expose the function-calling
        API required by the agent tool-use loop.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.supports_tool_calling() is True

    def test_verify_supports_tool_calling_across_models(self):
        """Validate that tool calling is enabled for all tested Gemini 2.5 models.

        The test iterates over Pro and Flash and asserts ``True`` for each
        because the agent framework requires uniform tool-call support across
        all available Gemini backends.
        """
        models = ["gemini-2.5-pro", "gemini-2.5-flash"]
        for m in models:
            be = GoogleBackend(api_key="fake-key", model=m)
            assert be.supports_tool_calling() is True, f"model={m}"

    def test_verify_supports_thinking(self):
        """Validate that Gemini 2.5 models support thinking/reasoning mode.

        The test exercises the default backend and asserts ``supports_thinking()``
        is ``True`` because the Gemini 2.5 line supports extended thinking
        tokens that the backend must forward to the client.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.supports_thinking() is True

    def test_verify_supports_grounding(self):
        """Validate that Gemini models advertise grounding capability.

        The test exercises the default backend and asserts ``supports_grounding()``
        is ``True`` because the Google backend exposes the grounding feature
        flag so the agent loop can conditionally enable Google Search lookups.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.supports_grounding() is True

    def test_verify_supports_prompt_caching_returns_bool(self):
        """Validate that ``supports_prompt_caching`` returns a boolean value.

        The test exercises the default backend and asserts the result is an
        ``bool`` because the agent loop branches on this flag to decide
        whether to attach prompt-cache control headers to the request.
        """
        be = GoogleBackend(api_key="fake-key")
        result = be.supports_prompt_caching()
        assert isinstance(result, bool)


# ===========================================================================
# Context window size
# ===========================================================================


class TestGoogleBackendContextWindow:
    """Engineered to validate context-window sizes for Gemini models.

    This test class exercises ``context_window_size()`` across 3 scenarios
    covering the default Pro model, Flash variant, and a positivity check.
    The design ensures the agent loop can truncate conversations to the
    correct 1,048,576-token limit so that API requests never exceed Google's
    context cap regardless of which Gemini 2.5 model is selected.
    """

    def test_verify_context_window_size_default(self):
        """Validate that the default Gemini model reports a 1,048,576-token context window.

        The test exercises the default backend and asserts 1048576 because
        Gemini 2.5 Pro supports the full million-token context required for
        long-document analysis workflows.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.context_window_size() == 1048576

    def test_verify_context_window_size_flash(self):
        """Validate that Gemini 2.5 Flash reports a 1,048,576-token context window.

        The test exercises the Flash model and asserts 1048576 because the
        Flash tier shares the same million-token context capacity as Pro.
        """
        be = GoogleBackend(api_key="fake-key", model="gemini-2.5-flash")
        assert be.context_window_size() == 1048576

    def test_verify_context_window_is_positive_integer(self):
        """Validate that the default model returns a positive integer context size.

        The test exercises the default backend and asserts the result is an
        ``int`` greater than zero because a non-positive context size would
        cause the agent loop to discard all conversation history immediately.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be.context_window_size() > 0
        assert isinstance(be.context_window_size(), int)


# ===========================================================================
# Token counting and model attribute
# ===========================================================================


class TestGoogleBackendTokens:
    """Engineered to validate token-counting resilience and model attribute access.

    This test class exercises ``count_tokens()`` across 4 scenarios covering
    normal text, empty strings, long text, and direct model attribute access.
    The design ensures token counting never raises on valid input and that
    the ``model`` attribute faithfully reflects the constructor argument.
    """

    def test_verify_count_tokens_returns_int(self):
        """Validate that ``count_tokens`` returns an integer for normal text.

        The test exercises a short string and asserts the result is an ``int``
        because the token counter must always produce an integer return type
        even when the underlying tokenizer is unavailable.
        """
        be = GoogleBackend(api_key="fake-key")
        result = be.count_tokens("hello world")
        assert isinstance(result, int)

    def test_verify_count_tokens_empty_string(self):
        """Validate that ``count_tokens`` does not crash on an empty string.

        The test exercises ``""`` and asserts the result is an ``int`` because
        the tokenizer must handle the zero-length edge case without raising.
        """
        be = GoogleBackend(api_key="fake-key")
        result = be.count_tokens("")
        assert isinstance(result, int)

    def test_verify_count_tokens_long_text(self):
        """Validate that ``count_tokens`` does not crash on long repeated text.

        The test exercises a 300-repetition string and asserts the result is
        an ``int`` because token counting must scale gracefully to large inputs
        without throwing, even if the count is approximate.
        """
        be = GoogleBackend(api_key="fake-key")
        result = be.count_tokens("Google Gemini token counting. " * 300)
        assert isinstance(result, int)

    def test_verify_model_attribute_matches_constructor(self):
        """Validate that the ``model`` attribute stores the constructor argument exactly.

        The test exercises construction with ``model="gemini-2.5-flash"`` and
        asserts the attribute is that exact string and is an instance of ``str``
        because the model name is used in every API request and must not be mutated.
        """
        be = GoogleBackend(api_key="fake-key", model="gemini-2.5-flash")
        assert be.model == "gemini-2.5-flash"
        assert isinstance(be.model, str)


# ===========================================================================
# Message conversion (internal protocol mapping)
# ===========================================================================


class TestGoogleBackendMessageConversion:
    """Engineered to validate OpenAI-to-Google message and tool format conversion.

    This test class exercises ``_convert_messages`` and ``_convert_tools``
    across 8 scenarios covering simple user messages, system-message extraction
    into ``systemInstruction``, assistant-role mapping, empty-input handling,
    OpenAI-to-Google tool conversion, non-function tool skipping, empty-tool
    lists, and missing-description tolerance. The design ensures the backend
    correctly translates the internal message protocol into Google's Gemini
    API format so that conversations round-trip without losing role semantics
    or tool definitions.
    """

    def test_verify_simple_user_message_conversion(self):
        """Validate that a user message is converted to Google format with the correct role and parts.

        The test exercises a single user message and asserts the contents list
        has one entry with role ``"user"`` and a single text part matching the
        original content because user messages must pass through with their
        text preserved in the Gemini ``Part`` structure.
        """
        be = GoogleBackend(api_key="fake-key")
        messages = [{"role": "user", "content": "Hello, Gemini!"}]
        contents, _system_instruction = be._convert_messages(messages)
        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert len(contents[0]["parts"]) == 1
        assert contents[0]["parts"][0]["text"] == "Hello, Gemini!"

    def test_verify_system_message_extracted_into_system_instruction(self):
        """Validate that system messages are extracted into ``systemInstruction`` rather than contents.

        The test exercises a system message followed by a user message and asserts
        the contents list contains only the user message while ``systemInstruction``
        carries the system text because Gemini's API separates system context
        from the conversational contents stream.
        """
        be = GoogleBackend(api_key="fake-key")
        messages = [
            {"role": "system", "content": "You are a helpful bot."},
            {"role": "user", "content": "Help me."},
        ]
        contents, system_instruction = be._convert_messages(messages)
        assert len(contents) == 1
        assert system_instruction is not None
        assert system_instruction["parts"][0]["text"] == "You are a helpful bot."

    def test_verify_assistant_role_mapped_to_model(self):
        """Validate that the assistant role is mapped to Gemini's ``model`` role.

        The test exercises a single assistant message and asserts the converted
        content has role ``"model"`` because Gemini uses ``model`` instead of
        ``assistant`` to denote AI-generated turns in the contents array.
        """
        be = GoogleBackend(api_key="fake-key")
        messages = [{"role": "assistant", "content": "I can help with that."}]
        contents, _ = be._convert_messages(messages)
        assert len(contents) == 1
        assert contents[0]["role"] == "model"

    def test_verify_empty_message_list_produces_empty_contents(self):
        """Validate that an empty message list returns empty contents and no system instruction.

        The test exercises ``[]`` and asserts both returned values are empty/None
        because a conversation with no messages must not produce any Gemini
        API fields that could be interpreted as spurious input.
        """
        be = GoogleBackend(api_key="fake-key")
        contents, system_instruction = be._convert_messages([])
        assert contents == []
        assert system_instruction is None

    def test_verify_tools_converted_to_function_declarations(self):
        """Validate that OpenAI tool definitions are converted to Google ``functionDeclarations``.

        The test exercises a single function tool and asserts the result is a
        list containing a ``functionDeclarations`` entry with the correct name
        and description because Gemini requires tools to be declared under
        the ``functionDeclarations`` key rather than the OpenAI ``function`` wrapper.
        """
        be = GoogleBackend(api_key="fake-key")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }
        ]
        result = be._convert_tools(tools)
        assert len(result) == 1
        assert "functionDeclarations" in result[0]
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "get_weather"
        assert decls[0]["description"] == "Get current weather"

    def test_verify_non_function_tools_are_skipped(self):
        """Validate that non-function tool types are filtered out during conversion.

        The test exercises a mix of ``code_interpreter`` and ``function`` tool
        types and asserts only the function tool appears in the declaration
        list because Gemini only supports function-calling tools and must
        ignore unsupported types rather than passing them through.
        """
        be = GoogleBackend(api_key="fake-key")
        tools = [
            {"type": "code_interpreter"},
            {"type": "function", "function": {"name": "calc"}},
        ]
        result = be._convert_tools(tools)
        assert len(result) > 0
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "calc"

    def test_verify_empty_tool_list_produces_empty_declarations(self):
        """Validate that an empty tool list produces a ``functionDeclarations`` entry with an empty list.

        The test exercises ``[]`` and asserts the result has one entry with
        ``functionDeclarations == []`` because the Gemini API expects the
        ``tools`` field to be present even when empty rather than omitted.
        """
        be = GoogleBackend(api_key="fake-key")
        result = be._convert_tools([])
        assert len(result) == 1
        assert result[0]["functionDeclarations"] == []

    def test_verify_tool_without_description_is_still_converted(self):
        """Validate that a tool missing a description is converted without the description field.

        The test exercises a function tool with only a name and asserts the
        declaration has the correct name and no ``description`` key because
        descriptions are optional in Gemini's function schema and tools must
        not be dropped solely due to a missing description.
        """
        be = GoogleBackend(api_key="fake-key")
        tools = [
            {
                "type": "function",
                "function": {"name": "simple_tool"},
            }
        ]
        result = be._convert_tools(tools)
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "simple_tool"
        assert "description" not in decls[0]


# ===========================================================================
# Finish reason mapping
# ===========================================================================


class TestGoogleBackendFinishReason:
    """Engineered to validate ``_map_finish_reason`` Google-to-unified finish-reason translation.

    This test class exercises the finish-reason mapper across 5 scenarios
    covering stop, max-tokens, safety, recitation, and unknown-fallback cases.
    The design ensures that Gemini-specific finish reasons are translated
    into the unified finish-reason strings that the agent loop expects so
    that termination logic works uniformly across all backend providers.
    """

    def test_verify_stop_reason_maps_to_stop(self):
        """Validate that Gemini's ``STOP`` reason maps to the unified ``"stop"`` string.

        The test exercises ``_map_finish_reason("STOP")`` and asserts the result
        is ``"stop"`` because a normal completed response must be recognized
        as a clean termination by the agent loop.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._map_finish_reason("STOP") == "stop"

    def test_verify_max_tokens_reason_maps_to_max_tokens(self):
        """Validate that Gemini's ``MAX_TOKENS`` reason maps to ``"max_tokens"``.

        The test exercises ``_map_finish_reason("MAX_TOKENS")`` and asserts the
        result is ``"max_tokens"`` because output-length exhaustion must be
        distinguished from normal completion so the agent can decide whether
        to continue the turn or truncate the response.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._map_finish_reason("MAX_TOKENS") == "max_tokens"

    def test_verify_safety_reason_maps_to_error(self):
        """Validate that Gemini's ``SAFETY`` reason maps to ``"error"``.

        The test exercises ``_map_finish_reason("SAFETY")`` and asserts the
        result is ``"error"`` because safety-blocked responses must be treated
        as failures by the agent loop rather than successful completions.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._map_finish_reason("SAFETY") == "error"

    def test_verify_recitation_reason_maps_to_error(self):
        """Validate that Gemini's ``RECITATION`` reason maps to ``"error"``.

        The test exercises ``_map_finish_reason("RECITATION")`` and asserts the
        result is ``"error"`` because recitation-blocked responses must be
        treated as failures so the agent can retry with a rephrased prompt.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._map_finish_reason("RECITATION") == "error"

    def test_verify_unknown_reason_falls_back_to_stop(self):
        """Validate that unrecognized finish reasons fall back to ``"stop"``.

        The test exercises ``_map_finish_reason("UNKNOWN_REASON")`` and asserts
        the result is ``"stop"`` because unknown reasons must not crash the
        mapper and should be treated as benign termination so the loop can
        proceed rather than entering an error state.
        """
        be = GoogleBackend(api_key="fake-key")
        assert be._map_finish_reason("UNKNOWN_REASON") == "stop"


# ===========================================================================
# Lifecycle
# ===========================================================================


class TestGoogleBackendLifecycle:
    """Engineered to validate backend resource cleanup and lifecycle safety.

    This test class exercises ``aclose()`` across 2 scenarios covering normal
    client closure and idempotent double-close. The design ensures that the
    async cleanup path closes the underlying httpx client and never raises
    on repeated calls, preventing unhandled exceptions during server shutdown.
    """

    def test_verify_aclose_closes_http_client(self):
        """Validate that ``aclose()`` closes the underlying httpx client.

        The test exercises construction, asserts the client exists, calls
        ``aclose()``, then asserts ``is_closed`` is ``True`` because the HTTP
        client must be properly released back to the event loop on backend
        shutdown to avoid connection leaks.
        """

        async def _close():
            """Close the backend and verify the client is closed."""
            be = GoogleBackend(api_key="fake-key")
            assert be._client is not None
            await be.aclose()
            assert be._client.is_closed

        asyncio.run(_close())

    def test_verify_aclose_is_idempotent(self):
        """Validate that calling ``aclose()`` twice does not raise.

        The test exercises a double-close sequence inside an async helper and
        asserts no exception is raised because shutdown handlers may invoke
        cleanup multiple times and idempotency prevents error propagation.
        """

        async def _double_close():
            """Close the backend twice in sequence."""
            be = GoogleBackend(api_key="fake-key")
            await be.aclose()
            await be.aclose()

        asyncio.run(_double_close())
