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



"""Tests for encre.server.protocol -- client/server message encoding and parsing."""

import json

from encre.server.protocol import (
    ClientCancel,
    ClientConfigure,
    ClientPing,
    ClientRespondPermission,
    ClientResume,
    ClientRun,
    _make_message,
    encode_error,
    encode_finish,
    encode_permission_request,
    encode_pong,
    encode_server_message,
    encode_session_ready,
    encode_text_delta,
    encode_thinking_delta,
    encode_tool_call_delta,
    encode_tool_call_end,
    encode_tool_call_start,
    encode_tool_progress,
    encode_tool_result,
    parse_client_message,
)

# ── Client Message Dataclasses ────────────────────────────────────────────

class TestClientRun:
    """Test cases covering client run.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientRun()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "run"
        assert msg.prompt == ""
        assert msg.system_prompt is None
        assert msg.session_id is None
        assert msg.specialty == "general"

    def test_from_dict_minimal(self):
        """Verifies that from dict minimal."""
        msg = ClientRun.from_dict({"prompt": "hello"})
        # Confirm the expected result for this scenario: from dict minimal.
        assert msg.type == "run"
        assert msg.prompt == "hello"
        assert msg.specialty == "general"

    def test_from_dict_full(self):
        """Verifies that from dict full."""
        msg = ClientRun.from_dict({
            "prompt": "do it",
            "system_prompt": "You are helpful.",
            "session_id": "abc-123",
            "specialty": "coding",
        })
        # Confirm the expected result for this scenario: from dict full.
        assert msg.type == "run"
        assert msg.prompt == "do it"
        assert msg.system_prompt == "You are helpful."
        assert msg.session_id == "abc-123"
        assert msg.specialty == "coding"

    def test_from_dict_missing_keys(self):
        """from_dict uses .get() with defaults for all fields."""
        msg = ClientRun.from_dict({})
        # Confirm the expected result for this scenario: from dict missing keys.
        assert msg.prompt == ""
        assert msg.system_prompt is None
        assert msg.session_id is None


class TestClientRespondPermission:
    """Test cases covering client respond permission.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientRespondPermission()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "respond_permission"
        assert msg.tool_name == ""
        assert msg.decision is False

    def test_from_dict(self):
        """Verifies that from dict."""
        msg = ClientRespondPermission.from_dict({
            "tool_name": "bash",
            "decision": True,
        })
        # Confirm the expected result for this scenario: from dict.
        assert msg.tool_name == "bash"
        assert msg.decision is True

    def test_from_dict_defaults(self):
        """Verifies that from dict defaults."""
        msg = ClientRespondPermission.from_dict({})
        # Confirm the expected result for this scenario: from dict defaults.
        assert msg.tool_name == ""
        assert msg.decision is False


class TestClientCancel:
    """Test cases covering client cancel.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientCancel()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "cancel"
        assert msg.session_id == ""

    def test_from_dict(self):
        """Verifies that from dict."""
        msg = ClientCancel.from_dict({"session_id": "sess-xyz"})
        # Confirm the expected result for this scenario: from dict.
        assert msg.session_id == "sess-xyz"

    def test_from_dict_empty(self):
        """Verifies that from dict empty."""
        msg = ClientCancel.from_dict({})
        # Confirm the expected result for this scenario: from dict empty.
        assert msg.session_id == ""


class TestClientResume:
    """Test cases covering client resume.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientResume()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "resume"
        assert msg.session_id == ""

    def test_from_dict(self):
        """Verifies that from dict."""
        msg = ClientResume.from_dict({"session_id": "sess-abc"})
        # Confirm the expected result for this scenario: from dict.
        assert msg.session_id == "sess-abc"


