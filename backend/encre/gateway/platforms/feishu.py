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
# feishu.py
#
# Platform adapter for Feishu / Lark in the Encre gateway framework.
# Provides the FeishuAdapter class that receives webhook callbacks and
# uses the Feishu Open API for outbound messaging.
#
# Exported classes:
#   - FeishuAdapter
#
import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.feishu")

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
FEISHU_TOKEN_URL = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = f"{FEISHU_BASE_URL}/im/v1/messages"
FEISHU_IMAGE_UPLOAD_URL = f"{FEISHU_BASE_URL}/im/v1/images"
FEISHU_CHAT_URL = f"{FEISHU_BASE_URL}/im/v1/chats"

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None


class FeishuAdapter(BasePlatformAdapter):
    """Feishu / Lark bot adapter.

    Supports two modes:
        1. Webhook mode -- receive messages via Feishu event callback
        2. App mode -- use Feishu Open API (requires app_id + app_secret)

    Both modes can be combined. When both are configured, the adapter
    starts a local HTTP server to receive webhook callbacks and uses
    the Open API to send messages.

    Supports text, image, and interactive (card) message types.
    """

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform = Platform.FEISHU,
    ) -> None:
        """Initialize the Feishu adapter.

        Args:
            config: Platform configuration.
            platform: The Platform enum value.
        """
        super().__init__(config=config, platform=platform)
        self._app_id = config.extra.get("app_id") or os.getenv("FEISHU_APP_ID")
        self._app_secret = config.extra.get("app_secret") or os.getenv("FEISHU_APP_SECRET")
        self._verify_token = config.extra.get("verify_token") or os.getenv("FEISHU_VERIFY_TOKEN")
        self._webhook_url = config.extra.get("webhook_url")
        self._port = int(config.extra.get("port", 0)) or int(os.getenv("FEISHU_PORT", "18794"))

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._server: asyncio.AbstractServer | None = None
        self._http: Any = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Connect: obtain token and start webhook server."""
        if self._app_id and self._app_secret:
            logger.info("[feishu] Step 1/2: Obtaining tenant access token...")
            await self._refresh_token()
            if not self._access_token:
                logger.error("[feishu] Step 1/2: Failed to obtain tenant access token")
                return False
            logger.info("[feishu] Step 1/2: Token obtained (app_id=%s)", self._app_id)

        if self._webhook_url or self._port:
            logger.info("[feishu] Step 2/2: Starting webhook server...")
            await self._start_webhook_server()
            logger.info(
                "[feishu] Step 2/2: Webhook server listening on port %d", self._port
            )

        self._running = True
        logger.info("[feishu] Connected")
        return True

    async def disconnect(self) -> None:
        """Disconnect and clean up."""
        self._running = False
        await self._stop_webhook_server()
        await self._cancel_background_tasks()
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:
                pass
            self._http = None
        logger.info("[feishu] Disconnected")

    # ── Token Management ──────────────────────────────────────────────────

    async def _refresh_token(self) -> bool:
        """Refresh the Feishu tenant_access_token."""
        if not self._app_id or not self._app_secret:
            logger.warning("[feishu] Cannot refresh token: app_id or app_secret missing")
            return False

        client = self._get_http_client()
        if client is None:
            logger.error("[feishu] httpx is required for token refresh")
            return False

        try:
            resp = await client.post(
                FEISHU_TOKEN_URL,
                headers={"User-Agent": "Encre/1.0.0 (Feishu Adapter)"},
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
            )
            data = resp.json()
            token = data.get("tenant_access_token")
            expire = data.get("expire", 7200)
            if not token:
                logger.error(
                    "[feishu] Token refresh failed: %s",
                    data.get("msg", "unknown error"),
                )
                return False
            self._access_token = token
            self._token_expires_at = time.time() + expire - 60
            logger.info("[feishu] Tenant access token refreshed (expires in %ds)", expire)
            return True
        except Exception as e:
            logger.error("[feishu] Token refresh error: %s", e)
            return False

    async def _ensure_token(self) -> bool:
        """Ensure a valid token is available, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at:
            return True
        return await self._refresh_token()

    # ── Send Messages ─────────────────────────────────────────────────────

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
        """Send a text message to a Feishu chat."""
        if not await self._ensure_token():
            return SendResult(
                success=False,
                error="No valid access token",
                retryable=True,
            )

        msg_type = "text"
        if metadata and metadata.get("msg_type") == "interactive":
            msg_type = "interactive"
            try:
                payload_content = content if isinstance(content, str) else json.dumps(content)
            except Exception:
                payload_content = str(content)
        elif metadata and metadata.get("msg_type") == "post":
            msg_type = "post"
            payload_content = content if isinstance(content, str) else json.dumps(content)
        else:
            payload_content = json.dumps({"text": content})

        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": payload_content,
        }

        if reply_to:
            body.setdefault("reply_to_message_id", reply_to)

        client = self._get_http_client()
        if client is None:
            return SendResult(success=False, error="httpx not available")

        try:
            resp = await client.post(
                FEISHU_MESSAGE_URL,
                params={"receive_id_type": "open_id"},
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Encre/1.0.0 (Feishu Adapter)",
                },
                json=body,
            )
            data = resp.json()
            if data.get("code") == 0:
                msg_id = None
                msg_data = data.get("data", {})
                if msg_data:
                    msg_id = msg_data.get("message_id")
                return SendResult(success=True, message_id=msg_id, raw=data)
            error_msg = data.get("msg", "unknown error")
            code = data.get("code", -1)
            logger.error("[feishu] Send error (code=%s): %s", code, error_msg)
            return SendResult(
                success=False,
                error=f"Feishu API error (code={code}): {error_msg}",
                raw=data,
                retryable=True,
            )
        except Exception as e:
            logger.error("[feishu] Send request failed: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Get information about a Feishu chat."""
        return {"id": chat_id, "platform": self.name}

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        _caption: str | None = None,
    ) -> SendResult:
        """Upload an image and send it to a Feishu chat."""
        if not await self._ensure_token():
            return SendResult(
                success=False,
                error="No valid access token",
                retryable=True,
            )

        client = self._get_http_client()
        if client is None:
            return SendResult(success=False, error="httpx not available")

        try:
            if not os.path.isfile(file_path):
                return SendResult(success=False, error=f"File not found: {file_path}")

            image_type = "message"
            with open(file_path, "rb") as f:
                files = {
                    "image_type": (None, image_type),
                    "image": (os.path.basename(file_path), f, self._infer_mime(file_path)),
                }
                upload_resp = await client.post(
                    FEISHU_IMAGE_UPLOAD_URL,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "User-Agent": "Encre/1.0.0 (Feishu Adapter)",
                    },
                    files=files,
                )
            upload_data = upload_resp.json()
            if upload_data.get("code") != 0:
                error_msg = upload_data.get("msg", "unknown error")
                logger.error("[feishu] Image upload failed: %s", error_msg)
                return SendResult(
                    success=False,
                    error=f"Image upload failed: {error_msg}",
                    raw=upload_data,
                )

            image_key = upload_data.get("data", {}).get("image_key")
            if not image_key:
                return SendResult(
                    success=False,
                    error="No image_key in upload response",
                    raw=upload_data,
                )

            body: dict[str, Any] = {
                "receive_id": chat_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}),
            }

            send_resp = await client.post(
                FEISHU_MESSAGE_URL,
                params={"receive_id_type": "open_id"},
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Encre/1.0.0 (Feishu Adapter)",
                },
                json=body,
            )
            send_data = send_resp.json()
            if send_data.get("code") == 0:
                msg_id = None
                msg_data = send_data.get("data", {})
                if msg_data:
                    msg_id = msg_data.get("message_id")
                return SendResult(success=True, message_id=msg_id, raw=send_data)
            error_msg = send_data.get("msg", "unknown error")
            return SendResult(
                success=False,
                error=f"Send image failed: {error_msg}",
                raw=send_data,
            )
        except Exception as e:
            logger.error("[feishu] send_image error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_card(
        self,
        chat_id: str,
        card: dict[str, Any] | str,
        *,
        reply_to: str | None = None,
    ) -> SendResult:
        """Send an interactive card message to a Feishu chat."""
        content = json.dumps(card) if isinstance(card, dict) else card
        return await self.send(
            chat_id,
            content,
            reply_to=reply_to,
            metadata={"msg_type": "interactive"},
        )

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to a Feishu chat."""
        if not await self._ensure_token():
            return
        client = self._get_http_client()
        if client is None:
            return
        try:
            await client.post(
                f"{FEISHU_BASE_URL}/im/v1/chat/{chat_id}/send_typing",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "User-Agent": "Encre/1.0.0 (Feishu Adapter)",
                },
                json={"chat_id": chat_id},
            )
        except Exception as e:
            logger.debug("[feishu] send_typing error: %s", e)

    # ── Webhook Server ────────────────────────────────────────────────────

    async def _start_webhook_server(self) -> None:
        """Start an async HTTP server to receive Feishu webhook callbacks."""
        try:
            self._server = await asyncio.start_server(
                self._handle_http_connection,
                host="0.0.0.0",
                port=self._port,
            )
            logger.info(
                "[feishu] Webhook server listening on 0.0.0.0:%d", self._port
            )
        except Exception as e:
            logger.error("[feishu] Failed to start webhook server: %s", e)
            self._server = None

    async def _stop_webhook_server(self) -> None:
        """Stop the webhook server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("[feishu] Webhook server stopped")

    async def _handle_http_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming HTTP connection."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not request_line:
                writer.close()
                return

            method, path, _ = request_line.decode("utf-8", errors="replace").strip().split(" ", 2)

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

            if method == "POST" and path == "/webhook/feishu":
                response_body, status = await self._process_webhook(body, headers)
            else:
                response_body = json.dumps({"error": "not found"}).encode()
                status = 404

            status_text = {200: "OK", 401: "Unauthorized", 404: "Not Found"}.get(
                status, "Internal Server Error"
            )
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
            logger.debug("[feishu] HTTP handler error: %s", e)
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    async def _process_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> tuple[bytes, int]:
        """Process a webhook request and return (response_body, status_code)."""
        result = await self.handle_webhook(body, headers)
        if isinstance(result, dict) and "error" in result:
            error_msg = result["error"]
            logger.warning("[feishu] Webhook error: %s", error_msg)
            return json.dumps(result).encode(), 401
        return json.dumps(result).encode(), 200

    async def handle_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Handle an incoming Feishu webhook callback."""
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        if self._verify_token and not self._verify_webhook_signature(body, headers, payload):
            return {"error": "invalid signature"}

        challenge = payload.get("challenge")
        if challenge is not None:
            return {"challenge": challenge}

        header = payload.get("header", {})
        event_type = header.get("event_type", "")
        token = header.get("token", "")

        if self._verify_token and token and token != self._verify_token:
            logger.warning("[feishu] Event token mismatch")
            return {"error": "token mismatch"}

        if event_type == "im.message.receive_v1":
            await self._handle_message_event(payload)

        return {"ok": True}

    def _verify_webhook_signature(
        self,
        body: bytes,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> bool:
        """Verify the Feishu webhook signature using the verify_token."""
        if not self._verify_token:
            return True

        signature = headers.get("x-lark-signature", "")
        if not signature:
            challenge = payload.get("challenge")
            if challenge is not None:
                logger.warning("[feishu] Challenge without signature, accepting")
                return True
            return False

        timestamp = headers.get("x-lark-request-timestamp", "")
        nonce = headers.get("x-lark-request-nonce", "")
        computed = hmac.new(
            self._verify_token.encode("utf-8"),
            f"{timestamp}{nonce}{body.decode('utf-8')}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if computed != signature:
            logger.warning("[feishu] Signature mismatch")
            return False
        return True

    async def _handle_message_event(self, payload: dict[str, Any]) -> None:
        """Parse and dispatch a Feishu message event."""
        try:
            event = payload.get("event", {})
            sender = event.get("sender", {})
            sender_id = sender.get("sender_id", {})
            user_id = sender_id.get("open_id", "") or sender.get("open_id", "")

            message = event.get("message", {})
            message_id = message.get("message_id", "")
            chat_id = message.get("chat_id", "")
            msg_type = message.get("message_type", "text")
            content_str = message.get("content", "{}")

            if isinstance(content_str, str):
                try:
                    content_data = json.loads(content_str)
                except json.JSONDecodeError:
                    content_data = {"text": content_str}
            else:
                content_data = content_str

            text = ""
            media_urls: list[str] = []
            media_types: list[str] = []

            if msg_type == "text":
                text = content_data.get("text", "")
            elif msg_type == "post":
                post_content = content_data.get("post", {})
                zh_content = post_content.get("zh_cn", post_content.get("en", {}))
                paragraphs = zh_content.get("content", [])
                text_parts: list[str] = []
                for para in paragraphs:
                    for elem in para:
                        if isinstance(elem, dict):
                            text_parts.append(elem.get("text", ""))
                text = "".join(text_parts)
            elif msg_type == "image":
                image_key = content_data.get("image_key", "")
                text = f"[Image: {image_key}]"
                if image_key:
                    media_urls.append(image_key)
                    media_types.append("image")
            elif msg_type == "file":
                file_key = content_data.get("file_key", "")
                file_name = content_data.get("file_name", "")
                text = f"[File: {file_name}]" if file_name else "[File]"
                if file_key:
                    media_urls.append(file_key)
                    media_types.append("file")
            elif msg_type == "audio":
                audio_key = content_data.get("audio_key", "")
                text = "[Audio]"
                if audio_key:
                    media_urls.append(audio_key)
                    media_types.append("audio")
            elif msg_type == "interactive":
                text = "[Card message]"

            if not text and not user_id:
                return
            if not user_id:
                user_id = "unknown"

            event_obj = MessageEvent(
                text=text,
                message_type=MessageType.IMAGE if msg_type == "image" else MessageType.TEXT,
                message_id=message_id,
                media_urls=media_urls,
                media_types=media_types,
                raw_message=payload,
                source=SessionSource(
                    platform=self.name,
                    chat_id=chat_id or user_id,
                    chat_type="dm",
                    user_id=user_id,
                ),
            )

            task = asyncio.create_task(self._dispatch_event(event_obj))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error("[feishu] Failed to handle message event: %s", e)

    # ── HTTP Client ───────────────────────────────────────────────────────

    def _get_http_client(self) -> Any | None:
        """Get or create an httpx AsyncClient."""
        if self._http is not None:
            return self._http
        if not HTTPX_AVAILABLE:
            logger.error(
                "[feishu] httpx is required. Install with: pip install httpx"
            )
            return None
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None
        self._http = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, verify=False, proxy=proxy_url
        )
        return self._http

    @staticmethod
    def _infer_mime(file_path: str) -> str:
        """Infer the MIME type of an image file from its extension."""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        return mime_map.get(ext, "image/png")


# ── Platform registration ─────────────────────────────────────────────────────

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return HTTPX_AVAILABLE


platform_registry.register(PlatformEntry(
    name="feishu",
    label="Feishu",
    platform=Platform.FEISHU,
    adapter_factory=lambda cfg: FeishuAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
))
