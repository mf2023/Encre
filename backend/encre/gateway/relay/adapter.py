#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Relay adapter: front N platforms over a single connector WebSocket.

Aligns with Hermes' ``gateway/relay/adapter.py``.  :class:`RelayAdapter` is
itself a :class:`~encre.adapters.base.BaseAdapter` subclass (registered as the
``relay`` platform).  Instead of speaking a concrete platform's protocol
directly, it dials out to a connector over a
:class:`~encre.gateway.relay.transport.RelayTransport` and lets the connector
front the real platform.  The gateway never learns which concrete platform it
is fronting; the connector owns all platform-specific socket/identity logic.

Key properties (mirrors Hermes):

- ``authorization_is_upstream`` -- the connector enforces authorization, so
  this adapter bypasses the local 5-layer check.
- ``go_dormant()`` -- scale-to-zero suspend (distinct from ``disconnect``).
- ``_platform_by_chat`` -- a single WS fronts N platforms; outbound replies
  carry the originating platform stamp so the connector's egress guard can
  route correctly.
- ``on_interrupt`` / ``_on_passthrough`` / ``_on_inbound`` -- bridges the
  connector's ``interrupt_inbound`` / ``passthrough_forward`` / ``inbound``
  frames into the adapter's existing per-session machinery.
- A 4401 close AFTER a successful handshake is a terminal revocation: the
  adapter marks itself with a non-retryable ``relay_disabled`` fatal error.
