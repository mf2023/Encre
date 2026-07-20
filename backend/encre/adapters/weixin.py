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
import io
import json
import logging
import os
import time
import uuid
from contextlib import suppress
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource

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


ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
CHANNEL_VERSION = "2.2.0"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
QR_TIMEOUT_MS = 35_000
LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
SESSION_EXPIRED_ERRCODE = -14


def _random_wechat_uin() -> str:
    import struct, secrets, base64
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _ilink_headers(token: str, body: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


def _random_wechat_uin() -> str:
    import struct, secrets, base64
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _ilink_headers(token: str, body: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


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
        *,
        api_url: str = "",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """Initialize the WeChat adapter.

        Args:
            app_id: Application ID from the iLink Bot server.
            token: Authentication token from the iLink Bot server.
            api_url: Base URL of the iLink Bot HTTP API server, e.g.
                ``http://127.0.0.1:8080``.  When empty, falls back to deriving
                from ``gateway_url`` (legacy behaviour).
            gateway_url: WebSocket URL of the Encre agent gateway.
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required.  Install with: pip install httpx"
            )
        self._app_id = app_id
        self._token = token
        self._api_base = api_url.rstrip("/") if api_url else _derive_api_base(gateway_url)

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
        """Continuously poll ``getupdates`` for inbound messages via iLink Bot API.

        Uses POST to the cloud API with proper authentication headers.
        """
        sync_buf = ""
        timeout_ms = LONG_POLL_TIMEOUT_MS
        consecutive_failures = 0
        max_failures = 5
        while self._running:
            if not self._http_client:
                logger.warning("[%s] HTTP client unavailable, stopping poll", self.name)
                return

            try:
                payload = {"get_updates_buf": sync_buf, "base_info": _base_info()}
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                api_base = ILINK_BASE_URL if self._api_base.startswith("http://127.0.0.1") else self._api_base
                resp = await self._http_client.post(
                    f"{api_base}/{EP_GET_UPDATES}",
                    content=body,
                    headers=_ilink_headers(self._token, body),
                    timeout=timeout_ms / 1000 + 5.0,
                )
                if resp.status_code != 200:
                    logger.warning("[%s] getupdates HTTP %d: %s", self.name, resp.status_code, resp.text[:200])
                    consecutive_failures += 1
                    await asyncio.sleep(min(30, 2 ** consecutive_failures))
                    continue

                data = resp.json()
                ret = data.get("ret", 0)
                errcode = data.get("errcode", 0)
                if ret not in {0, None} or errcode not in {0, None}:
                    if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
                        logger.error("[%s] Session expired; pausing for 10 minutes", self.name)
                        await asyncio.sleep(600)
                        continue
                    consecutive_failures += 1
                    logger.warning("[%s] getupdates error ret=%s errcode=%s: %s", self.name, ret, errcode, data.get("errmsg", ""))
                    await asyncio.sleep(min(30, 2 ** consecutive_failures))
                    if consecutive_failures >= max_failures:
                        consecutive_failures = 0
                    continue

                consecutive_failures = 0
                new_sync_buf = str(data.get("get_updates_buf") or "")
                if new_sync_buf:
                    sync_buf = new_sync_buf

                suggested_timeout = data.get("longpolling_timeout_ms")
                if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                    timeout_ms = suggested_timeout

                for message in data.get("msgs") or []:
                    asyncio.ensure_future(self._handle_message(message))

            except httpx.TimeoutException:
                pass
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("[%s] poll_loop error", self.name)
                if not self._running:
                    return
                await asyncio.sleep(_POLL_INTERVAL)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Process a single message from the iLink Bot API."""
        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id or sender_id == self._app_id:
            return

        message_id = str(message.get("message_id") or "").strip()
        if message_id:
            if message_id in self._seen_updates:
                return
            self._seen_updates[message_id] = time.time()
            if len(self._seen_updates) > 5000:
                cutoff = time.time() - _MESSAGE_DEDUP_TTL_SECONDS
                self._seen_updates = {k: v for k, v in self._seen_updates.items() if v > cutoff}

        item_list = message.get("item_list") or []
        text = ""
        for item in item_list:
            if isinstance(item, dict):
                text_item = item.get("text_item") or {}
                text = text_item.get("text", "") or text

        if not text:
            return

        chat_id = sender_id
        msg_id = message_id or uuid.uuid4().hex[:16]

        event = MessageEvent(
            text=text,
            message_id=msg_id,
            chat_id=chat_id,
            user_id=sender_id,
            source=SessionSource(
                platform=self.name,
                chat_id=chat_id,
                chat_type="dm",
                user_id=sender_id,
            ),
        )
        await self._dispatch_event(event)

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.chat_id:
            try:
                await self.send_typing(event.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

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

        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": chat_id,
            "client_id": uuid.uuid4().hex[:16],
            "message_type": 1,
            "message_state": 4,
            "item_list": [{"type": 1, "text_item": {"text": content}}],
        }
        if reply_to:
            message["reply_to_message_id"] = reply_to
        if metadata:
            message.update(metadata)

        payload = {"msg": message, "base_info": _base_info()}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            api_base = ILINK_BASE_URL if self._api_base.startswith("http://127.0.0.1") else self._api_base
            resp = await self._http_client.post(
                f"{api_base}/{EP_SEND_MESSAGE}",
                content=body,
                headers=_ilink_headers(self._token, body),
                timeout=API_TIMEOUT_MS / 1000,
            )
            body_resp = resp.json() if resp.text else {}
            ret = body_resp.get("ret", 0)
            errcode = body_resp.get("errcode", 0)
            if ret == 0 and (errcode == 0 or errcode is None):
                return SendResult(
                    success=True,
                    message_id=str(body_resp.get("message_id", uuid.uuid4().hex[:16])),
                    raw=body_resp,
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
        payload = {"to_user_id": chat_id, "base_info": _base_info()}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            api_base = ILINK_BASE_URL if self._api_base.startswith("http://127.0.0.1") else self._api_base
            await self._http_client.post(
                f"{api_base}/{EP_SEND_TYPING}",
                content=body,
                headers=_ilink_headers(self._token, body),
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("[%s] send_typing error: %s", self.name, exc)

    async def get_qrcode_url(self) -> tuple[str, str]:
        """Fetch a WeChat login QR code from the iLink Bot cloud API.

        Calls ``https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode`` to
        get a scannable liteapp URL, then renders it as a base64 data URI so
        the frontend can display it as an inline image.  The QR code is
        scannable for ~120 seconds.

        Returns:
            A tuple of (data_uri, qrcode_token).
        """
        import httpx
        try:
            import qrcode  # type: ignore
        except ImportError:
            qrcode = None  # type: ignore
        # Prefer the configured api_url (if it points at a local iLink mirror),
        # otherwise use the official Tencent cloud endpoint.  The legacy
        # _derive_api_base produces a 127.0.0.1 address (the Encre WS gateway),
        # which is NOT the iLink Bot API -- override it here.
        base = ILINK_BASE_URL
        if self._api_base and not self._api_base.startswith("http://127.0.0.1"):
            base = self._api_base
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }
        try:
            async with httpx.AsyncClient(timeout=QR_TIMEOUT_MS / 1000, follow_redirects=True) as client:
                resp = await client.get(
                    f"{base.rstrip('/')}/{EP_GET_BOT_QR}",
                    params={"bot_type": "3"},
                    headers=headers,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"iLink HTTP {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
            qrcode_value = str(data.get("qrcode") or "")
            qrcode_url = str(data.get("qrcode_img_content") or "")
            if not qrcode_value:
                raise RuntimeError("iLink response missing qrcode token")
            # qrcode_img_content is the full scannable liteapp URL; qrcode is
            # just the hex token.  WeChat scans the full URL.
            scan_data = qrcode_url if qrcode_url else qrcode_value
            if qrcode is not None:
                # Render to a PNG data URI so the frontend can inline it.
                img = qrcode.make(scan_data)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = buf.getvalue().hex()
                # Build data URI without base64 codec (hex is fine for PNG).
                import base64 as _b64
                return ("data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode("ascii"), qrcode_value)
            return (scan_data, qrcode_value)
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to iLink Bot server (https://ilinkai.weixin.qq.com)")
        except httpx.TimeoutException:
            raise RuntimeError("iLink Bot server timed out")

    async def poll_qrcode_status(self, qrcode_token: str) -> dict | None:
        """Poll the iLink Bot API for QR code scan status.

        Calls ``get_qrcode_status?qrcode=<token>`` repeatedly until the
        status is ``confirmed``, ``expired``, or the timeout is reached.

        Returns:
            A dict with credentials when confirmed, or None on timeout/error.
        """
        import httpx
        base = ILINK_BASE_URL
        if self._api_base and not self._api_base.startswith("http://127.0.0.1"):
            base = self._api_base
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }
        deadline = time.time() + 120
        backoff = 2
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                while time.time() < deadline:
                    try:
                        resp = await client.get(
                            f"{base.rstrip('/')}/{EP_GET_QR_STATUS}",
                            params={"qrcode": qrcode_token},
                            headers=headers,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            status = data.get("status", "wait")
                            if status == "confirmed":
                                return {
                                    "ilink_bot_id": data.get("ilink_bot_id", ""),
                                    "bot_token": data.get("bot_token", ""),
                                    "baseurl": data.get("baseurl", ""),
                                    "ilink_user_id": data.get("ilink_user_id", ""),
                                }
                            elif status == "expired":
                                return None
                    except Exception:
                        pass
                    await asyncio.sleep(backoff)
                    backoff = min(backoff + 1, 5)
        except Exception:
            pass
        return None
