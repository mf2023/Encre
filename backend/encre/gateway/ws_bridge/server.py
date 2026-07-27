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

"""WS Bridge server: accepts remote adapter connections over WebSocket.

Implements :class:`WsBridgeServer`, a localhost WebSocket server that accepts
connections from remote/plugin adapters and wraps each one as a
:class:`~encre.gateway.ws_bridge.remote_adapter.RemotePlatformAdapter`
registered with the GatewayRunner.

This is used ONLY for remote adapters that cannot run in-process. Core adapters
run in the same process and interact directly with the GatewayRunner, bypassing
this server entirely.

The server is the bridge's server half: it owns the listening socket, performs
the HELLO handshake, tracks live connections, answers heartbeats, and routes
inbound ``SUBMIT`` / ``SUBMIT_STREAM`` frames to the runner while streaming the
runner's reply events back out as ``TEXT_DELTA`` / ``TOOL_RESULT`` / ``FINISH``
frames.
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp
from encre.gateway.session import SessionSource
from encre.utils.types import Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.ws_bridge.server")

# Seconds a connection may be missing before it is considered dead (currently
# informational; heartbeats use the websockets library's own ping machinery).
RECONNECT_TIMEOUT = 30.0
# Seconds between server->client heartbeat pings.
HEARTBEAT_INTERVAL = 15.0
# Maximum number of in-flight request frames queued before backpressure.
MAX_PENDING = 256


class _AdapterConnection:
    """Lightweight, mutable record describing one live remote connection.

    Holds the socket plus bookkeeping the server needs to track an adapter:
    identity, capabilities, connection timestamp, and heartbeat liveness.
    """

    def __init__(self, name: str, ws: Any) -> None:
        self.name = name
        self.ws = ws
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.status: str = "connected"
        self.capabilities: list[str] = []

    @property
    def uptime(self) -> float:
        """Return how many seconds this connection has been alive."""
        return time.time() - self.connected_at


class WsBridgeServer:
    """WebSocket bridge that accepts connections from remote adapters
    and routes messages to/from the GatewayRunner.

    Architecture::

        RemoteAdapter ──WS──> WsBridgeServer ──> GatewayRunner -> EventRouter
        RemoteAdapter <─WS─── WsBridgeServer <── GatewayRunner <- EventRouter

    Each remote adapter connection is tracked in ``_adapters``. The bridge
    performs the HELLO handshake, answers HEARTBEAT pings, enforces the maximum
    connection cap, and dispatches inbound ``SUBMIT`` / ``SUBMIT_STREAM`` /
    ``CANCEL`` / ``ADAPTER_UPDATE`` / ``SHUTDOWN`` frames to the parent
    GatewayRunner. Replies from the runner are streamed back as gateway wire
    messages.
    """

    def __init__(
        self,
        runner: Any,
        host: str = "127.0.0.1",
        port: int = 18792,
        max_connections: int = 32,
    ) -> None:
        self._runner = runner
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
        """Return the number of currently connected remote adapters."""
        return len(self._adapters)

    @property
    def adapters(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot of each connected adapter's public metadata.

        Returns:
            A mapping of adapter name to a dict with ``name``, ``status``,
            ``uptime`` and ``capabilities``.
        """
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
        """Begin listening for WebSocket connections on the configured host/port.

        Imports ``websockets`` lazily and serves ``_handle_connection`` for each
        inbound socket. Logs the listen address on success.

        Args:
            None.

        Returns:
            None.
        """
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
        logger.info("WS bridge listening on ws://%s:%s/gateway", self._host, self._port)

    async def stop(self) -> None:
        """Stop listening and close every open adapter connection.

        Closes all live sockets, clears the adapter registry, and stops the
        underlying server. Safe to call even if ``start`` was never called.

        Args:
            None.

        Returns:
            None.
        """
        self._running = False
        for conn in list(self._adapters.values()):
            with contextlib.suppress(Exception):
                await conn.ws.close()
        self._adapters.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("WS bridge stopped")

    def get_status(self) -> dict[str, Any]:
        """Return a status snapshot for health/diagnostic endpoints.

        Returns:
            A dict with ``running``, ``host``, ``port``, ``adapter_count`` and
            the per-adapter ``adapters`` snapshot.
        """
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "adapter_count": self.adapter_count,
            "adapters": self.adapters,
        }

    async def _handle_connection(self, ws: Any, _path: str | None = None) -> None:
        """Per-connection coroutine: handshake and dispatch loop for one socket.

        Rejects the connection (close code 4001) when at capacity. Otherwise it
        reads frames in a loop, parsing each JSON message into a
        :class:`GatewayMessage` and dispatching on its ``op``: HELLO performs the
        handshake and registers the adapter, HEARTBEAT is acknowledged, SUBMIT /
        SUBMIT_STREAM spawn background handler tasks, and CANCEL / ADAPTER_UPDATE
        / SHUTDOWN update local state. A SHUTDOWN frame or any read error breaks
        the loop; cleanup unregisters the adapter either way.

        Args:
            ws: The WebSocket protocol object for this connection.
            _path: The request path (unused; present for the websockets API).

        Returns:
            None.
        """
        if len(self._adapters) >= self._max_connections:
            await ws.close(4001, "Server at capacity")
            return

        adapter_name = f"remote-{len(self._adapters) + 1}"
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
                    logger.info("Remote adapter '%s' connected (%d total)", adapter_name, self.adapter_count)
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
                    router = getattr(self._runner, "_router", None)
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
            logger.info("Remote adapter '%s' disconnected (%d remaining)", adapter_name, self.adapter_count)
            self._sync_adapter_list()

    async def _handle_submit(self, ws: Any, conn: _AdapterConnection, msg: GatewayMessage) -> None:
        """Handle a one-shot SUBMIT frame: run the turn, return the full reply.

        Validates the prompt, resolves the target session (from a ``source``
        dict when present, otherwise the adapter's default session), calls the
        runner's synchronous ``submit`` (collecting the whole text), then sends
        a single ``TEXT_DELTA`` followed by ``FINISH``. Errors are reported as
        ``ERROR`` frames.

        Args:
            ws: The connection socket to write replies to.
            conn: The originating :class:`_AdapterConnection`.
            msg: The parsed SUBMIT ``GatewayMessage``.

        Returns:
            None.
        """
        prompt = msg.data.get("prompt", "")
        request_id = str(msg.data.get("request_id", ""))
        if not prompt.strip():
            logger.warning("[ws-bridge] %s submit empty prompt", conn.name)
            await self._send(ws, GatewayMessage.error("Empty prompt", request_id=request_id))
            return
        session_id = msg.data.get("session_id")
        system_prompt = msg.data.get("system_prompt")
        source_dict = msg.data.get("source")
        logger.info("[ws-bridge] %s submit prompt=%.60s session=%s", conn.name, prompt, session_id or "(new)")
        router = getattr(self._runner, "_router", None)
        if router is None:
            logger.warning("[ws-bridge] %s submit failed -- runner not ready", conn.name)
            await self._send(ws, GatewayMessage.error("Engine not ready", request_id=request_id))
            return
        try:
            async with router.iclaw_context():
                if source_dict is not None:
                    source = SessionSource.from_dict(source_dict)
                    session_id = await self._runner.resolve_session(conn.name, source)
                    channel_name = source.platform
                else:
                    if not session_id:
                        session_id = await self._runner.ensure_adapter_session(conn.name)
                    channel_name = conn.name
                result = await router.submit(
                    channel_name, prompt,
                    session_id=session_id,
                    system_prompt=system_prompt,
                )
                if isinstance(result, str) and result:
                    await self._send(ws, GatewayMessage.text_delta(result, session_id=session_id or "", request_id=request_id))
                await self._send(ws, GatewayMessage.finish(request_id=request_id))
        except Exception as e:
            logger.error("[ws-bridge] %s submit error: %s %s", conn.name, type(e).__name__, e)
            await self._send(ws, GatewayMessage.error(str(e), request_id=request_id))

    async def _handle_submit_stream(self, ws: Any, conn: _AdapterConnection, msg: GatewayMessage) -> None:
        """Handle a SUBMIT_STREAM frame: run the turn and stream events back.

        Like :meth:`_handle_submit` for session resolution, but iterates the
        runner's ``submit_stream`` async generator and forwards each event:
        ``TextDelta`` -> ``TEXT_DELTA`` frame, ``ToolResult`` -> ``TOOL_RESULT``
        frame, ``Finish`` -> terminal ``FINISH`` frame (carrying reason, usage
        and error). Logs text length for observability. Errors become ``ERROR``
        frames.

        Args:
            ws: The connection socket to write replies to.
            conn: The originating :class:`_AdapterConnection`.
            msg: The parsed SUBMIT_STREAM ``GatewayMessage``.

        Returns:
            None.
        """
        prompt = msg.data.get("prompt", "")
        request_id = str(msg.data.get("request_id", ""))
        if not prompt.strip():
            logger.warning("[ws-bridge] %s submit_stream empty prompt", conn.name)
            await self._send(ws, GatewayMessage.error("Empty prompt", request_id=request_id))
            return
        session_id = msg.data.get("session_id")
        system_prompt = msg.data.get("system_prompt")
        source_dict = msg.data.get("source")
        logger.info("[ws-bridge] %s submit_stream prompt=%.60s session=%s", conn.name, prompt, session_id or "(new)")
        router = getattr(self._runner, "_router", None)
        if router is None:
            logger.warning("[ws-bridge] %s submit_stream failed -- runner not ready", conn.name)
            await self._send(ws, GatewayMessage.error("Engine not ready", request_id=request_id))
            return
        text_len = 0
        try:
            async with router.iclaw_context():
                if source_dict is not None:
                    source = SessionSource.from_dict(source_dict)
                    session_id = await self._runner.resolve_session(conn.name, source)
                    channel_name = source.platform
                else:
                    if not session_id:
                        session_id = await self._runner.ensure_adapter_session(conn.name)
                    channel_name = conn.name
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
                            logger.warning("[ws-bridge] %s finish with error: %s (text_len=%d)", conn.name, event.error, text_len)
                        else:
                            logger.info("[ws-bridge] %s finish reason=%s text_len=%d", conn.name, event.reason, text_len)
                        await self._send(ws, GatewayMessage.finish(event.reason, usage, event.error or "", request_id=request_id))
        except Exception as e:
            logger.error("[ws-bridge] %s submit_stream error: %s %s", conn.name, type(e).__name__, e)
            await self._send(ws, GatewayMessage.error(str(e), request_id=request_id))

    def _sync_adapter_list(self) -> None:
        """Sync connected remote adapter names to the runner's router.

        Combines the in-process adapter instances with the currently connected
        remote adapters and pushes the merged list to the router so the gateway
        knows the full set of available adapters.

        Args:
            None.

        Returns:
            None.
        """
        router = getattr(self._runner, "_router", None)
        if router and hasattr(router, "set_connected_adapters"):
            # Merge in-process adapters + remote adapters
            in_process = list(getattr(self._runner, "_instances", {}).keys())
            remote = list(self._adapters.keys())
            router.set_connected_adapters(in_process + remote)

    async def _send(self, ws: Any, msg: GatewayMessage) -> None:
        """Serialize and write a ``GatewayMessage`` to a connection socket.

        Assigns the next ``seq`` then writes the JSON form; send failures are
        logged but not raised so a dead socket does not crash the dispatcher.

        Args:
            ws: The target WebSocket protocol object.
            msg: The message to transmit.

        Returns:
            None.
        """
        self._seq += 1
        msg.seq = self._seq
        try:
            await ws.send(json.dumps(msg.to_dict()))
        except Exception as e:
            logger.warning("[ws-bridge] send error: %s", e)
