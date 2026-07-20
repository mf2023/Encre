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
# msgraph.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - MSGraphAdapter
#
import asyncio
import contextlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any
from urllib.parse import parse_qs

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource

logger = logging.getLogger("encre.adapters.msgraph")

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = Any  # type: ignore[misc,assignment]

MSGRAPH_AUTH_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
MSGRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
MSGRAPH_SUBSCRIPTIONS_URL = f"{MSGRAPH_API_BASE}/subscriptions"


class MSGraphAdapter(BaseAdapter):
    """
    MSGraphAdapter adapter component.
    
    Inherits from BaseAdapter and integrates an external platform or
    channel into the Encre adapter framework. It implements the standard
    adapter contract used by the manager to connect, send and receive
    messages, and to dispatch normalized events into the agent runtime.
    
    Responsibilities:
        * Establish and maintain a connection/session to the platform.
        * Translate inbound platform events into normalized messages.
        * Translate outbound messages into platform-specific API calls.
        * Expose lifecycle hooks (connect/disconnect, start/stop).
    """
    name = "msgraph"

    MAX_MESSAGE_LENGTH = 28000

    def __init__(
        self,
        *,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        host: str = "127.0.0.1",
        port: int = 8646,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """
        Initialize the instance..

        Args:
            tenant_id (str):
            client_id (str):
            client_secret (str):
            host (str):
            port (int):
            gateway_url (str):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        self._tenant_id = tenant_id or os.getenv("MSGRAPH_TENANT_ID", "")
        self._client_id = client_id or os.getenv("MSGRAPH_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("MSGRAPH_CLIENT_SECRET", "")
        self._host = host or os.getenv("MSGRAPH_WEBHOOK_HOST", "127.0.0.1")
        self._port = port or int(os.getenv("MSGRAPH_WEBHOOK_PORT", "8646"))

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._subscription_id: str | None = None
        self._client_state: str = ""
        self._server: asyncio.AbstractServer | None = None
        self._http: Any = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Token Management ──────────────────────────────────────────────────

    async def _get_access_token(self) -> str | None:
        """
        Get access token.

        Returns:
            str | None
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self._tenant_id or not self._client_id or not self._client_secret:
            logger.error("[msgraph] Missing tenant_id, client_id, or client_secret")
            return None

        client = self._get_http_client()
        if client is None:
            return None

        token_url = MSGRAPH_AUTH_URL.format(tenant_id=self._tenant_id)
        try:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            data = resp.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            if not token:
                error_desc = data.get("error_description", "unknown error")
                logger.error("[msgraph] Token acquisition failed: %s", error_desc)
                return None
            self._access_token = token
            self._token_expires_at = time.time() + expires_in - 60
            logger.info("[msgraph] Access token acquired (expires in %ds)", expires_in)
            return token
        except Exception as e:
            logger.error("[msgraph] Token acquisition error: %s", e)
            return None

    # ── Subscription Management ───────────────────────────────────────────

    async def _create_subscription(self) -> str | None:
        """
        Create subscription.

        Returns:
            str | None
        """
        client = self._get_http_client()
        if client is None:
            return None

        token = await self._get_access_token()
        if not token:
            return None

        self._client_state = str(uuid.uuid4())
        notification_url = os.getenv(
            "MSGRAPH_NOTIFICATION_URL",
            f"http://{self._host}:{self._port}/webhook/msgraph",
        )

        expiration = int(time.time()) + 3600
        body = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": "/communications/presences",
            "expirationDateTime": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(expiration)
            ),
            "clientState": self._client_state,
        }

        try:
            resp = await client.post(
                MSGRAPH_SUBSCRIPTIONS_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            sub_id = data.get("id")
            if sub_id:
                logger.info("[msgraph] Subscription created: %s", sub_id)
                self._subscription_id = sub_id
                return sub_id
            error_msg = data.get("error", {}).get("message", "unknown error")
            logger.error("[msgraph] Subscription creation failed: %s", error_msg)
            return None
        except Exception as e:
            logger.error("[msgraph] Subscription creation error: %s", e)
            return None

    async def _delete_subscription(self) -> bool:
        """
        Delete subscription.

        Returns:
            bool
        """
        if not self._subscription_id:
            return True

        client = self._get_http_client()
        if client is None:
            return False

        token = await self._get_access_token()
        if not token:
            return False

        url = f"{MSGRAPH_SUBSCRIPTIONS_URL}/{self._subscription_id}"
        try:
            resp = await client.delete(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code in (204, 200):
                logger.info(
                    "[msgraph] Subscription deleted: %s", self._subscription_id
                )
            else:
                logger.warning(
                    "[msgraph] Subscription deletion returned %d: %s",
                    resp.status_code,
                    resp.text,
                )
            self._subscription_id = None
            return True
        except Exception as e:
            logger.error("[msgraph] Subscription deletion error: %s", e)
            self._subscription_id = None
            return False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Connect.

        Returns:
            bool
        """
        if not HTTPX_AVAILABLE:
            logger.error(
                "[msgraph] httpx is required. Install with: pip install httpx"
            )
            return False

        logger.info("[msgraph] Acquiring access token")
        token = await self._get_access_token()
        if not token:
            logger.error("[msgraph] Failed to obtain access token")
            return False

        logger.info("[msgraph] Starting webhook server")
        await self._start_webhook_server()
        logger.info("[msgraph] Creating subscription")
        sub_id = await self._create_subscription()
        if not sub_id:
            logger.warning(
                "[msgraph] Subscription creation failed, continuing without notifications"
            )

        logger.info("[msgraph] Connecting to Encre gateway")
        result = await super().connect()
        logger.info(
            "[msgraph] Connected (host=%s, port=%d, subscription=%s)",
            self._host,
            self._port,
            self._subscription_id or "none",
        )
        return result

    async def disconnect(self) -> None:
        """
        Disconnect.

        Returns:
            None
        """
        self._running = False
        for task in list(self._background_tasks):
            task.cancel()
        await self._delete_subscription()
        await self._stop_webhook_server()
        await super().disconnect()

    async def _on_connected(self) -> None:
        """
        On connected.

        Returns:
            None
        """
        logger.info("[msgraph] Gateway connected")

    async def _on_disconnected(self) -> None:
        """
        On disconnected.

        Returns:
            None
        """
        logger.info("[msgraph] Gateway disconnected")

    # ── Messaging ─────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """
        Send.

        Args:
            chat_id (str):
            content (str):
            reply_to (str | None):
            metadata (dict[str, Any] | None):

        Returns:
            SendResult
        """
        client = self._get_http_client()
        if client is None:
            return SendResult(success=False, error="httpx not available")

        token = await self._get_access_token()
        if not token:
            return SendResult(
                success=False,
                error="No valid access token",
                retryable=True,
            )

        if "@" in chat_id and "." in chat_id.split("@")[-1]:
            return await self._send_email(client, token, chat_id, content, metadata)

        if ":" in chat_id:
            team_id, channel_id = chat_id.split(":", 1)
            return await self._send_teams_channel_message(
                client, token, team_id, channel_id, content, reply_to
            )

        return await self._send_chat_message(client, token, chat_id, content, reply_to)

    async def _send_teams_channel_message(
        self,
        client: Any,
        token: str,
        team_id: str,
        channel_id: str,
        content: str,
        reply_to: str | None = None,
    ) -> SendResult:
        """
        Send teams channel message.

        Args:
            client (Any):
            token (str):
            team_id (str):
            channel_id (str):
            content (str):
            reply_to (str | None):

        Returns:
            SendResult
        """
        url = f"{MSGRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages"
        body: dict[str, Any] = {
            "body": {
                "contentType": "text",
                "content": content,
            },
        }
        if reply_to:
            body["replyToId"] = reply_to

        try:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                msg_id = data.get("id", "")
                return SendResult(success=True, message_id=msg_id, raw=data)
            error_msg = data.get("error", {}).get("message", "unknown error")
            logger.error("[msgraph] Teams channel send error: %s", error_msg)
            return SendResult(
                success=False,
                error=f"Teams channel error: {error_msg}",
                raw=data,
                retryable=True,
            )
        except Exception as e:
            logger.error("[msgraph] Teams channel send exception: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def _send_chat_message(
        self,
        client: Any,
        token: str,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
    ) -> SendResult:
        """
        Send chat message.

        Args:
            client (Any):
            token (str):
            chat_id (str):
            content (str):
            reply_to (str | None):

        Returns:
            SendResult
        """
        url = f"{MSGRAPH_API_BASE}/chats/{chat_id}/messages"
        body: dict[str, Any] = {
            "body": {
                "contentType": "text",
                "content": content,
            },
        }
        if reply_to:
            body["replyToId"] = reply_to

        try:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                msg_id = data.get("id", "")
                return SendResult(success=True, message_id=msg_id, raw=data)
            error_msg = data.get("error", {}).get("message", "unknown error")
            logger.error("[msgraph] Chat send error: %s", error_msg)
            return SendResult(
                success=False,
                error=f"Chat error: {error_msg}",
                raw=data,
                retryable=True,
            )
        except Exception as e:
            logger.error("[msgraph] Chat send exception: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def _send_email(
        self,
        client: Any,
        token: str,
        recipient: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """
        Send email.

        Args:
            client (Any):
            token (str):
            recipient (str):
            content (str):
            metadata (dict[str, Any] | None):

        Returns:
            SendResult
        """
        url = f"{MSGRAPH_API_BASE}/me/sendMail"
        subject = "Message from Encre AI"
        if metadata and "subject" in metadata:
            subject = str(metadata["subject"])
        else:
            first_line = content.split("\n")[0].strip()
            if first_line:
                subject = first_line if len(first_line) <= 80 else first_line[:77] + "..."

        body: dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": content,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": recipient,
                        },
                    },
                ],
            },
        }

        try:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code in (200, 202):
                return SendResult(success=True)
            data = resp.json()
            error_msg = data.get("error", {}).get("message", "unknown error")
            logger.error("[msgraph] Email send error: %s", error_msg)
            return SendResult(
                success=False,
                error=f"Email error: {error_msg}",
                raw=data,
                retryable=True,
            )
        except Exception as e:
            logger.error("[msgraph] Email send exception: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ── Webhook Server ────────────────────────────────────────────────────

    async def _start_webhook_server(self) -> None:
        """
        Start webhook server.

        Returns:
            None
        """
        try:
            self._server = await asyncio.start_server(
                self._handle_http_connection,
                host=self._host,
                port=self._port,
            )
            logger.info(
                "[msgraph] Webhook server listening on %s:%d",
                self._host,
                self._port,
            )
        except Exception as e:
            logger.error("[msgraph] Failed to start webhook server: %s", e)
            self._server = None

    async def _stop_webhook_server(self) -> None:
        """
        Stop webhook server.

        Returns:
            None
        """
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("[msgraph] Webhook server stopped")

    async def _handle_http_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle http connection.

        Args:
            reader (asyncio.StreamReader):
            writer (asyncio.StreamWriter):

        Returns:
            None
        """
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not request_line:
                writer.close()
                return

            line_str = request_line.decode("utf-8", errors="replace").strip()
            parts = line_str.split(" ", 2)
            if len(parts) != 3:
                writer.close()
                return
            method, path, _ = parts

            headers: dict[str, str] = {}
            while True:
                header_line = await asyncio.wait_for(reader.readline(), timeout=5)
                decoded = header_line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    break
                if ":" in decoded:
                    key, value = decoded.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            content_length = int(headers.get("content-length", "0"))
            body = b""
            if content_length > 0:
                body = await asyncio.wait_for(
                    reader.readexactly(content_length), timeout=10
                )

            if path.startswith("/webhook/msgraph"):
                if method == "GET":
                    response_body, status = await self._handle_validation(path)
                elif method == "POST":
                    response_body, status = await self._handle_notification(body)
                else:
                    response_body = json.dumps({"error": "method not allowed"}).encode()
                    status = 405
            else:
                response_body = json.dumps({"error": "not found"}).encode()
                status = 404

            status_text = {
                200: "OK",
                202: "Accepted",
                400: "Bad Request",
                401: "Unauthorized",
                404: "Not Found",
                405: "Method Not Allowed",
                500: "Internal Server Error",
            }.get(status, "Internal Server Error")

            response_headers = (
                f"HTTP/1.1 {status} {status_text}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(response_body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            writer.write(response_headers + response_body)
            await writer.drain()
        except TimeoutError:
            pass
        except Exception as e:
            logger.debug("[msgraph] HTTP handler error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    async def _handle_validation(
        self,
        path: str,
    ) -> tuple[bytes, int]:
        """
        Handle validation.

        Args:
            path (str):

        Returns:
            tuple[bytes, int]
        """
        query_string = ""
        if "?" in path:
            query_string = path.split("?", 1)[1]
        params = parse_qs(query_string)
        validation_tokens = params.get("validationToken", [])
        if not validation_tokens:
            return json.dumps({"error": "missing validationToken"}).encode(), 400

        token_value = validation_tokens[0]
        logger.info("[msgraph] Validation request received, echoing token")
        response_body = token_value.encode("utf-8")
        return response_body, 200

    async def _handle_notification(
        self,
        body: bytes,
    ) -> tuple[bytes, int]:
        """
        Handle notification.

        Args:
            body (bytes):

        Returns:
            tuple[bytes, int]
        """
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return json.dumps({"error": "invalid JSON"}).encode(), 400

        values = payload.get("value", [])
        if not isinstance(values, list) or not values:
            logger.warning("[msgraph] Notification with no value array")
            return json.dumps({"error": "no values"}).encode(), 200

        for notification in values:
            client_state = notification.get("clientState", "")
            if self._client_state and client_state and client_state != self._client_state:
                logger.warning("[msgraph] Client state mismatch, ignoring notification")
                continue

            change_type = notification.get("changeType", "")
            resource = notification.get("resource", "")
            resource_data = notification.get("resourceData", {})

            if change_type != "created" or not resource:
                continue

            task = asyncio.ensure_future(
                self._process_notification(resource, resource_data, notification)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        return json.dumps({"ok": True}).encode(), 202

    async def _process_notification(
        self,
        resource: str,
        resource_data: dict[str, Any],
        raw_notification: dict[str, Any],
    ) -> None:
        """
        Process notification.

        Args:
            resource (str):
            resource_data (dict[str, Any]):
            raw_notification (dict[str, Any]):

        Returns:
            None
        """
        client = self._get_http_client()
        if client is None:
            return

        token = await self._get_access_token()
        if not token:
            return

        try:
            resource_url = f"{MSGRAPH_API_BASE}/{resource.lstrip('/')}"
            resp = await client.get(
                resource_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "[msgraph] Failed to fetch resource %s (status=%d)",
                    resource,
                    resp.status_code,
                )
                return

            message_data = resp.json()
            await self._dispatch_from_message_data(
                message_data, resource, resource_data, raw_notification
            )
        except Exception as e:
            logger.error("[msgraph] Failed to process notification: %s", e)

    async def _dispatch_from_message_data(
        self,
        message_data: dict[str, Any],
        resource: str,
        resource_data: dict[str, Any],
        raw_notification: dict[str, Any],
    ) -> None:
        """
        Dispatch from message data.

        Args:
            message_data (dict[str, Any]):
            resource (str):
            resource_data (dict[str, Any]):
            raw_notification (dict[str, Any]):

        Returns:
            None
        """
        try:
            message_id = message_data.get("id", "") or resource_data.get("id", "")
            content_body = message_data.get("body", {})
            text = ""
            content_type = "text"
            if isinstance(content_body, dict):
                text = content_body.get("content", "")
                content_type = content_body.get("contentType", "text")
            elif isinstance(content_body, str):
                text = content_body

            if content_type == "html":
                text = re.sub(r"<[^>]+>", "", text)
                text = text.replace("&nbsp;", " ").replace("&amp;", "&")

            from_prop = message_data.get("from", {})
            user_id = ""
            if isinstance(from_prop, dict):
                user_prop = from_prop.get("user", from_prop)
                if isinstance(user_prop, dict):
                    user_id = user_prop.get("id", "") or user_prop.get("displayName", "")

            chat_id = self._extract_chat_id(resource, message_data)

            reply_to_id: str | None = None
            reply_to = message_data.get("replyToId") or message_data.get("replyTo")
            if reply_to:
                reply_to_id = str(reply_to)

            if not text and not user_id:
                return

            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                message_id=message_id,
                chat_id=chat_id,
                user_id=user_id or "unknown",
                reply_to_message_id=reply_to_id,
                raw=raw_notification,
                source=SessionSource(
                    platform=self.name,
                    chat_id=chat_id,
                    chat_type="dm",
                    user_id=user_id or "unknown",
                ),
            )

            task = asyncio.create_task(
                self._dispatch_event(event)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error("[msgraph] dispatch_from_message_data error: %s", e)

    @staticmethod
    def _extract_chat_id(
        resource: str,
        message_data: dict[str, Any],
    ) -> str:
        """
        Extract chat id.

        Args:
            resource (str):
            message_data (dict[str, Any]):

        Returns:
            str
        """
        chat_id = message_data.get("chatId", "")
        if chat_id:
            return chat_id

        channel_identity = message_data.get("channelIdentity", {})
        if isinstance(channel_identity, dict):
            team_id = channel_identity.get("teamId", "")
            chan_id = channel_identity.get("channelId", "")
            if team_id and chan_id:
                return f"{team_id}:{chan_id}"

        parts = resource.strip("/").split("/")
        for i, part in enumerate(parts):
            if part == "teams" and i + 1 < len(parts):
                team_id = parts[i + 1]
                if i + 2 < len(parts) and parts[i + 2] == "channels" and i + 3 < len(parts):
                    channel_ident = parts[i + 3]
                    return f"{team_id}:{channel_ident}"
                return team_id
            if part == "chats" and i + 1 < len(parts):
                return parts[i + 1]

        return resource

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.chat_id:
            try:
                await self.send_typing(event.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """
        Process chat.

        Args:
            chat_id (str):
            content (str):

        Returns:
            None
        """
        session_id = self.get_session(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    # ── HTTP Client ───────────────────────────────────────────────────────

    def _get_http_client(self) -> Any | None:
        """
        Get http client.

        Returns:
            Any | None
        """
        if self._http is not None:
            return self._http
        if not HTTPX_AVAILABLE:
            logger.error(
                "[msgraph] httpx is required. Install with: pip install httpx"
            )
            return None
        self._http = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Encre/1.0.0"},
        )
        return self._http
