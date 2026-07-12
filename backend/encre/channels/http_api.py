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

"""Encre agent channels: REST / NDJSON HTTP transport.

Implements :class:`HTTPChannel`, a lightweight HTTP server exposing the agent
to headless clients and tests.  ``POST /chat`` either returns the full
response as JSON or streams server-sent NDJSON events; ``GET /health``,
``GET /sessions``, ``DELETE /sessions/:id`` and ``POST /sessions/:id/cancel``
mirror the desktop client's management actions.
"""

import asyncio
import json
import logging
from typing import Any

from encre.channels.base import Channel, EventRouter
from encre.utils.types import Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.channels.http")


class HTTPChannel(Channel):
    """REST API channel with session management.

    Endpoints:
      GET  /health          -- health check
      GET  /sessions        -- list sessions from index
      POST /chat            -- submit prompt, returns JSON or NDJSON stream
      DELETE /sessions/:id  -- delete a session from disk
      POST /sessions/:id/cancel -- cancel a running session
    """

    name = "http_api"

    def __init__(self, host: str = "127.0.0.1", port: int = 18792) -> None:
        self._host = host
        self._port = port
        self._server: asyncio.AbstractServer | None = None
        self._router: EventRouter | None = None

    async def start(self, router: EventRouter) -> None:
        self._router = router
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
        )
        logger.info(
            "HTTP API channel ready: http://%s:%s",
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return
            request_str = request_line.decode("utf-8").strip()
            parts = request_str.split(" ")
            if len(parts) < 2:
                self._respond(writer, 400, {"error": "Bad request"})
                return
            method, path = parts[0], parts[1]

            # Parse headers
            headers: dict[str, str] = {}
            while True:
                header_line = await reader.readline()
                header_str = header_line.decode("utf-8").strip()
                if not header_str:
                    break
                if ":" in header_str:
                    key, value = header_str.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Read body
            content_length = int(headers.get("content-length", "0"))
            body = ""
            if content_length > 0 and content_length < 10 * 1024 * 1024:
                raw_body = await reader.readexactly(content_length)
                body = raw_body.decode("utf-8")

            await self._route(method, path, body, headers, writer)

        except Exception as e:
            logger.error("HTTP client error: %s", e)
            self._respond(writer, 500, {"error": str(e)})
        finally:
            writer.close()

    async def _route(
        self,
        method: str,
        path: str,
        body: str,
        headers: dict[str, str],
        writer: asyncio.StreamWriter,
    ) -> None:
        """Map an HTTP method + path to a channel action.

        Implements ``GET /health``, ``GET /sessions``,
        ``DELETE /sessions/:id``, ``POST /sessions/:id/cancel`` and
        ``POST /chat`` (delegating to :meth:`_handle_chat`).
        """
        router = self._router

        # GET /health
        if method == "GET" and path == "/health":
            self._respond(writer, 200, {
                "status": "ok",
                "active_sessions": self._router.session_manager.active_count if self._router else 0,
            })
            return

        # GET /sessions
        if method == "GET" and path == "/sessions":
            if router is None:
                self._respond(writer, 503, {"error": "Not ready"})
                return
            sessions = router.session_manager.query_index()
            self._respond(writer, 200, {"sessions": sessions})
            return

        # DELETE /sessions/:id
        if method == "DELETE" and path.startswith("/sessions/"):
            if router is None:
                self._respond(writer, 503, {"error": "Not ready"})
                return
            sid = path.split("/sessions/", 1)[1]
            router.cancel_session(sid)
            ok = router.session_manager.delete_session_from_disk(sid)
            if ok:
                self._respond(writer, 200, {"deleted": sid})
            else:
                self._respond(writer, 404, {"error": "Session not found"})
            return

        # POST /sessions/:id/cancel
        if method == "POST" and path.endswith("/cancel") and "/sessions/" in path:
            if router is None:
                self._respond(writer, 503, {"error": "Not ready"})
                return
            sid = path.split("/sessions/", 1)[1].rsplit("/cancel", 1)[0]
            if router.cancel_session(sid):
                self._respond(writer, 200, {"cancelled": sid})
            else:
                self._respond(writer, 404, {"error": "Session not found or not running"})
            return

        # POST /chat
        if method == "POST" and path == "/chat":
            if router is None:
                self._respond(writer, 503, {"error": "Not ready"})
                return
            await self._handle_chat(body, headers, writer)
            return

        self._respond(writer, 404, {"error": "Not found"})

    async def _handle_chat(
        self,
        body: str,
        _headers: dict[str, str],
        writer: asyncio.StreamWriter,
    ) -> None:
        router = self._router
        if router is None:
            self._respond(writer, 503, {"error": "Router not ready"})
            return

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._respond(writer, 400, {"error": "Invalid JSON"})
            return

        prompt = data.get("prompt", "")
        if not prompt.strip():
            self._respond(writer, 400, {"error": "Empty prompt"})
            return

        session_id = data.get("session_id")
        system_prompt = data.get("system_prompt")
        stream = data.get("stream", False)

        if stream:
            self._write_status(writer, 200, "application/x-ndjson")
            try:
                async for event in router.submit_stream(
                    self.name, prompt,
                    session_id=session_id,
                    system_prompt=system_prompt,
                ):
                    if isinstance(event, TextDelta) and event.text:
                        line = json.dumps({"type": "delta", "content": event.text}, ensure_ascii=False) + "\n"
                        writer.write(line.encode("utf-8"))
                    elif isinstance(event, ToolResult):
                        line = json.dumps({
                            "type": "tool_result",
                            "id": event.id,
                            "content": event.content[:500],
                        }, ensure_ascii=False) + "\n"
                        writer.write(line.encode("utf-8"))
                    elif isinstance(event, Finish):
                        payload: dict[str, Any] = {"type": "finish", "reason": event.reason}
                        if event.usage:
                            payload["usage"] = event.usage
                        line = json.dumps(payload, ensure_ascii=False) + "\n"
                        writer.write(line.encode("utf-8"))
                await writer.drain()
            except Exception as e:
                logger.error("HTTP stream error: %s", e)
        else:
            result = await router.submit(
                self.name, prompt,
                session_id=session_id,
                system_prompt=system_prompt,
            )
            # Get the session_id used
            info = router.session_manager.create_session()
            router.session_manager.remove_session(info.session_id)
            self._respond(writer, 200, {
                "response": result,
                "session_id": session_id,
            })

    # ── HTTP helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _respond(writer: asyncio.StreamWriter, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False)
        HTTPChannel._write_status(writer, status, "application/json")
        writer.write(body.encode("utf-8"))
        writer.write(b"\r\n")

    @staticmethod
    def _write_status(writer: asyncio.StreamWriter, status: int, content_type: str) -> None:
        status_map = {
            200: b"200 OK",
            400: b"400 Bad Request",
            404: b"404 Not Found",
            500: b"500 Internal Server Error",
            503: b"503 Service Unavailable",
        }
        status_line = status_map.get(status, b"200 OK")
        headers = (
            f"HTTP/1.1 {status_line.decode()}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(headers.encode("utf-8"))
