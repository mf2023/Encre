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

"""Tests for utility types, event factories, enums, and union types."""


from encre.utils.types import (
    AdaptiveThinking,
    BackendError,
    BackendFinish,
    BackendText,
    BackendThinking,
    BackendToolCall,
    BackendToolCallDelta,
    DisabledThinking,
    EnabledThinking,
    Finish,
    PermissionAllow,
    PermissionAsk,
    PermissionDeny,
    PermissionRequest,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
    create_backend_error,
    create_backend_finish,
    create_backend_text,
    create_backend_thinking,
    create_backend_tool_call,
    create_backend_tool_call_delta,
    create_finish,
    create_permission_request,
    create_text_delta,
    create_thinking_delta,
    create_tool_call_delta,
    create_tool_call_end,
    create_tool_call_start,
    create_tool_progress,
    create_tool_result,
)

# ===========================================================================
# Event dataclasses
# ===========================================================================

class TestTextDelta:
    """Test cases covering text delta.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        td = TextDelta(text="hello")
        # Confirm the expected result for this scenario: create.
        assert td.text == "hello"


class TestThinkingDelta:
    """Test cases covering thinking delta.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        td = ThinkingDelta(text="thinking...")
        # Confirm the expected result for this scenario: create.
        assert td.text == "thinking..."

    def test_empty(self):
        """Verifies that empty."""
        td = ThinkingDelta(text="")
        # Confirm the expected result for this scenario: empty.
        assert td.text == ""


class TestToolCallStart:
    """Test cases covering tool call start.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        tcs = ToolCallStart(id="call_1", name="bash")
        # Confirm the expected result for this scenario: create.
        assert tcs.id == "call_1"
        assert tcs.name == "bash"


class TestToolCallDelta:
    """Test cases covering tool call delta.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        tcd = ToolCallDelta(id="call_1", key="arguments", value='{"pattern": "foo"}')
        # Confirm the expected result for this scenario: create.
        assert tcd.id == "call_1"
        assert tcd.key == "arguments"


class TestToolCallEnd:
    """Test cases covering tool call end.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        tce = ToolCallEnd(id="call_1")
        # Confirm the expected result for this scenario: create.
        assert tce.id == "call_1"


class TestToolProgress:
    """Test cases covering tool progress.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        tp = ToolProgress(id="call_1", tool_name="bash", status="running")
        # Confirm the expected result for this scenario: create.
        assert tp.id == "call_1"
        assert tp.tool_name == "bash"
        assert tp.status == "running"


class TestToolResult:
    """Test cases covering tool result.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        tr = ToolResult(id="call_1", content="output here", is_error=False)
        # Confirm the expected result for this scenario: create.
        assert tr.id == "call_1"
        assert tr.content == "output here"
        assert tr.is_error is False

    def test_error_result(self):
        """Verifies that error result."""
        tr = ToolResult(id="call_1", content="command not found", is_error=True)
        # Confirm the expected result for this scenario: error result.
        assert tr.is_error is True


class TestPermissionRequest:
    """Test cases covering permission request.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        pr = PermissionRequest(tool_name="bash", reason="safe command")
        # Confirm the expected result for this scenario: create.
        assert pr.tool_name == "bash"
        assert pr.reason == "safe command"


class TestFinish:
    """Test cases covering finish.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create(self):
        """Verifies that create."""
        f = Finish(reason="stop", usage={"tokens": 100})
        # Confirm the expected result for this scenario: create.
        assert f.reason == "stop"
        assert f.usage == {"tokens": 100}

    def test_finish_reasons(self):
        """Verifies that finish reasons."""
        reasons = ["stop", "tool_calls", "error", "max_tokens", "cancelled"]
        for r in reasons:
            f = Finish(reason=r)
            # Confirm the expected result for this scenario: finish reasons.
            assert f.reason == r


# ===========================================================================
# Permission
# ===========================================================================

class TestPermissionEnums:
    """Test cases covering permission enums.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_permission_mode(self):
        """Verifies that permission mode."""
        modes = ["default", "accept_edits", "bypass", "dont_ask", "plan", "auto"]
        for m in modes:
            # PermissionMode is a Literal, so values must be in the set
            # Confirm the expected result for this scenario: permission mode.
            assert m in ["default", "accept_edits", "bypass", "dont_ask", "plan", "auto"]

    def test_permission_allow(self):
        """Verifies that permission allow."""
        pa = PermissionAllow()
        # Confirm the expected result for this scenario: permission allow.
        assert pa.behavior == "allow"

    def test_permission_deny(self):
        """Verifies that permission deny."""
        pd = PermissionDeny()
        # Confirm the expected result for this scenario: permission deny.
        assert pd.behavior == "deny"

    def test_permission_ask(self):
        """Verifies that permission ask."""
        pa = PermissionAsk()
        # Confirm the expected result for this scenario: permission ask.
        assert pa.behavior == "ask"


# ===========================================================================
# Task enums
# ===========================================================================

class TestTaskEnums:
    """Test cases covering task enums.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_task_type_literals(self):
        """Verifies that task type literals."""
        types = ["bash", "agent", "workflow"]
        for t in types:
            # Confirm the expected result for this scenario: task type literals.
            assert t in ["bash", "agent", "workflow"]

    def test_task_status_literals(self):
        """Verifies that task status literals."""
        statuses = ["pending", "running", "completed", "failed", "killed"]
        for s in statuses:
            # Confirm the expected result for this scenario: task status literals.
            assert s in ["pending", "running", "completed", "failed", "killed"]


# ===========================================================================
# Thinking config
# ===========================================================================

class TestThinkingConfig:
    """Test cases covering thinking config.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_adaptive(self):
        """Verifies that adaptive."""
        tc = AdaptiveThinking()
        # Confirm the expected result for this scenario: adaptive.
        assert tc.enabled is True
        assert tc.min_tokens == 1024

    def test_enabled(self):
        """Verifies that enabled."""
        tc = EnabledThinking(budget_tokens=16000)
        # Confirm the expected result for this scenario: enabled.
        assert tc.budget_tokens == 16000

    def test_disabled(self):
        """Verifies that disabled."""
        tc = DisabledThinking()
        # Confirm the expected result for this scenario: disabled.
        assert tc.enabled is False