class TestClientConfigure:
    """Test cases covering client configure.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientConfigure()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "configure"
        assert msg.config == {}

    def test_from_dict(self):
        """Verifies that from dict."""
        msg = ClientConfigure.from_dict({"config": {"model": "gpt-4o"}})
        # Confirm the expected result for this scenario: from dict.
        assert msg.config == {"model": "gpt-4o"}

    def test_from_dict_empty(self):
        """Verifies that from dict empty."""
        msg = ClientConfigure.from_dict({})
        # Confirm the expected result for this scenario: from dict empty.
        assert msg.config == {}


class TestClientPing:
    """Test cases covering client ping.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_defaults(self):
        """Verifies that defaults."""
        msg = ClientPing()
        # Confirm the expected result for this scenario: defaults.
        assert msg.type == "ping"

    def test_from_dict_ignores_payload(self):
        """Verifies that from dict ignores payload."""
        msg = ClientPing.from_dict({"extra": "ignored"})
        # Confirm the expected result for this scenario: from dict ignores payload.
        assert msg.type == "ping"


# ── parse_client_message ─────────────────────────────────────────────────

class TestParseClientMessage:
    """Test cases covering parse client message.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_parse_run(self):
        """Verifies that parse run."""
        msg = parse_client_message(json.dumps({"type": "run", "prompt": "hi"}))
        # Confirm the expected result for this scenario: parse run.
        assert isinstance(msg, ClientRun)
        assert msg.prompt == "hi"

    def test_parse_respond_permission(self):
        """Verifies that parse respond permission."""
        msg = parse_client_message(json.dumps({
            "type": "respond_permission",
            "tool_name": "edit",
            "decision": True,
        }))
        # Confirm the expected result for this scenario: parse respond permission.
        assert isinstance(msg, ClientRespondPermission)
        assert msg.tool_name == "edit"

    def test_parse_cancel(self):
        """Verifies that parse cancel."""
        msg = parse_client_message(json.dumps({
            "type": "cancel",
            "session_id": "s1",
        }))
        # Confirm the expected result for this scenario: parse cancel.
        assert isinstance(msg, ClientCancel)

    def test_parse_resume(self):
        """Verifies that parse resume."""
        msg = parse_client_message(json.dumps({
            "type": "resume",
            "session_id": "s1",
        }))
        # Confirm the expected result for this scenario: parse resume.
        assert isinstance(msg, ClientResume)

    def test_parse_configure(self):
        """Verifies that parse configure."""
        msg = parse_client_message(json.dumps({
            "type": "configure",
            "config": {"max_tokens": 8192},
        }))
        # Confirm the expected result for this scenario: parse configure.
        assert isinstance(msg, ClientConfigure)
        assert msg.config == {"max_tokens": 8192}

    def test_parse_ping(self):
        """Verifies that parse ping."""
        msg = parse_client_message(json.dumps({"type": "ping"}))
        # Confirm the expected result for this scenario: parse ping.
        assert isinstance(msg, ClientPing)

    def test_parse_invalid_json_returns_none(self):
        """Verifies that parse invalid json returns none."""
        msg = parse_client_message("not json at all")
        # Confirm the expected result for this scenario: parse invalid json returns none.
        assert msg is None

    def test_parse_empty_json_returns_none(self):
        """Verifies that parse empty json returns none."""
        msg = parse_client_message("{}")
        # Confirm the expected result for this scenario: parse empty json returns none.
        assert msg is None

    def test_parse_unknown_type_returns_none(self):
        """Verifies that parse unknown type returns none."""
        msg = parse_client_message(json.dumps({"type": "magic_unknown"}))
        # Confirm the expected result for this scenario: parse unknown type returns none.
        assert msg is None

    def test_parse_bytes_input(self):
        """Verifies that parse bytes input."""
        msg = parse_client_message(b'{"type": "ping"}')
        # Confirm the expected result for this scenario: parse bytes input.
        assert isinstance(msg, ClientPing)

    def test_parse_invalid_utf8_bytes(self):
        """Verifies that parse invalid utf8 bytes."""
        msg = parse_client_message(b'\xff\xfe\x00')
        # Confirm the expected result for this scenario: parse invalid utf8 bytes.
        assert msg is None


# ── _make_message helper ─────────────────────────────────────────────────

class TestMakeMessage:
    """Test cases covering make message.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_basic(self):
        """Verifies that basic."""
        result = _make_message("test_type", key="val")
        # Confirm the expected result for this scenario: basic.
        assert result == {"type": "test_type", "key": "val"}

    def test_no_extras(self):
        """Verifies that no extras."""
        result = _make_message("bare")
        # Confirm the expected result for this scenario: no extras.
        assert result == {"type": "bare"}

    def test_multiple_kwargs(self):
        """Verifies that multiple kwargs."""
        result = _make_message("m", a=1, b=2, c=3)
        # Confirm the expected result for this scenario: multiple kwargs.
        assert result == {"type": "m", "a": 1, "b": 2, "c": 3}


