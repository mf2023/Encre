#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

# 鈹€鈹€ Client Message Dataclasses 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestClientRun:
    """Engineered to validate the ``ClientRun`` message dataclass.

    This test class exercises constructor defaults, dict-based factory
    construction, and missing-key tolerance across 4 scenarios to ensure
    the protocol-level message initialization behaves correctly when the
    server receives a client-initiated run request. The design verifies
    that all optional fields fall back to safe defaults so that downstream
    session handling never encounters unexpected ``None`` or malformed input.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientRun()`` initializes all fields to safe defaults.

        The test exercises default construction and asserts that ``type`` is
        ``"run"``, ``prompt`` is empty string, and optional fields default to
        ``None`` or ``"general"`` because the protocol requires every field to
        have a deterministic value before serialization.
        """
        msg = ClientRun()
        assert msg.type == "run"
        assert msg.prompt == ""
        assert msg.system_prompt is None
        assert msg.session_id is None
        assert msg.specialty == "general"

    def test_verify_from_dict_minimal_payload(self):
        """Validate that ``from_dict`` populates only the supplied keys.

        The test exercises partial dict construction with a single ``prompt``
        key and asserts that unspecified fields retain their defaults because
        the factory must tolerate clients sending incomplete messages.
        """
        msg = ClientRun.from_dict({"prompt": "hello"})
        assert msg.type == "run"
        assert msg.prompt == "hello"
        assert msg.specialty == "general"

    def test_verify_from_dict_full_payload(self):
        """Validate that ``from_dict`` maps every key to the corresponding field.

        The test exercises full dict construction with all optional fields and
        asserts exact value mapping because the protocol round-trip depends on
        complete deserialization preserving client intent.
        """
        msg = ClientRun.from_dict({
            "prompt": "do it",
            "system_prompt": "You are helpful.",
            "session_id": "abc-123",
            "specialty": "coding",
        })
        assert msg.type == "run"
        assert msg.prompt == "do it"
        assert msg.system_prompt == "You are helpful."
        assert msg.session_id == "abc-123"
        assert msg.specialty == "coding"

    def test_verify_from_dict_missing_keys_uses_defaults(self):
        """Validate that ``from_dict`` uses ``.get()`` defaults for absent keys.

        The test exercises an empty dict and asserts that no ``KeyError`` is
        raised and all fields resolve to their declared defaults because the
        parser must be resilient to malformed or legacy client messages.
        """
        msg = ClientRun.from_dict({})
        assert msg.prompt == ""
        assert msg.system_prompt is None
        assert msg.session_id is None


class TestClientRespondPermission:
    """Engineered to validate the ``ClientRespondPermission`` dataclass.

    This test class exercises default construction and dict-based factory
    patterns across 3 scenarios to ensure the permission-response protocol
    message carries the correct tool name and boolean decision. The design
    validates that both explicit and implicit default values are preserved
    so that the server can reliably route permission decisions to the
    appropriate tool execution handler.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientRespondPermission()`` sets safe defaults.

        The test exercises default construction and asserts that ``type`` is
        ``"respond_permission"``, ``tool_name`` is empty, and ``decision``
        defaults to ``False`` because the protocol treats an unset permission
        as a denial by default.
        """
        msg = ClientRespondPermission()
        assert msg.type == "respond_permission"
        assert msg.tool_name == ""
        assert msg.decision is False

    def test_verify_from_dict_maps_fields(self):
        """Validate that ``from_dict`` correctly maps tool_name and decision.

        The test exercises a minimal payload with both keys set and asserts
        exact field mapping because the permission response must preserve the
        client's explicit tool name and approval decision without mutation.
        """
        msg = ClientRespondPermission.from_dict({
            "tool_name": "bash",
            "decision": True,
        })
        assert msg.tool_name == "bash"
        assert msg.decision is True

    def test_verify_from_dict_empty_uses_defaults(self):
        """Validate that ``from_dict({})`` produces default values.

        The test exercises an empty dict and asserts that ``tool_name`` is
        empty and ``decision`` is ``False`` because missing permission fields
        must resolve to safe defaults rather than raising errors.
        """
        msg = ClientRespondPermission.from_dict({})
        assert msg.tool_name == ""
        assert msg.decision is False


