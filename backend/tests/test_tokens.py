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

"""Tests for token estimation utilities: estimate_tokens, count_message_tokens."""


from encre.utils.tokens import (
    count_message_tokens,
    estimate_tokens,
    estimate_tokens_simple,
    is_tiktoken_available,
)


class TestEstimateTokens:
    """Test cases covering estimate tokens.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify estimate_tokens() returns sensible integer counts."""

    def test_empty_string_returns_zero(self):
        """Verifies that empty string returns zero."""
        # Confirm the expected result for this scenario: empty string returns zero.
        assert estimate_tokens("") == 0

    def test_short_string(self):
        """Verifies that short string."""
        count = estimate_tokens("hello world")
        # Confirm the expected result for this scenario: short string.
        assert isinstance(count, int)
        assert count > 0

    def test_long_string(self):
        """Verifies that long string."""
        count = estimate_tokens("hello world " * 100)
        # Confirm the expected result for this scenario: long string.
        assert isinstance(count, int)
        assert count > 50

    def test_result_is_int(self):
        """Verifies that result is int."""
        count = estimate_tokens("any text")
        # Confirm the expected result for this scenario: result is int.
        assert isinstance(count, int)

    def test_non_negative(self):
        """Verifies that non negative."""
        count = estimate_tokens("test")
        # Confirm the expected result for this scenario: non negative.
        assert count >= 0

    def test_grows_with_length(self):
        """Verifies that grows with length."""
        short = estimate_tokens("hi")
        long = estimate_tokens("hi " * 200)
        # Confirm the expected result for this scenario: grows with length.
        assert long > short

    def test_model_kwarg_accepted(self):
        """Verifies that model kwarg accepted."""
        count = estimate_tokens("hello", model="gpt-4o")
        # Confirm the expected result for this scenario: model kwarg accepted.
        assert isinstance(count, int)
        assert count > 0

    def test_different_model_kwarg(self):
        """Verifies that different model kwarg."""
        count = estimate_tokens("hello", model="gpt-4")
        # Confirm the expected result for this scenario: different model kwarg.
        assert isinstance(count, int)
        assert count > 0

    def test_unicode_text(self):
        """Verifies that unicode text."""
        count = estimate_tokens("你好世界")
        # Confirm the expected result for this scenario: unicode text.
        assert isinstance(count, int)
        assert count > 0

    def test_code_snippet(self):
        """Verifies that code snippet."""
        code = "def foo():\n    return 42\n"
        count = estimate_tokens(code)
        # Confirm the expected result for this scenario: code snippet.
        assert count > 0

    def test_special_characters(self):
        """Verifies that special characters."""
        text = "!@#$%^&*()_+{}|:\"<>?[];',./"
        count = estimate_tokens(text)
        # Confirm the expected result for this scenario: special characters.
        assert isinstance(count, int)

    def test_pure_whitespace(self):
        """Verifies that pure whitespace."""
        count = estimate_tokens("     ")
        # Confirm the expected result for this scenario: pure whitespace.
        assert isinstance(count, int)


class TestEstimateTokensSimple:
    """Test cases covering estimate tokens simple.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify estimate_tokens_simple() compatibility wrapper."""

    def test_returns_int(self):
        """Verifies that returns int."""
        count = estimate_tokens_simple("hello")
        # Confirm the expected result for this scenario: returns int.
        assert isinstance(count, int)

    def test_empty_string(self):
        """Verifies that empty string."""
        count = estimate_tokens_simple("")
        # Confirm the expected result for this scenario: empty string.
        assert count == 0

    def test_consistency_with_main_function(self):
        """Verifies that consistency with main function."""
        c1 = estimate_tokens_simple("hello world")
        c2 = estimate_tokens("hello world")
        # Confirm the expected result for this scenario: consistency with main function.
        assert c1 == c2


class TestCountMessageTokens:
    """Test cases covering count message tokens.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify count_message_tokens() for message dicts."""

    def test_single_message(self):
        """Verifies that single message."""
        msgs = [{"role": "user", "content": "hello"}]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: single message.
        assert isinstance(count, int)
        assert count > 0

    def test_empty_messages_list(self):
        """Verifies that empty messages list."""
        count = count_message_tokens([])
        # Confirm the expected result for this scenario: empty messages list.
        assert count == 0

    def test_multiple_messages(self):
        """Verifies that multiple messages."""
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is..."},
        ]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: multiple messages.
        assert isinstance(count, int)
        assert count > 0

    def test_message_with_empty_content(self):
        """Verifies that message with empty content."""
        msgs = [{"role": "user", "content": ""}]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: message with empty content.
        assert isinstance(count, int)
        # Should have at least the per-message overhead (4 tokens)
        assert count >= 4

    def test_message_with_missing_content_key(self):
        """Verifies that message with missing content key."""
        msgs = [{"role": "user"}]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: message with missing content key.
        assert isinstance(count, int)

    def test_list_content_blocks(self):
        """Verifies that list content blocks."""
        msgs = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ],
        }]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: list content blocks.
        assert isinstance(count, int)
        assert count > 0

    def test_message_with_tool_calls(self):
        """Verifies that message with tool calls."""
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "bash", "arguments": '{"cmd": "ls"}'},
                {"id": "call_2", "name": "read", "arguments": '{"path": "/tmp"}'},
            ],
        }]
        count = count_message_tokens(msgs)
        # Confirm the expected result for this scenario: message with tool calls.
        assert isinstance(count, int)
        assert count > 0

    def test_model_kwarg_accepted(self):
        """Verifies that model kwarg accepted."""
        msgs = [{"role": "user", "content": "hello"}]
        count = count_message_tokens(msgs, model="gpt-4")
        # Confirm the expected result for this scenario: model kwarg accepted.
        assert isinstance(count, int)

    def test_batch_grows_with_messages(self):
        """Verifies that batch grows with messages."""
        single = count_message_tokens([{"role": "user", "content": "hello"}])
        double = count_message_tokens([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ])
        # Confirm the expected result for this scenario: batch grows with messages.
        assert double > single


class TestTiktokenAvailability:
    """Test cases covering tiktoken availability.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify is_tiktoken_available() reports truthfully."""

    def test_import_works(self):
        """Just call it to ensure no import errors."""
        available = is_tiktoken_available()
        # It returns a bool regardless of whether tiktoken is installed
        # Confirm the expected result for this scenario: import works.
        assert isinstance(available, bool)
