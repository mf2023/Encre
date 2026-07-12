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

"""Encre agent channels: WebSocket transport.

Implements :class:`WebSocketChannel`, the primary interactive channel.  It
serves a raw RFC 6455 WebSocket (using the ``websockets`` library), creates
one agent session per connection, and translates the agent's
:class:`~encre.utils.types.AgentEvent` stream into JSON frames understood by
the desktop client (``session_ready``, ``text_delta``, ``tool_call_*``,
``finish`` ...).
"""

import asyncio
import contextlib
import json
import logging
import traceback
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

ServerConnection = WebSocketServerProtocol

from encre.channels.base import Channel, EventRouter  # noqa: E402
from encre.utils.types import (  # noqa: E402
    BackendError,
    EngineInstallProgress,
    EngineInstallRequest,
    Finish,
    PermissionRequest,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
)

logger = logging.getLogger("encre.channels.ws")


class WebSocketChannel(Channel):
    """Real WebSocket channel using the websockets library (RFC 6455).

    Each WebSocket connection gets its own isolated agent session.
    Supports chat, cancel, ping, list_sessions, new_session actions.
    """

    name = "websocket"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 18791,
        max_message_size: int = 10 * 1024 * 1024,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._max_message_size = max_message_size
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._server: websockets.WebSocketServer | None = None
        self._router: EventRouter | None = None
        self._connections: dict[str, ServerConnection] = {}

    async def start(self, router: EventRouter) -> None:
        self._router = router
        self._server = await websockets.serve(
            self._handle_connection,
            host=self._host,
            port=self._port,
            max_size=self._max_message_size,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        )
        # Resolve actual port when port=0 (OS-assigned)
        actual_port = self._port
        if actual_port == 0 and self._server.sockets:
            actual_port = self._server.sockets[0].getsockname()[1]
        logger.info(
            "WebSocket channel ready: ws://%s:%s",
            self._host,
            actual_port,
        )

    async def stop(self) -> None:
        for ws in list(self._connections.values()):
            with contextlib.suppress(Exception):
                await ws.close(1001, "Server shutting down")
        self._connections.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, ws: ServerConnection) -> None:
        """Handle a single WebSocket client connection."""
        # Create a new session for this connection
        info = self._router.session_manager.create_session()
        session_id = info.session_id
        self._connections[session_id] = ws

        try:
            # Send session_ready
            await ws.send(json.dumps({
                "type": "session_ready",
                "session_id": session_id,
            }, ensure_ascii=False))

            async for raw in ws:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    await self._send_error(ws, "Invalid JSON")
                    continue

                action = data.get("action", data.get("type", ""))
                await self._dispatch(ws, session_id, action, data)

        except websockets.exceptions.ConnectionClosedOK:
            pass
        except websockets.exceptions.ConnectionClosedError as e:
            logger.debug("WebSocket connection closed with error: %s", e)
        except Exception:
            logger.exception("WebSocket handler error")
        finally:
            self._connections.pop(session_id, None)
            # Cancel any running agent for this session
            if self._router:
                self._router.cancel_session(session_id)

    async def _dispatch(
        self,
        ws: ServerConnection,
        session_id: str,
        action: str,
        data: dict[str, Any],
    ) -> None:
        """Route a parsed client action to the right agent behaviour.

        Supports ``chat`` (run a prompt, streaming events back),
        ``cancel``, ``engine_install_response``, ``list_sessions``,
        ``new_session``, ``delete_session`` and ``get_config``.
        """
        router = self._router
        if router is None:
            return

        if action in ("ping", "pong"):
            await ws.send(json.dumps({"type": "pong"}, ensure_ascii=False))

        elif action == "chat":
            prompt = data.get("prompt", "")
            if not prompt.strip():
                await self._send_error(ws, "Empty prompt")
                return
            system_prompt = data.get("system_prompt")

            info = router.session_manager.get_session(session_id)
            if info is None:
                await self._send_error(ws, "Session not found")
                return

            if info.is_running:
                await self._send_error(ws, "Session already running")
                return

            acquired = await router.session_manager.acquire_slot()
            if not acquired:
                await self._send_error(ws, "Server at capacity")
                return

            info.is_running = True
            router.session_manager.touch(session_id)

            # Wire the engine-install requester's IMMEDIATE emit
            # hook so the desktop dialog pops up the moment a
            # browser / desktop action needs the engine, without
            # waiting for the agent's event loop to tick.  This
            # closure captures ``ws`` and forwards the request
            # directly to the renderer.
            async def _emit_engine(evt: Any) -> None:
                try:
                    await self._send_event(ws, evt, session_id)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("engine emit failed: %s", exc)
            try:
                info.agent.set_engine_emit(_emit_engine)
            except Exception:
                logger.debug("agent has no set_engine_emit", exc_info=True)

            try:
                async for event in info.agent.run(
                    prompt=prompt,
                    system_prompt=system_prompt,
                ):
                    await self._send_event(ws, event, session_id)
            except asyncio.CancelledError:
                await ws.send(json.dumps({"type": "finish", "reason": "cancelled", "session_id": session_id}, ensure_ascii=False))
            except Exception as e:
                logger.error("Agent run error: %s\n%s", e, traceback.format_exc())
                await self._send_error(ws, str(e))
                await ws.send(json.dumps({"type": "finish", "reason": "error", "session_id": session_id}, ensure_ascii=False))
            finally:
                info.is_running = False
                router.session_manager.release_slot()
                router.session_manager._save_session(info)

        elif action == "cancel":
            router.cancel_session(session_id)
            await ws.send(json.dumps({"type": "finish", "reason": "cancelled", "session_id": session_id}, ensure_ascii=False))

        elif action == "engine_install_response":
            # Frontend reply to a pending EngineInstallRequest.
            # The session that yielded the request is suspended
            # in the requester; resolving it lets the original
            # tool action (browser click, navigate, ...) continue.
            req_id = data.get("request_id", "")
            choice = str(data.get("choice", "cancelled"))

            # 1) Check agent-bound engine requests first
            info = router.session_manager.get_session(session_id)
            agent = getattr(info, "agent", None) if info is not None else None
            resolved = False
            if agent is not None and hasattr(agent, "resolve_engine_install"):
                resolved = agent.resolve_engine_install(req_id, choice)

            await ws.send(json.dumps({
                "type": "engine_install_response_ack",
                "request_id": req_id,
                "choice": choice,
                "resolved": bool(resolved),
            }, ensure_ascii=False))

        elif action == "list_sessions":
            sessions = router.session_manager.query_index()
            await ws.send(json.dumps({"type": "sessions_list", "sessions": sessions}, ensure_ascii=False))

        elif action == "new_session":
            # Cancel current session's agent if running
            router.cancel_session(session_id)
            # Create fresh session
            info = router.session_manager.create_session()
            new_id = info.session_id
            self._connections.pop(session_id, None)
            self._connections[new_id] = ws
            await ws.send(json.dumps({
                "type": "session_ready",
                "session_id": new_id,
            }, ensure_ascii=False))

        elif action == "delete_session":
            sid = data.get("session_id", "")
            if sid:
                router.cancel_session(sid)
                router.session_manager.delete_session_from_disk(sid)
                await ws.send(json.dumps({
                    "type": "session_deleted",
                    "session_id": sid,
                }, ensure_ascii=False))

        elif action == "get_config":
            info = router.session_manager.get_session(session_id)
            if info:
                config_data = info.agent.config.to_dict(encrypt_api_keys=False)
                from encre.backends.catalog import catalog_payload
                config_data["model_catalog"] = catalog_payload()
                await ws.send(json.dumps({
                    "type": "config_data",
                    "config": config_data,
                }, ensure_ascii=False))

        else:
            await self._send_error(ws, f"Unknown action: {action}")

    async def _send_event(self, ws: ServerConnection, event: Any, session_id: str | None = None) -> None:
        """Serialize an AgentEvent to JSON and send over WebSocket."""
        if isinstance(event, TextDelta) and event.text:
            await ws.send(json.dumps({
                "type": "text_delta",
                "text": event.text,
            }, ensure_ascii=False))

        elif isinstance(event, ThinkingDelta) and event.text:
            await ws.send(json.dumps({
                "type": "thinking_delta",
                "text": event.text,
            }, ensure_ascii=False))

        elif isinstance(event, ToolCallStart):
            await ws.send(json.dumps({
                "type": "tool_call_start",
                "name": event.name,
                "id": event.id,
            }, ensure_ascii=False))

        elif isinstance(event, ToolCallDelta):
            await ws.send(json.dumps({
                "type": "tool_call_delta",
                "id": event.id,
                "key": event.key,
                "value": event.value,
            }, ensure_ascii=False))

        elif isinstance(event, ToolCallEnd):
            await ws.send(json.dumps({
                "type": "tool_call_end",
                "id": event.id,
            }, ensure_ascii=False))

        elif isinstance(event, ToolProgress):
            await ws.send(json.dumps({
                "type": "tool_progress",
                "id": event.id,
                "tool_name": event.tool_name,
                "status": event.status,
            }, ensure_ascii=False))

        elif isinstance(event, ToolResult):
            content = event.content
            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated)"
            await ws.send(json.dumps({
                "type": "tool_result",
                "id": event.id,
                "content": content,
                "is_error": event.is_error,
            }, ensure_ascii=False))

        elif isinstance(event, PermissionRequest):
            await ws.send(json.dumps({
                "type": "permission_request",
                "tool_name": event.tool_name,
                "reason": event.reason,
            }, ensure_ascii=False))

        elif isinstance(event, EngineInstallRequest):
            # Sent to the desktop frontend when a tool needs the
            # user to install / provision a browser engine.  The
            # LLM is NOT involved: the renderer shows a native
            # dialog and echoes back an ``engine_install_response``
            # action with the same ``request_id``.
            payload: dict[str, Any] = {
                "type": "engine_install_request",
                "request_id": event.request_id,
                "engine": event.engine,
                "title": event.title,
                "body": event.body,
                "hint": event.hint,
                "options": list(event.options),
            }
            if event.title_code:
                payload["title_code"] = event.title_code
            if event.title_args:
                payload["title_args"] = dict(event.title_args)
            if event.body_code:
                payload["body_code"] = event.body_code
            if event.body_args:
                payload["body_args"] = dict(event.body_args)
            if event.hint_code:
                payload["hint_code"] = event.hint_code
            if event.hint_args:
                payload["hint_args"] = dict(event.hint_args)
            await ws.send(json.dumps(payload, ensure_ascii=False))

        elif isinstance(event, EngineInstallProgress):
            payload: dict[str, Any] = {
                "type": "engine_install_progress",
                "request_id": event.request_id,
                "pct": event.pct,
                "message": event.message,
                "sub_message": event.sub_message,
                "indeterminate": event.indeterminate,
                "status": event.status,
            }
            if event.message_code:
                payload["message_code"] = event.message_code
            if event.message_args:
                payload["message_args"] = dict(event.message_args)
            if event.sub_message_code:
                payload["sub_message_code"] = event.sub_message_code
            if event.sub_message_args:
                payload["sub_message_args"] = dict(event.sub_message_args)
            await ws.send(json.dumps(payload, ensure_ascii=False))

        elif isinstance(event, Finish):
            payload: dict[str, Any] = {
                "type": "finish",
                "reason": event.reason,
            }
            if session_id:
                payload["session_id"] = session_id
            if event.usage:
                payload["usage"] = event.usage
            if event.error:
                payload["error"] = event.error
            await ws.send(json.dumps(payload, ensure_ascii=False))

        elif isinstance(event, BackendError):
            await ws.send(json.dumps({
                "type": "error",
                "message": event.error,
                "code": "backend_error",
                "session_id": session_id or "",
            }, ensure_ascii=False))

    async def _send_error(self, ws: ServerConnection, message: str) -> None:
        await ws.send(json.dumps({
            "type": "error",
            "message": message,
        }, ensure_ascii=False))
