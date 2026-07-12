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
# qqbot.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - QQCloseError
#   - QQBotAdapter
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

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.qqbot")

try:
    import aiohttp

    QQ_AVAILABLE = True
except ImportError:
    QQ_AVAILABLE = False


API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GATEWAY_URL_PATH = "/gateway"

DEFAULT_API_TIMEOUT = 30.0
CONNECT_TIMEOUT_SECONDS = 20.0
MAX_MESSAGE_LENGTH = 4000

MSG_TYPE_TEXT = 0
MSG_TYPE_INPUT_NOTIFY = 6

DEDUP_WINDOW_SECONDS = 300
DEDUP_MAX_SIZE = 1000

RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_RECONNECT_ATTEMPTS = 100
QUICK_DISCONNECT_THRESHOLD = 5.0
MAX_QUICK_DISCONNECT_COUNT = 3


class QQCloseError(Exception):
    """
    QQCloseError adapter component.
    
    Inherits from Exception and integrates an external platform or
    channel into the Encre adapter framework. It implements the standard
    adapter contract used by the manager to connect, send and receive
    messages, and to dispatch normalized events into the agent runtime.
    
    Responsibilities:
        * Establish and maintain a connection/session to the platform.
        * Translate inbound platform events into normalized messages.
        * Translate outbound messages into platform-specific API calls.
        * Expose lifecycle hooks (connect/disconnect, start/stop).
    """
    def __init__(self, code: int | None = None, reason: str = "") -> None:
        """
        Initialize the instance..

        Args:
            code (int | None):
            reason (str):

        Returns:
            None
        """
        self.code = int(code) if code is not None else None
        self.reason = str(reason) if reason else ""
        super().__init__(f"WebSocket closed (code={self.code}, reason={self.reason})")


