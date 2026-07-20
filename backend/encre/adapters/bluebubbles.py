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

#
# bluebubbles.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - BlueBubblesAdapter
#
import asyncio
import json
import logging
import os
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource

logger = logging.getLogger("encre.adapters.bluebubbles")

_BLUEBUBBLES_SSE_RECONNECT_DELAY = 5.0


class BlueBubblesAdapter(BaseAdapter):
    """BlueBubbles iMessage bridge adapter.

    Connects to a `BlueBubbles <https://bluebubbles.app>`_ server via its
    REST API and relays iMessage conversations to the Encre gateway for AI
    processing. The adapter authenticates with a password, listens for
    incoming messages via Server-Sent Events (SSE), and sends outgoing
    messages through the REST API.

    Requires:
        pip install httpx

    And a running BlueBubbles server::

        # BlueBubbles server running on default ports
        # REST: http://127.0.0.1:1234
        # Gateway WebSocket: ws://127.0.0.1:18792/gateway

    Args:
        server_url: The URL of the BlueBubbles REST API server.
        password: The BlueBubbles server password for authentication.
        gateway_url: Encre gateway WebSocket URL.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.bluebubbles import BlueBubblesAdapter  # noqa: E402

        async def main():
            adapter = BlueBubblesAdapter(
                server_url="http://127.0.0.1:1234",
                password="your-password",
            )
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "bluebubbles"

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:1234",
        password: str = "",
        *,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """
        Initialize the instance..

        Args:
            server_url (str):
            password (str):
            gateway_url (str):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text", "image", "file"])
        self._server_url = server_url.rstrip("/")
        self._password = password
        self._api_base = f"{self._server_url}/api/v1"
        self._http_client: httpx.AsyncClient | None = None
        self._sse_task: asyncio.Task | None = None
        self._last_sse_event = ""

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Authenticate with the BlueBubbles server and start the SSE listener."""
        if not HTTPX_AVAILABLE:
            logger.warning(
                "[bluebubbles] httpx not installed. Run: pip install httpx"
            )
            return False

        if not self._password:
            logger.error("[bluebubbles] No password configured")
            return False

        logger.info("[bluebubbles] Creating HTTP client")
        self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        logger.info("[bluebubbles] Authenticating with server")
        authenticated = await self._authenticate()
        if not authenticated:
            logger.error("[bluebubbles] Authentication failed")
            await self._http_client.aclose()
            self._http_client = None
            return False

        logger.info("[bluebubbles] Starting SSE listener")
        self._sse_task = asyncio.create_task(self._sse_listener())

        self._mark_connected()
        logger.info(
            "[bluebubbles] Connected to %s",
            self._server_url,
        )
        return True

    async def disconnect(self) -> None:
        """Disconnect from BlueBubbles and stop the SSE listener."""
        self._running = False

        if self._sse_task is not None:
            self._sse_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sse_task
            self._sse_task = None

        await self._logout()

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        await self._client.disconnect()
        logger.info("[bluebubbles] Disconnected")

    async def _authenticate(self) -> bool:
        """Authenticate with the BlueBubbles server using the configured password."""
        if self._http_client is None:
            return False
        try:
            resp = await self._http_client.post(
                f"{self._api_base}/auth/authenticate",
                json={"password": self._password},
                timeout=10.0,
            )
            if resp.status_code == 200:
                logger.info("[bluebubbles] Authentication successful")
                return True
            logger.warning(
                "[bluebubbles] Authentication failed HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        except httpx.TimeoutException:
            logger.error("[bluebubbles] Authentication timeout")
            return False
        except Exception as e:
            logger.error("[bluebubbles] Authentication error: %s", e)
            return False

    async def _logout(self) -> None:
        """Log out from the BlueBubbles server."""
        if self._http_client is None:
            return
        try:
            await self._http_client.post(
                f"{self._api_base}/auth/logout",
                timeout=10.0,
            )
        except Exception as e:
            logger.debug("[bluebubbles] Logout error: %s", e)

    # ── Outbound messaging ────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        _metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message via the BlueBubbles REST API.

        Posts to ``/api/v1/chat/send`` with the chat GUID and text content.
        If ``reply_to`` is provided, the message is sent as a reply to
        the specified message GUID.
        """
        if self._http_client is None:
            return SendResult(success=False, error="HTTP client not initialized")

        body: dict[str, Any] = {
            "chatGuid": chat_id,
            "text": content,
        }
        if reply_to is not None:
            body["selectedMessageGuid"] = reply_to

        try:
            resp = await self._http_client.post(
                f"{self._api_base}/chat/send",
                json=body,
                timeout=30.0,
            )
            if resp.status_code < 300:
                data = resp.json()
                message = data.get("message", {})
                msg_guid = message.get("guid", "")
                return SendResult(
                    success=True,
                    message_id=msg_guid or uuid.uuid4().hex[:12],
                    raw=data,
                )
            body_text = resp.text
            logger.warning(
                "[bluebubbles] send failed HTTP %d: %s",
                resp.status_code,
                body_text[:200],
            )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {body_text[:200]}",
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[bluebubbles] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Send an image attachment via the BlueBubbles REST API.

        Posts to ``/api/v1/chat/send-attachment`` with the chat GUID and
        the file path on the BlueBubbles server filesystem.

        Note:
            ``file_path`` refers to a path on the **BlueBubbles server**
            filesystem, not the local machine. The file must already be
            accessible to the BlueBubbles server.
        """
        if self._http_client is None:
            return SendResult(success=False, error="HTTP client not initialized")

        body: dict[str, Any] = {
            "chatGuid": chat_id,
            "filePath": file_path,
            "fileName": os.path.basename(file_path),
        }
        if caption is not None:
            body["text"] = caption

        try:
            resp = await self._http_client.post(
                f"{self._api_base}/chat/send-attachment",
                json=body,
                timeout=60.0,
            )
            if resp.status_code < 300:
                return SendResult(success=True, raw=resp.json())
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[bluebubbles] send_image error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Send a file/document attachment via the BlueBubbles REST API.

        Posts to ``/api/v1/chat/send-attachment`` with the chat GUID and
        the file path on the BlueBubbles server filesystem.

        Note:
            ``file_path`` refers to a path on the **BlueBubbles server**
            filesystem, not the local machine. The file must already be
            accessible to the BlueBubbles server.
        """
        if self._http_client is None:
            return SendResult(success=False, error="HTTP client not initialized")

        body: dict[str, Any] = {
            "chatGuid": chat_id,
            "filePath": file_path,
            "fileName": os.path.basename(file_path),
        }
        if caption is not None:
            body["text"] = caption
        if caption is None:
            body["text"] = ""

        try:
            resp = await self._http_client.post(
                f"{self._api_base}/chat/send-attachment",
                json=body,
                timeout=60.0,
            )
            if resp.status_code < 300:
                return SendResult(success=True, raw=resp.json())
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[bluebubbles] send_document error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator via the BlueBubbles REST API.

        Posts to ``/api/v1/chat/typing`` to indicate the bot is typing.
        """
        if self._http_client is None:
            return
        try:
            await self._http_client.post(
                f"{self._api_base}/chat/typing",
                json={"chatGuid": chat_id, "typing": True},
                timeout=10.0,
            )
        except Exception as e:
            logger.debug("[bluebubbles] send_typing error: %s", e)

    # ── SSE listener ──────────────────────────────────────────────────────

    async def _sse_listener(self) -> None:
        """Listen for incoming messages via the BlueBubbles SSE event stream."""
        while self._running:
            if self._http_client is None:
                logger.error("[bluebubbles] SSE listener: HTTP client unavailable")
                break

            try:
                async with self._http_client.stream(
                    "GET",
                    f"{self._api_base}/live/events",
                    headers={"Accept": "text/event-stream"},
                    timeout=None,
                ) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "[bluebubbles] SSE endpoint returned HTTP %d",
                            response.status_code,
                        )
                        await asyncio.sleep(_BLUEBUBBLES_SSE_RECONNECT_DELAY)
                        continue

                    logger.info("[bluebubbles] SSE listener started")
                    self._last_sse_event = ""
                    buffer = ""
                    async for line in response.aiter_lines():
                        if not self._running:
                            break
                        buffer = self._process_sse_line(line, buffer)
                    logger.info("[bluebubbles] SSE stream ended")
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "[bluebubbles] SSE error: %s (reconnecting in %.0fs)",
                    e,
                    _BLUEBUBBLES_SSE_RECONNECT_DELAY,
                )

            if self._running:
                await asyncio.sleep(_BLUEBUBBLES_SSE_RECONNECT_DELAY)

    def _process_sse_line(self, line: str, buffer: str) -> str:
        """Process a single SSE line. Returns the accumulated buffer."""
        if line.startswith("data: "):
            raw = line[6:]
            if buffer:
                raw = buffer + raw
            try:
                data = json.loads(raw)
                event_type = self._last_sse_event or data.get("event", "")
                self._last_sse_event = ""
                self._handle_event(event_type, data)
                return ""
            except json.JSONDecodeError:
                return raw
        elif line.startswith("event: "):
            self._last_sse_event = line[7:]
            return buffer
        elif line.strip() == "":
            return buffer
        return buffer

    def _handle_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Process a single SSE event from the BlueBubbles server."""
        try:
            if event_type != "message":
                return

            chat_guid = data.get("chatGuid", "")
            text = data.get("text", "")
            sender = data.get("sender", {}) or {}
            sender_guid = sender.get("guid", "")
            message_guid = data.get("guid", "") or data.get("id", "")
            timestamp_m = data.get("date", 0) or data.get("timestamp", 0)

            if not text or not chat_guid:
                return

            is_from_self = sender_guid and self._is_own_message(sender_guid)
            if is_from_self:
                return

            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                message_id=message_guid or uuid.uuid4().hex[:12],
                chat_id=chat_guid,
                user_id=sender_guid or chat_guid,
                raw=data,
                timestamp=(
                    datetime.fromtimestamp(timestamp_m / 1000)
                    if timestamp_m
                    else datetime.now()
                ),
                source=SessionSource(
                    platform=self.name,
                    chat_id=chat_guid,
                    chat_type="dm",
                    user_id=sender_guid or chat_guid,
                ),
            )

            task = asyncio.create_task(self._dispatch_event(event))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error("[bluebubbles] Error handling event: %s", e)

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.chat_id:
            try:
                await self.send_typing(event.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _is_own_message(_sender_guid: str) -> bool:
        """Check if the message was sent by the local user.

        Override this in a subclass to implement custom logic for detecting
        messages sent by the bot itself (e.g. by matching against the bot's
        Apple ID GUID).

        Returns:
            ``False`` by default -- all messages are treated as incoming.
        """
        return False