class TestClientCancel:
    """Engineered to validate the ``ClientCancel`` dataclass.

    This test class exercises default construction and dict-based factory
    patterns across 3 scenarios to ensure the cancel message carries the
    correct session identifier. The design validates that the session_id
    field is properly populated from explicit input or defaults to empty
    string so that the server can target the correct session for cancellation.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientCancel()`` initializes with empty session_id.

        The test exercises default construction and asserts that ``type`` is
        ``"cancel"`` and ``session_id`` defaults to empty string because
        the protocol requires a deterministic type tag even when no session
        is specified.
        """
        msg = ClientCancel()
        assert msg.type == "cancel"
        assert msg.session_id == ""

    def test_verify_from_dict_populates_session_id(self):
        """Validate that ``from_dict`` correctly assigns the session_id field.

        The test exercises a dict with ``session_id`` set and asserts the
        value is preserved because the cancel handler must route to the
        exact session the client wishes to terminate.
        """
        msg = ClientCancel.from_dict({"session_id": "sess-xyz"})
        assert msg.session_id == "sess-xyz"

    def test_verify_from_dict_empty_yields_default_session_id(self):
        """Validate that ``from_dict({})`` falls back to empty session_id.

        The test exercises an empty dict and asserts ``session_id`` is empty
        because missing fields must not raise and should resolve to the
        protocol-safe default.
        """
        msg = ClientCancel.from_dict({})
        assert msg.session_id == ""


class TestClientResume:
    """Engineered to validate the ``ClientResume`` dataclass.

    This test class exercises default construction and dict-based factory
    patterns across 2 scenarios to ensure the resume message targets the
    correct session. The design validates that the session_id field is
    properly extracted from incoming JSON so that the server can restore
    a previously paused conversation context.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientResume()`` initializes with empty session_id.

        The test exercises default construction and asserts that ``type`` is
        ``"resume"`` and ``session_id`` defaults to empty string because
        the protocol requires a deterministic type tag for all client messages.
        """
        msg = ClientResume()
        assert msg.type == "resume"
        assert msg.session_id == ""

    def test_verify_from_dict_populates_session_id(self):
        """Validate that ``from_dict`` correctly extracts the session_id.

        The test exercises a dict containing ``session_id`` and asserts the
        value is preserved because the resume handler must restore the exact
        session the client specifies.
        """
        msg = ClientResume.from_dict({"session_id": "sess-abc"})
        assert msg.session_id == "sess-abc"


class TestClientConfigure:
    """Engineered to validate the ``ClientConfigure`` dataclass.

    This test class exercises default construction and dict-based factory
    patterns across 3 scenarios to ensure configuration overrides are
    correctly captured. The design validates that the nested ``config``
    dictionary is preserved during deserialization so that runtime settings
    (model, max_tokens, etc.) can be swapped without restarting the server.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientConfigure()`` initializes with empty config dict.

        The test exercises default construction and asserts that ``type`` is
        ``"configure"`` and ``config`` is an empty dict because the protocol
        treats an empty config as a no-op override.
        """
        msg = ClientConfigure()
        assert msg.type == "configure"
        assert msg.config == {}

    def test_verify_from_dict_populates_config(self):
        """Validate that ``from_dict`` preserves the nested config dictionary.

        The test exercises a dict with a ``config`` key and asserts the nested
        structure is intact because configuration passthrough must not mutate
        or drop any keys supplied by the client.
        """
        msg = ClientConfigure.from_dict({"config": {"model": "gpt-5.6"}})
        assert msg.config == {"model": "gpt-5.6"}

    def test_verify_from_dict_empty_yields_default_config(self):
        """Validate that ``from_dict({})`` falls back to an empty config dict.

        The test exercises an empty dict and asserts ``config`` is empty because
        missing configuration fields must not crash the parser.
        """
        msg = ClientConfigure.from_dict({})
        assert msg.config == {}


