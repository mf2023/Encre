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

"""Tests for AgentEvent union, BackendEvent union, and factory function variants."""


from encre.utils.types import (
    BackendError,
    BackendFinish,
    BackendText,
    BackendThinking,
    BackendToolCall,
    BackendToolCallDelta,
    Finish,
    PermissionRequest,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
)


class TestAgentEventUnion:
    """Verify every member type passes isinstance check against AgentEvent."""

    def test_text_delta_in_union(self):
        """Test: Text delta in union."""
        e = TextDelta(text="hello")
        # Verify: isinstance(e, TextDelta)
        assert isinstance(e, TextDelta)

    def test_thinking_delta_in_union(self):
        """Test: Thinking delta in union."""
        e = ThinkingDelta(text="thinking...")
        # Verify: isinstance(e, ThinkingDelta)
        assert isinstance(e, ThinkingDelta)

    def test_tool_call_start_in_union(self):
        """Test: Tool call start in union."""
        e = ToolCallStart(name="bash", id="call_1")
        # Verify: isinstance(e, ToolCallStart)
        assert isinstance(e, ToolCallStart)

    def test_tool_call_delta_in_union(self):
        """Test: Tool call delta in union."""
        e = ToolCallDelta(id="call_1", key="args", value="{}")
        # Verify: isinstance(e, ToolCallDelta)
        assert isinstance(e, ToolCallDelta)

    def test_tool_call_end_in_union(self):
        """Test: Tool call end in union."""
        e = ToolCallEnd(id="call_1")
        # Verify: isinstance(e, ToolCallEnd)
        assert isinstance(e, ToolCallEnd)

    def test_tool_progress_in_union(self):
        """Test: Tool progress in union."""
        e = ToolProgress(id="call_1", tool_name="bash", status="running")
        # Verify: isinstance(e, ToolProgress)
        assert isinstance(e, ToolProgress)

    def test_tool_result_in_union(self):
        """Test: Tool result in union."""
        e = ToolResult(id="call_1", content="output", is_error=False)
        # Verify: isinstance(e, ToolResult)
        assert isinstance(e, ToolResult)

    def test_permission_request_in_union(self):
        """Test: Permission request in union."""
        e = PermissionRequest(tool_name="bash", reason="safe")
        # Verify: isinstance(e, PermissionRequest)
        assert isinstance(e, PermissionRequest)

    def test_finish_in_union(self):
        """Test: Finish in union."""
        e = Finish(reason="stop")
        # Verify: isinstance(e, Finish)
        assert isinstance(e, Finish)


class TestBackendEventUnion:
    """Verify every backend event type passes isinstance check."""

    def test_backend_text_in_union(self):
        """Test: Backend text in union."""
        e = BackendText(text="hello")
        # Verify: isinstance(e, BackendText)
        assert isinstance(e, BackendText)

    def test_backend_thinking_in_union(self):
        """Test: Backend thinking in union."""
        e = BackendThinking(text="hmm...", signature_delta=None)
        # Verify: isinstance(e, BackendThinking)
        assert isinstance(e, BackendThinking)

    def test_backend_tool_call_in_union(self):
        """Test: Backend tool call in union."""
        e = BackendToolCall(id="c1", name="bash", arguments="{}")
        # Verify: isinstance(e, BackendToolCall)
        assert isinstance(e, BackendToolCall)

    def test_backend_tool_call_delta_in_union(self):
        """Test: Backend tool call delta in union."""
        e = BackendToolCallDelta(index=0, key="k", value="v")
        # Verify: isinstance(e, BackendToolCallDelta)
        assert isinstance(e, BackendToolCallDelta)

    def test_backend_finish_in_union(self):
        """Test: Backend finish in union."""
        e = BackendFinish(reason="stop")
        # Verify: isinstance(e, BackendFinish)
        assert isinstance(e, BackendFinish)

    def test_backend_error_in_union(self):
        """Test: Backend error in union."""
        e = BackendError(error="timeout")
        # Verify: isinstance(e, BackendError)
        assert isinstance(e, BackendError)

    def test_backend_thinking_with_signature(self):
        """Test: Backend thinking with signature."""
        e = BackendThinking(text="deep thought", signature_delta="sig123")
        # Verify: e.signature_delta == "sig123"
        assert e.signature_delta == "sig123"