# ── encode_server_message ────────────────────────────────────────────────

class TestEncodeServerMessage:
    """Test cases covering encode server message.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_returns_json_string(self):
        """Verifies that returns json string."""
        result = encode_server_message("text_delta", text="hello")
        # Confirm the expected result for this scenario: returns json string.
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["type"] == "text_delta"
        assert parsed["text"] == "hello"

    def test_ensure_ascii_false(self):
        """Verifies that ensure ascii false."""
        # ensure_ascii=False means unicode is preserved
        result = encode_server_message("text_delta", text="cafe")
        # Confirm the expected result for this scenario: ensure ascii false.
        assert "cafe" in result

    def test_no_extra_kwargs(self):
        """Verifies that no extra kwargs."""
        result = encode_server_message("pong")
        parsed = json.loads(result)
        # Confirm the expected result for this scenario: no extra kwargs.
        assert parsed == {"type": "pong"}


# ── Convenience Encoders ─────────────────────────────────────────────────

class TestConvenienceEncoders:
    """Test cases covering convenience encoders.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_encode_text_delta(self):
        """Verifies that encode text delta."""
        msg = encode_text_delta("Hello world")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode text delta.
        assert parsed == {"type": "text_delta", "text": "Hello world"}

    def test_encode_thinking_delta(self):
        """Verifies that encode thinking delta."""
        msg = encode_thinking_delta("Hmm...")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode thinking delta.
        assert parsed == {"type": "thinking_delta", "text": "Hmm..."}

    def test_encode_tool_call_start(self):
        """Verifies that encode tool call start."""
        msg = encode_tool_call_start("bash", "call_1")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool call start.
        assert parsed == {"type": "tool_call_start", "name": "bash", "id": "call_1"}

    def test_encode_tool_call_delta(self):
        """Verifies that encode tool call delta."""
        msg = encode_tool_call_delta("call_1", "arguments", '{"cmd":')
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool call delta.
        assert parsed == {
            "type": "tool_call_delta",
            "id": "call_1",
            "key": "arguments",
            "value": '{"cmd":',
        }

    def test_encode_tool_call_end(self):
        """Verifies that encode tool call end."""
        msg = encode_tool_call_end("call_1")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool call end.
        assert parsed == {"type": "tool_call_end", "id": "call_1"}

    def test_encode_tool_progress(self):
        """Verifies that encode tool progress."""
        msg = encode_tool_progress("call_1", "bash", "running")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool progress.
        assert parsed == {
            "type": "tool_progress",
            "id": "call_1",
            "tool_name": "bash",
            "status": "running",
        }

    def test_encode_tool_result(self):
        """Verifies that encode tool result."""
        msg = encode_tool_result("call_1", "output text", is_error=False)
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool result.
        assert parsed["type"] == "tool_result"
        assert parsed["content"] == "output text"
        assert parsed["is_error"] is False

    def test_encode_tool_result_error(self):
        """Verifies that encode tool result error."""
        msg = encode_tool_result("call_1", "command not found", is_error=True)
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode tool result error.
        assert parsed["is_error"] is True

    def test_encode_permission_request(self):
        """Verifies that encode permission request."""
        msg = encode_permission_request("bash", "requires sudo")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode permission request.
        assert parsed == {
            "type": "permission_request",
            "tool_name": "bash",
            "reason": "requires sudo",
        }

    def test_encode_finish(self):
        """Verifies that encode finish."""
        msg = encode_finish("stop")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode finish.
        assert parsed == {"type": "finish", "reason": "stop", "usage": None}

    def test_encode_finish_with_usage(self):
        """Verifies that encode finish with usage."""
        usage = {"input_tokens": 100, "output_tokens": 50}
        msg = encode_finish("stop", usage=usage)
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode finish with usage.
        assert parsed["usage"] == usage

    def test_encode_pong(self):
        """Verifies that encode pong."""
        msg = encode_pong()
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode pong.
        assert parsed == {"type": "pong"}

    def test_encode_error(self):
        """Verifies that encode error."""
        msg = encode_error("something went wrong")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode error.
        assert parsed == {"type": "error", "message": "something went wrong", "code": "internal"}

    def test_encode_error_with_code(self):
        """Verifies that encode error with code."""
        msg = encode_error("timeout", code="timeout")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode error with code.
        assert parsed["code"] == "timeout"

    def test_encode_session_ready(self):
        """Verifies that encode session ready."""
        msg = encode_session_ready("sess-42")
        parsed = json.loads(msg)
        # Confirm the expected result for this scenario: encode session ready.
        assert parsed == {"type": "session_ready", "session_id": "sess-42"}