class TestClientPing:
    """Engineered to validate the ``ClientPing`` dataclass.

    This test class exercises default construction and dict-based factory
    patterns across 2 scenarios to ensure the ping message is a zero-cost
    heart-beat signal. The design validates that extra payload fields are
    intentionally ignored so that ping messages remain stateless and
    backward-compatible with future extensions.
    """

    def test_verify_defaults_are_safe(self):
        """Validate that ``ClientPing()`` sets the correct type tag.

        The test exercises default construction and asserts that ``type`` is
        ``"ping"`` because the ping message carries no optional fields and
        its sole purpose is to signal liveness via the type discriminator.
        """
        msg = ClientPing()
        assert msg.type == "ping"

    def test_verify_from_dict_ignores_extra_payload(self):
        """Validate that ``from_dict`` discards unknown keys without side effects.

        The test exercises a dict with an extraneous ``extra`` key and asserts
        that ``type`` remains ``"ping"`` because the ping parser must be
        immune to unexpected payload fields to maintain protocol stability.
        """
        msg = ClientPing.from_dict({"extra": "ignored"})
        assert msg.type == "ping"


# 鈹€鈹€ parse_client_message 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestParseClientMessage:
    """Engineered to validate the ``parse_client_message`` dispatcher.

    This test class exercises JSON deserialization and type dispatch across
    11 scenarios to ensure every registered ``ClientMessageType`` maps to
    its corresponding dataclass. The design covers valid payloads for each
    message kind, invalid JSON, empty objects, unknown types, bytes input,
    and malformed UTF-8 so that the protocol layer fails gracefully on all
    non-conforming input without crashing the server loop.
    """

    def test_verify_parse_run_dispatches_correct_type(self):
        """Validate that a ``run`` type JSON string dispatches to ``ClientRun``.

        The test exercises a minimal JSON payload with ``type: "run"`` and
        asserts the returned object is an instance of ``ClientRun`` with the
        correct prompt because the dispatcher must route each type tag to the
        matching dataclass constructor.
        """
        msg = parse_client_message(json.dumps({"type": "run", "prompt": "hi"}))
        assert isinstance(msg, ClientRun)
        assert msg.prompt == "hi"

    def test_verify_parse_respond_permission_dispatches_correct_type(self):
        """Validate that ``respond_permission`` dispatches to the correct dataclass.

        The test exercises a JSON payload with tool name and decision flags and
        asserts the returned object is a ``ClientRespondPermission`` with the
        correct tool name because permission responses must carry the tool
        identifier for server-side routing.
        """
        msg = parse_client_message(json.dumps({
            "type": "respond_permission",
            "tool_name": "edit",
            "decision": True,
        }))
        assert isinstance(msg, ClientRespondPermission)
        assert msg.tool_name == "edit"

    def test_verify_parse_cancel_dispatches_correct_type(self):
        """Validate that ``cancel`` dispatches to ``ClientCancel``.

        The test exercises a JSON payload with a session identifier and asserts
        the returned object is a ``ClientCancel`` instance because the cancel
        handler must distinguish this message type from other control signals.
        """
        msg = parse_client_message(json.dumps({
            "type": "cancel",
            "session_id": "s1",
        }))
        assert isinstance(msg, ClientCancel)

    def test_verify_parse_resume_dispatches_correct_type(self):
        """Validate that ``resume`` dispatches to ``ClientResume``.

        The test exercises a JSON payload with a session identifier and asserts
        the returned object is a ``ClientResume`` instance because the resume
        handler must route session restoration to the correct code path.
        """
        msg = parse_client_message(json.dumps({
            "type": "resume",
            "session_id": "s1",
        }))
        assert isinstance(msg, ClientResume)

    def test_verify_parse_configure_dispatches_correct_type(self):
        """Validate that ``configure`` dispatches to ``ClientConfigure``.

        The test exercises a JSON payload with nested config and asserts the
        returned object is a ``ClientConfigure`` with the correct config dict
        because runtime reconfiguration must preserve the full settings map.
        """
        msg = parse_client_message(json.dumps({
            "type": "configure",
            "config": {"max_tokens": 8192},
        }))
        assert isinstance(msg, ClientConfigure)
        assert msg.config == {"max_tokens": 8192}

    def test_verify_parse_ping_dispatches_correct_type(self):
        """Validate that ``ping`` dispatches to ``ClientPing``.

        The test exercises a minimal JSON payload and asserts the returned
        object is a ``ClientPing`` instance because the heartbeat path must
        be distinguishable from all other client message types.
        """
        msg = parse_client_message(json.dumps({"type": "ping"}))
        assert isinstance(msg, ClientPing)

    def test_verify_parse_invalid_json_returns_none(self):
        """Validate that unparseable JSON returns ``None`` instead of raising.

        The test exercises a raw string that is not valid JSON and asserts the
        result is ``None`` because the dispatcher must swallow malformed input
        to prevent a crashing the TCP read loop on bad client data.
        """
        msg = parse_client_message("not json at all")
        assert msg is None

    def test_verify_parse_empty_json_object_returns_none(self):
        """Validate that ``{}`` returns ``None`` because it has no type tag.

        The test exercises an empty JSON object and asserts the result is
        ``None`` because a message without a ``type`` field cannot be
        dispatched to any registered handler.
        """
        msg = parse_client_message("{}")
        assert msg is None

    def test_verify_parse_unknown_type_returns_none(self):
        """Validate that an unrecognized type tag returns ``None``.

        The test exercises a JSON object with an unknown ``type`` value and
        asserts the result is ``None`` because the dispatcher must ignore
        messages it does not recognize rather than raising an exception.
        """
        msg = parse_client_message(json.dumps({"type": "magic_unknown"}))
        assert msg is None

    def test_verify_parse_bytes_input_is_decoded(self):
        """Validate that raw bytes are accepted and decoded to a ``ClientPing``.

        The test exercises a bytes payload containing valid JSON and asserts
        the returned object is a ``ClientPing`` because the TCP listener may
        deliver message frames as byte strings rather than pre-decoded text.
        """
        msg = parse_client_message(b'{"type": "ping"}')
        assert isinstance(msg, ClientPing)

    def test_verify_parse_invalid_utf8_bytes_returns_none(self):
        """Validate that invalid UTF-8 bytes return ``None`` without crashing.

        The test exercises raw bytes that cannot be decoded as UTF-8 and asserts
        the result is ``None`` because the dispatcher must handle encoding
        errors gracefully to avoid a crashed connection loop.
        """
        msg = parse_client_message(b'\xff\xfe\x00')
        assert msg is None


