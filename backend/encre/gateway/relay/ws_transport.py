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

"""WebSocket relay transport (production).

The gateway dials **out** to the connector's ``/relay`` WebSocket endpoint,
authenticates the upgrade with a per-gateway HMAC bearer token, and exchanges
newline-delimited JSON frames:

  gateway -> connector:
    hello            {type, gatewayId?}
    outbound         {type, requestId, action}         (send/edit/typing)
    follow_up        {type, requestId, action}         (token-less capability)
    interrupt        {type, session_key, reason?}
    going_idle       {type}
    inbound_ack      {type, bufferId}

  connector -> gateway:
    descriptor       {type, descriptor}                 (handshake result)
    inbound          {type, event, bufferId?}
    outbound_result  {type, requestId, result}
    interrupt_inbound {type, session_key, chat_id}
    going_idle_ack   {type}
    passthrough_forward {type, forward, bufferId?}      (body base64)

Outbound RPCs (``send``/``edit``/``typing``/``follow_up``/``get_chat_info``)
block on a per-``requestId`` :class:`asyncio.Future` until the matching
``outbound_result`` arrives, with a 30s timeout.  A 4401 close AFTER a prior
successful handshake is a terminal revocation: the transport stops
reconnecting and surfaces ``was_revoked=True`` so the adapter can mark the
``relay`` platform as disabled (non-retryable fatal).  A 4401 before any
successful handshake stays retryable (a cold-start / not-yet-provisioned race).
"""

import asyncio
import json
import logging
import secrets
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

from encre.gateway.relay.auth import make_upgrade_token
from encre.gateway.relay.descriptor import CapabilityDescriptor

logger = logging.getLogger("encre.gateway.relay.ws_transport")

# A 4401 close after a successful handshake = terminal revocation.
_RELAY_UNAUTHORIZED_CLOSE_CODE = 4401

RECONNECT_BASE = 1.0
RECONNECT_MAX = 30.0
OUTBOUND_TIMEOUT = 30.0


