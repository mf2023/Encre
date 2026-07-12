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
# weixin.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - WeixinAdapter
#
# Module-level helpers:
#   - _derive_api_base
#
import asyncio
import logging
import os
import time
import uuid
from contextlib import suppress
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

import importlib

CRYPTO_AVAILABLE = importlib.util.find_spec("cryptography") is not None



logger = logging.getLogger("encre.adapters.weixin")

_POLL_INTERVAL = 0.5
_RECONNECT_BACKOFF = [1, 2, 5, 10, 30]
_POLL_TIMEOUT = 30.0
_SEND_TIMEOUT = 15.0
_MESSAGE_DEDUP_TTL_SECONDS = 300


def _derive_api_base(gateway_url: str) -> str:
    """
    Derive api base.

    Args:
        gateway_url (str):

    Returns:
        str
    """
    gateway_url = gateway_url.strip()
    if gateway_url.startswith("ws://"):
        rest = gateway_url[5:]
    elif gateway_url.startswith("wss://"):
        rest = gateway_url[6:]
    else:
        rest = gateway_url
    host_part = rest.split("/")[0]
    return f"http://{host_part}"


class WeixinAdapter(BaseAdapter):
    """WeChat bot adapter using Tencent iLink Bot API.

    Connects to a local iLink Bot gateway via long-polling and relays
    messages to the Encre gateway for AI processing.  Supports text
    messages and typing indicators.

    The iLink Bot API is provided by Tencent's official WeChat bot
    framework (https://ilinkai.weixin.qq.com).  A local gateway process
    must be running on the configured ``gateway_url`` port.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.weixin import WeixinAdapter  # noqa: E402

        async def main():
            adapter = WeixinAdapter(app_id="wx_xxx", token="bot_token")
            await adapter.start()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.stop()

        asyncio.run(main())
    """

    name = "weixin"

    def __init__(
        self,
        app_id: str = "",
        token: str = "",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """
        Initialize the instance..

        Args:
            app_id (str):
            token (str):
            gateway_url (str):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required.  Install with: pip install httpx"
            )
        self._app_id = app_id
        self._token = token
        self._api_base = _derive_api_base(gateway_url)

        self._http_client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[Any] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._offset: int = 0
        self._seen_updates: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Initialize the HTTP client and start the long-poll loop."""
        if not self._app_id and not self._token:
            logger.warning(
                "[%s] Neither app_id nor token provided; polling will be unauthenticated",
                self.name,
            )

        try:
            logger.info("[%s] Initializing HTTP client...", self.name)
            proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
            client_kwargs: dict[str, Any] = {"timeout": 30.0, "follow_redirects": True}
            if proxy_url:
                client_kwargs["proxies"] = {"http://": proxy_url, "https://": proxy_url}
                logger.info("[%s] Using proxy: %s", self.name, proxy_url)
            self._http_client = httpx.AsyncClient(**client_kwargs)

            logger.info("[%s] Marking connected state...", self.name)
            self._mark_connected()
            logger.info("[%s] Starting poll loop...", self.name)
            self._poll_task = asyncio.create_task(self._poll_loop())

            logger.info(
                "[%s] Connected, polling iLink Bot API at %s",
                self.name, self._api_base,
            )
            return True
        except Exception:
            logger.exception("[%s] Failed to connect", self.name)
            await self._cleanup_http()
            return False

    async def disconnect(self) -> None:
        """Stop polling and clean up HTTP client."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self._cleanup_http()
        await self._client.disconnect()
        self._mark_disconnected()
        logger.info("[%s] Disconnected", self.name)

    async def _cleanup_http(self) -> None:
        """
        Cleanup http.

        Returns:
            None
        """
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Long-poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Continuously poll ``getupdates`` for inbound messages.

        Runs as a background task for the lifetime of the adapter.
        Uses an offset-based cursor (like Telegram's getUpdates) to
        acknowledge messages and avoid re-processing.
        """
        backoff_idx = 0
        while self._running:
            if not self._http_client:
                logger.warning("[%s] HTTP client unavailable, stopping poll", self.name)
                return

            try:
                params: dict[str, Any] = {
                    "offset": self._offset,
                    "timeout": _POLL_TIMEOUT,
                }
                if self._token:
                    params["token"] = self._token
                if self._app_id:
                    params["app_id"] = self._app_id

                resp = await self._http_client.get(
                    f"{self._api_base}/ilink/bot/getupdates",
                    params=params,
                    timeout=_POLL_TIMEOUT + 5.0,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok") and isinstance(data.get("result"), list):
                        updates = data["result"]
                        if updates:
                            backoff_idx = 0
                            for update in updates:
                                self._handle_update(update)
                            max_update_id = max(
                                u["update_id"] for u in updates
                                if isinstance(u.get("update_id"), int)
                            )
                            self._offset = max_update_id + 1
                    continue

                logger.warning(
                    "[%s] getupdates HTTP %d: %s",
                    self.name, resp.status_code, resp.text[:200],
                )

            except httpx.TimeoutException:
                pass
            except httpx.ConnectError:
                if not self._running:
                    return
                delay = _RECONNECT_BACKOFF[
                    min(backoff_idx, len(_RECONNECT_BACKOFF) - 1)
                ]
                logger.info(
                    "[%s] Connection refused, retrying in %ds...",
                    self.name, delay,
                )
                await asyncio.sleep(delay)
                backoff_idx += 1
                continue
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("[%s] poll_loop error", self.name)
                if not self._running:
                    return
                await asyncio.sleep(_POLL_INTERVAL)
                continue

            backoff_idx = 0
            await asyncio.sleep(_POLL_INTERVAL)

    def _handle_update(self, update: dict[str, Any]) -> None:
        """Parse a single update dict and dispatch a MessageEvent."""
        update_id = update.get("update_id")
        if update_id is not None:
            now = time.time()
            if update_id in self._seen_updates and now - self._seen_updates[update_id] < _MESSAGE_DEDUP_TTL_SECONDS:
                return
            self._seen_updates[update_id] = now
            if len(self._seen_updates) > 5000:
                cutoff = now - _MESSAGE_DEDUP_TTL_SECONDS
                self._seen_updates = {
                    k: v for k, v in self._seen_updates.items() if v > cutoff
                }

        message = update.get("message") or update.get("Message") or {}
        if not isinstance(message, dict):
            return

        text = (
            message.get("text")
            or message.get("Text")
            or message.get("content")
            or message.get("Content")
            or ""
        )
        if not text:
            return

        chat_id = (
            message.get("chat_id")
            or message.get("ChatId")
            or message.get("ChatID")
            or message.get("from_user")
            or message.get("FromUser")
            or message.get("FromUserName")
            or ""
        )
        if not chat_id:
            chat_id = str(update_id) if update_id is not None else ""

        msg_id = (
            message.get("message_id")
            or message.get("MessageId")
            or message.get("MsgId")
            or uuid.uuid4().hex[:16]
        )

        user_id = (
            message.get("from_user")
            or message.get("FromUser")
            or message.get("FromUserName")
            or message.get("user_id")
            or message.get("UserId")
            or chat_id
        )

        reply_to_message_id: str | None = None
        reply_to_text: str | None = None
        reply_to = message.get("reply_to_message") or message.get("ReplyToMessage") or {}
        if isinstance(reply_to, dict):
            reply_to_message_id = (
                reply_to.get("message_id")
                or reply_to.get("MessageId")
                or reply_to.get("MsgId")
            )
            reply_to_text = (
                reply_to.get("text")
                or reply_to.get("Text")
                or reply_to.get("content")
                or reply_to.get("Content")
            )

        event = MessageEvent(
            text=str(text),
            message_type=MessageType.TEXT,
            message_id=str(msg_id),
            chat_id=str(chat_id),
            user_id=str(user_id),
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            raw=update,
        )

        self.dispatch_message(event)

        task = asyncio.create_task(self._process_chat(str(chat_id), str(text)))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response to chat."""
        if not content.strip():
            return
        session_id = self.get_session(chat_id)
        await self.send_typing(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    # ------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message via the iLink Bot ``sendmessage`` endpoint."""
        if not self._http_client:
            return SendResult(success=False, error="Adapter not connected")

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": content,
        }
        if self._token:
            payload["token"] = self._token
        if self._app_id:
            payload["app_id"] = self._app_id
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to

        if metadata:
            payload.update(metadata)

        try:
            resp = await self._http_client.post(
                f"{self._api_base}/ilink/bot/sendmessage",
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
            body = resp.json() if resp.text else {}
            if resp.status_code < 300 and body.get("ok", True):
                return SendResult(
                    success=True,
                    message_id=str(body.get("message_id", body.get("MessageId", uuid.uuid4().hex[:16]))),
                    raw=body,
                )
            logger.warning(
                "[%s] send error HTTP %d: %s",
                self.name, resp.status_code, resp.text[:200],
            )
            return SendResult(
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                retryable=resp.status_code >= 500,
            )
        except httpx.TimeoutException:
            return SendResult(success=False, error="Timeout", retryable=True)
        except Exception as exc:
            logger.error("[%s] send exception: %s", self.name, exc)
            return SendResult(success=False, error=str(exc), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator via the iLink Bot ``sendtyping`` endpoint."""
        if not self._http_client:
            return
        payload: dict[str, Any] = {
            "chat_id": chat_id,
        }
        if self._token:
            payload["token"] = self._token
        if self._app_id:
            payload["app_id"] = self._app_id
        try:
            await self._http_client.post(
                f"{self._api_base}/ilink/bot/sendtyping",
                json=payload,
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("[%s] send_typing error: %s", self.name, exc)