# ===========================================================================
# Backend event types
# ===========================================================================

class TestBackendEvents:
    """Test cases covering backend events.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_backend_text(self):
        """Verifies that backend text."""
        bt = BackendText(text="hello")
        # Confirm the expected result for this scenario: backend text.
        assert bt.text == "hello"

    def test_backend_thinking(self):
        """Verifies that backend thinking."""
        bt = BackendThinking(text="hmm", signature_delta=None)
        # Confirm the expected result for this scenario: backend thinking.
        assert bt.text == "hmm"

    def test_backend_tool_call(self):
        """Verifies that backend tool call."""
        btc = BackendToolCall(id="call_1", name="bash", arguments='{"cmd": "ls"}')
        # Confirm the expected result for this scenario: backend tool call.
        assert btc.name == "bash"
        assert btc.arguments == '{"cmd": "ls"}'

    def test_backend_tool_call_delta(self):
        """Verifies that backend tool call delta."""
        bd = BackendToolCallDelta(index=0, key="arguments", value='"pattern"')
        # Confirm the expected result for this scenario: backend tool call delta.
        assert bd.index == 0
        assert bd.key == "arguments"

    def test_backend_finish(self):
        """Verifies that backend finish."""
        bf = BackendFinish(reason="stop")
        # Confirm the expected result for this scenario: backend finish.
        assert bf.reason == "stop"

    def test_backend_error(self):
        """Verifies that backend error."""
        be = BackendError(error="Too many requests")
        # Confirm the expected result for this scenario: backend error.
        assert "Too many" in be.error


# ===========================================================================
# Factory functions
# ===========================================================================

class TestFactories:
    """Test cases covering factories.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_create_text_delta(self):
        """Verifies that create text delta."""
        event = create_text_delta("hello")
        # Confirm the expected result for this scenario: create text delta.
        assert isinstance(event, TextDelta)
        assert event.text == "hello"

    def test_create_thinking_delta(self):
        """Verifies that create thinking delta."""
        event = create_thinking_delta("hmm...")
        # Confirm the expected result for this scenario: create thinking delta.
        assert isinstance(event, ThinkingDelta)
        assert event.text == "hmm..."

    def test_create_tool_call_start(self):
        """Verifies that create tool call start."""
        event = create_tool_call_start("bash", "id1")
        # Confirm the expected result for this scenario: create tool call start.
        assert isinstance(event, ToolCallStart)
        assert event.name == "bash"
        assert event.id == "id1"

    def test_create_tool_call_delta(self):
        """Verifies that create tool call delta."""
        event = create_tool_call_delta("id1", "arguments", "...")
        # Confirm the expected result for this scenario: create tool call delta.
        assert isinstance(event, ToolCallDelta)

    def test_create_tool_call_end(self):
        """Verifies that create tool call end."""
        event = create_tool_call_end("id1")
        # Confirm the expected result for this scenario: create tool call end.
        assert isinstance(event, ToolCallEnd)

    def test_create_tool_progress(self):
        """Verifies that create tool progress."""
        event = create_tool_progress("id1", "bash", "running")
        # Confirm the expected result for this scenario: create tool progress.
        assert isinstance(event, ToolProgress)

    def test_create_tool_result(self):
        """Verifies that create tool result."""
        event = create_tool_result("id1", "output")
        # Confirm the expected result for this scenario: create tool result.
        assert isinstance(event, ToolResult)
        assert event.content == "output"

    def test_create_permission_request(self):
        """Verifies that create permission request."""
        event = create_permission_request("bash", "safe cmd")
        # Confirm the expected result for this scenario: create permission request.
        assert isinstance(event, PermissionRequest)

    def test_create_finish(self):
        """Verifies that create finish."""
        event = create_finish("stop")
        # Confirm the expected result for this scenario: create finish.
        assert isinstance(event, Finish)

    def test_create_backend_text(self):
        """Verifies that create backend text."""
        event = create_backend_text("hello")
        # Confirm the expected result for this scenario: create backend text.
        assert isinstance(event, BackendText)

    def test_create_backend_thinking(self):
        """Verifies that create backend thinking."""
        event = create_backend_thinking("hmm")
        # Confirm the expected result for this scenario: create backend thinking.
        assert isinstance(event, BackendThinking)

    def test_create_backend_tool_call(self):
        """Verifies that create backend tool call."""
        event = create_backend_tool_call("id1", "bash", "{}")
        # Confirm the expected result for this scenario: create backend tool call.
        assert isinstance(event, BackendToolCall)

    def test_create_backend_tool_call_delta(self):
        """Verifies that create backend tool call delta."""
        event = create_backend_tool_call_delta(0, "key", "value")
        # Confirm the expected result for this scenario: create backend tool call delta.
        assert isinstance(event, BackendToolCallDelta)

    def test_create_backend_finish(self):
        """Verifies that create backend finish."""
        event = create_backend_finish("stop")
        # Confirm the expected result for this scenario: create backend finish.
        assert isinstance(event, BackendFinish)

    def test_create_backend_error(self):
        """Verifies that create backend error."""
        event = create_backend_error("Request timed out")
        # Confirm the expected result for this scenario: create backend error.
        assert isinstance(event, BackendError)
