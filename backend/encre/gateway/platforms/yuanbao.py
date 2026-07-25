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
# yuanbao.py
#
# Platform adapter for Yuanbao (Tencent AI Bot) integration.
# Uses persistent WebSocket for real-time messages and REST API
# for outbound messaging with HMAC-SHA256 authentication.
#
# Exported classes:
#   - YuanbaoProtocol
#   - YuanbaoAdapter
#
import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from contextlib import suppress
from typing import Any

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    from websockets.exceptions import ConnectionClosed

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketClientProtocol = None
    ConnectionClosed = Exception

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.yuanbao")

YUANBAO_DEFAULT_WS_URL = "wss://ws.yuanbao.example.com/gateway"
YUANBAO_API_DOMAIN = "https://api.yuanbao.example.com"

HEARTBEAT_INTERVAL = 30.0
HEARTBEAT_TIMEOUT = 10.0
CONNECT_TIMEOUT = 15.0
SEND_TIMEOUT = 30.0
MAX_RECONNECT_ATTEMPTS = 100
MESSAGE_DEDUP_TTL = 300.0
MAX_MESSAGE_LENGTH = 16000

RECONNECT_BACKOFF = [1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0]


class YuanbaoProtocol:
    """Yuanbao WebSocket protocol message builder and parser."""

    OP_AUTH = "auth"
    OP_AUTH_RESP = "auth_resp"
    OP_HEARTBEAT = "heartbeat"
    OP_HEARTBEAT_RESP = "heartbeat_resp"
    OP_MESSAGE = "message"
    OP_MESSAGE_ACK = "message_ack"
    OP_TYPING = "typing"
    OP_TYPING_RESP = "typing_resp"
    OP_ERROR = "error"

    @staticmethod
    def build_auth(app_key: str, app_secret: str) -> dict[str, Any]:
        timestamp = str(int(time.time() * 1000))
        raw = f"{app_key}{timestamp}"
        signature = hmac.new(
            app_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "op": YuanbaoProtocol.OP_AUTH,
            "data": {
                "app_key": app_key,
                "signature": signature,
                "timestamp": timestamp,
            },
        }

    @staticmethod
    def build_heartbeat() -> dict[str, Any]:
        return {
            "op": YuanbaoProtocol.OP_HEARTBEAT,
            "data": {"timestamp": str(int(time.time() * 1000))},
        }

    @staticmethod
    def build_typing(chat_id: str) -> dict[str, Any]:
        return {
            "op": YuanbaoProtocol.OP_TYPING,
            "data": {"chat_id": chat_id},
        }

    @staticmethod
    def build_message_ack(msg_id: str) -> dict[str, Any]:
        return {
            "op": YuanbaoProtocol.OP_MESSAGE_ACK,
            "data": {"msg_id": msg_id},
        }

    @staticmethod
    def parse_message(data: dict[str, Any]) -> dict[str, Any] | None:
        op = data.get("op", "")
        if op == YuanbaoProtocol.OP_AUTH_RESP:
            return {"type": "auth", "success": data.get("data", {}).get("success", False), "raw": data}
        if op == YuanbaoProtocol.OP_HEARTBEAT_RESP:
            return {"type": "heartbeat", "raw": data}
        if op == YuanbaoProtocol.OP_MESSAGE:
            msg_data = data.get("data", {})
            return {
                "type": "message",
                "msg_id": msg_data.get("msg_id", ""),
                "from_account": msg_data.get("from_account", ""),
                "from_group": msg_data.get("from_group", ""),
                "chat_type": msg_data.get("chat_type", "c2c"),
                "content_type": msg_data.get("content_type", "text"),
                "content": msg_data.get("content", ""),
                "media_url": msg_data.get("media_url", ""),
                "media_name": msg_data.get("media_name", ""),
                "reply_to_msg_id": msg_data.get("reply_to_msg_id", ""),
                "reply_to_content": msg_data.get("reply_to_content", ""),
                "timestamp": msg_data.get("timestamp", 0),
                "raw": data,
            }
        if op == YuanbaoProtocol.OP_ERROR:
            return {"type": "error", "code": data.get("code", ""), "message": data.get("message", ""), "raw": data}
        if op == YuanbaoProtocol.OP_TYPING_RESP:
            return {"type": "typing_ack", "raw": data}
        return None

    @staticmethod
    def build_rest_signature(
        _app_key: str, app_secret: str, method: str, path: str, body: str, timestamp: str
    ) -> str:
        raw = f"{method}\n{path}\n{timestamp}\n{body}"
        return hmac.new(
            app_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class YuanbaoAdapter(BasePlatformAdapter):
    """Yuanbao (Tencent AI Bot) adapter.

    Uses a persistent WebSocket connection to receive real-time messages
    from the Yuanbao platform, and the Yuanbao REST API to send outbound
    messages.  Authentication is performed via HMAC-SHA256 signatures.

    Requires:
        pip install websockets httpx
    """

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform = Platform.YUANBAO,
    ) -> None:
        super().__init__(config=config, platform=platform)
        self._app_key = config.token
        self._app_secret = config.extra.get("app_secret", "")
        self._bot_id = config.extra.get("bot_id", "")
        self._ws_url = config.extra.get("ws_url", YUANBAO_DEFAULT_WS_URL)
        self._api_domain = config.extra.get("api_domain", YUANBAO_API_DOMAIN).rstrip("/")

        self._ws: WebSocketClientProtocol | None = None
        self._ws_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._connected_event: asyncio.Event = asyncio.Event()
        self._seen_messages: dict[str, float] = {}
        self._reconnect_count: int = 0

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Connect to Yuanbao WebSocket gateway."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error(
                "[yuanbao] websockets not installed. Run: pip install websockets"
            )
            return False
        if not HTTPX_AVAILABLE:
            logger.error(
                "[yuanbao] httpx not installed. Run: pip install httpx"
            )
            return False
        if not self._app_key or not self._app_secret:
            logger.error("[yuanbao] app_key and app_secret are required")
            return False

        try:
            logger.info("[yuanbao] Creating HTTP client")
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Encre/1.0.0"},
            )

            self._connected_event.clear()
            self._reconnect_count = 0
            logger.info("[yuanbao] Starting WebSocket task")
            self._ws_task = asyncio.create_task(self._run_websocket())

            try:
                logger.info("[yuanbao] Waiting for WebSocket connection (timeout=%ds)", CONNECT_TIMEOUT)
                await asyncio.wait_for(self._connected_event.wait(), timeout=CONNECT_TIMEOUT)
            except TimeoutError:
                logger.error("[yuanbao] Connection timed out after %ds", CONNECT_TIMEOUT)
                return False

            self._running = True
            logger.info("[yuanbao] Connected to WebSocket gateway")
            return True
        except Exception as e:
            logger.error("[yuanbao] Failed to connect: %s", e)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Yuanbao."""
        self._running = False
        self._connected_event.clear()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        if self._ws is not None:
            with suppress(Exception):
                await self._ws.close()
            self._ws = None

        if self._ws_task:
            self._ws_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("[yuanbao] Disconnected")

    # ── WebSocket runner ─────────────────────────────────────────────────

    async def _run_websocket(self) -> None:
        """Main WebSocket loop with automatic reconnection."""
        while self._running:
            try:
                self._ws = await websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5.0,
                    max_size=10 * 1024 * 1024,
                )
                logger.info("[yuanbao] WebSocket connection established")

                if not await self._authenticate():
                    logger.error("[yuanbao] Authentication failed")
                    await self._ws.close()
                    self._ws = None
                    await asyncio.sleep(5.0)
                    continue

                self._reconnect_count = 0

                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                await self._message_loop()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[yuanbao] WebSocket error: %s", e)

            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._heartbeat_task
                self._heartbeat_task = None

            self._ws = None
            self._connected_event.clear()

            if not self._running:
                break

            delay = self._get_reconnect_delay()
            logger.info("[yuanbao] Reconnecting in %.1fs... (attempt %d)", delay, self._reconnect_count)
            self._reconnect_count += 1
            await asyncio.sleep(delay)

    async def _authenticate(self) -> bool:
        """Authenticate with the Yuanbao WebSocket gateway."""
        if not self._ws:
            return False

        auth_msg = YuanbaoProtocol.build_auth(self._app_key, self._app_secret)
        await self._ws.send(json.dumps(auth_msg))

        raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        data = json.loads(raw)
        parsed = YuanbaoProtocol.parse_message(data)

        if not parsed or parsed.get("type") != "auth" or not parsed.get("success"):
            logger.error("[yuanbao] Auth failed: %s", data)
            return False

        auth_data = data.get("data", {})
        discovered_bot_id = auth_data.get("bot_id", "")
        if discovered_bot_id and not self._bot_id:
            self._bot_id = discovered_bot_id
            logger.info("[yuanbao] Bot ID auto-discovered: %s", self._bot_id)

        self._connected_event.set()
        logger.info("[yuanbao] Authentication successful")
        return True

    async def _message_loop(self) -> None:
        """Read and process incoming WebSocket messages."""
        if not self._ws:
            return

        async for raw in self._ws:
            try:
                data = json.loads(raw)
                parsed = YuanbaoProtocol.parse_message(data)
                if parsed is None:
                    continue

                msg_type = parsed.get("type")

                if msg_type == "heartbeat":
                    continue

                if msg_type == "message":
                    await self._handle_inbound_message(parsed)
                elif msg_type == "error":
                    logger.warning("[yuanbao] Server error: %s", parsed.get("message", ""))
                elif msg_type == "typing_ack":
                    continue

            except json.JSONDecodeError:
                logger.debug("[yuanbao] Invalid JSON received")
            except Exception as e:
                logger.error("[yuanbao] Error processing message: %s", e)

    async def _handle_inbound_message(self, parsed: dict[str, Any]) -> None:
        """Process an inbound Yuanbao message and dispatch it."""
        msg_id = parsed.get("msg_id", "") or uuid.uuid4().hex
        now = time.time()

        if msg_id in self._seen_messages and now - self._seen_messages[msg_id] < MESSAGE_DEDUP_TTL:
            logger.debug("[yuanbao] Duplicate message %s, skipping", msg_id)
            return
        self._seen_messages[msg_id] = now
        if len(self._seen_messages) > 2000:
            cutoff = now - MESSAGE_DEDUP_TTL
            self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}

        content_type = parsed.get("content_type", "text")
        content = parsed.get("content", "")
        from_account = parsed.get("from_account", "")
        from_group = parsed.get("from_group", "")
        chat_type = parsed.get("chat_type", "c2c")

        chat_id = f"group:{from_group}" if chat_type == "group" and from_group else f"direct:{from_account}"

        media_url = parsed.get("media_url", "")
        media_name = parsed.get("media_name", "")

        message_type = MessageType.TEXT
        media_urls: list[str] = []
        media_types: list[str] = []

        if content_type == "image":
            message_type = MessageType.IMAGE
            if media_url:
                media_urls.append(media_url)
                media_types.append("image")
        elif content_type == "voice" or content_type == "audio":
            message_type = MessageType.VOICE
            if media_url:
                media_urls.append(media_url)
                media_types.append("audio")
        elif content_type == "file":
            message_type = MessageType.FILE
            if media_url:
                media_urls.append(media_url)
                media_types.append("file")
                if media_name:
                    content = f"[File: {media_name}]"
        elif content_type == "sticker":
            message_type = MessageType.STICKER

        if not content and not media_urls:
            logger.debug("[yuanbao] Empty message, skipping")
            return

        if not from_account:
            from_account = "unknown"

        reply_to_msg_id = parsed.get("reply_to_msg_id", "")
        reply_to_content = parsed.get("reply_to_content", "")

        event = MessageEvent(
            text=content,
            message_type=message_type,
            message_id=msg_id,
            reply_to_message_id=reply_to_msg_id or None,
            reply_to_text=reply_to_content or None,
            media_urls=media_urls,
            media_types=media_types,
            raw_message=parsed.get("raw", parsed),
            source=SessionSource(
                platform=self.name,
                chat_id=chat_id,
                chat_type="group" if chat_type == "group" else "dm",
                user_id=from_account,
            ),
        )

        if self._ws:
            ack = YuanbaoProtocol.build_message_ack(msg_id)
            with suppress(Exception):
                await self._ws.send(json.dumps(ack))

        task = asyncio.create_task(self._dispatch_event(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    # ── Heartbeat ─────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep the WebSocket connection alive."""
        while self._running and self._ws is not None:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self._ws is None:
                    break
                hb = YuanbaoProtocol.build_heartbeat()
                await asyncio.wait_for(
                    self._ws.send(json.dumps(hb)),
                    timeout=HEARTBEAT_TIMEOUT,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("[yuanbao] Heartbeat error: %s", e)
                break

    # ── Reconnection backoff ──────────────────────────────────────────────

    def _get_reconnect_delay(self) -> float:
        idx = min(self._reconnect_count, len(RECONNECT_BACKOFF) - 1)
        return RECONNECT_BACKOFF[idx]

    # ── Outbound messaging ────────────────────────────────────────────────

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.source and event.source.chat_id:
            try:
                await self.send_typing(event.source.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a message via the Yuanbao REST API.

        Long messages are automatically chunked to fit platform limits.
        """
        metadata = metadata or {}

        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        rest_chunks = self._chunk_content(content)

        first_result: SendResult | None = None

        for i, chunk in enumerate(rest_chunks):
            result = await self._send_chunk(chat_id, chunk, metadata)
            if i == 0:
                first_result = result
            if not result.success:
                logger.warning("[yuanbao] Chunk %d/%d send failed: %s", i + 1, len(rest_chunks), result.error)

        if first_result is None:
            return SendResult(success=False, error="send failed")

        return first_result

    async def _send_chunk(
        self, chat_id: str, content: str, _metadata: dict[str, Any]
    ) -> SendResult:
        """Send a single message chunk via the Yuanbao REST API."""
        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        timestamp = str(int(time.time() * 1000))
        body = json.dumps({
            "chat_id": chat_id,
            "content": content,
            "content_type": "text",
            "timestamp": timestamp,
        })

        path = "/v1/message/send"
        signature = YuanbaoProtocol.build_rest_signature(
            self._app_key, self._app_secret, "POST", path, body, timestamp
        )

        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self._app_key,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
        }

        try:
            resp = await self._http_client.post(
                f"{self._api_domain}{path}",
                headers=headers,
                content=body,
                timeout=SEND_TIMEOUT,
            )
            data = resp.json()
            if resp.status_code < 300 and data.get("code", 0) == 0:
                msg_id = data.get("data", {}).get("msg_id", uuid.uuid4().hex[:12])
                return SendResult(success=True, message_id=msg_id, raw=data)
            error_msg = data.get("message", "") or data.get("msg", "") or str(resp.status_code)
            logger.warning(
                "[yuanbao] Send failed HTTP %d: %s",
                resp.status_code, error_msg[:200],
            )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {error_msg[:200]}",
                raw=data,
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as e:
            logger.error("[yuanbao] Send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    @staticmethod
    def _chunk_content(content: str) -> list[str]:
        """Split long content into chunks respecting markdown boundaries."""
        if len(content) <= MAX_MESSAGE_LENGTH:
            return [content]

        chunks: list[str] = []
        while content:
            if len(content) <= MAX_MESSAGE_LENGTH:
                chunks.append(content)
                break

            split_at = MAX_MESSAGE_LENGTH
            candidate = content[:split_at]

            fence_pos = -1
            for marker in ["```", "~~~"]:
                pos = candidate.rfind(marker)
                if pos > split_at // 2:
                    fence_pos = pos
                    break

            newline_pos = candidate.rfind("\n\n")
            if newline_pos > split_at // 2:
                split_at = newline_pos + 1
            elif fence_pos > split_at // 2:
                split_at = fence_pos
                chunk = content[:split_at]
                if not chunk.endswith("\n"):
                    chunk += "\n"
                chunk += "```\n[message truncated]"
                chunks.append(chunk)
                content = content[split_at:].lstrip()
                continue
            else:
                newline_pos = candidate.rfind("\n")
                if newline_pos > split_at // 3:
                    split_at = newline_pos + 1

            chunks.append(content[:split_at])
            content = content[split_at:].lstrip()

        return chunks

    # ── Typing indicator ──────────────────────────────────────────────────

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to the Yuanbao chat."""
        if not self._ws:
            return
        try:
            msg = YuanbaoProtocol.build_typing(chat_id)
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.debug("[yuanbao] send_typing error: %s", e)

    # ── Media send helpers ─────────────────────────────────────────────────

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Upload and send an image to a Yuanbao chat."""
        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        media_id, upload_err = await self._upload_media(file_path, "image")
        if not media_id:
            return SendResult(success=False, error=upload_err or "media upload failed")

        timestamp = str(int(time.time() * 1000))
        body_dict: dict[str, Any] = {
            "chat_id": chat_id,
            "content_type": "image",
            "media_id": media_id,
            "timestamp": timestamp,
        }
        if caption:
            body_dict["content"] = caption

        body = json.dumps(body_dict)
        path = "/v1/message/send"
        signature = YuanbaoProtocol.build_rest_signature(
            self._app_key, self._app_secret, "POST", path, body, timestamp
        )

        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self._app_key,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
        }

        try:
            resp = await self._http_client.post(
                f"{self._api_domain}{path}",
                headers=headers,
                content=body,
                timeout=SEND_TIMEOUT,
            )
            data = resp.json()
            if resp.status_code < 300 and data.get("code", 0) == 0:
                msg_id = data.get("data", {}).get("msg_id", uuid.uuid4().hex[:12])
                return SendResult(success=True, message_id=msg_id, raw=data)
            return SendResult(
                success=False,
                error=data.get("message", str(resp.status_code)),
                raw=data,
            )
        except Exception as e:
            logger.error("[yuanbao] send_image error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Upload and send a file to a Yuanbao chat."""
        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        media_id, upload_err = await self._upload_media(file_path, "file")
        if not media_id:
            return SendResult(success=False, error=upload_err or "file upload failed")

        timestamp = str(int(time.time() * 1000))
        body_dict: dict[str, Any] = {
            "chat_id": chat_id,
            "content_type": "file",
            "media_id": media_id,
            "timestamp": timestamp,
        }
        if caption:
            body_dict["content"] = caption

        body = json.dumps(body_dict)
        path = "/v1/message/send"
        signature = YuanbaoProtocol.build_rest_signature(
            self._app_key, self._app_secret, "POST", path, body, timestamp
        )

        headers = {
            "Content-Type": "application/json",
            "X-App-Key": self._app_key,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
        }

        try:
            resp = await self._http_client.post(
                f"{self._api_domain}{path}",
                headers=headers,
                content=body,
                timeout=SEND_TIMEOUT,
            )
            data = resp.json()
            if resp.status_code < 300 and data.get("code", 0) == 0:
                msg_id = data.get("data", {}).get("msg_id", uuid.uuid4().hex[:12])
                return SendResult(success=True, message_id=msg_id, raw=data)
            return SendResult(
                success=False,
                error=data.get("message", str(resp.status_code)),
                raw=data,
            )
        except Exception as e:
            logger.error("[yuanbao] send_document error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def _upload_media(self, file_path: str, media_type: str) -> tuple[str | None, str | None]:
        """Upload a media file to the Yuanbao platform."""
        if not self._http_client:
            return None, "HTTP client not initialized"

        timestamp = str(int(time.time() * 1000))
        path = "/v1/media/upload"
        body_json = json.dumps({"file_name": file_path.rsplit("/", 1)[-1], "media_type": media_type})
        signature = YuanbaoProtocol.build_rest_signature(
            self._app_key, self._app_secret, "POST", path, body_json, timestamp
        )

        headers = {
            "X-App-Key": self._app_key,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
        }

        try:
            import os as _os

            if not _os.path.isfile(file_path):
                return None, f"File not found: {file_path}"

            with open(file_path, "rb") as f:
                files = {
                    "file": (file_path.rsplit("/", 1)[-1], f, "application/octet-stream"),
                    "media_type": (None, media_type),
                }
                resp = await self._http_client.post(
                    f"{self._api_domain}{path}",
                    headers=headers,
                    files=files,
                    timeout=60.0,
                )

            data = resp.json()
            if resp.status_code < 300 and data.get("code", 0) == 0:
                media_id = data.get("data", {}).get("media_id", "")
                if media_id:
                    return media_id, None
            return None, data.get("message", "upload failed")
        except Exception as e:
            logger.error("[yuanbao] Media upload error: %s", e)
            return None, str(e)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"id": chat_id, "platform": self.name}


# ── Platform registration ─────────────────────────────────────────────────

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return WEBSOCKETS_AVAILABLE and HTTPX_AVAILABLE


platform_registry.register(PlatformEntry(
    name="yuanbao",
    label="Yuanbao",
    platform=Platform.YUANBAO,
    adapter_factory=lambda cfg: YuanbaoAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["YUANBAO_APP_KEY", "YUANBAO_APP_SECRET"],
))
