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

"""WS Bridge client: SDK for remote adapters.

Implements :class:`GatewayClient`, the WebSocket client used by remote adapters
to talk to :class:`encre.gateway.ws_bridge.server.WsBridgeServer`.
It manages the connection lifecycle (connect / reconnect with exponential backoff,
heartbeats) and exposes :meth:`submit` (request/response) and
:meth:`submit_stream` (async generator of agent events).
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp
from encre.utils.types import AgentEvent, Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.ws_bridge.client")

RECONNECT_BASE = 1.0
RECONNECT_MAX = 30.0
HEARTBEAT_INTERVAL = 15.0


class GatewayClient:
    """WebSocket client that connects to a WsBridgeServer.

    Thin transport layer -- sends and receives GatewayMessage objects.
    Handles reconnection with exponential backoff and heartbeats.

    Used by remote/plugin adapters that cannot run in-process.
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
        self._msg_queue: asyncio.Queue[GatewayMessage | None] = asyncio.Queue()
        self._pending: dict[str, asyncio.Queue[GatewayMessage | None]] = {}
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
                    logger.info("%s connected to WS bridge at %s", self._name, self._url)
                    self._emit("connected")
                    _t1 = asyncio.ensure_future(self._heartbeat_loop())
                    _t2 = asyncio.ensure_future(self._read_loop())
                    self._background_tasks.add(_t1)
                    self._background_tasks.add(_t2)
                    return
                else:
                    raise ConnectionError("Unexpected handshake response")

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    attempt += 1
                    delay = min(RECONNECT_BASE * (2 ** (attempt - 1)), RECONNECT_MAX)
                    logger.warning("%s WS bridge reconnect in %.1fs (attempt %d): %s", self._name, delay, attempt, e)
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
        await self._msg_queue.put(None)
        for queue in self._pending.values():
            await queue.put(None)
        logger.info("%s disconnected from WS bridge", self._name)

    async def submit(self, prompt: str, session_id: str | None = None, system_prompt: str | None = None) -> str:
        if not self._connected:
            return ""
        request_id = uuid.uuid4().hex
        response_queue: asyncio.Queue[GatewayMessage | None] = asyncio.Queue()
        self._pending[request_id] = response_queue
        msg = GatewayMessage.submit(prompt, session_id, system_prompt, request_id=request_id)
        await self._send(msg)
        parts: list[str] = []
        timeout_count = 0
        max_timeouts = 10
        while self._connected:
            try:
                response = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                if response is None:
                    break
                if response.op == GatewayOp.TEXT_DELTA:
                    parts.append(response.data.get("text", ""))
                elif response.op == GatewayOp.FINISH:
                    break
                elif response.op == GatewayOp.ERROR:
                    break
            except TimeoutError:
                timeout_count += 1
                if timeout_count >= max_timeouts:
                    break
                continue
            except asyncio.CancelledError:
                self._pending.pop(request_id, None)
                raise
            except Exception:
                break
        self._pending.pop(request_id, None)
        return "".join(parts)

    async def submit_stream(
        self,
        prompt: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
        *,
        source: dict[str, Any] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if not self._connected:
            yield Finish(reason="error", error="WS bridge not connected")
            return
        request_id = uuid.uuid4().hex
        response_queue: asyncio.Queue[GatewayMessage | None] = asyncio.Queue()
        self._pending[request_id] = response_queue
        msg = GatewayMessage.submit_stream(prompt, session_id, system_prompt, source=source, request_id=request_id)
        await self._send(msg)
        timeout_count = 0
        max_timeouts = 10
        while self._connected:
            try:
                response = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                if response is None:
                    self._pending.pop(request_id, None)
                    yield Finish(reason="error", error="WS bridge connection closed")
                    return
                if response.op == GatewayOp.TEXT_DELTA:
                    yield TextDelta(text=response.data.get("text", ""))
                elif response.op == GatewayOp.TOOL_RESULT:
                    d = response.data
                    yield ToolResult(id=d.get("id", ""), content=d.get("content", ""), is_error=d.get("is_error", False))
                elif response.op == GatewayOp.FINISH:
                    self._pending.pop(request_id, None)
                    yield Finish(reason=response.data.get("reason", "done"), error=response.data.get("error", ""), usage=response.data.get("usage"))
                    return
                elif response.op == GatewayOp.ERROR:
                    self._pending.pop(request_id, None)
                    yield Finish(reason="error", error=response.data.get("message", ""))
                    return
            except TimeoutError:
                timeout_count += 1
                if timeout_count >= max_timeouts:
                    self._pending.pop(request_id, None)
                    yield Finish(reason="error", error="Server did not respond")
                    return
                continue
            except asyncio.CancelledError:
                self._pending.pop(request_id, None)
                raise
            except Exception:
                self._pending.pop(request_id, None)
                yield Finish(reason="error", error="WS bridge connection lost")
                return
        self._pending.pop(request_id, None)

    async def _send(self, msg: GatewayMessage) -> None:
        self._seq += 1
        msg.seq = self._seq
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps(msg.to_dict()))
        except Exception as e:
            logger.warning("[ws-client] %s send error: %s", self._name, e)

    async def _heartbeat_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await self._send(GatewayMessage.heartbeat())
            except Exception:
                break

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = GatewayMessage.from_dict(json.loads(raw))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
                if msg.op == GatewayOp.HEARTBEAT:
                    await self._send(GatewayMessage.heartbeat_ack())
                request_id = str(msg.data.get("request_id", ""))
                queue = self._pending.get(request_id) if request_id else None
                if queue is not None:
                    await queue.put(msg)
                else:
                    await self._msg_queue.put(msg)
        except Exception:
            pass
        finally:
            self._connected = False
            self._emit("disconnected")
            await self._msg_queue.put(None)
            for queue in self._pending.values():
                await queue.put(None)

    def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for cb in self._listeners.get(event, []):
            with contextlib.suppress(Exception):
                cb(*args, **kwargs)