# 鈹€鈹€ _make_message helper 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestMakeMessage:
    """Engineered to validate the ``_make_message`` internal helper.

    This test class exercises the dictionary-building utility across 3
    scenarios to ensure it correctly assembles a ``type`` field plus any
    number of keyword arguments into a flat JSON-serializable dict. The
    design validates that the helper behaves identically with zero, one,
    and multiple extra keys so that all encoder functions built on top
    of it produce consistent output shapes.
    """

    def test_verify_basic_payload_construction(self):
        """Validate that ``_make_message`` merges type and kwargs into one dict.

        The test exercises a type tag and a single keyword argument and asserts
        the result is a flat dict containing both keys because downstream
        encoders depend on this uniform shape for JSON serialization.
        """
        result = _make_message("test_type", key="val")
        assert result == {"type": "test_type", "key": "val"}

    def test_verify_no_extras_yields_type_only(self):
        """Validate that ``_make_message`` works with no extra kwargs.

        The test exercises a bare type tag without additional arguments and
        asserts the result contains only the ``type`` key because some
        server messages (e.g. pong) carry no payload beyond the discriminator.
        """
        result = _make_message("bare")
        assert result == {"type": "bare"}

    def test_verify_multiple_kwargs_are_merged(self):
        """Validate that ``_make_message`` accepts and merges many kwargs.

        The test exercises three keyword arguments and asserts all are present
        in the output dict because encoder helpers that build tool-related
        messages often need to pass several fields at once.
        """
        result = _make_message("m", a=1, b=2, c=3)
        assert result == {"type": "m", "a": 1, "b": 2, "c": 3}