"""

import asyncio
import logging
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource
from encre.gateway.relay.descriptor import CapabilityDescriptor
from encre.gateway.relay.transport import RelayTransport
from encre.gateway.relay.ws_transport import WebSocketRelayTransport

logger = logging.getLogger("encre.gateway.relay.adapter")

# Fatal error code surfaced when the connector revokes the gateway.
RELAY_DISABLED_CODE = "relay_disabled"


class RelayAdapter(BaseAdapter):
    """A platform adapter that fronts connector-backed platforms.

    Registered as the ``relay`` platform when ``GATEWAY_RELAY_URL`` /
    ``gateway.relay_url`` is configured (see :mod:`encre.gateway.relay`).
    """

    name = "relay"

    def __init__(
        self,
        transport: RelayTransport | None = None,
        *,
        descriptor: CapabilityDescriptor | None = None,
        gateway_url: str = "",
    ) -> None:
        # Bypass BaseAdapter.__init__'s GatewayClient wiring -- the relay
        # adapter does not submit to a local gateway server; inbound messages
        # arrive over the relay transport and are routed via handle_message
        # -> the injected message handler (same as any other adapter).
        self._transport: RelayTransport | None = transport
        self._descriptor = descriptor
        self._client = None  # no local GatewayClient
        self._running = False
        self._gateway_started = False
        self._reconnecting = False
        self._fatal_error_code: str | None = None
        self._fatal_error_message: str | None = None
        self._message_handler = None
        self._active_sessions: dict[str, asyncio.Event] = {}
        self._pending_messages: dict[str, MessageEvent] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._last_push_chat_id: str | None = None
        self._authz = None
        self._pairing = None
        # Outbound reply platform stamp: chat_id -> originating platform name.
        # A single WS fronts N platforms, so the connector's egress guard
        # needs to know which platform a reply targets.
        self._platform_by_chat: dict[str, str] = {}

    # ── capability bits ────────────────────────────────────────────────

    @property
    def authorization_is_upstream(self) -> bool:
        """The connector enforces authorization -- bypass the local 5-layer check."""
        return True

    @property
    def max_message_length(self) -> int:
        if self._descriptor is not None:
            return self._descriptor.max_message_length
        return 0

    @property
    def splits_long_messages(self) -> bool:
        # If the connector fronted platform supports edit streaming, let the
        # adapter self-chunk; otherwise the router truncates.
        return bool(self._descriptor and self._descriptor.supports_edit)

    # RelayAdapter has no local GatewayClient -- override the base properties
    # that read self._client so they report transport state instead.
    @property
    def is_connected(self) -> bool:
        return self._running and self._transport is not None and getattr(self._transport, "is_connected", True)

    @property
    def client(self):  # type: ignore[override]
        """The relay adapter has no local GatewayClient (it fronts via the
        connector transport).  Returns None."""
        return None

    # ── lifecycle ──────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Open the relay transport and register inbound/passthrough handlers."""
        if self._transport is None:
            self._set_fatal_error(RELAY_DISABLED_CODE, "no relay transport configured")
            return False
        self._transport.set_inbound_handler(self._on_inbound)
        self._transport.set_passthrough_handler(self._on_passthrough)
        ok = await self._transport.connect()
        if not ok:
            if self._transport.was_revoked:
                self._set_fatal_error(
                    RELAY_DISABLED_CODE,
                    "relay connector revoked this gateway (4401 after handshake)",
                )
            else:
                self._set_fatal_error("connect_failed", "relay transport connect failed")
            return False
        self._descriptor = await self._transport.handshake()
        self._mark_connected()
        # Monitor for a post-handshake revocation (4401) in the background.
        _t = asyncio.ensure_future(self._monitor_revocation())
        self._background_tasks.add(_t)
        _t.add_done_callback(self._background_tasks.discard)
        return True

    async def _monitor_revocation(self) -> None:
        """Watch the transport for a terminal 4401 revocation."""
        transport = self._transport
        if transport is None:
            return
        while self._running:
            await asyncio.sleep(5.0)
            if getattr(transport, "was_revoked", False):
                self._set_fatal_error(
                    RELAY_DISABLED_CODE,
                    "relay connector revoked this gateway (4401 after handshake)",
                )
                return

    async def disconnect(self) -> None:
        self._mark_disconnected()
        if self._transport is not None:
            await self._transport.disconnect()

    async def go_dormant(self) -> bool:
        """Scale-to-zero primitive: ask the connector to buffer + flip to idle.

        Distinct from ``disconnect`` -- the connector buffers inbound while the
        gateway is gone and replays on reconnect.  Returns True if the
        connector acked the going-idle flip.
        """
        if self._transport is None:
            return False
        return await self._transport.go_idle()

    # ── the BaseAdapter abstract surface ───────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        if self._transport is None or not self._transport.is_connected:
            return SendResult(success=False, error="relay not connected", retryable=True, error_kind="transient")
        action: dict[str, Any] = {"op": "send", "chat_id": chat_id, "content": content}
        if reply_to:
            action["reply_to"] = reply_to
        if metadata:
            action["metadata"] = metadata
        result = await self._transport.send_outbound(action, platform=self._platform_by_chat.get(chat_id))
        return self._result_from_transport(result)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        if self._transport is None:
            return {"name": chat_id, "type": "dm"}
        return await self._transport.get_chat_info(chat_id)

    async def send_follow_up(
        self,
        session_key: str,
        kind: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Token-less follow_up (A2 shared-identity capability).

        The gateway names the session + capability kind; the connector resolves
        the real value from its vault.  The gateway holds zero capability
        material, so a leaked gateway cannot wield tenant credentials.
        """
        if self._transport is None:
            return SendResult(success=False, error="relay not connected", retryable=True)
        action = {
            "op": "follow_up",
            "session_key": session_key,
            "kind": kind,
            "content": content,
        }
        if metadata:
            action["metadata"] = metadata
        result = await self._transport.send_follow_up(action)
        return self._result_from_transport(result)

    @staticmethod
    def _result_from_transport(result: dict[str, Any]) -> SendResult:
        return SendResult(
            success=bool(result.get("success", False)),
            message_id=result.get("message_id"),
            error=result.get("error"),
            retryable=bool(result.get("retryable", False)),
            error_kind=result.get("error_kind"),
        )

    # ── inbound / passthrough / interrupt bridging ────────────────────

    def _on_inbound(self, event: dict[str, Any]) -> None:
        """Bridge a connector ``inbound`` frame into the adapter's handle_message.

        The connector delivers a normalized ``MessageEvent`` dict; we rebuild
        the local dataclass + SessionSource and route it through the standard
        inbound path (which runs hooks, the two-level guard, etc.).
        """
        # interrupt_inbound frames arrive via the same inbound handler path
        # (the transport tags them with __interrupt__).
        if event.get("__interrupt__"):
            self.on_interrupt(event.get("session_key", ""), event.get("chat_id", ""))
            return
        source_dict = event.get("source") or {}
        source = SessionSource.from_dict(source_dict) if source_dict else None
        chat_id = event.get("chat_id") or (source.chat_id if source else "")
        if source and chat_id:
            self._platform_by_chat[chat_id] = source.platform
        me = MessageEvent(
            text=event.get("text", ""),
            message_type=MessageType.TEXT,
            message_id=event.get("message_id"),
            chat_id=chat_id,
            user_id=event.get("user_id") or (source.user_id if source else None),
            reply_to_message_id=event.get("reply_to_message_id"),
            reply_to_text=event.get("reply_to_text"),
            media_urls=event.get("media_urls", []),
            media_types=event.get("media_types", []),
            raw=event.get("raw"),
            source=source,
        )
        _t = asyncio.ensure_future(self.handle_message(me))
        self._background_tasks.add(_t)
        _t.add_done_callback(self._background_tasks.discard)

    def _on_passthrough(self, forward: dict[str, Any]) -> None:
        """Bridge a ``passthrough_forward`` frame (Class-2/3 webhook).

        The connector already verified the provider signature at the edge and
        stripped the shared-identity credential; the gateway re-processes a
        sanitized, token-free body.  Default: decode + route as an inbound
        message (a Discord interaction decodes to a MessageEvent).
        """
        logger.info("[relay] passthrough forward: platform=%s method=%s",
                    forward.get("platform"), forward.get("method"))
        # Subclasses / connectors decode platform-specific bodies; the base
        # implementation logs and drops, since decoding is platform-specific.

    def on_interrupt(self, session_key: str, chat_id: str) -> None:
        """Bridge a connector ``interrupt_inbound`` for a session.

        Cancels exactly that turn (siblings untouched) by routing the interrupt
        to the adapter's per-session interrupt mechanism.
        """
        logger.info("[relay] interrupt_inbound session=%s chat=%s", session_key, chat_id)
        # Cancel via the EventRouter if wired, else mark the session inactive.
        for key in [session_key, chat_id]:
            if key in self._active_sessions:
                self._active_sessions[key].set()