class TestFactoryFunctionEdgeCases:
    """Test factory functions for edge cases and full kwarg coverage."""

    def test_create_finish_with_usage(self):
        """Test: Create finish with usage."""
        from encre.utils.types import create_finish
        f = create_finish("stop", usage={"prompt_tokens": 10, "completion_tokens": 20})
        # Verify: f.usage == {"prompt_tokens": 10, "completion_tokens": 20}
        assert f.usage == {"prompt_tokens": 10, "completion_tokens": 20}

    def test_create_finish_without_usage(self):
        """Test: Create finish without usage."""
        from encre.utils.types import create_finish
        f = create_finish("error")
        # Verify: f.usage is None
        assert f.usage is None

    def test_create_finish_all_reasons(self):
        """Test: Create finish all reasons."""
        from encre.utils.types import create_finish
        for reason in ["stop", "tool_calls", "error", "max_tokens", "cancelled"]:
            f = create_finish(reason)
            # Verify: f.reason == reason
            assert f.reason == reason

    def test_create_text_delta_empty(self):
        """Test: Create text delta empty."""
        from encre.utils.types import create_text_delta
        e = create_text_delta("")
        # Verify: e.text == ""
        assert e.text == ""

    def test_create_text_delta_multiline(self):
        """Test: Create text delta multiline."""
        from encre.utils.types import create_text_delta
        e = create_text_delta("line1\nline2\nline3")
        # Verify: "line2" in e.text
        assert "line2" in e.text

    def test_create_tool_result_with_error(self):
        """Test: Create tool result with error."""
        from encre.utils.types import create_tool_result
        e = create_tool_result("call_err", "command failed", is_error=True)
        # Verify: e.is_error is True
        assert e.is_error is True

    def test_create_permission_request(self):
        """Test: Create permission request."""
        from encre.utils.types import create_permission_request
        e = create_permission_request("bash", "Running potentially dangerous command")
        # Verify: e.tool_name == "bash"
        assert e.tool_name == "bash"

    def test_create_backend_thinking_with_signature(self):
        """Test: Create backend thinking with signature."""
        from encre.utils.types import create_backend_thinking
        e = create_backend_thinking("deep thoughts", signature_delta="sig_abc")
        # Verify: e.signature_delta == "sig_abc"
        assert e.signature_delta == "sig_abc"

    def test_create_backend_thinking_without_signature(self):
        """Test: Create backend thinking without signature."""
        from encre.utils.types import create_backend_thinking
        e = create_backend_thinking("just thinking")
        # Verify: e.signature_delta is None
        assert e.signature_delta is None

    def test_create_backend_error_long_message(self):
        """Test: Create backend error long message."""
        from encre.utils.types import create_backend_error
        e = create_backend_error("A" * 1000)
        # Verify: len(e.error) == 1000
        assert len(e.error) == 1000


class TestFinishReasonVariants:
    """Verify every FinishReason literal works."""

    def test_finish_stop(self):
        """Test: Finish stop."""
        f = Finish(reason="stop")
        # Verify: f.reason == "stop"
        assert f.reason == "stop"

    def test_finish_tool_calls(self):
        """Test: Finish tool calls."""
        f = Finish(reason="tool_calls")
        # Verify: f.reason == "tool_calls"
        assert f.reason == "tool_calls"

    def test_finish_error(self):
        """Test: Finish error."""
        f = Finish(reason="error")
        # Verify: f.reason == "error"
        assert f.reason == "error"

    def test_finish_max_tokens(self):
        """Test: Finish max tokens."""
        f = Finish(reason="max_tokens")
        # Verify: f.reason == "max_tokens"
        assert f.reason == "max_tokens"

    def test_finish_cancelled(self):
        """Test: Finish cancelled."""
        f = Finish(reason="cancelled")
        # Verify: f.reason == "cancelled"
        assert f.reason == "cancelled"


class TestToolResultPatterns:
    """Test ToolResult success and error patterns."""

    def test_tool_result_success(self):
        """Test: Tool result success."""
        tr = ToolResult(id="t1", content="file contents here", is_error=False)
        # Verify: tr.is_error is False
        assert tr.is_error is False
        # Verify: len(tr.content) > 0
        assert len(tr.content) > 0

    def test_tool_result_error(self):
        """Test: Tool result error."""
        tr = ToolResult(id="t2", content="Permission denied", is_error=True)
        # Verify: tr.is_error is True
        assert tr.is_error is True

    def test_tool_result_empty_content(self):
        """Test: Tool result empty content."""
        tr = ToolResult(id="t3", content="", is_error=False)
        # Verify: tr.content == ""
        assert tr.content == ""
        # Verify: tr.is_error is False
        assert tr.is_error is False

    def test_tool_result_large_content(self):
        """Test: Tool result large content."""
        big = "x" * 5000
        tr = ToolResult(id="t4", content=big, is_error=False)
        # Verify: len(tr.content) == 5000
        assert len(tr.content) == 5000
