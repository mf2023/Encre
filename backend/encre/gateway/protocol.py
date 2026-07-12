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
container used on the wire between :class:`encre.gateway.server.GatewayServer`
and :class:`encre.gateway.client.GatewayClient`.  Messages are JSON objects of
the shape ``{"op": <str>, "d": <dict>, "seq": <int>}``.

Helper constructors (``hello``, ``submit``, ``text_delta``, ``finish`` ...)
build typed messages; ``to_dict`` / ``from_dict`` handle (de)serialization.
"""

import enum
from dataclasses import dataclass, field
from typing import Any


class GatewayOp(enum.Enum):
    """Operation codes for the gateway wire protocol."""

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
    op: GatewayOp
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op.value,
            "d": self.data,
            "seq": self.seq,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GatewayMessage":
        return cls(
            op=GatewayOp(raw.get("op", "")),
            data=raw.get("d", {}),
            seq=raw.get("seq", 0),
        )

    @staticmethod
    def hello(adapter_name: str) -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.HELLO, data={"name": adapter_name})

    @staticmethod
    def heartbeat() -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.HEARTBEAT)

    @staticmethod
    def heartbeat_ack() -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.HEARTBEAT_ACK)

    @staticmethod
    def submit(prompt: str, session_id: str | None = None, system_prompt: str | None = None) -> "GatewayMessage":
        d: dict[str, Any] = {"prompt": prompt}
        if session_id:
            d["session_id"] = session_id
        if system_prompt:
            d["system_prompt"] = system_prompt
        return GatewayMessage(op=GatewayOp.SUBMIT, data=d)

    @staticmethod
    def submit_stream(prompt: str, session_id: str | None = None, system_prompt: str | None = None) -> "GatewayMessage":
        d: dict[str, Any] = {"prompt": prompt}
        if session_id:
            d["session_id"] = session_id
        if system_prompt:
            d["system_prompt"] = system_prompt
        return GatewayMessage(op=GatewayOp.SUBMIT_STREAM, data=d)

    @staticmethod
    def text_delta(text: str, msg_id: str = "") -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.TEXT_DELTA, data={"text": text, "id": msg_id})

    @staticmethod
    def tool_result(tool_id: str, content: str, is_error: bool = False) -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.TOOL_RESULT, data={"id": tool_id, "content": content, "is_error": is_error})

    @staticmethod
    def finish(reason: str = "done", usage: dict[str, Any] | None = None, error: str = "") -> "GatewayMessage":
        d: dict[str, Any] = {"reason": reason}
        if usage:
            d["usage"] = usage
        if error:
            d["error"] = error
        return GatewayMessage(op=GatewayOp.FINISH, data=d)

    @staticmethod
    def error(message: str) -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.ERROR, data={"message": message})

    @staticmethod
    def adapter_info(name: str, status: str, capabilities: list[str] | None = None) -> "GatewayMessage":
        d: dict[str, Any] = {"name": name, "status": status}
        if capabilities:
            d["capabilities"] = capabilities
        return GatewayMessage(op=GatewayOp.ADAPTER_INFO, data=d)

    @staticmethod
    def cancel(session_id: str) -> "GatewayMessage":
        return GatewayMessage(op=GatewayOp.CANCEL, data={"session_id": session_id})
