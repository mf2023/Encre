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
import json
import logging
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

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.signal")

_SIGNAL_JSON_RPC_VERSION = "2.0"
_SIGNAL_RATE_LIMIT_DELAY = 0.5
_SIGNAL_MAX_MESSAGE_LENGTH = 2000
_SIGNAL_ATTACHMENT_MAX_SIZE = 100 * 1024 * 1024
_SIGNAL_SSE_RECONNECT_DELAY = 5.0


class SignalAdapter(BaseAdapter):
    """Signal bot adapter using signal-cli JSON-RPC over HTTP.

    Connects to a ``signal-cli`` daemon running in JSON-RPC mode and
    relays messages to the Encre gateway for AI processing. The adapter
    receives incoming messages via Server-Sent Events (SSE) and sends
    outgoing messages via the JSON-RPC API.

    Requires:
        pip install httpx

    And a running ``signal-cli`` daemon::

        signal-cli --account +1234567890 daemon --http

    Args:
        account: The Signal account (phone number) to use.
        http_url: The URL of the signal-cli HTTP daemon.
        gateway_url: Encre gateway WebSocket URL.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.signal import SignalAdapter  # noqa: E402

        async def main():
            adapter = SignalAdapter(
                account="+1234567890",
                http_url="http://127.0.0.1:8080",
            )
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "signal"

    def __init__(
        self,
        account: str = "",
        http_url: str = "http://127.0.0.1:8080",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        self._account = account
        self._http_url = http_url.rstrip("/")
        self._rpc_url = f"{self._http_url}/api/v1/rpc"
        self._events_url = f"{self._http_url}/api/v1/events"
        self._http_client: httpx.AsyncClient | None = None
        self._sse_task: asyncio.Task | None = None
        self._request_id = 0
        self._rate_limit_lock = asyncio.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to the signal-cli HTTP daemon and start the SSE listener."""
        if not HTTPX_AVAILABLE:
            logger.warning(
                "[signal] httpx not installed. Run: pip install httpx"
            )
            return False

        logger.info("[signal] Creating HTTP client")
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Encre/1.0.0"},
        )

        logger.info("[signal] Starting SSE listener")
        self._sse_task = asyncio.create_task(self._sse_listener())

        self._mark_connected()
        logger.info(
            "[signal] Connected to %s (account=%s)",
            self._http_url,
            self._account or "(not set)",
        )
        return True

    async def disconnect(self) -> None:
        """Disconnect from signal-cli and stop the SSE listener."""
        self._running = False

        if self._sse_task is not None:
            self._sse_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sse_task
            self._sse_task = None

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        await self._client.disconnect()
        logger.info("[signal] Disconnected")

    # ── Outbound messaging ────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        _reply_to: str | None = None,
        _metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message via signal-cli JSON-RPC."""
        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized")

        truncated = content[:_SIGNAL_MAX_MESSAGE_LENGTH]

        params: dict[str, Any] = {
            "recipient": [chat_id],
            "messageBody": truncated,
        }
        if self._account:
            params["account"] = self._account

        payload = {
            "jsonrpc": _SIGNAL_JSON_RPC_VERSION,
            "method": "send",
            "params": params,
            "id": self._next_request_id(),
        }

        async with self._rate_limit_lock:
            try:
                resp = await self._http_client.post(
                    self._rpc_url,
                    json=payload,
                    timeout=30.0,
                )
                if resp.status_code < 300:
                    body = resp.json()
                    result = body.get("result", {})
                    timestamp = result.get("timestamp")
                    return SendResult(
                        success=True,
                        message_id=str(timestamp) if timestamp else uuid.uuid4().hex[:12],
                        raw=body,
                    )
                body_text = resp.text
                logger.warning(
                    "[signal] send failed HTTP %d: %s",
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
                logger.error("[signal] send error: %s", e)
                return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator via signal-cli JSON-RPC."""
        if not self._http_client:
            return

        params: dict[str, Any] = {
            "recipient": [chat_id],
            "stop": False,
        }
        if self._account:
            params["account"] = self._account

        payload = {
            "jsonrpc": _SIGNAL_JSON_RPC_VERSION,
            "method": "sendTyping",
            "params": params,
            "id": self._next_request_id(),
        }

        try:
            await self._http_client.post(self._rpc_url, json=payload, timeout=10.0)
        except Exception as e:
            logger.warning("[signal] send_typing error: %s", e)

    # ── SSE listener ──────────────────────────────────────────────────────

    async def _sse_listener(self) -> None:
        """Listen for incoming messages via the signal-cli SSE event stream."""
        while self._running:
            if not self._http_client:
                logger.error("[signal] SSE listener: HTTP client unavailable")
                break

            try:
                async with self._http_client.stream(
                    "GET",
                    self._events_url,
                    headers={"Accept": "text/event-stream"},
                    timeout=None,
                ) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "[signal] SSE endpoint returned HTTP %d",
                            response.status_code,
                        )
                        await asyncio.sleep(_SIGNAL_SSE_RECONNECT_DELAY)
                        continue

                    logger.info("[signal] SSE listener started")
                    buffer = ""
                    async for line in response.aiter_lines():
                        if not self._running:
                            break
                        buffer = self._process_sse_line(line, buffer)
                    logger.info("[signal] SSE stream ended")
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "[signal] SSE error: %s (reconnecting in %.0fs)",
                    e,
                    _SIGNAL_SSE_RECONNECT_DELAY,
                )

            if self._running:
                await asyncio.sleep(_SIGNAL_SSE_RECONNECT_DELAY)

    def _process_sse_line(self, line: str, buffer: str) -> str:
        """Process a single SSE line. Returns the accumulated buffer."""
        if line.startswith("data: "):
            raw = line[6:]
            if buffer:
                raw = buffer + raw
            try:
                data = json.loads(raw)
                self._handle_envelope(data)
                return ""
            except json.JSONDecodeError:
                return raw
        elif line.startswith("event: "):
            self._last_sse_event = line[7:]
            return buffer
        elif line.strip() == "":
            return buffer
        return buffer

    def _handle_envelope(self, data: dict[str, Any]) -> None:
        """Process a single SSE envelope from signal-cli."""
        try:
            envelope = data.get("envelope") or data
            if not isinstance(envelope, dict):
                return

            source = envelope.get("source", "") or ""
            data_message = envelope.get("dataMessage") or {}

            if not data_message or not data_message.get("message"):
                return

            text = data_message["message"]
            timestamp = data_message.get("timestamp", 0)
            raw_message_id = str(timestamp) if timestamp else uuid.uuid4().hex[:12]

            chat_id = source
            user_id = source

            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                message_id=raw_message_id,
                chat_id=chat_id,
                user_id=user_id,
                raw=envelope,
                timestamp=(
                    datetime.fromtimestamp(timestamp / 1000)
                    if timestamp
                    else datetime.now()
                ),
            )

            logger.debug(
                "[signal] Message from %s: %s",
                source,
                text[:80],
            )

            self.dispatch_message(event)
        except Exception as e:
            logger.error("[signal] Error handling envelope: %s", e)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _next_request_id(self) -> str:
        """Generate a unique JSON-RPC request ID."""
        self._request_id += 1
        return f"encre-{self._request_id}-{uuid.uuid4().hex[:6]}"
