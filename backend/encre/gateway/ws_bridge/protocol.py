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

"""Encre channel-adapter gateway: wire protocol.

Defines the :class:`GatewayOp` operation enum and the :class:`GatewayMessage`
container used on the wire between
:class:`encre.gateway.ws_bridge.server.WsBridgeServer` and
:class:`encre.gateway.ws_bridge.client.GatewayClient`. Messages are JSON objects
of the shape ``{"op": <str>, "d": <dict>, "seq": <int>}`` -- ``op`` is the
operation code, ``d`` carries operation-specific payload data, and ``seq`` is a
monotonic send counter used for diagnostics.

The module provides:
    * :class:`GatewayOp` -- the full set of opcodes understood by both ends.
    * :class:`GatewayMessage` -- a dataclass plus a family of static factory
      constructors (``hello``, ``submit``, ``text_delta``, ``finish`` ...) that
      build typed messages, and ``to_dict`` / ``from_dict`` for
      (de)serialization.

Both the client and the server import this single definition so the two sides
can never disagree on the wire format.
"""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any


class GatewayOp(enum.Enum):
    """Operation codes for the gateway wire protocol.

    Each value is the wire string written into the ``op`` field of a
    :class:`GatewayMessage`. The set covers connection lifecycle (HELLO,
    HEARTBEAT, HEARTBEAT_ACK), request flow (SUBMIT, SUBMIT_STREAM), streaming
    payloads (TEXT_DELTA, TOOL_RESULT, FINISH, ERROR), adapter metadata
    (ADAPTER_INFO, ADAPTER_UPDATE), and control (CANCEL, SHUTDOWN).
    """

    HELLO = "hello"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    SUBMIT = "submit"
    SUBMIT_STREAM = "submit_stream"
    TEXT_DELTA = "text_delta"
    TOOL_RESULT = "tool_result"
    FINISH = "finish"
    ERROR = "error"
    ADAPTER_INFO = "adapter_info"
    ADAPTER_UPDATE = "adapter_update"
    CANCEL = "cancel"
    SHUTDOWN = "shutdown"


