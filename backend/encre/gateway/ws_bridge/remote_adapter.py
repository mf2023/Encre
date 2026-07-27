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

"""Remote platform adapter: wraps a WS connection as a BasePlatformAdapter.

When a remote adapter connects to the WsBridgeServer, the server wraps that
socket in a :class:`RemotePlatformAdapter` instance. To the rest of the
gateway this object looks exactly like any in-process
:class:`~encre.gateway.platforms.base.BasePlatformAdapter`, so the
GatewayRunner can drive it uniformly.

Data flow:
    * Inbound -- the server receives a ``SUBMIT`` / ``SUBMIT_STREAM`` frame
      over the socket, builds a :class:`MessageEvent`, and dispatches it via
      ``handle_message`` (inherited from the base adapter).
    * Outbound -- calls to ``send()`` are translated into ``TEXT_DELTA`` (and a
      following ``FINISH``) frames written back over the same WebSocket, so the
      remote side receives the agent's reply.
"""

import asyncio
import json
import logging
from typing import Any

from encre.gateway.config import Platform, PlatformConfig
from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp

logger = logging.getLogger("encre.gateway.ws_bridge.remote_adapter")


class RemotePlatformAdapter(BasePlatformAdapter):
    """Wraps a remote WebSocket connection as a local BasePlatformAdapter.

    Acts as a proxy for an adapter that lives behind the WS bridge: the remote
    side sends ``SUBMIT`` / ``SUBMIT_STREAM`` frames which this adapter turns
    into ``MessageEvent`` dispatches, and this adapter's ``send()`` calls become
    ``TEXT_DELTA`` + ``FINISH`` frames returned over the socket. The gateway
    therefore never needs to know whether an adapter is local or remote.
    """

    # The gateway can deliver replies to this adapter without blocking on a
    # synchronous reply, since the WS socket is already asynchronous.
    supports_async_delivery: bool = True

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform,
        ws: Any,
        remote_name: str,
    ) -> None:
        super().__init__(config=config, platform=platform)
        self._ws = ws
        self._remote_name = remote_name
        self._seq = 0

    @property
    def name(self) -> str:  # type: ignore[override]
        """Return the remote adapter's identifier, overriding the base."""
        return self._remote_name

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Mark the adapter running; the WS link is already established.

        The underlying socket is owned by the bridge server, so "connecting"
        here only flips the running flag rather than opening a new transport.

        Args:
            is_reconnect: Whether this is a reconnect attempt (unused; the link
                is already live).

        Returns:
            True to signal the gateway that the adapter is usable.
        """
        self._running = True
        return True

    async def disconnect(self) -> None:
        """Close the WS connection to the remote adapter and drop the socket.

        Args:
            None.

        Returns:
            None.
        """
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send reply content back to the remote adapter over the WebSocket.

        Serializes a ``TEXT_DELTA`` frame keyed to ``chat_id`` (used as the
        session id on the wire) and writes it to the socket. Failures are
        captured into a retryable :class:`SendResult` so the gateway can decide
        whether to retry.

        Args:
            chat_id: The conversation/session id; mapped to the wire session id.
            content: The text to deliver.
            reply_to: Optional id of the message being replied to (currently
                not encoded into the frame).
            metadata: Optional metadata (currently not encoded into the frame).

        Returns:
            A :class:`SendResult` indicating success, or failure with a
            retryable flag when the socket write raised.
        """
        if not self._ws:
            return SendResult(success=False, error="WS disconnected")
        try:
            self._seq += 1
            msg = GatewayMessage.text_delta(content, session_id=chat_id)
            msg.seq = self._seq
            await self._ws.send(json.dumps(msg.to_dict()))
            return SendResult(success=True)
        except Exception as e:
            logger.error("[remote-adapter] %s send error: %s", self._remote_name, e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Return minimal chat-info metadata for a remote conversation.

        Remote adapters do not expose richer chat details, so this returns only
        the identifiers the gateway needs to label the conversation.

        Args:
            chat_id: The conversation/session id being described.

        Returns:
            A dict with the chat id, a fixed ``"remote"`` type, and the adapter
            name.
        """
        return {"id": chat_id, "type": "remote", "adapter": self._remote_name}