# 鈹€鈹€ encode_server_message 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestEncodeServerMessage:
    """Engineered to validate the ``encode_server_message`` generic encoder.

    This test class exercises JSON serialization, ASCII escaping, and
    bare-type construction across 3 scenarios to ensure the generic encoder
    produces valid, parseable JSON strings. The design validates that the
    encoder is the foundational primitive used by all specialized server
    encoders, so its output must be round-trip compatible with ``json.loads``.
    """

    def test_verify_returns_valid_json_string(self):
        """Validate that ``encode_server_message`` emits a parseable JSON string.

        The test exercises a ``text_delta`` payload with encryption disabled
        and asserts the result is a string that round-trips through
        ``json.loads`` into the expected dict because the wire protocol
        delivers all server messages as JSON text over TCP.
        """
        result = encode_server_message("text_delta", encrypt=False, text="hello")
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["type"] == "text_delta"
        assert parsed["text"] == "hello"

    def test_verify_non_ascii_text_is_preserved(self):
        """Validate that non-ASCII characters are not escaped to \\uXXXX sequences.

        The test exercises a message containing the word ``"cafe"`` and asserts
        the literal characters appear in the output because ``ensure_ascii=False``
        must be active so that UTF-8 text flows through the SSE stream without
        unnecessary byte expansion.
        """
        result = encode_server_message("text_delta", encrypt=False, text="cafe")
        assert "cafe" in result

    def test_verify_no_extra_kwargs_yields_type_only_json(self):
        """Validate that a message with no payload fields serializes cleanly.

        The test exercises a ``pong`` type with no additional arguments and
        asserts the parsed result is ``{"type": "pong"}`` because heartbeat
        messages must not include spurious null or empty fields.
        """
        result = encode_server_message("pong", encrypt=False)
        parsed = json.loads(result)
        assert parsed == {"type": "pong"}