def _ws_dial_url(url: str) -> str:
    """Normalize a relay URL to a ``ws(s)://host/relay`` dial target.

    ``https://`` -> ``wss://``, ``http://`` -> ``ws://``; the path is forced to
    end with ``/relay`` (the connector's WS endpoint).
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme == "https":
        scheme = "wss"
    elif scheme == "http":
        scheme = "ws"
    elif scheme not in ("ws", "wss"):
        scheme = "wss" if scheme == "https" else "ws"
    path = parsed.path or ""
    if not path.endswith("/relay"):
        path = (path.rstrip("/") + "/relay") if path else "/relay"
    return urlunparse((scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


class WebSocketRelayTransport:
    """Production relay transport over an outbound WebSocket.

    Implements the :class:`~encre.gateway.relay.transport.RelayTransport`
    Protocol.  The gateway dials the connector, authenticates with a per-gateway
    HMAC bearer token, receives a :class:`CapabilityDescriptor` at handshake,
    and then exchanges frames.
    """

    def __init__(
        self,
        url: str,
        platform: str,
        bot_id: str | None = None,
        *,
        identities: list[dict[str, Any]] | None = None,
        connect_timeout_s: float = 30.0,
        outbound_timeout_s: float = OUTBOUND_TIMEOUT,
        gateway_id: str | None = None,
        upgrade_secret: str | None = None,
        reconnect: bool = False,
        reconnect_backoff_s: float = RECONNECT_BASE,
        reconnect_max_backoff_s: float = RECONNECT_MAX,
    ) -> None:
        self._url = _ws_dial_url(url)
        self._platform = platform
        self._bot_id = bot_id
        self._identities = identities or []
        self._connect_timeout = connect_timeout_s
        self._outbound_timeout = outbound_timeout_s
        self._gateway_id = gateway_id
        self._upgrade_secret = upgrade_secret
        self._reconnect = reconnect
        self._reconnect_base = reconnect_backoff_s
        self._reconnect_max = reconnect_max_backoff_s

        self._ws: Any = None
        self._running = False
        self._connected = False
        self._handshake_done = False
        # True once the connector closed with 4401 AFTER a successful handshake
        # (terminal revocation -- stop reconnecting).
        self._was_revoked = False
        self._descriptor: CapabilityDescriptor | None = None
        # requestId -> future awaiting the matching outbound_result.
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        # Phase 5 §5.3: future awaiting the connector's going_idle_ack.
        self._going_idle_ack: asyncio.Future[None] | None = None
        self._inbound_handler: Callable[[dict[str, Any]], None] | None = None
        self._passthrough_handler: Callable[[dict[str, Any]], None] | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._read_buf = ""

    # ── properties ─────────────────────────────────────────────────────

    @property
    def was_revoked(self) -> bool:
        return self._was_revoked

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── handler registration ───────────────────────────────────────────

    def set_inbound_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._inbound_handler = handler

    def set_passthrough_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._passthrough_handler = handler

    # ── connect / handshake ────────────────────────────────────────────

    async def connect(self) -> bool:
        """Open the WS, perform the handshake, start the read loop.

        Returns True on success.  On a terminal 4401 revocation, returns False
        and sets :attr:`was_revoked`; the caller must NOT retry.
        """
        import websockets

        self._running = True
        headers: dict[str, str] = {}
        if self._gateway_id and self._upgrade_secret:
            token = make_upgrade_token(self._gateway_id, self._upgrade_secret)
            headers["Authorization"] = f"Bearer {token}"

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    additional_headers=headers,
                    max_size=10 * 1024 * 1024,
                    ping_interval=15.0,
                    ping_timeout=10.0,
                ),
                timeout=self._connect_timeout,
            )
        except Exception as e:
            logger.warning("[relay] connect to %s failed: %s %s", self._url, type(e).__name__, e)
            self._running = False
            return False

        # Send hello + wait for the descriptor handshake frame.
        hello: dict[str, Any] = {"type": "hello"}
        if self._gateway_id:
            hello["gatewayId"] = self._gateway_id
        if self._identities:
            hello["identities"] = self._identities
        await self._send_raw(hello)

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self._connect_timeout)
        except Exception as e:
            logger.warning("[relay] handshake descriptor not received: %s", e)
            await self._ws.close()
            self._running = False
            return False

        frame = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if frame.get("type") != "descriptor":
            logger.error("[relay] expected descriptor, got %s", frame.get("type"))
            await self._ws.close()
            self._running = False
            return False

        self._descriptor = CapabilityDescriptor.from_dict(frame["descriptor"])
        self._connected = True
        self._handshake_done = True
        logger.info("[relay] handshake OK: platform=%s label=%s max_len=%d",
                    self._descriptor.platform, self._descriptor.label,
                    self._descriptor.max_message_length)
        self._read_task = asyncio.ensure_future(self._read_loop())
        return True

    async def handshake(self) -> CapabilityDescriptor:
        if self._descriptor is None:
            raise RuntimeError("handshake not complete -- call connect() first")
        return self._descriptor

    async def disconnect(self) -> None:
        self._running = False
        self._connected = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        # Fail any pending outbound RPCs.
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("relay transport closed"))
        self._pending.clear()
        if self._going_idle_ack is not None and not self._going_idle_ack.done():
            self._going_idle_ack.set_exception(RuntimeError("relay transport closed"))
            self._going_idle_ack = None

    # ── outbound RPC ───────────────────────────────────────────────────

    async def _send_with_request(
        self,
        frame_type: str,
        action: dict[str, Any],
        *,
        platform: str | None = None,
    ) -> dict[str, Any]:
        """Send an outbound frame and await the matching ``outbound_result``.

        Blocks on a per-``requestId`` future with a 30s timeout.  Raises
        :class:`asyncio.TimeoutError` on timeout.
        """
        if not self._connected:
            return {"success": False, "error": "relay not connected"}
        request_id = secrets.token_hex(8)
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = fut
        frame: dict[str, Any] = {"type": frame_type, "requestId": request_id, "action": action}
        if platform:
            frame["platform"] = platform
        try:
            await self._send_raw(frame)
            return await asyncio.wait_for(fut, timeout=self._outbound_timeout)
        except asyncio.TimeoutError:
            logger.warning("[relay] outbound %s timed out (requestId=%s)", frame_type, request_id)
            return {"success": False, "error": "outbound timed out"}
        finally:
            self._pending.pop(request_id, None)

    async def send_outbound(self, action: dict[str, Any], *, platform: str | None = None) -> dict[str, Any]:
        return await self._send_with_request("outbound", action, platform=platform)

    async def send_follow_up(self, action: dict[str, Any], *, platform: str | None = None) -> dict[str, Any]:
        return await self._send_with_request("follow_up", action, platform=platform)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        result = await self._send_with_request(
            "outbound", {"op": "get_chat_info", "chat_id": chat_id}
        )
        if result.get("success"):
            return result.get("chat_info", {"name": chat_id, "type": "dm"})
        return {"name": chat_id, "type": "dm"}

    async def send_interrupt(self, session_key: str, reason: str | None = None) -> None:
        if not self._connected:
            return
        frame: dict[str, Any] = {"type": "interrupt", "session_key": session_key}
        if reason:
            frame["reason"] = reason
        await self._send_raw(frame)

    async def go_idle(self, timeout_s: float = 10.0) -> bool:
        """Emit ``going_idle`` and await ``going_idle_ack`` (scale-to-zero primitive)."""
        if not self._connected:
            return False
        loop = asyncio.get_event_loop()
        self._going_idle_ack = loop.create_future()
        try:
            await self._send_raw({"type": "going_idle"})
            await asyncio.wait_for(self._going_idle_ack, timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            logger.warning("[relay] going_idle_ack timed out")
            return False
        finally:
            self._going_idle_ack = None

    # ── raw send ────────────────────────────────────────────────────────

    async def _send_raw(self, frame: dict[str, Any]) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps(frame, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("[relay] send failed: %s", e)
            self._connected = False

    # ── read loop / frame dispatch ─────────────────────────────────────

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                self._read_buf += raw
                # Newline-delimited JSON: split complete lines, keep the tail.
                while "\n" in self._read_buf:
                    line, self._read_buf = self._read_buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        await self._handle_frame(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("[relay] bad frame: %.80s", line)
                    except Exception as e:
                        logger.warning("[relay] frame handler error: %s %s", type(e).__name__, e)
        except Exception as e:
            # Detect a 4401 close after a successful handshake = revocation.
            close_code = getattr(getattr(e, "code", None), "value", None) or getattr(e, "code", None)
            if close_code == _RELAY_UNAUTHORIZED_CLOSE_CODE and self._handshake_done:
                self._was_revoked = True
                logger.error("[relay] closed 4401 after handshake -- terminal revocation, not reconnecting")
            else:
                logger.info("[relay] read loop ended: %s %s", type(e).__name__, e)
        finally:
            self._connected = False
            # Fail pending RPCs.
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError("relay connection closed"))
            self._pending.clear()

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        ftype = frame.get("type", "")
        if ftype == "inbound":
            if self._inbound_handler:
                self._inbound_handler(frame.get("event", {}))
            # Ack buffered delivery if a bufferId was present.
            buf = frame.get("bufferId")
            if buf:
                await self._send_raw({"type": "inbound_ack", "bufferId": buf})
        elif ftype == "outbound_result":
            fut = self._pending.get(frame.get("requestId", ""))
            if fut is not None and not fut.done():
                fut.set_result(frame.get("result", {}))
        elif ftype == "interrupt_inbound":
            # Bridged by the adapter's on_interrupt via the inbound handler path.
            if self._inbound_handler:
                self._inbound_handler({
                    "__interrupt__": True,
                    "session_key": frame.get("session_key"),
                    "chat_id": frame.get("chat_id"),
                })
        elif ftype == "going_idle_ack":
            if self._going_idle_ack is not None and not self._going_idle_ack.done():
                self._going_idle_ack.set_result(None)
        elif ftype == "passthrough_forward":
            if self._passthrough_handler:
                self._passthrough_handler(frame.get("forward", {}))
        elif ftype == "descriptor":
            # A late/re-handshake descriptor -- accept it.
            self._descriptor = CapabilityDescriptor.from_dict(frame.get("descriptor", {}))
        else:
            logger.debug("[relay] unhandled frame type: %s", ftype)
