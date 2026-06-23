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

import asyncio
import logging
import mimetypes
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.matrix")

MATRIX_SYNC_TIMEOUT = 30000
MATRIX_TYPING_TIMEOUT = 30000
MATRIX_RECONNECT_DELAY = 5.0
MATRIX_API_PATHS = {
    "login": "/_matrix/client/v3/login",
    "logout": "/_matrix/client/v3/logout",
    "sync": "/_matrix/client/v3/sync",
    "send": "/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
    "typing": "/_matrix/client/v3/rooms/{room_id}/typing/{user_id}",
    "upload": "/_matrix/media/v3/upload",
}


class MatrixAdapter(BaseAdapter):
    """Matrix bot adapter using the Matrix Client-Server API.

    Connects to a Matrix homeserver via password-based login and
    maintains a continuous sync loop to receive and process room
    messages. Outgoing messages are sent via the standard ``m.room.
    message`` event type.

    Requires:
        pip install httpx

    Args:
        homeserver: The Matrix homeserver URL (e.g.
            ``https://matrix-client.matrix.org``).
        user_id: The full Matrix user ID (e.g. ``@user:matrix.org``).
        password: The account password.
        device_id: Optional device identifier sent during login.
        gateway_url: Encre gateway WebSocket URL.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.matrix import MatrixAdapter  # noqa: E402

        async def main():
            adapter = MatrixAdapter(
                homeserver="https://matrix-client.matrix.org",
                user_id="@mybot:matrix.org",
                password="s3cret",
            )
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "matrix"

    def __init__(
        self,
        homeserver: str = "https://matrix-client.matrix.org",
        user_id: str = "",
        password: str = "",
        *,
        device_id: str = "",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text", "image"])
        self._homeserver = homeserver.rstrip("/")
        self._user_id = user_id
        self._password = password
        self._device_id = device_id
        self._access_token: str = ""
        self._sync_token: str = ""
        self._http_client: httpx.AsyncClient | None = None
        self._sync_task: asyncio.Task[Any] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._txn_counter = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Log into the Matrix homeserver and start the sync loop."""
        if not HTTPX_AVAILABLE:
            logger.warning(
                "[matrix] httpx not installed. Run: pip install httpx"
            )
            return False

        self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        logger.info("[matrix] HTTP client created, logging in to %s", self._homeserver)

        login_payload: dict[str, Any] = {
            "type": "m.login.password",
            "identifier": {
                "type": "m.id.user",
                "user": self._user_id,
            },
            "password": self._password,
        }
        if self._device_id:
            login_payload["device_id"] = self._device_id

        try:
            resp = await self._http_client.post(
                self._homeserver + MATRIX_API_PATHS["login"],
                json=login_payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "[matrix] Login failed HTTP %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return False

            data = resp.json()
            self._access_token = data.get("access_token", "")
            if not self._access_token:
                logger.error("[matrix] No access_token in login response")
                return False

            logged_user = data.get("user_id", self._user_id)
            logger.info("[matrix] Logged in as %s", logged_user)

            logger.info("[matrix] Starting sync loop")
            self._sync_task = asyncio.create_task(self._sync_loop())
            self._mark_connected()
            return True

        except httpx.TimeoutException:
            logger.error("[matrix] Login timed out")
            return False
        except Exception as e:
            logger.error("[matrix] Login error: %s", e)
            return False

    async def disconnect(self) -> None:
        """Log out of Matrix and stop the sync loop."""
        self._running = False

        if self._sync_task is not None:
            self._sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None

        if self._access_token and self._http_client:
            try:
                await self._http_client.post(
                    self._homeserver + MATRIX_API_PATHS["logout"],
                    headers=self._auth_headers,
                )
            except Exception as e:
                logger.warning("[matrix] Logout error: %s", e)

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        self._access_token = ""
        self._sync_token = ""

        await self._client.disconnect()
        logger.info("[matrix] Disconnected")

    # ── Outbound messaging ────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        _metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a Matrix room."""
        if not self._http_client or not self._access_token:
            return SendResult(success=False, error="Not connected")

        event_content: dict[str, Any] = {
            "msgtype": "m.text",
            "body": content,
        }
        if reply_to is not None:
            event_content["m.relates_to"] = {
                "m.in_reply_to": {
                    "event_id": reply_to,
                }
            }

        txn_id = self._next_txn_id()
        url = self._homeserver + MATRIX_API_PATHS["send"].format(
            room_id=chat_id,
            txn_id=txn_id,
        )

        try:
            resp = await self._http_client.put(
                url,
                json=event_content,
                headers=self._auth_headers,
            )
            if resp.status_code < 300:
                data = resp.json()
                event_id = data.get("event_id", "")
                return SendResult(
                    success=True,
                    message_id=event_id,
                    raw=data,
                )
            body_text = resp.text
            logger.warning(
                "[matrix] send failed HTTP %d: %s",
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
            logger.error("[matrix] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to a Matrix room."""
        if not self._http_client or not self._access_token:
            return

        url = self._homeserver + MATRIX_API_PATHS["typing"].format(
            room_id=chat_id,
            user_id=self._user_id,
        )
        payload = {
            "typing": True,
            "timeout": MATRIX_TYPING_TIMEOUT,
        }

        try:
            await self._http_client.put(
                url,
                json=payload,
                headers=self._auth_headers,
            )
        except Exception as e:
            logger.warning("[matrix] send_typing error: %s", e)

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Upload an image and send it as an m.image message."""
        if not self._http_client or not self._access_token:
            return SendResult(success=False, error="Not connected")

        try:
            mxc_url = await self._upload_media(file_path)
        except Exception as e:
            logger.error("[matrix] Image upload error: %s", e)
            return SendResult(
                success=False,
                error=f"Upload failed: {e}",
                retryable=True,
            )

        caption_text = caption or ""
        event_content: dict[str, Any] = {
            "msgtype": "m.image",
            "body": caption_text,
            "url": mxc_url,
        }

        txn_id = self._next_txn_id()
        url = self._homeserver + MATRIX_API_PATHS["send"].format(
            room_id=chat_id,
            txn_id=txn_id,
        )

        try:
            resp = await self._http_client.put(
                url,
                json=event_content,
                headers=self._auth_headers,
            )
            if resp.status_code < 300:
                data = resp.json()
                event_id = data.get("event_id", "")
                return SendResult(
                    success=True,
                    message_id=event_id,
                    raw=data,
                )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}",
                retryable=resp.status_code >= 500,
            )
        except Exception as e:
            logger.error("[matrix] send_image error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ── Sync loop ──────────────────────────────────────────────────────────

    async def _sync_loop(self) -> None:
        """Continuously call the Matrix /sync endpoint.

        Processes room timeline events and dispatches them as
        :class:`MessageEvent` instances.
        """
        while self._running:
            if not self._http_client:
                logger.error("[matrix] Sync loop: HTTP client unavailable")
                break

            params: dict[str, Any] = {
                "timeout": MATRIX_SYNC_TIMEOUT,
            }
            if self._sync_token:
                params["since"] = self._sync_token

            try:
                resp = await self._http_client.get(
                    self._homeserver + MATRIX_API_PATHS["sync"],
                    params=params,
                    headers=self._auth_headers,
                    timeout=MATRIX_SYNC_TIMEOUT / 1000 + 10.0,
                )

                if resp.status_code != 200:
                    logger.warning(
                        "[matrix] Sync returned HTTP %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    if resp.status_code == 401:
                        logger.error(
                            "[matrix] Access token expired, reconnecting..."
                        )
                        self._set_fatal_error("auth_expired", resp.text[:200])
                        break
                    await asyncio.sleep(MATRIX_RECONNECT_DELAY)
                    continue

                data = resp.json()
                self._sync_token = data.get("next_batch", self._sync_token)
                self._process_sync_data(data)

            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                continue
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "[matrix] Sync error: %s (reconnecting in %.0fs)",
                    e,
                    MATRIX_RECONNECT_DELAY,
                )
                await asyncio.sleep(MATRIX_RECONNECT_DELAY)

    def _process_sync_data(self, data: dict[str, Any]) -> None:
        """Process a sync response and dispatch room message events."""
        rooms = data.get("rooms", {})
        join_rooms = rooms.get("join", {})

        for room_id, room_data in join_rooms.items():
            timeline = room_data.get("timeline", {})
            events = timeline.get("events", [])

            for event in events:
                if event.get("type") != "m.room.message":
                    continue

                sender = event.get("sender", "")
                if sender == self._user_id:
                    continue

                self._handle_room_event(room_id, event)

    def _handle_room_event(self, room_id: str, event: dict[str, Any]) -> None:
        """Create a MessageEvent from a Matrix room event and dispatch it."""
        try:
            content = event.get("content", {})
            msgtype = content.get("msgtype", "")
            body = content.get("body", "")

            if not body:
                return

            event_id = event.get("event_id", "")
            sender = event.get("sender", "")
            ts = event.get("origin_server_ts", 0)

            message_type = MessageType.TEXT
            if msgtype == "m.image":
                message_type = MessageType.IMAGE

            reply_to_message_id: str | None = None
            reply_to_text: str | None = None
            relates_to = content.get("m.relates_to")
            if isinstance(relates_to, dict):
                in_reply_to = relates_to.get("m.in_reply_to")
                if isinstance(in_reply_to, dict):
                    reply_to_message_id = in_reply_to.get("event_id")

            timestamp = (
                datetime.fromtimestamp(ts / 1000, tz=UTC)
                if ts
                else datetime.now(UTC)
            )

            msg_event = MessageEvent(
                text=body,
                message_type=message_type,
                message_id=event_id,
                chat_id=room_id,
                user_id=sender,
                reply_to_message_id=reply_to_message_id,
                reply_to_text=reply_to_text,
                raw=event,
                timestamp=timestamp,
            )

            logger.debug(
                "[matrix] Message from %s in %s: %s",
                sender,
                room_id,
                body[:80],
            )

            self.dispatch_message(msg_event)

            task = asyncio.create_task(
                self._process_chat(room_id, body)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        except Exception as e:
            logger.error("[matrix] Error handling room event: %s", e)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response."""
        session_id = self.get_session(chat_id)
        await self.send_typing(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    # ── Media helpers ─────────────────────────────────────────────────────

    async def _upload_media(self, file_path: str) -> str:
        """Upload a file to the Matrix media repository.

        Returns the ``mxc://`` content URI.

        Raises:
            FileNotFoundError: If the file does not exist.
            httpx.HTTPStatusError: If the upload fails.
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        content_type = mime_type or "application/octet-stream"

        headers = dict(self._auth_headers)
        headers["Content-Type"] = content_type

        url = self._homeserver + MATRIX_API_PATHS["upload"]

        with open(file_path, "rb") as f:
            resp = await self._http_client.post(
                url,
                content=f,
                headers=headers,
            )

        if resp.status_code >= 300:
            raise httpx.HTTPStatusError(
                f"Upload failed HTTP {resp.status_code}",
                request=resp.request,
                response=resp,
            )

        data = resp.json()
        content_uri = data.get("content_uri", "")
        if not content_uri:
            raise ValueError("No content_uri in upload response")
        return content_uri

    # ── Internal helpers ──────────────────────────────────────────────────

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
        }

    def _next_txn_id(self) -> str:
        """Generate a unique transaction ID for event sending."""
        self._txn_counter += 1
        return f"encre-{self._txn_counter}-{uuid.uuid4().hex[:8]}"