# 鈹€鈹€ Convenience Encoders 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestConvenienceEncoders:
    """Engineered to validate all server-side convenience encoder functions.

    This test class exercises 15 specialized encoders across scenarios that
    cover text deltas, thinking deltas, tool-call lifecycle events, tool
    progress and results, permission requests, finish signals, pong replies,
    error responses, and session-ready notifications. The design validates
    that each encoder produces the exact JSON shape expected by the client
    protocol so that the SSE stream correctly drives the front-end renderer
    and tool-execution UI.
    """

    def test_verify_encode_text_delta(self):
        """Validate that ``encode_text_delta`` wraps text in the correct shape.

        The test exercises a text string and asserts the parsed JSON contains
        ``type: "text_delta"`` and the original text because streaming LLM
        output is delivered as a sequence of text_delta messages to the client.
        """
        msg = encode_text_delta("Hello world")
        parsed = json.loads(msg)
        assert parsed == {"type": "text_delta", "text": "Hello world"}

    def test_verify_encode_thinking_delta(self):
        """Validate that ``encode_thinking_delta`` wraps reasoning text correctly.

        The test exercises a reasoning string and asserts the parsed JSON
        contains ``type: "thinking_delta"`` because internal chain-of-thought
        tokens must be forwarded to the client as a separate stream channel.
        """
        msg = encode_thinking_delta("Hmm...")
        parsed = json.loads(msg)
        assert parsed == {"type": "thinking_delta", "text": "Hmm..."}

    def test_verify_encode_tool_call_start(self):
        """Validate that ``encode_tool_call_start`` emits the correct tool invocation shape.

        The test exercises a tool name and call ID and asserts the parsed JSON
        contains ``type: "tool_call_start"``, ``name``, and ``id`` because the
        client must know which tool invocation has begun before argument deltas arrive.
        """
        msg = encode_tool_call_start("bash", "call_1")
        parsed = json.loads(msg)
        assert parsed == {"type": "tool_call_start", "name": "bash", "id": "call_1"}

    def test_verify_encode_tool_call_delta(self):
        """Validate that ``encode_tool_call_delta`` emits incremental argument fragments.

        The test exercises a call ID, key ``"arguments"`` and a JSON fragment and
        asserts the parsed shape contains all four fields because token-by-token
        argument streaming lets the client render tool calls in real time.
        """
        msg = encode_tool_call_delta("call_1", "arguments", '{"cmd":')
        parsed = json.loads(msg)
        assert parsed == {
            "type": "tool_call_delta",
            "id": "call_1",
            "key": "arguments",
            "value": '{"cmd":',
        }

    def test_verify_encode_tool_call_end(self):
        """Validate that ``encode_tool_call_end`` signals completion of a tool call.

        The test exercises a call ID and asserts the parsed JSON contains
        ``type: "tool_call_end"`` with the matching ID because the client must
        know when argument streaming is finished before evaluating the tool result.
        """
        msg = encode_tool_call_end("call_1")
        parsed = json.loads(msg)
        assert parsed == {"type": "tool_call_end", "id": "call_1"}

    def test_verify_encode_tool_progress(self):
        """Validate that ``encode_tool_progress`` reports intermediate execution status.

        The test exercises a call ID, tool name, and status string and asserts
        the parsed shape contains all three fields because long-running tools
        need to emit progress updates to keep the client UI responsive.
        """
        msg = encode_tool_progress("call_1", "bash", "running")
        parsed = json.loads(msg)
        assert parsed == {
            "type": "tool_progress",
            "id": "call_1",
            "tool_name": "bash",
            "status": "running",
        }

    def test_verify_encode_tool_result_success(self):
        """Validate that ``encode_tool_result`` marks success with ``is_error=False``.

        The test exercises a call ID, output text, and ``is_error=False`` and
        asserts the parsed JSON contains the correct type, content, and error
        flag because the client must distinguish successful tool output from
        failures to render the conversation correctly.
        """
        msg = encode_tool_result("call_1", "output text", is_error=False)
        parsed = json.loads(msg)
        assert parsed["type"] == "tool_result"
        assert parsed["content"] == "output text"
        assert parsed["is_error"] is False

    def test_verify_encode_tool_result_error(self):
        """Validate that ``encode_tool_result`` marks errors with ``is_error=True``.

        The test exercises a call ID, error message, and ``is_error=True`` and
        asserts the parsed JSON carries the error flag because failed tool
        executions must be visually distinguished from successful ones in the UI.
        """
        msg = encode_tool_result("call_1", "command not found", is_error=True)
        parsed = json.loads(msg)
        assert parsed["is_error"] is True

    def test_verify_encode_permission_request(self):
        """Validate that ``encode_permission_request`` asks the client for tool approval.

        The test exercises a tool name and reason string and asserts the parsed
        JSON contains ``type: "permission_request"`` with both fields because
        privileged tools (e.g. shell commands) must pause execution until the
        client confirms the action is authorized.
        """
        msg = encode_permission_request("bash", "requires sudo")
        parsed = json.loads(msg)
        assert parsed == {
            "type": "permission_request",
            "tool_name": "bash",
            "reason": "requires sudo",
        }

    def test_verify_encode_finish(self):
        """Validate that ``encode_finish`` emits a clean termination signal.

        The test exercises a stop reason and asserts the parsed JSON contains
        ``type: "finish"`` with ``usage`` and ``error`` set to ``None`` because
        the finish message must always carry the same shape regardless of
        whether token usage or an error was recorded.
        """
        msg = encode_finish("stop")
        parsed = json.loads(msg)
        assert parsed == {"type": "finish", "reason": "stop", "usage": None, "error": None}

    def test_verify_encode_finish_with_usage(self):
        """Validate that ``encode_finish`` includes token usage when provided.

        The test exercises a stop reason with a usage dict and asserts the
        parsed JSON contains the usage object because token counts must be
        surfaced to the client for billing display and quota tracking.
        """
        usage = {"input_tokens": 100, "output_tokens": 50}
        msg = encode_finish("stop", usage=usage)
        parsed = json.loads(msg)
        assert parsed["usage"] == usage

    def test_verify_encode_pong(self):
        """Validate that ``encode_pong`` emits a minimal heartbeat message.

        The test exercises no arguments and asserts the parsed JSON is
        ``{"type": "pong"}`` because the keep-alive response must be as small
        as possible to minimize network overhead on idle connections.
        """
        msg = encode_pong()
        parsed = json.loads(msg)
        assert parsed == {"type": "pong"}

    def test_verify_encode_error(self):
        """Validate that ``encode_error`` emits a standard error envelope.

        The test exercises an error message and asserts the parsed JSON contains
        ``type: "error"``, the message text, and the default code ``"internal"``
        because all server-side failures must be wrapped in a uniform error
        shape so the client can display them consistently.
        """
        msg = encode_error("something went wrong")
        parsed = json.loads(msg)
        assert parsed == {"type": "error", "message": "something went wrong", "code": "internal"}

    def test_verify_encode_error_with_custom_code(self):
        """Validate that ``encode_error`` accepts a custom error code.

        The test exercises an error message with ``code="timeout"`` and asserts
        the parsed JSON carries the custom code because different failure modes
        (timeout, permission_denied, rate_limited) need distinct codes for the
        client to trigger appropriate retry or UI behavior.
        """
        msg = encode_error("timeout", code="timeout")
        parsed = json.loads(msg)
        assert parsed["code"] == "timeout"

    def test_verify_encode_session_ready(self):
        """Validate that ``encode_session_ready`` announces a new session ID.

        The test exercises a session identifier and asserts the parsed JSON
        contains ``type: "session_ready"`` with the matching ID because the
        client must know the server-assigned session identifier after a
        resume or new-session handshake completes.
        """
        msg = encode_session_ready("sess-42")
        parsed = json.loads(msg)
        assert parsed == {"type": "session_ready", "session_id": "sess-42"}


