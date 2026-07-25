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
# whatsapp.py
#
# WhatsApp Business Cloud API platform adapter for the Encre gateway.
#
# Exported classes:
#   - WhatsAppAdapter
#
import asyncio
import json
import logging
import os
from typing import Any

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.whatsapp")

WHATSAPP_API_VERSION = "v21.0"
WHATSAPP_BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPX_AVAILABLE = False


class WhatsAppAdapter(BasePlatformAdapter):
    """WhatsApp Business Cloud API adapter.

    Connects to the WhatsApp Business Cloud API (graph.facebook.com) and
    relays messages to the Encre gateway for AI processing. The adapter
    dispatches incoming :class:`MessageEvent` instances and streams
    responses back to WhatsApp chats.

    Requires a Meta Developer account with a WhatsApp Business App and a
    permanent access token (`token`) along with the `phone_number_id`
    of the business phone number.
    """

    def __init__(self, config: PlatformConfig, platform: Platform = Platform.WHATSAPP) -> None:
        super().__init__(config=config, platform=platform)
        self._phone_number_id = config.extra.get("phone_number_id", "")
        self._token = config.token
        self._http: Any = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Initialize the HTTP client and verify the access token."""
        if not HTTPX_AVAILABLE:
            logger.error("[whatsapp] httpx is required for WhatsApp adapter")
            return False

        logger.info("[whatsapp] Initializing HTTP client...")
        self._http = self._get_http_client()
        if self._http is None:
            logger.error("[whatsapp] Failed to create HTTP client")
            return False

        if not self._token:
            logger.error("[whatsapp] No access token configured")
            return False

        logger.info("[whatsapp] Verifying access token...")
        if not await self._verify_token():
            logger.error("[whatsapp] Token verification failed")
            return False

        self._mark_connected()
        logger.info(
            "[whatsapp] Connected (phone_number_id=%s)",
            self._phone_number_id,
        )
        return True

    async def disconnect(self) -> None:
        """Close the HTTP client and disconnect."""
        self._running = False
        if self._http:
            try:
                await self._http.aclose()
            except Exception as e:
                logger.warning("[whatsapp] HTTP client close error: %s", e)
            self._http = None
        await self._cancel_background_tasks()
        self._mark_disconnected()
        logger.info("[whatsapp] Disconnected")

    async def _verify_token(self) -> bool:
        """Verify the access token by calling GET /me on the Graph API."""
        if self._http is None:
            return False
        try:
            resp = await self._http.get(
                f"{WHATSAPP_BASE_URL}/me",
                params={"access_token": self._token},
                headers={"User-Agent": "Encre/1.0.0"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("id"):
                logger.info(
                    "[whatsapp] Token verified (app_id=%s)",
                    data.get("id", "unknown"),
                )
                return True
            error_info = data.get("error", {})
            logger.error(
                "[whatsapp] Token verification failed: %s",
                error_info.get("message", resp.text),
            )
            return False
        except Exception as e:
            logger.error("[whatsapp] Token verification error: %s", e)
            return False

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a WhatsApp chat."""
        if self._http is None:
            return SendResult(success=False, error="HTTP client not connected")

        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "text",
            "text": {"preview_url": False, "body": content},
        }

        if reply_to is not None:
            body["context"] = {"message_id": reply_to}

        try:
            resp = await self._http.post(
                f"{WHATSAPP_BASE_URL}/{self._phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Encre/1.0.0",
                },
                json=body,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and data.get("messages"):
                msg_id = data["messages"][0].get("id", "")
                return SendResult(
                    success=True,
                    message_id=msg_id,
                    raw=data,
                )
            error_info = data.get("error", {})
            error_msg = error_info.get("message", "unknown error")
            error_code = error_info.get("code", -1)
            logger.error(
                "[whatsapp] Send error (code=%s): %s",
                error_code,
                error_msg,
            )
            return SendResult(
                success=False,
                error=f"WhatsApp API error (code={error_code}): {error_msg}",
                raw=data,
                retryable=True,
            )
        except Exception as e:
            logger.error("[whatsapp] Send request failed: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to a WhatsApp chat."""
        if self._http is None:
            return
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "action",
            "action": {"name": "typing"},
        }
        try:
            await self._http.post(
                f"{WHATSAPP_BASE_URL}/{self._phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except Exception as e:
            logger.debug("[whatsapp] send_typing error: %s", e)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"id": chat_id, "platform": self.name}

    # ── Webhook ────────────────────────────────────────────────────────────

    async def handle_webhook(
        self,
        body: Any,
        _headers: dict[str, str],
        verify_token: str | None = None,
    ) -> dict[str, Any]:
        """Handle an incoming WhatsApp webhook callback.

        Supports two modes:

        1. **GET (verification challenge)** -- responds to Meta's webhook
           verification challenge.

        2. **POST (incoming message)** -- parses incoming text messages and
           dispatches them as :class:`MessageEvent` instances.
        """
        effective_token = verify_token or self._token

        if isinstance(body, dict):
            mode = body.get("hub.mode") or body.get("hub_mode")
            token = body.get("hub.verify_token") or body.get("hub_verify_token")
            challenge = body.get("hub.challenge") or body.get("hub_challenge")

            if mode and mode == "subscribe" and challenge is not None:
                if effective_token and token != effective_token:
                    logger.warning("[whatsapp] Webhook verify token mismatch")
                    return {"error": "verify token mismatch"}
                logger.info("[whatsapp] Webhook verified")
                return {"challenge": int(challenge) if challenge.isdigit() else challenge}

        if isinstance(body, bytes | str):
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return {"error": "invalid json"}
        elif isinstance(body, dict):
            payload = body
        else:
            return {"error": "unsupported body type"}

        try:
            await self._process_webhook_payload(payload)
        except Exception as e:
            logger.error("[whatsapp] Webhook processing error: %s", e)

        return {"ok": True}

    async def _process_webhook_payload(self, payload: dict[str, Any]) -> None:
        """Process an incoming WhatsApp webhook JSON payload."""
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    from_number = msg.get("from", "")
                    msg_id = msg.get("id", "")
                    msg_type = msg.get("type", "text")
                    timestamp = msg.get("timestamp", "")

                    text = ""
                    if msg_type == "text":
                        text = msg.get("text", {}).get("body", "")
                    elif msg_type == "button":
                        text = msg.get("button", {}).get("text", "")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        button_reply = interactive.get("button_reply", {})
                        list_reply = interactive.get("list_reply", {})
                        text = (
                            button_reply.get("title", "")
                            or list_reply.get("title", "")
                            or ""
                        )
                    elif msg_type == "image":
                        image = msg.get("image", {})
                        caption = image.get("caption", "")
                        image_id = image.get("id", "")
                        text = caption or f"[Image: {image_id}]"
                    elif msg_type == "audio":
                        text = "[Audio]"
                    elif msg_type == "video":
                        video = msg.get("video", {})
                        caption = video.get("caption", "")
                        video_id = video.get("id", "")
                        text = caption or f"[Video: {video_id}]"
                    elif msg_type == "document":
                        document = msg.get("document", {})
                        caption = document.get("caption", "")
                        filename = document.get("filename", "")
                        text = caption or f"[Document: {filename}]"

                    if text:
                        await self._on_message_received(from_number, text, msg_id, timestamp)

    async def _on_message_received(
        self,
        from_number: str,
        text: str,
        msg_id: str,
        timestamp: str = "",
    ) -> None:
        """Create a :class:`MessageEvent` and dispatch it to the handler."""
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=msg_id,
            raw_message={"from": from_number, "message_id": msg_id, "timestamp": timestamp},
            source=SessionSource(
                platform=self.name,
                chat_id=from_number,
                chat_type="dm",
                user_id=from_number,
            ),
        )

        self._spawn_task(self._dispatch_event(event))

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.source and event.source.chat_id:
            try:
                await self.send_typing(event.source.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    # ── HTTP Client ───────────────────────────────────────────────────────

    def _get_http_client(self) -> Any | None:
        """Get or create an httpx AsyncClient."""
        if self._http is not None:
            return self._http
        try:
            import httpx as _httpx
            proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
            client_kwargs: dict[str, Any] = {"timeout": 30.0, "follow_redirects": True}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
                logger.info("[whatsapp] Using proxy: %s", proxy_url)
            return _httpx.AsyncClient(**client_kwargs)
        except ImportError:
            logger.error(
                "[whatsapp] httpx is required. Install with: pip install httpx"
            )
            return None


# ---------------------------------------------------------------------------
# Platform registration
# ---------------------------------------------------------------------------

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return HTTPX_AVAILABLE


platform_registry.register(PlatformEntry(
    name="whatsapp",
    label="WhatsApp",
    platform=Platform.WHATSAPP,
    adapter_factory=lambda cfg: WhatsAppAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["WHATSAPP_PHONE_NUMBER"],
    install_hint="pip install httpx",
))
