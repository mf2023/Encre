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

"""Encre channel-adapter gateway: client side.

Implements :class:`GatewayClient`, the WebSocket client used by channel adapters
(QQ, Telegram, ...) to talk to :class:`encre.gateway.server.GatewayServer`.
It manages the connection lifecycle (connect / reconnect with exponential backoff,
heartbeats) and exposes :meth:`submit` (request/response) and
:meth:`submit_stream` (async generator of agent events).

Incoming frames are read by :meth:`_read_loop` and funnelled into a single
``_msg_queue`` so multiple callers can consume by op-code without racing on the
underlying WebSocket.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from encre.gateway.protocol import GatewayMessage, GatewayOp
from encre.utils.types import AgentEvent, Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.client")

RECONNECT_BASE = 1.0
RECONNECT_MAX = 30.0
HEARTBEAT_INTERVAL = 15.0


class GatewayClient:
    """WebSocket client that connects to a GatewayServer.

    Thin transport layer -- sends and receives GatewayMessage objects.
    Handles reconnection with exponential backoff and heartbeats.

    Uses an internal message queue to avoid reader contention on the
    WebSocket: _read_loop pushes all incoming messages into a queue,
    and submit / submit_stream consume from the same queue.
    """

    def __init__(
        self,
        adapter_name: str,
        url: str = "ws://127.0.0.1:18792/gateway",
        capabilities: list[str] | None = None,
    ) -> None:
        self._name = adapter_name
        self._url = url
        self._capabilities = capabilities or []
        self._ws: Any = None
        self._running = False
        self._connected = False
        self._seq = 0
        self._listeners: dict[str, list[Any]] = {}
        # Message queue: _read_loop pushes, submit/submit_stream consume
        self._msg_queue: asyncio.Queue[GatewayMessage | None] = asyncio.Queue()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def on(self, event: str, callback: Any) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Any) -> None:
        self._listeners.setdefault(event, []).append(callback)
        self._listeners[event] = [cb for cb in self._listeners[event] if cb is not callback]

    async def connect(self) -> None:
        import websockets
        self._running = True
        attempt = 0
        while self._running:
            try:
                self._ws = await websockets.connect(
                    self._url,
                    max_size=10 * 1024 * 1024,
                    ping_interval=HEARTBEAT_INTERVAL,
                    ping_timeout=10.0,
                )
                hello = GatewayMessage.hello(self._name)
                hello.data["capabilities"] = self._capabilities
                await self._send(hello)

                response_raw = await self._ws.recv()
                response = GatewayMessage.from_dict(json.loads(response_raw))
                if response.op == GatewayOp.HELLO:
                    self._connected = True
                    attempt = 0
                    logger.info("%s connected to gateway at %s", self._name, self._url)
                    self._emit("connected")
                    # Background tasks: heartbeat sender + message reader
                    _t1 = asyncio.ensure_future(self._heartbeat_loop())
                    _t2 = asyncio.ensure_future(self._read_loop())
                    self._background_tasks.add(_t1)
                    self._background_tasks.add(_t2)
                    # connect() returns -- reads happen via _msg_queue
                    return
                else:
                    raise ConnectionError("Unexpected handshake response")

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    attempt += 1
                    delay = min(RECONNECT_BASE * (2 ** (attempt - 1)), RECONNECT_MAX)
                    logger.warning("%s gateway reconnect in %.1fs (attempt %d): %s", self._name, delay, attempt, e)
                    self._connected = False
                    self._emit("disconnected")
                    await asyncio.sleep(delay)

    async def disconnect(self) -> None:
        self._running = False
        self._connected = False
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        # Unblock any consumer waiting on the queue
        await self._msg_queue.put(None)
        logger.info("%s disconnected from gateway", self._name)

    async def submit(self, prompt: str, session_id: str | None = None, system_prompt: str | None = None) -> str:
        logger.info("[gateway-client] %s submit prompt=%.60s session=%s", self._name, prompt, session_id or "(new)")
        if not self._connected:
            logger.error("[gateway-client] %s cannot submit -- not connected to gateway", self._name)
            return ""
        msg = GatewayMessage.submit(prompt, session_id, system_prompt)
        await self._send(msg)
        parts: list[str] = []
        timeout_count = 0
        max_timeouts = 10
        while self._connected:
            try:
                response = await asyncio.wait_for(self._msg_queue.get(), timeout=30.0)
                if response is None:
                    logger.warning("[gateway-client] %s submit disconnected during response", self._name)
                    break  # disconnected
                if response.op == GatewayOp.TEXT_DELTA:
                    parts.append(response.data.get("text", ""))
                elif response.op == GatewayOp.FINISH:
                    logger.info("[gateway-client] %s submit finish reason=%s text_len=%d",
                                self._name, response.data.get("reason", "?"), len("".join(parts)))
                    break
                elif response.op == GatewayOp.ERROR:
                    logger.warning("[gateway-client] %s submit error: %s", self._name, response.data.get("message", ""))
                    break
            except TimeoutError:
                timeout_count += 1
                if timeout_count >= max_timeouts:
                    logger.error("[gateway-client] %s submit timed out %d times, giving up", self._name, max_timeouts)
                    break
                logger.warning("[gateway-client] %s submit timeout #%d, retrying...", self._name, timeout_count)
                continue
            except Exception as e:
                logger.warning("[gateway-client] %s submit exception: %s", self._name, e)
                break
        result = "".join(parts)
        logger.info("[gateway-client] %s submit done len=%d", self._name, len(result))
        return result

    async def submit_stream(
        self,
        prompt: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        logger.info("[gateway-client] %s submit_stream prompt=%.60s session=%s", self._name, prompt, session_id or "(new)")
        if not self._connected:
            logger.error("[gateway-client] %s cannot submit_stream -- not connected (ws=%s running=%s)",
                         self._name, self._ws is not None, self._running)
            yield Finish(reason="error", error="Gateway not connected")
            return
        msg = GatewayMessage.submit_stream(prompt, session_id, system_prompt)
        await self._send(msg)
        text_len = 0
        timeout_count = 0
        max_timeouts = 10
        while self._connected:
            try:
                response = await asyncio.wait_for(self._msg_queue.get(), timeout=30.0)
                if response is None:
                    logger.warning("[gateway-client] %s submit_stream disconnected", self._name)
                    yield Finish(reason="error", error="Gateway connection closed")
                    return
                if response.op == GatewayOp.TEXT_DELTA:
                    t = response.data.get("text", "")
                    text_len += len(t)
                    yield TextDelta(text=t)
                elif response.op == GatewayOp.TOOL_RESULT:
                    d = response.data
                    yield ToolResult(id=d.get("id", ""), content=d.get("content", ""), is_error=d.get("is_error", False))
                elif response.op == GatewayOp.FINISH:
                    err = response.data.get("error", "")
                    if err:
                        logger.warning("[gateway-client] %s finish with error: %s (text_len=%d)", self._name, err, text_len)
                    else:
                        logger.info("[gateway-client] %s finish reason=%s text_len=%d", self._name, response.data.get("reason", "?"), text_len)
                    yield Finish(reason=response.data.get("reason", "done"), error=err, usage=response.data.get("usage"))
                    return
                elif response.op == GatewayOp.ERROR:
                    logger.warning("[gateway-client] %s error: %s", self._name, response.data.get("message", ""))
                    yield Finish(reason="error", error=response.data.get("message", ""))
                    return
            except TimeoutError:
                timeout_count += 1
                if timeout_count >= max_timeouts:
                    logger.error("[gateway-client] %s submit_stream timed out %d times, giving up", self._name, max_timeouts)
                    yield Finish(reason="error", error="Server did not respond")
                    return
                logger.warning("[gateway-client] %s submit_stream timeout #%d, retrying...", self._name, timeout_count)
                continue
            except Exception as e:
                logger.warning("[gateway-client] %s submit_stream exception: %s", self._name, e)
                yield Finish(reason="error", error="Gateway connection lost")
                return

    async def _send(self, msg: GatewayMessage) -> None:
        self._seq += 1
        msg.seq = self._seq
        if not self._ws:
            logger.warning("[gateway-client] %s cannot send -- WebSocket not connected (op=%s seq=%d)",
                           self._name, msg.op.name if msg.op else "?", self._seq)
            return
        try:
            await self._ws.send(json.dumps(msg.to_dict()))
            if msg.op == GatewayOp.SUBMIT or msg.op == GatewayOp.SUBMIT_STREAM:
                logger.info("[gateway-client] %s sent op=%s seq=%d prompt=%.60s",
                            self._name, msg.op.name, msg.seq, msg.data.get("prompt", "")[:60])
            elif msg.op == GatewayOp.HEARTBEAT or msg.op == GatewayOp.HEARTBEAT_ACK:
                pass  # too noisy
            else:
                logger.info("[gateway-client] %s sent op=%s seq=%d", self._name, msg.op.name, msg.seq)
        except Exception as e:
            logger.warning("[gateway-client] %s send error: %s", self._name, e)

    async def _heartbeat_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self._send(GatewayMessage.heartbeat())
            except Exception:
                break

    async def _read_loop(self) -> None:
        """Read all messages from WebSocket and push them into _msg_queue.

        Runs as a background asyncio Task. Any consumer (submit, submit_stream)
        pulls messages from the same queue by op-code.
        A sentinel None is pushed on disconnect.
        """
        try:
            async for raw in self._ws:
                try:
                    msg = GatewayMessage.from_dict(json.loads(raw))
                except (json.JSONDecodeError, KeyError, ValueError):
                    logger.warning("[gateway-client] %s bad message: %.80s", self._name, raw)
                    continue
                # Handle heartbeats inline so consumers don't need to
                if msg.op == GatewayOp.HEARTBEAT:
                    await self._send(GatewayMessage.heartbeat_ack())
                elif msg.op == GatewayOp.TEXT_DELTA:
                    text = msg.data.get("text", "")
                    logger.info("[gateway-client] %s recv text_delta len=%d", self._name, len(text))
                elif msg.op == GatewayOp.FINISH:
                    reason = msg.data.get("reason", "")
                    err = msg.data.get("error", "")
                    logger.info("[gateway-client] %s recv finish reason=%s error=%s", self._name, reason, err or "none")
                elif msg.op == GatewayOp.ERROR:
                    logger.warning("[gateway-client] %s recv error: %s", self._name, msg.data.get("message", ""))
                # Forward everything to the shared queue
                await self._msg_queue.put(msg)
        except Exception as e:
            logger.warning("[gateway-client] %s read_loop ended: %s %s", self._name, type(e).__name__, e)
        finally:
            self._connected = False
            self._emit("disconnected")
            await self._msg_queue.put(None)
            await self._msg_queue.put(None)

    def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for cb in self._listeners.get(event, []):
            with contextlib.suppress(Exception):
                cb(*args, **kwargs)