@dataclass
class GatewayMessage:
    """A single envelope exchanged over the gateway WebSocket.

    Attributes:
        op: The :class:`GatewayOp` describing what this message means.
        data: Operation-specific payload. The exact keys depend on ``op`` (see
            the individual factory constructors for the contract of each).
        seq: A monotonic send-sequence number assigned by the sender; used for
            logging/debugging, not for routing.
    """

    op: GatewayOp
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to its wire dictionary form.

        Returns:
            A ``{"op": <str>, "d": <dict>, "seq": <int>}`` mapping ready to be
            JSON-encoded.
        """
        return {
            "op": self.op.value,
            "d": self.data,
            "seq": self.seq,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GatewayMessage":
        """Reconstruct a :class:`GatewayMessage` from a decoded wire dict.

        Args:
            raw: The parsed JSON object (must contain at least an ``op`` key).

        Returns:
            The reconstructed message. ``op`` is resolved from the ``op`` string
            via the :class:`GatewayOp` enum; unknown values raise ``ValueError``.

        Raises:
            ValueError: If ``raw["op"]`` is not a known :class:`GatewayOp`.
        """
        return cls(
            op=GatewayOp(raw.get("op", "")),
            data=raw.get("d", {}),
            seq=raw.get("seq", 0),
        )

    @staticmethod
    def hello(adapter_name: str) -> "GatewayMessage":
        """Build a HELLO message announcing an adapter by ``adapter_name``.

        Args:
            adapter_name: The identifier of the connecting adapter.

        Returns:
            A HELLO ``GatewayMessage`` carrying ``{"name": adapter_name}``.
        """
        return GatewayMessage(op=GatewayOp.HELLO, data={"name": adapter_name})

    @staticmethod
    def heartbeat() -> "GatewayMessage":
        """Build an empty HEARTBEAT ping message.

        Returns:
            A HEARTBEAT ``GatewayMessage`` with no payload.
        """
        return GatewayMessage(op=GatewayOp.HEARTBEAT)

    @staticmethod
    def heartbeat_ack() -> "GatewayMessage":
        """Build a HEARTBEAT_ACK acknowledging a received ping.

        Returns:
            A HEARTBEAT_ACK ``GatewayMessage`` with no payload.
        """
        return GatewayMessage(op=GatewayOp.HEARTBEAT_ACK)

    @staticmethod
    def submit(
        prompt: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
        source: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> "GatewayMessage":
        """Build a SUBMIT message for a one-shot (non-streaming) request.

        Args:
            prompt: The user prompt to send.
            session_id: Optional conversation session id, added when present.
            system_prompt: Optional system prompt override, added when present.
            source: Optional origin metadata, added when present.
            request_id: Optional caller-supplied id; a random one is generated
                when omitted (used to correlate the reply).

        Returns:
            A SUBMIT ``GatewayMessage`` with a ``request_id`` and any provided
            optional fields.
        """
        d: dict[str, Any] = {"prompt": prompt}
        d["request_id"] = request_id or uuid.uuid4().hex
        if session_id:
            d["session_id"] = session_id
        if system_prompt:
            d["system_prompt"] = system_prompt
        if source:
            d["source"] = source
        return GatewayMessage(op=GatewayOp.SUBMIT, data=d)

    @staticmethod
    def submit_stream(
        prompt: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
        source: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> "GatewayMessage":
        """Build a SUBMIT_STREAM message requesting a streamed reply.

        Same contract as :meth:`submit` but the server is expected to stream
        ``TEXT_DELTA`` / ``TOOL_RESULT`` messages back under the same
        ``request_id`` until a terminal ``FINISH`` or ``ERROR``.

        Args:
            prompt: The user prompt to send.
            session_id: Optional conversation session id, added when present.
            system_prompt: Optional system prompt override, added when present.
            source: Optional origin metadata, added when present.
            request_id: Optional caller-supplied id; a random one is generated
                when omitted.

        Returns:
            A SUBMIT_STREAM ``GatewayMessage`` with a ``request_id`` and any
            provided optional fields.
        """
        d: dict[str, Any] = {"prompt": prompt}
        d["request_id"] = request_id or uuid.uuid4().hex
        if session_id:
            d["session_id"] = session_id
        if system_prompt:
            d["system_prompt"] = system_prompt
        if source:
            d["source"] = source
        return GatewayMessage(op=GatewayOp.SUBMIT_STREAM, data=d)

    @staticmethod
    def text_delta(text: str, msg_id: str = "", session_id: str = "", request_id: str = "") -> "GatewayMessage":
        """Build a TEXT_DELTA message carrying an incremental text fragment.

        Args:
            text: The incremental assistant text fragment.
            msg_id: Optional message id this delta belongs to.
            session_id: Optional session id, added when present.
            request_id: Optional request id linking to the originating submit.

        Returns:
            A TEXT_DELTA ``GatewayMessage`` with ``text`` and ``id`` plus any
            provided optional fields.
        """
        d: dict[str, Any] = {"text": text, "id": msg_id}
        if session_id:
            d["session_id"] = session_id
        if request_id:
            d["request_id"] = request_id
        return GatewayMessage(op=GatewayOp.TEXT_DELTA, data=d)

    @staticmethod
    def tool_result(tool_id: str, content: str, is_error: bool = False, request_id: str = "") -> "GatewayMessage":
        """Build a TOOL_RESULT message reporting a tool's output.

        Args:
            tool_id: The identifier of the finished tool call.
            content: The textual result returned by the tool.
            is_error: True if the tool failed / returned an error result.
            request_id: Optional request id linking to the originating submit.

        Returns:
            A TOOL_RESULT ``GatewayMessage`` with ``id``, ``content`` and
            ``is_error`` (plus ``request_id`` when provided).
        """
        d = {"id": tool_id, "content": content, "is_error": is_error}
        if request_id:
            d["request_id"] = request_id
        return GatewayMessage(op=GatewayOp.TOOL_RESULT, data=d)

    @staticmethod
    def finish(reason: str = "done", usage: dict[str, Any] | None = None, error: str = "", request_id: str = "") -> "GatewayMessage":
        """Build a terminal FINISH message ending a request/turn.

        Args:
            reason: A short completion reason (e.g. ``"done"``, ``"error"``).
            usage: Optional token-usage statistics dict, added when present.
            error: Optional error detail; present when the turn failed.
            request_id: Optional request id linking to the originating submit.

        Returns:
            A FINISH ``GatewayMessage`` carrying ``reason`` and any provided
            optional fields.
        """
        d: dict[str, Any] = {"reason": reason}
        if usage:
            d["usage"] = usage
        if error:
            d["error"] = error
        if request_id:
            d["request_id"] = request_id
        return GatewayMessage(op=GatewayOp.FINISH, data=d)

    @staticmethod
    def error(message: str, request_id: str = "") -> "GatewayMessage":
        """Build an ERROR message describing a failure.

        Args:
            message: A human-readable error description.
            request_id: Optional request id linking to the originating submit.

        Returns:
            An ERROR ``GatewayMessage`` with ``message`` (and ``request_id`` when
            provided).
        """
        d = {"message": message}
        if request_id:
            d["request_id"] = request_id
        return GatewayMessage(op=GatewayOp.ERROR, data=d)

    @staticmethod
    def adapter_info(name: str, status: str, capabilities: list[str] | None = None) -> "GatewayMessage":
        """Build an ADAPTER_INFO message describing an adapter's state.

        Args:
            name: The adapter identifier.
            status: A status string (e.g. ``"online"``, ``"offline"``).
            capabilities: Optional list of capability strings, added when present.

        Returns:
            An ADAPTER_INFO ``GatewayMessage`` with ``name`` and ``status`` (and
            ``capabilities`` when provided).
        """
        d: dict[str, Any] = {"name": name, "status": status}
        if capabilities:
            d["capabilities"] = capabilities
        return GatewayMessage(op=GatewayOp.ADAPTER_INFO, data=d)

    @staticmethod
    def cancel(session_id: str) -> "GatewayMessage":
        """Build a CANCEL message requesting cancellation of a session.

        Args:
            session_id: The session whose in-flight request should be cancelled.

        Returns:
            A CANCEL ``GatewayMessage`` carrying ``{"session_id": session_id}``.
        """
        return GatewayMessage(op=GatewayOp.CANCEL, data={"session_id": session_id})