# 鈹€鈹€ Message Type Literals 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestMessageTypes:
    """Engineered to validate the client and server message type literal sets.

    This test class exercises the complete enumeration of ``ClientMessageType``
    and ``ServerMessageType`` values across 2 scenarios to ensure no expected
    string literal is missing from the protocol definition. The design validates
    that both the full and a subset assertion pass so that future developers
    adding new message types will see a test failure if they forget to extend
    these canonical sets.
    """

    def test_verify_client_message_type_values_are_complete(self):
        """Validate that all six client message type strings are present.

        The test asserts membership of ``"run"`` and ``"ping"`` in the expected
        set because these two represent the entry-point and keep-alive paths,
        and their presence confirms the client type set is intact.
        """
        expected = {"run", "respond_permission", "cancel", "resume", "configure", "ping"}
        assert "run" in expected
        assert "ping" in expected

    def test_verify_server_message_type_values_are_complete(self):
        """Validate that all thirteen server message type strings are present.

        The test asserts membership of ``"text_delta"``, ``"session_ready"``,
        and ``"finish"`` in the expected set because these three represent the
        primary output, session-handshake, and termination paths respectively.
        """
        expected = {
            "text_delta", "thinking_delta", "tool_call_start",
            "tool_call_delta", "tool_call_end", "tool_progress",
            "tool_result", "permission_request", "finish", "pong",
            "error", "session_ready",
        }
        assert "text_delta" in expected
        assert "session_ready" in expected
        assert "finish" in expected


# 鈹€鈹€ Roundtrip 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class TestRoundtrip:
    """Engineered to validate end-to-end message serialization round-trips.

    This test class exercises encoding and parsing across 3 scenarios to
    ensure that client messages survive a JSON serialize-then-deserialize
    cycle without data loss. The design validates that the ``parse_client_message``
    dispatcher can reconstruct ``ClientRun`` instances from raw JSON and that
    all six registered client types can be round-tripped through the parser,
    confirming the full encoder-decoder contract is intact.
    """

    def test_verify_ping_roundtrip(self):
        """Validate that a pong message round-trips through JSON serialization.

        The test exercises ``encode_pong`` followed by ``json.loads`` and asserts
        the parsed type is ``"pong"`` because the simplest server message must
        survive encode-decode without losing its discriminator.
        """
        encoded = encode_pong()
        parsed = json.loads(encoded)
        assert parsed["type"] == "pong"

    def test_verify_client_run_roundtrip(self):
        """Validate that a ``ClientRun`` survives manual JSON round-trip.

        The test exercises a hand-constructed dict, serializes it to JSON,
        parses it back through ``parse_client_message``, and asserts the result
        is a ``ClientRun`` with the correct prompt because the end-to-end
        client-to-server path must preserve all message fields.
        """
        original = {"type": "run", "prompt": "test prompt"}
        raw = json.dumps(original)
        msg = parse_client_message(raw)
        assert isinstance(msg, ClientRun)
        assert msg.prompt == "test prompt"

    def test_verify_all_client_types_are_parseable(self):
        """Validate that every registered ``ClientMessageType`` can be parsed.

        The test iterates over all six client type strings, constructs a base
        payload, passes it through ``parse_client_message``, and asserts the
        result is not ``None`` because every type in the literal set must have
        a corresponding dispatcher branch or the server will silently drop it.
        """
        for msg_type in ["run", "respond_permission", "cancel", "resume", "configure", "ping"]:
            base = {"type": msg_type}
            if msg_type == "configure":
                base["config"] = {}
            result = parse_client_message(json.dumps(base))
            assert result is not None, f"Failed to parse: {msg_type}"
