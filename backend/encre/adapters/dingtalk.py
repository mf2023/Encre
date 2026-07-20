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
# dingtalk.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - DingTalkAdapter
#   - _IncomingHandler
#
import asyncio
import json
import logging
import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

try:
    import dingtalk_stream
    from dingtalk_stream import ChatbotMessage
    from dingtalk_stream.frames import AckMessage, CallbackMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    dingtalk_stream = None
    ChatbotMessage = None
    CallbackMessage = None
    AckMessage = type(
        "AckMessage",
        (),
        {
            "STATUS_OK": 200,
            "STATUS_SYSTEM_EXCEPTION": 500,
        },
    )

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource

logger = logging.getLogger("encre.adapters.dingtalk")

_DINGTALK_WEBHOOK_RE = re.compile(r"^https://(?:api|oapi)\.dingtalk\.com/")
_MAX_MESSAGE_LENGTH = 20000
_SESSION_WEBHOOKS_MAX = 500
_RECONNECT_BACKOFF = [2, 5, 10, 30, 60]


class DingTalkAdapter(BaseAdapter):
    """DingTalk chatbot adapter using Stream Mode.

    Uses the ``dingtalk-stream`` SDK (>=0.20) for real-time message
    reception via a long-lived WebSocket connection.  Replies are sent
    via session webhooks (markdown format) attached to each incoming
    message, with a fallback to the DingTalk Open API batchSend endpoint.

    Requires:
        pip install dingtalk-stream httpx

    Args:
        client_id: DingTalk application Client ID (AppKey).
        client_secret: DingTalk application Client Secret (AppSecret).
        gateway_url: Encre gateway WebSocket URL.
    """

    name = "dingtalk"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """
        Initialize the instance..

        Args:
            client_id (str):
            client_secret (str):
            gateway_url (str):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text", "markdown"])
        self._client_id = client_id
        self._client_secret = client_secret
        self._stream_client: Any = None
        self._stream_task: asyncio.Task | None = None
        self._gateway_task: asyncio.Task | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._session_webhooks: dict[str, tuple[str, int]] = {}
        self._robot_code: str = client_id

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to DingTalk via Stream Mode and to the Encre gateway."""
        if not DINGTALK_AVAILABLE:
            logger.warning(
                "[dingtalk] dingtalk-stream not installed. Run: pip install dingtalk-stream>=0.20"
            )
            return False
        if not HTTPX_AVAILABLE:
            logger.warning(
                "[dingtalk] httpx not installed. Run: pip install httpx"
            )
            return False
        if not self._client_id or not self._client_secret:
            logger.warning("[dingtalk] client_id and client_secret are required")
            return False

        try:
            logger.info("[dingtalk] Step 1/4: Initializing HTTP client...")
            self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, proxy=BaseAdapter.resolve_proxy_url())
            logger.info("[dingtalk] Step 1/4: HTTP client ready")

            logger.info("[dingtalk] Step 2/4: Creating DingTalk stream client...")
            credential = dingtalk_stream.Credential(
                self._client_id, self._client_secret
            )
            self._stream_client = dingtalk_stream.DingTalkStreamClient(credential)

            loop = asyncio.get_running_loop()
            handler = _IncomingHandler(self, loop)
            self._stream_client.register_callback_handler(
                dingtalk_stream.ChatbotMessage.TOPIC, handler
            )
            logger.info("[dingtalk] Step 2/4: Stream client created")

            logger.info("[dingtalk] Step 3/4: Starting stream background task...")
            self._stream_task = asyncio.create_task(self._run_stream())
            logger.info("[dingtalk] Step 3/4: Stream task started")

            logger.info("[dingtalk] Step 4/4: Refreshing access token...")
            self._access_token = await self._refresh_token()
            logger.info("[dingtalk] Step 4/4: Token refreshed")

            self._running = True
            self._gateway_task = asyncio.ensure_future(self._client.connect())
            logger.info("[dingtalk] Connected via Stream Mode")
            return True
        except Exception as e:
            logger.error("[dingtalk] Failed to connect: %s", e)
            return False

    async def disconnect(self) -> None:
        """Disconnect from DingTalk and the Encre gateway."""
        self._running = False

        websocket = (
            getattr(self._stream_client, "websocket", None)
            if self._stream_client
            else None
        )
        if websocket is not None:
            with suppress(Exception):
                await websocket.close()

        if self._stream_task:
            if hasattr(self._stream_client, "close"):
                with suppress(Exception):
                    await asyncio.to_thread(self._stream_client.close)
            self._stream_task.cancel()
            with suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._stream_task, timeout=5.0)
            self._stream_task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._stream_client = None
        self._session_webhooks.clear()
        self._access_token = None

        await self._client.disconnect()
        logger.info("[dingtalk] Disconnected")

    async def _run_stream(self) -> None:
        """Run the dingtalk-stream client with exponential-backoff reconnection."""
        logger.info("[dingtalk] _run_stream STARTING, stream_client=%s", self._stream_client is not None)
        backoff_idx = 0
        while self._running:
            try:
                logger.info("[dingtalk] calling stream_client.start()...")
                await self._stream_client.start()
                logger.info("[dingtalk] stream_client.start() returned (unexpected)")
            except asyncio.CancelledError:
                return
            except Exception as e:
                if not self._running:
                    return
                logger.warning("[dingtalk] Stream client error: %s %s", type(e).__name__, e)

            if not self._running:
                return

            delay = _RECONNECT_BACKOFF[
                min(backoff_idx, len(_RECONNECT_BACKOFF) - 1)
            ]
            logger.info("[dingtalk] Reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            backoff_idx += 1

    # ── Token management ─────────────────────────────────────────────────

    async def _refresh_token(self) -> str | None:
        """Refresh the DingTalk access token via the stream client."""
        if not self._stream_client:
            return None
        try:
            token = await asyncio.to_thread(self._stream_client.get_access_token)
            self._access_token = token
            return token
        except Exception as e:
            logger.error("[dingtalk] Failed to refresh access token: %s", e)
            return None

    # ── Inbound message handling ─────────────────────────────────────────

    async def _on_stream_message(self, data: dict[str, Any]) -> None:
        """Process an incoming DingTalk stream message and dispatch it."""
        logger.info("[dingtalk] _on_stream_message data keys=%s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
        try:
            message = ChatbotMessage.from_dict(data) if ChatbotMessage else None
            if message is None:
                return

            msg_id = getattr(message, "message_id", None) or uuid.uuid4().hex
            conversation_id = getattr(message, "conversation_id", "") or ""
            sender_id = getattr(message, "sender_id", "") or ""
            sender_nick = getattr(message, "sender_nick", "") or sender_id

            chat_id = conversation_id or sender_id

            session_webhook = getattr(message, "session_webhook", None) or ""
            session_webhook_expired_time = (
                getattr(message, "session_webhook_expired_time", 0) or 0
            )
            if session_webhook and chat_id and _DINGTALK_WEBHOOK_RE.match(session_webhook):
                if len(self._session_webhooks) >= _SESSION_WEBHOOKS_MAX:
                    with suppress(StopIteration):
                        self._session_webhooks.pop(next(iter(self._session_webhooks)))
                self._session_webhooks[chat_id] = (
                    session_webhook,
                    session_webhook_expired_time,
                )

            text = self._extract_text(message)

            if not text:
                logger.debug("[dingtalk] Empty message, skipping")
                return

            create_at = getattr(message, "create_at", None)
            try:
                timestamp = (
                    datetime.fromtimestamp(int(create_at) / 1000, tz=UTC)
                    if create_at
                    else datetime.now(tz=UTC)
                )
            except (ValueError, OSError, TypeError):
                timestamp = datetime.now(tz=UTC)

            msg_type = MessageType.TEXT
            msg_type_str = getattr(message, "message_type", "") or ""
            if msg_type_str == "picture":
                msg_type = MessageType.IMAGE

            event = MessageEvent(
                text=text,
                message_type=msg_type,
                message_id=msg_id,
                chat_id=chat_id,
                user_id=sender_id,
                raw=data,
                timestamp=timestamp,
                source=SessionSource(
                    platform=self.name,
                    chat_id=chat_id or "",
                    chat_type="dm",
                    user_id=sender_id or "",
                ),
            )

            task = asyncio.create_task(self._dispatch_event(event))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error("[dingtalk] Error processing stream message: %s", e)

    @staticmethod
    def _extract_text(message: Any) -> str:
        """Extract plain text from a DingTalk ChatbotMessage."""
        text = getattr(message, "text", None) or ""
        if hasattr(text, "content"):
            content = (text.content or "").strip()
        elif isinstance(text, dict):
            content = text.get("content", "").strip()
        else:
            content = str(text).strip()
        return content

    # ── Outbound messaging ───────────────────────────────────────────────

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.chat_id:
            try:
                await self.send_typing(event.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        _reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a message via DingTalk session webhook or Open API.

        Primary path: send markdown via the session webhook tied to the
        most recent incoming message from this chat.
        Fallback path: use the DingTalk Open API batchSend endpoint when
        no valid webhook is available.
        """
        metadata = metadata or {}

        session_webhook = metadata.get("session_webhook")
        if not session_webhook:
            webhook_info = self._get_valid_webhook(chat_id)
            if webhook_info:
                session_webhook, _ = webhook_info

        if session_webhook and self._http_client:
            return await self._send_via_webhook(content, session_webhook)

        return await self._send_via_openapi(chat_id, content)

    async def _send_via_webhook(
        self, content: str, webhook: str
    ) -> SendResult:
        """Send a markdown message via DingTalk session webhook."""
        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        normalized = self._normalize_markdown(content[:_MAX_MESSAGE_LENGTH])

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "Encre",
                "text": normalized,
            },
        }

        try:
            resp = await self._http_client.post(
                webhook,
                headers={"User-Agent": BaseAdapter.build_user_agent()},
                json=payload,
                timeout=15.0,
            )
            if resp.status_code < 300:
                return SendResult(
                    success=True,
                    message_id=uuid.uuid4().hex[:12],
                )
            body = resp.text
            logger.warning(
                "[dingtalk] Webhook send failed HTTP %d: %s",
                resp.status_code, body[:200],
            )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {body[:200]}",
                retryable=True,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[dingtalk] Webhook send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def _send_via_openapi(
        self, chat_id: str, content: str
    ) -> SendResult:
        """Send a message via DingTalk Open API batchSend as fallback."""
        token = self._access_token
        if not token:
            token = await self._refresh_token()
        if not token:
            return SendResult(
                success=False,
                error="No access token available",
                retryable=True,
            )

        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        truncated = content[:_MAX_MESSAGE_LENGTH]
        is_markdown = self._contains_markdown(truncated)

        if is_markdown:
            msg_key = "sampleMarkdown"
            msg_param = json.dumps({
                "title": "Encre",
                "text": truncated,
            })
        else:
            msg_key = "sampleText"
            msg_param = json.dumps({"content": truncated})

        payload = {
            "robotCode": self._robot_code,
            "userIds": [chat_id],
            "msgKey": msg_key,
            "msgParam": msg_param,
        }

        try:
            resp = await self._http_client.post(
                "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                    "User-Agent": BaseAdapter.build_user_agent(),
                },
                json=payload,
                timeout=15.0,
            )
            if resp.status_code < 300:
                body = resp.json()
                return SendResult(
                    success=True,
                    message_id=body.get("processQueryKey", uuid.uuid4().hex[:12]),
                )
            if resp.status_code == 401:
                self._access_token = None
            body = resp.text
            logger.warning(
                "[dingtalk] OpenAPI send failed HTTP %d: %s",
                resp.status_code, body[:200],
            )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {body[:200]}",
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[dingtalk] OpenAPI send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    def _get_valid_webhook(self, chat_id: str) -> tuple[str, int] | None:
        """Get a valid (non-expired) session webhook for the given chat_id."""
        info = self._session_webhooks.get(chat_id)
        if not info:
            return None
        _webhook, expired_time_ms = info
        if expired_time_ms and expired_time_ms > 0:
            now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
            safety_margin_ms = 5 * 60 * 1000
            if now_ms + safety_margin_ms >= expired_time_ms:
                self._session_webhooks.pop(chat_id, None)
                return None
        return info

    @staticmethod
    def _contains_markdown(text: str) -> bool:
        """Heuristic check whether text contains markdown formatting."""
        md_chars = {"*", "_", "`", "#", "[", "!", ">", "|"}
        return any(c in text for c in md_chars)

    @staticmethod
    def _normalize_markdown(text: str) -> str:
        """Normalize markdown for DingTalk's parser."""
        lines = text.split("\n")
        out: list[str] = []
        for i, line in enumerate(lines):
            is_numbered = re.match(r"^\d+\.\s", line.strip())
            if is_numbered and i > 0:
                prev = lines[i - 1]
                if prev.strip() and not re.match(r"^\d+\.\s", prev.strip()):
                    out.append("")
            if line.strip().startswith("```") and line != line.lstrip():
                indent = len(line) - len(line.lstrip())
                line = line[indent:]
            out.append(line)
        return "\n".join(out)


# ---------------------------------------------------------------------------
# Internal stream handler
# ---------------------------------------------------------------------------


class _IncomingHandler(
    dingtalk_stream.ChatbotHandler if DINGTALK_AVAILABLE else object
):
    """dingtalk-stream ChatbotHandler that forwards messages to the adapter."""

    def __init__(
        self,
        adapter: DingTalkAdapter,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """
        Initialize the instance..

        Args:
            adapter (DingTalkAdapter):
            loop (asyncio.AbstractEventLoop | None):

        Returns:
            None
        """
        if DINGTALK_AVAILABLE:
            super().__init__()
        self._adapter = adapter
        self._loop = loop
        self._dispatch_tasks: set[asyncio.Task] = set()

    def pre_start(self) -> None:
        """
        Pre start.

        Returns:
            None
        """
        return

    async def process(self, message: CallbackMessage) -> tuple[int, str]:
        """Called by dingtalk-stream when a message arrives."""
        logger.info("[dingtalk] process() CALLED, incoming message received")
        try:
            data = message.data
            if isinstance(data, str):
                data = json.loads(data)

            if not isinstance(data, dict):
                return AckMessage.STATUS_SYSTEM_EXCEPTION, "invalid payload"

            chatbot_msg = ChatbotMessage.from_dict(data)

            if not getattr(chatbot_msg, "session_webhook", None):
                webhook = data.get("sessionWebhook") or data.get("session_webhook") or ""
                if webhook:
                    chatbot_msg.session_webhook = webhook

            task = asyncio.create_task(self._adapter._on_stream_message(data))
            self._dispatch_tasks.add(task)
            task.add_done_callback(self._dispatch_tasks.discard)
        except Exception:
            logger.exception("[dingtalk] Error preparing incoming message")
            return AckMessage.STATUS_SYSTEM_EXCEPTION, "error"

        return AckMessage.STATUS_OK, "OK"