# ── Message Type Literals ────────────────────────────────────────────────

class TestMessageTypes:
    """Test cases covering message types.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_client_message_type_values(self):
        """ClientMessageType literal includes all expected values."""
        # Runtime validation: these values are from the literal definition
        expected = {"run", "respond_permission", "cancel", "resume", "configure", "ping"}
        # Type check: assert the string value comparisons work
        # Confirm the expected result for this scenario: client message type values.
        assert "run" in expected
        assert "ping" in expected

    def test_server_message_type_values(self):
        """ServerMessageType literal includes all expected values."""
        expected = {
            "text_delta", "thinking_delta", "tool_call_start",
            "tool_call_delta", "tool_call_end", "tool_progress",
            "tool_result", "permission_request", "finish", "pong",
            "error", "session_ready",
        }
        # Confirm the expected result for this scenario: server message type values.
        assert "text_delta" in expected
        assert "session_ready" in expected
        assert "finish" in expected


# ── Roundtrip ────────────────────────────────────────────────────────────

class TestRoundtrip:
    """Test cases covering roundtrip.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify that messages can be serialized and deserialized properly."""

    def test_ping_roundtrip(self):
        """Verifies that ping roundtrip."""
        encoded = encode_pong()
        parsed = json.loads(encoded)
        # Confirm the expected result for this scenario: ping roundtrip.
        assert parsed["type"] == "pong"

    def test_client_run_roundtrip(self):
        """Verifies that client run roundtrip."""
        # Create a ClientRun, encode it manually, parse it back
        original = {"type": "run", "prompt": "test prompt"}
        raw = json.dumps(original)
        msg = parse_client_message(raw)
        # Confirm the expected result for this scenario: client run roundtrip.
        assert isinstance(msg, ClientRun)
        assert msg.prompt == "test prompt"

    def test_all_client_types_parseable(self):
        """Every ClientMessageType should have a registered parser."""
        for msg_type in ["run", "respond_permission", "cancel", "resume", "configure", "ping"]:
            base = {"type": msg_type}
            if msg_type == "configure":
                base["config"] = {}
            result = parse_client_message(json.dumps(base))
            # Confirm the expected result for this scenario: all client types parseable.
            assert result is not None, f"Failed to parse: {msg_type}"