class QQBotAdapter(BaseAdapter):
    """QQ Bot adapter using the Official QQ Bot API v2.

    Connects to the QQ Bot WebSocket Gateway for receiving events and uses the
    REST API (``api.sgroup.qq.com``) for sending messages.

    Requires ``aiohttp`` for WebSocket and HTTP operations.
    """

    name = "qqbot"

    @classmethod
    async def validate_config(cls, config: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate config.

        Args:
            config (dict[str, Any]):

        Returns:
            tuple[bool, str]
        """
        app_id = config.get("app_id", "")
        client_secret = config.get("client_secret", "")
        if not app_id:
            return (False, "app_id is required")
        if not client_secret:
            return (False, "client_secret is required")
        if not QQ_AVAILABLE:
            return (False, "aiohttp is required: pip install aiohttp")
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session, session.post(
                TOKEN_URL,
                json={"appId": app_id, "clientSecret": client_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "access_token" in data:
                        return (True, "Authentication successful")
                    return (False, f"Unexpected response: {data}")
                text = await resp.text()
                return (False, f"Auth failed (HTTP {resp.status}): {text[:200]}")
        except TimeoutError:
            return (False, "Connection timed out to bots.qq.com")
        except Exception as e:
            return (False, f"Connection error: {e}")

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        """
        Initialize the instance..

        Args:
            app_id (str):
            client_secret (str):
            gateway_url (str):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not QQ_AVAILABLE:
            raise ImportError(
                "aiohttp is required for QQ Bot adapter. "
                "Install with: pip install aiohttp"
            )
        self._app_id = app_id
        self._client_secret = client_secret

        self._ws_session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._listen_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval: float = 30.0
        self._session_id: str | None = None
        self._last_seq: int | None = None

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

        self._seen_messages: dict[str, float] = {}
        self._chat_type_map: dict[str, str] = {}
        self._last_msg_id: dict[str, str] = {}
        self._http_session: aiohttp.ClientSession | None = None
        self._typing_sent_at: dict[str, float] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Authenticate, obtain QQ gateway URL, open WS, and start listeners."""
        if not self._app_id or not self._client_secret:
            msg = "QQ_APP_ID and QQ_CLIENT_SECRET are required"
            logger.error("[qqbot] %s", msg)
            self._set_fatal_error("config_missing", msg)
            return False

        # Start GatewayClient so process_with_stream can reach the server
        self._gateway_started = True
        _t = asyncio.ensure_future(self._client.connect())
        self._background_tasks.add(_t)
        # Wait up to 15s for the gateway connection to establish
        for _i in range(30):
            if self._client.is_connected:
                logger.info("[qqbot] GatewayClient connected")
                break
            await asyncio.sleep(0.5)
        else:
            logger.warning("[qqbot] GatewayClient not connected after 15s, retrying in background")

        # Create shared HTTP session for REST API calls
        try:
            self._http_session = aiohttp.ClientSession(trust_env=True)
        except Exception as exc:
            msg = f"Failed to create HTTP session: {exc}"
            logger.error("[qqbot] %s", msg)
            self._set_fatal_error("http_session", msg)
            return False

        # Step 1: Get access token
        try:
            await self._ensure_token()
            logger.info("[qqbot] Step 1 OK -- token obtained")
        except Exception as exc:
            msg = f"Step 1 FAILED -- token request: {exc}"
            logger.error("[qqbot] %s", msg, exc_info=True)
            self._set_fatal_error("token", msg)
            await self._cleanup()
            return False

        # Step 2: Get WebSocket gateway URL
        try:
            gateway_url = await self._get_gateway_url()
            if not gateway_url:
                raise RuntimeError("Empty gateway URL returned")
            logger.info("[qqbot] Step 2 OK -- gateway URL: %s", gateway_url)
        except Exception as exc:
            msg = f"Step 2 FAILED -- gateway URL: {exc}"
            logger.error("[qqbot] %s", msg, exc_info=True)
            self._set_fatal_error("gateway_url", msg)
            await self._cleanup()
            return False

        # Step 3: Open WebSocket connection to QQ Bot
        try:
            await self._open_ws(gateway_url)
            logger.info("[qqbot] Step 3 OK -- WebSocket opened")
        except Exception as exc:
            msg = f"Step 3 FAILED -- WebSocket connect: {exc}"
            logger.error("[qqbot] %s", msg, exc_info=True)
            self._set_fatal_error("ws_connect", msg)
            await self._cleanup()
            return False

        # Step 4: Start background listeners
        try:
            self._listen_task = asyncio.create_task(self._ws_listen())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("[qqbot] Step 4 OK -- listeners started")
        except Exception as exc:
            msg = f"Step 4 FAILED -- create listeners: {exc}"
            logger.error("[qqbot] %s", msg, exc_info=True)
            self._set_fatal_error("listeners", msg)
            await self._cleanup()
            return False

        self._mark_connected()
        logger.info("[qqbot] QQ Bot adapter fully connected")
        return True

    async def disconnect(self) -> None:
        """Close all connections and stop listeners."""
        self._running = False

        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        await self._cleanup()
        await super().disconnect()
        logger.info("[qqbot] Disconnected")

    async def _cleanup(self) -> None:
        """Close WebSocket and HTTP sessions."""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._ws_session and not self._ws_session.closed:
            await self._ws_session.close()
        self._ws_session = None

        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        self._http_session = None

    def _bg_task(self, coro: Any) -> asyncio.Task:
        """Schedule a background task tracked in _background_tasks."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        def _log_error(t: asyncio.Task) -> None:
            """
            Log error.

            Args:
                t (asyncio.Task):

            Returns:
                None
            """
            self._background_tasks.discard(t)
            exc = t.exception()
            if exc:
                logger.error("[qqbot] background task failed: %s", exc, exc_info=exc)
        task.add_done_callback(_log_error)
        return task

    # ── Token management ───────────────────────────────────────────────────

    async def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        async with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 60:
                return self._access_token

            try:
                session = self._http_session or aiohttp.ClientSession(trust_env=True)
                async with session.post(
                    TOKEN_URL,
                    json={"appId": self._app_id, "clientSecret": self._client_secret},
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_API_TIMEOUT),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            except TimeoutError:
                raise RuntimeError("Timed out connecting to bots.qq.com (30s)") from None
            except aiohttp.ClientResponseError as exc:
                raise RuntimeError(f"Token API returned HTTP {exc.status}: {exc.message}") from exc
            except Exception as exc:
                raise RuntimeError(f"Failed to get QQ Bot access token: {exc}") from exc

            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"QQ Bot token response missing access_token: {data}")

            expires_in = int(data.get("expires_in", 7200))
            self._access_token = token
            self._token_expires_at = time.time() + expires_in
            logger.info("[qqbot] Access token refreshed, expires in %ds", expires_in)
            return self._access_token

    async def _get_gateway_url(self) -> str:
        """Fetch the WebSocket gateway URL from the REST API."""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "User-Agent": self._build_user_agent(),
        }
        try:
            session = self._http_session or aiohttp.ClientSession(trust_env=True)
            async with session.get(
                f"{API_BASE}{GATEWAY_URL_PATH}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_API_TIMEOUT),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Gateway URL API returned HTTP {resp.status}: {body[:500]}"
                    )
                data = await resp.json()
        except TimeoutError:
            raise RuntimeError("Timed out fetching gateway URL from api.sgroup.qq.com (30s)") from None
        except aiohttp.ClientResponseError as exc:
            raise RuntimeError(f"Gateway URL API returned HTTP {exc.status}: {exc.message}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to get QQ Bot gateway URL: {exc}") from exc

        url = data.get("url")
        if not url:
            raise RuntimeError(f"QQ Bot gateway response missing url: {data}")
        return url

    # ── WebSocket lifecycle ────────────────────────────────────────────────

    async def _open_ws(self, gateway_url: str) -> None:
        """Open a WebSocket connection to the QQ Bot gateway.

        Respects proxy env vars (WSS_PROXY, HTTPS_PROXY, ALL_PROXY) for
        users behind enterprise/corporate proxies (matching Hermes behavior).
        """
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        if self._ws_session and not self._ws_session.closed:
            await self._ws_session.close()
        self._ws_session = None

        # Honor proxy env vars -- critical for users behind corporate proxies
        ws_proxy = (
            os.getenv("WSS_PROXY")
            or os.getenv("WSS_PROXY")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("ALL_PROXY")
            or os.getenv("ALL_PROXY")
        )
        logger.info("[qqbot] WebSocket proxy: %s", ws_proxy or "(none)")

        self._ws_session = aiohttp.ClientSession(trust_env=True)
        self._ws = await self._ws_session.ws_connect(
            gateway_url,
            headers={"User-Agent": self._build_user_agent()},
            timeout=CONNECT_TIMEOUT_SECONDS,
            proxy=ws_proxy,
        )
        logger.info("[qqbot] WebSocket connected to %s", gateway_url)

    async def _ws_listen(self) -> None:
        """Read WebSocket events and handle protocol lifecycle."""
        backoff_idx = 0
        connect_time = 0.0
        quick_disconnect_count = 0

        while self._running:
            try:
                connect_time = time.monotonic()
                await self._read_events()
                backoff_idx = 0
                quick_disconnect_count = 0
            except asyncio.CancelledError:
                return
            except QQCloseError as exc:
                if not self._running:
                    return

                code = exc.code
                logger.warning("[qqbot] WebSocket closed: code=%s reason=%s", code, exc.reason)

                duration = time.monotonic() - connect_time
                if duration < QUICK_DISCONNECT_THRESHOLD and connect_time > 0:
                    quick_disconnect_count += 1
                    if quick_disconnect_count >= MAX_QUICK_DISCONNECT_COUNT:
                        msg = (
                            "[qqbot] Too many quick disconnects "
                            "\u2014 check bot permissions"
                        )
                        logger.error(msg)
                        self._set_fatal_error(
                            "qq_quick_disconnect", "Too many quick disconnects"
                        )
                        return
                else:
                    quick_disconnect_count = 0

                if code in {4001, 4002, 4010, 4011, 4012, 4013, 4014, 4914, 4915}:
                    descriptions = {
                        4001: "invalid opcode", 4002: "invalid payload",
                        4010: "invalid shard", 4011: "sharding required",
                        4012: "invalid API version", 4013: "invalid intent",
                        4014: "intent not authorized", 4914: "offline/sandbox-only",
                        4915: "banned",
                    }
                    desc = descriptions.get(code, f"fatal error (code={code})")
                    logger.error("[qqbot] Bot is %s. Check QQ Open Platform.", desc)
                    self._set_fatal_error(f"qq_{desc}", f"Bot is {desc}")
                    return

                if code == 4004:
                    self._access_token = None
                    self._token_expires_at = 0.0

                if code in {4006, 4007, 4900, 4901, 4902, 4903, 4904, 4905, 4906,
                            4907, 4908, 4909, 4910, 4911, 4912, 4913}:
                    self._session_id = None
                    self._last_seq = None

                if await self._reconnect(backoff_idx):
                    backoff_idx = 0
                    quick_disconnect_count = 0
                else:
                    backoff_idx += 1
                    if backoff_idx >= MAX_RECONNECT_ATTEMPTS:
                        logger.error("[qqbot] Max reconnect attempts reached")
                        self._mark_disconnected()
                        return

            except Exception as exc:
                if not self._running:
                    return
                logger.warning("[qqbot] WebSocket error: %s", exc)
                self._mark_disconnected()
                if backoff_idx >= MAX_RECONNECT_ATTEMPTS:
                    logger.error("[qqbot] Max reconnect attempts reached")
                    return
                if await self._reconnect(backoff_idx):
                    backoff_idx = 0
                    quick_disconnect_count = 0
                else:
                    backoff_idx += 1

    async def _reconnect(self, backoff_idx: int) -> bool:
        """Attempt to reconnect the WebSocket. Returns True on success."""
        delay = RECONNECT_BACKOFF[min(backoff_idx, len(RECONNECT_BACKOFF) - 1)]
        logger.info("[qqbot] Reconnecting in %ds (attempt %d)...", delay, backoff_idx + 1)
        await asyncio.sleep(delay)

        self._heartbeat_interval = 30.0
        try:
            await self._ensure_token()
            gateway_url = await self._get_gateway_url()
            await self._open_ws(gateway_url)
            self._mark_connected()
            logger.info("[qqbot] Reconnected")
            return True
        except Exception as exc:
            logger.warning("[qqbot] Reconnect failed: %s", exc)
            return False

    async def _read_events(self) -> None:
        """Read WebSocket frames until connection closes."""
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        while self._running and self._ws and not self._ws.closed:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                logger.info("[qqbot] WS recv: %.120s", msg.data[:120])
                payload = self._parse_json(msg.data)
                if payload:
                    self._dispatch_payload(payload)
            elif msg.type == aiohttp.WSMsgType.PING:
                pass
            elif msg.type == aiohttp.WSMsgType.CLOSE:
                raise QQCloseError(msg.data, msg.extra)
            elif msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                raise RuntimeError("WebSocket closed")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats (op 1 heartbeat with latest seq)."""
        try:
            while self._running:
                await asyncio.sleep(self._heartbeat_interval)
                if not self._ws or self._ws.closed:
                    continue
                try:
                    await self._ws.send_json({"op": 1, "d": self._last_seq})
                except Exception as exc:
                    logger.debug("[qqbot] Heartbeat failed: %s", exc)
        except asyncio.CancelledError:
            pass

    async def _send_identify(self) -> None:
        """Send op 2 Identify to authenticate the WebSocket connection.

        Intents:
          1<<25 = C2C_MESSAGE (私聊消息)
          1<<30 = GROUP_AT_MESSAGE (群聊@消息)
          1<<12 = DIRECT_MESSAGE (频道私信)
          1<<26 = INTERACTION (按钮交互事件)
        """
        token = await self._ensure_token()
        identify_payload = {
            "op": 2,
            "d": {
                "token": f"QQBot {token}",
                "intents": (1 << 25) | (1 << 30) | (1 << 12) | (1 << 26),
                "shard": [0, 1],
                "properties": {
                    "$os": "windows",
                    "$browser": "encre",
                    "$device": "encre",
                },
            },
        }
        try:
            if self._ws and not self._ws.closed:
                await self._ws.send_json(identify_payload)
                logger.info("[qqbot] Identify sent")
            else:
                logger.warning("[qqbot] Cannot send Identify: WebSocket not connected")
        except Exception as exc:
            logger.error("[qqbot] Failed to send Identify: %s", exc)

    async def _send_resume(self) -> None:
        """Send op 6 Resume to re-authenticate after reconnection."""
        token = await self._ensure_token()
        resume_payload = {
            "op": 6,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self._session_id,
                "seq": self._last_seq,
            },
        }
        try:
            if self._ws and not self._ws.closed:
                await self._ws.send_json(resume_payload)
                logger.info(
                    "[qqbot] Resume sent (session_id=%s, seq=%s)",
                    self._session_id,
                    self._last_seq,
                )
        except Exception as exc:
            logger.error("[qqbot] Failed to send Resume: %s", exc)
            self._session_id = None
            self._last_seq = None

    # ── Payload dispatch ───────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: Any) -> dict | None:
        """
        Parse json.

        Args:
            raw (Any):

        Returns:
            dict | None
        """
        try:
            payload = json.loads(raw)
        except Exception:
            logger.warning("[qqbot] Failed to parse JSON: %r", raw)
            return None
        return payload if isinstance(payload, dict) else None

    def _dispatch_payload(self, payload: dict) -> None:
        """Route inbound WebSocket payloads."""
        op = payload.get("op")
        t = payload.get("t")
        s = payload.get("s")
        d = payload.get("d")
        if isinstance(s, int) and (self._last_seq is None or s > self._last_seq):
            self._last_seq = s

        if op == 10:
            d_data = d if isinstance(d, dict) else {}
            interval_ms = d_data.get("heartbeat_interval", 30000)
            self._heartbeat_interval = interval_ms / 1000.0 * 0.8
            logger.debug("[qqbot] Hello received, heartbeat_interval=%dms", interval_ms)
            if self._session_id and self._last_seq is not None:
                self._bg_task(self._send_resume())
            else:
                self._bg_task(self._send_identify())
            return

        if op == 0 and t:
            if t == "READY":
                self._handle_ready(d)
            elif t == "RESUMED":
                logger.info("[qqbot] Session resumed")
            elif t in {"C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"}:
                logger.info("[qqbot] Dispatching %s to handler", t)
                self._bg_task(self._handle_message(t, d))
            else:
                logger.debug("[qqbot] Unhandled dispatch: %s", t)
            return

        if op == 11:
            return

        if op == 7:
            logger.info("[qqbot] Server requested reconnect (op 7)")
            if self._ws and not self._ws.closed:
                self._bg_task(self._ws.close())
            return

        if op == 9:
            resumable = bool(d) if d is not None else False
            if not resumable:
                logger.info("[qqbot] Invalid session (op 9, not resumable), clearing session")
                self._session_id = None
                self._last_seq = None
            if self._ws and not self._ws.closed:
                self._bg_task(self._ws.close())
            return

    def _handle_ready(self, d: Any) -> None:
        """
        Handle ready.

        Args:
            d (Any):

        Returns:
            None
        """
        if isinstance(d, dict):
            self._session_id = d.get("session_id")
            logger.info("[qqbot] Ready, session_id=%s", self._session_id)

    # ── Message handling ───────────────────────────────────────────────────

    async def _handle_message(self, event_type: str, d: Any) -> None:
        """Process an inbound QQ Bot message event."""
        if not isinstance(d, dict):
            return

        msg_id = str(d.get("id", ""))
        if not msg_id or self._is_duplicate(msg_id):
            return

        content = str(d.get("content", "")).strip()
        author = d.get("author") if isinstance(d.get("author"), dict) else {}

        if event_type == "C2C_MESSAGE_CREATE":
            await self._handle_c2c_message(d, msg_id, content, author)
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            await self._handle_group_message(d, msg_id, content, author)

    async def _handle_c2c_message(
        self,
        d: dict,
        msg_id: str,
        content: str,
        author: dict,
    ) -> None:
        """Handle a C2C (private) message event."""
        user_openid = str(author.get("user_openid", ""))
        if not user_openid:
            return

        logger.info(
            "[qqbot] C2C message: id=%s content=%s",
            msg_id,
            content[:50] if content else "",
        )

        self._chat_type_map[user_openid] = "c2c"
        event = MessageEvent(
            text=content,
            message_type=MessageType.TEXT,
            message_id=msg_id,
            chat_id=user_openid,
            user_id=user_openid,
            raw=d,
        )
        self._last_msg_id[user_openid] = msg_id
        self.dispatch_message(event)
        self._bg_task(self._process_chat(user_openid, content))

    async def _handle_group_message(
        self,
        d: dict,
        msg_id: str,
        content: str,
        author: dict,
    ) -> None:
        """Handle a group @-message event."""
        group_openid = str(d.get("group_openid", ""))
        if not group_openid:
            return

        text = self._strip_at_mention(content)
        member_openid = str(author.get("member_openid", ""))

        logger.info(
            "[qqbot] Group message: id=%s group=%s content=%s",
            msg_id,
            group_openid,
            text[:50] if text else "",
        )

        self._chat_type_map[group_openid] = "group"
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=msg_id,
            chat_id=group_openid,
            user_id=member_openid or group_openid,
            raw=d,
        )
        self._last_msg_id[group_openid] = msg_id
        self.dispatch_message(event)
        self._bg_task(self._process_chat(group_openid, text))

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response."""
        session_id = self.get_session(chat_id)
        logger.info("[qqbot] _process_chat chat=%s session=%s content=%.60s",
                     chat_id, session_id or "(none)", content)
        await self.send_typing(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)
        logger.info("[qqbot] _process_chat done for chat=%s", chat_id)

    # ── Outbound messaging (REST API) ──────────────────────────────────────

    async def _api_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: float = DEFAULT_API_TIMEOUT,
    ) -> dict:
        """Make an authenticated REST API request to QQ Bot API."""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "User-Agent": self._build_user_agent(),
        }
        session = self._http_session or aiohttp.ClientSession(trust_env=True)
        async with session.request(
            method,
            f"{API_BASE}{path}",
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise RuntimeError(
                    f"QQ Bot API error [{resp.status}] {path}: {data.get('message', data)}"
                )
            return data

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a QQ user or group."""
        del metadata

        if not content or not content.strip():
            logger.warning("[qqbot] send empty content to %s", chat_id)
            return SendResult(success=True)

        chat_type = self._guess_chat_type(chat_id)
        logger.info("[qqbot] send chat=%s type=%s content=%.60s reply_to=%s",
                     chat_id, chat_type, content, reply_to or "none")
        try:
            msg_seq = self._next_msg_seq()
            body: dict[str, Any] = {
                "content": content[:MAX_MESSAGE_LENGTH],
                "msg_type": MSG_TYPE_TEXT,
                "msg_seq": msg_seq,
            }
            if reply_to:
                body["msg_id"] = reply_to

            if chat_type == "c2c":
                data = await self._api_request("POST", f"/v2/users/{chat_id}/messages", body)
            else:
                data = await self._api_request("POST", f"/v2/groups/{chat_id}/messages", body)

            msg_id = str(data.get("id", uuid.uuid4().hex[:12]))
            logger.info("[qqbot] send success chat=%s msg_id=%s", chat_id, msg_id)
            return SendResult(success=True, message_id=msg_id, raw=data)
        except Exception as exc:
            logger.error("[qqbot] send error for %s: %s", chat_id, exc)
            return SendResult(success=False, error=str(exc), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator (input_notify) to a C2C user."""
        chat_type = self._guess_chat_type(chat_id)
        if chat_type != "c2c":
            return

        msg_id = self._last_msg_id.get(chat_id)
        if not msg_id:
            return

        now = time.time()
        if now - self._typing_sent_at.get(chat_id, 0.0) < 50.0:
            return

        try:
            msg_seq = self._next_msg_seq()
            body = {
                "msg_type": MSG_TYPE_INPUT_NOTIFY,
                "msg_id": msg_id,
                "input_notify": {
                    "input_type": 1,
                    "input_second": 60,
                },
                "msg_seq": msg_seq,
            }
            await self._api_request("POST", f"/v2/users/{chat_id}/messages", body)
            self._typing_sent_at[chat_id] = now
        except Exception as exc:
            logger.debug("[qqbot] send_typing failed: %s", exc)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_user_agent() -> str:
        """
        Build user agent.

        Returns:
            str
        """
        return "Encre/1.0.0 (QQ Bot Adapter)"

    @staticmethod
    def _strip_at_mention(content: str) -> str:
        """Strip the @bot mention prefix from group message content."""
        return re.sub(r"^@\S+\s*", "", content.strip())

    def _guess_chat_type(self, chat_id: str) -> str:
        """Determine chat type from stored inbound metadata, fallback to 'c2c'."""
        return self._chat_type_map.get(chat_id, "c2c")

    @property
    def default_push_chat_id(self) -> str | None:
        """Return the most recently active **group** chat for push notifications.

        Prefers group chats over C2C since automation results are typically
        useful to share in a team/group context.  Falls back to the most recent
        C2C chat if no group has messaged the bot yet.

        The chat_type_map is populated whenever the bot receives an inbound
        message, so at least one person/group must have sent a message since the
        adapter started for this to return a value.
        """
        if not self._chat_type_map:
            return None
        # Prefer group chats; fall back to the most recent overall entry.
        groups = [cid for cid, ctype in self._chat_type_map.items() if ctype == "group"]
        if groups:
            return groups[-1]  # most recent group
        return next(reversed(list(self._chat_type_map.keys())))

    def _is_duplicate(self, msg_id: str) -> bool:
        """Check if a message ID has already been processed."""
        now = time.time()
        if len(self._seen_messages) > DEDUP_MAX_SIZE:
            cutoff = now - DEDUP_WINDOW_SECONDS
            self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}
        if msg_id in self._seen_messages:
            return True
        self._seen_messages[msg_id] = now
        return False

    @staticmethod
    def _next_msg_seq() -> int:
        """Generate a message sequence number in 0..65535 range."""
        time_part = int(time.time()) % 100000000
        rand = int(uuid.uuid4().hex[:4], 16)
        return (time_part ^ rand) % 65536
