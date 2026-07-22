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

"""Encre channel-adapter gateway: server side.

Implements :class:`GatewayServer`, a localhost WebSocket server that accepts
connections from channel adapters and routes their requests to the iClaw engine
(EventRouter).  It tracks connected adapters, performs heartbeat/reconnection
bookkeeping, and bridges adapter-submitted prompts to
:meth:`EventRouter.submit` / :meth:`EventRouter.submit_stream`.

See :mod:`encre.gateway` for the package overview and
:mod:`encre.gateway.protocol` for the wire format.
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from encre.gateway.protocol import GatewayMessage, GatewayOp
from encre.gateway.session import SessionSource
from encre.utils.types import Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.server")

RECONNECT_TIMEOUT = 30.0
HEARTBEAT_INTERVAL = 15.0
MAX_PENDING = 256


class _AdapterConnection:
    def __init__(self, name: str, ws: Any) -> None:
        self.name = name
        self.ws = ws
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.status: str = "connected"
        self.capabilities: list[str] = []

    @property
    def uptime(self) -> float:
        return time.time() - self.connected_at


class GatewayServer:
    """WebSocket gateway that accepts connections from channel adapters
    and routes messages to/from the iClaw engine.

    Architecture::

        Adapter ──WS──-> GatewayServer ──-> iClawEngine (EventRouter)
        Adapter <-──WS── GatewayServer <-── iClawEngine (EventRouter)

    Each adapter connection is tracked in the adapter registry. The gateway
    handles heartbeat, reconnection, and message routing.
    """

    def __init__(
        self,
        engine: Any,
        host: str = "127.0.0.1",
        port: int = 18792,
        max_connections: int = 32,
    ) -> None:
        self._engine = engine
        self._host = host
        self._port = port
        self._max_connections = max_connections
        self._server: asyncio.AbstractServer | None = None
        self._running = False
        self._adapters: dict[str, _AdapterConnection] = {}
        self._seq = 0
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    @property
    def adapters(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "name": conn.name,
                "status": conn.status,
                "uptime": conn.uptime,
                "capabilities": conn.capabilities,
            }
            for name, conn in self._adapters.items()
        }

    async def start(self) -> None:
        self._running = True
        import websockets
        self._server = await websockets.serve(
            self._handle_connection,
            host=self._host,
            port=self._port,
            max_size=10 * 1024 * 1024,
            ping_interval=HEARTBEAT_INTERVAL,
            ping_timeout=10.0,
        )
        logger.info("Gateway server listening on ws://%s:%s/gateway", self._host, self._port)

    async def stop(self) -> None:
        self._running = False
        for conn in list(self._adapters.values()):
            with contextlib.suppress(Exception):
                await conn.ws.close()
        self._adapters.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("Gateway server stopped")

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "adapter_count": self.adapter_count,
            "adapters": self.adapters,
        }

    async def _handle_connection(self, ws: Any, _path: str | None = None) -> None:
        if len(self._adapters) >= self._max_connections:
            await ws.close(4001, "Server at capacity")
            return

        adapter_name = f"adapter-{len(self._adapters) + 1}"
        conn = _AdapterConnection(adapter_name, ws)

        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send(ws, GatewayMessage.error("Invalid JSON"))
                    continue

                msg = GatewayMessage.from_dict(data)

                if msg.op == GatewayOp.HELLO:
                    adapter_name = msg.data.get("name", adapter_name)
                    conn.name = adapter_name
                    conn.capabilities = msg.data.get("capabilities", [])
                    self._adapters[adapter_name] = conn
                    logger.info("Adapter '%s' connected (%d total)", adapter_name, self.adapter_count)
                    await self._send(ws, GatewayMessage.hello(adapter_name))
                    self._sync_adapter_list()

                elif msg.op == GatewayOp.HEARTBEAT:
                    conn.last_heartbeat = time.time()
                    await self._send(ws, GatewayMessage.heartbeat_ack())

                elif msg.op == GatewayOp.SUBMIT:
                    _t = asyncio.ensure_future(self._handle_submit(ws, conn, msg))
                    self._background_tasks.add(_t)

                elif msg.op == GatewayOp.SUBMIT_STREAM:
                    _t2 = asyncio.ensure_future(self._handle_submit_stream(ws, conn, msg))
                    self._background_tasks.add(_t2)

                elif msg.op == GatewayOp.CANCEL:
                    session_id = msg.data.get("session_id", "")
                    router = getattr(self._engine, "_router", None)
                    if router:
                        router.cancel_session(session_id)

                elif msg.op == GatewayOp.ADAPTER_UPDATE:
                    conn.status = msg.data.get("status", conn.status)
                    conn.capabilities = msg.data.get("capabilities", conn.capabilities)

                elif msg.op == GatewayOp.SHUTDOWN:
                    break

        except Exception:
            pass
        finally:
            if adapter_name in self._adapters:
                del self._adapters[adapter_name]
            logger.info("Adapter '%s' disconnected (%d remaining)", adapter_name, self.adapter_count)
            self._sync_adapter_list()

    async def _handle_submit(self, ws: Any, conn: _AdapterConnection, msg: GatewayMessage) -> None:
        prompt = msg.data.get("prompt", "")
        request_id = str(msg.data.get("request_id", ""))
        if not prompt.strip():
            logger.warning("[gateway] %s submit empty prompt", conn.name)
            await self._send(ws, GatewayMessage.error("Empty prompt", request_id=request_id))
            return
        session_id = msg.data.get("session_id")
        system_prompt = msg.data.get("system_prompt")
        source_dict = msg.data.get("source")
        logger.info("[gateway] %s submit prompt=%.60s session=%s", conn.name, prompt, session_id or "(new)")
        router = getattr(self._engine, "_router", None)
        if router is None:
            logger.warning("[gateway] %s submit failed -- engine not ready", conn.name)
            await self._send(ws, GatewayMessage.error("Engine not ready", request_id=request_id))
            return
        try:
            async with router.iclaw_context():
                if source_dict is not None and hasattr(self._engine, "resolve_session"):
                    source = SessionSource.from_dict(source_dict)
                    session_id = await self._engine.resolve_session(conn, source)
                    channel_name = source.platform
                else:
                    source = None
                    if not session_id and hasattr(self._engine, "ensure_adapter_session"):
                        session_id = await self._engine.ensure_adapter_session(conn.name)
                    channel_name = conn.name
                result = await router.submit(
                    channel_name, prompt,
                    session_id=session_id,
                    system_prompt=system_prompt,
                )
                if isinstance(result, str) and result:
                    logger.info("[gateway] %s submit response len=%d session=%s", conn.name, len(result), session_id or "?")
                    await self._send(ws, GatewayMessage.text_delta(result, session_id=session_id or "", request_id=request_id))
                else:
                    logger.info("[gateway] %s submit empty response", conn.name)
                await self._send(ws, GatewayMessage.finish(request_id=request_id))
        except Exception as e:
            logger.error("[gateway] %s submit error: %s %s", conn.name, type(e).__name__, e)
            await self._send(ws, GatewayMessage.error(str(e), request_id=request_id))

    async def _handle_submit_stream(self, ws: Any, conn: _AdapterConnection, msg: GatewayMessage) -> None:
        prompt = msg.data.get("prompt", "")
        request_id = str(msg.data.get("request_id", ""))
        if not prompt.strip():
            logger.warning("[gateway] %s submit_stream empty prompt", conn.name)
            await self._send(ws, GatewayMessage.error("Empty prompt", request_id=request_id))
            return
        session_id = msg.data.get("session_id")
        system_prompt = msg.data.get("system_prompt")
        source_dict = msg.data.get("source")
        logger.info("[gateway] %s submit_stream prompt=%.60s session=%s", conn.name, prompt, session_id or "(new)")
        router = getattr(self._engine, "_router", None)
        if router is None:
            logger.warning("[gateway] %s submit_stream failed -- engine not ready", conn.name)
            await self._send(ws, GatewayMessage.error("Engine not ready", request_id=request_id))
            return
        text_len = 0
        try:
            async with router.iclaw_context():
                # Source-bearing frames still use source for platform delivery
                # and authorization.  Agent context is persistent per adapter.
                if source_dict is not None and hasattr(self._engine, "resolve_session"):
                    source = SessionSource.from_dict(source_dict)
                    logger.info("[gateway] %s submit_stream with source platform=%s chat=%s",
                                conn.name, source.platform, source.chat_id)
                    session_id = await self._engine.resolve_session(conn, source)
                    logger.info("[gateway] %s resolve_session returned session_id=%s",
                                conn.name, session_id or "(none)")
                    channel_name = source.platform
                else:
                    source = None
                    if not session_id and hasattr(self._engine, "ensure_adapter_session"):
                        session_id = await self._engine.ensure_adapter_session(conn.name)
                    channel_name = conn.name
                logger.info("[gateway] %s router=%s session_id=%s channel=%s",
                            conn.name, router is not None, session_id or "(none)", channel_name)
                async for event in router.submit_stream(
                    channel_name, prompt,
                    session_id=session_id,
                    system_prompt=system_prompt,
                ):
                    if isinstance(event, TextDelta) and event.text:
                        text_len += len(event.text)
                        await self._send(ws, GatewayMessage.text_delta(event.text, session_id=session_id or "", request_id=request_id))
                    elif isinstance(event, ToolResult):
                        await self._send(ws, GatewayMessage.tool_result(
                            event.id or "", event.content or "", event.is_error, request_id=request_id
                        ))
                    elif isinstance(event, Finish):
                        usage = None
                        if event.usage:
                            usage = dict(event.usage) if hasattr(event.usage, "items") else {}
                        if event.error:
                            logger.warning("[gateway] %s finish with error: %s (text_len=%d)", conn.name, event.error, text_len)
                        else:
                            logger.info("[gateway] %s finish reason=%s text_len=%d", conn.name, event.reason, text_len)
                        await self._send(ws, GatewayMessage.finish(event.reason, usage, event.error or "", request_id=request_id))
        except Exception as e:
            logger.error("[gateway] %s submit_stream error: %s %s", conn.name, type(e).__name__, e)
            await self._send(ws, GatewayMessage.error(str(e), request_id=request_id))

    def _sync_adapter_list(self) -> None:
        """Sync connected adapter names to the EventRouter so the AI
        knows which IM platforms are active."""
        router = getattr(self._engine, "_router", None)
        if router and hasattr(router, "set_connected_adapters"):
            router.set_connected_adapters(list(self._adapters.keys()))

    async def _send(self, ws: Any, msg: GatewayMessage) -> None:
        self._seq += 1
        msg.seq = self._seq
        try:
            await ws.send(json.dumps(msg.to_dict()))
            if msg.op in (GatewayOp.TEXT_DELTA, GatewayOp.HEARTBEAT_ACK, GatewayOp.HEARTBEAT):
                pass  # too noisy
            elif msg.op == GatewayOp.ERROR:
                logger.warning("[gateway] send ERROR seq=%d: %s", msg.seq, msg.data.get("message", ""))
            elif msg.op == GatewayOp.FINISH:
                logger.info("[gateway] send FINISH seq=%d reason=%s", msg.seq, msg.data.get("reason", ""))
            else:
                logger.info("[gateway] send %s seq=%d", msg.op.name, msg.seq)
        except Exception as e:
            logger.warning("[gateway] send error: %s", e)
