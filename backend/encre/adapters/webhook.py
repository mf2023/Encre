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
import hashlib
import hmac
import json
import logging
import socket as _socket
import time
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.webhook")

try:
    import aiohttp
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    web = None
    aiohttp = None
    AIOHTTP_AVAILABLE = False


class WebhookAdapter(BaseAdapter):
    """Generic HTTP webhook receiver adapter.

    Runs an aiohttp HTTP server that receives webhook POSTs from external
    services, validates HMAC-SHA256 signatures, creates :class:`MessageEvent`
    instances, and dispatches them to the registered message handler.

    The ``send()`` method POSTs the response content back to the webhook's
    reply URL (extracted from the ``X-Reply-URL`` header of the incoming
    request) or to any arbitrary URL passed as ``chat_id``.

    To use:
        1. Install ``aiohttp``
        2. Configure the adapter with a shared ``secret``
        3. Point your external service to ``http://{host}:{port}/webhook``
           and sign the payload with HMAC-SHA256

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.webhook import WebhookAdapter  # noqa: E402

        async def main():
            adapter = WebhookAdapter(secret="your-hmac-secret")
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "webhook"

    def __init__(
        self,
        *,
        secret: str = "",
        host: str = "127.0.0.1",
        port: int = 8644,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp is required. "
                "Install with: pip install aiohttp"
            )
        self._secret = secret
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None
        self._session: aiohttp.ClientSession | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Start the aiohttp webhook server and register routes."""
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/webhook", self._handle_post)

        # Port conflict detection -- fail fast if port is already in use
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", self._port))
            logger.error(
                "[webhook] Port %d already in use. Set a different port.",
                self._port,
            )
            return False
        except (ConnectionRefusedError, OSError):
            pass

        logger.info("[webhook] Creating HTTP session")
        self._session = aiohttp.ClientSession(trust_env=True)
        logger.info("[webhook] Starting aiohttp server on %s:%d", self._host, self._port)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        self._mark_connected()
        logger.info(
            "[webhook] Listening on %s:%d",
            self._host,
            self._port,
        )
        return True

    async def disconnect(self) -> None:
        """Stop the webhook server and clean up resources."""
        await super().disconnect()
        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception as e:
                logger.warning("[webhook] Runner cleanup error: %s", e)
            self._runner = None
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning("[webhook] Session close error: %s", e)
            self._session = None
        logger.info("[webhook] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a response by POSTing to the webhook's reply URL.

        ``chat_id`` is the target URL. The payload is sent as JSON::

            {"content": "...", "reply_to": "...", "metadata": {...}}
        """
        if not chat_id:
            logger.info("[webhook] No reply URL, logging response: %s", content[:200])
            return SendResult(success=True)

        session = self._session
        if session is None:
            return SendResult(success=False, error="Not connected")

        try:
            payload: dict[str, Any] = {"content": content}
            if reply_to:
                payload["reply_to"] = reply_to
            if metadata:
                payload["metadata"] = metadata

            async with session.post(
                chat_id,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                if resp.status < 400:
                    return SendResult(
                        success=True,
                        message_id=str(resp.headers.get("X-Message-ID", "")),
                        raw=body,
                    )
                return SendResult(
                    success=False,
                    error=f"HTTP {resp.status}: {body[:500]}",
                    retryable=resp.status >= 500,
                )
        except TimeoutError:
            return SendResult(
                success=False,
                error="Request timed out",
                retryable=True,
            )
        except Exception as e:
            logger.error("[webhook] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ── HTTP Handlers ──────────────────────────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /health -- simple health check."""
        return web.json_response({"status": "ok", "adapter": "webhook"})

    async def _handle_post(self, request: web.Request) -> web.Response:
        """POST /webhook -- receive and process an incoming webhook event.

        Validates the HMAC-SHA256 signature from the ``X-Webhook-Signature``
        header, parses the JSON body, creates a :class:`MessageEvent`, and
        dispatches it to the registered message handler.
        """
        # Read body
        try:
            raw_body = await request.read()
        except Exception as e:
            logger.error("[webhook] Failed to read body: %s", e)
            return web.json_response({"error": "Bad request"}, status=400)

        # Validate HMAC-SHA256 signature
        if self._secret:
            signature = request.headers.get("X-Webhook-Signature", "")
            if not signature:
                logger.warning("[webhook] Missing X-Webhook-Signature header")
                return web.json_response(
                    {"error": "Missing signature"}, status=401
                )
            expected = hmac.new(
                self._secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                logger.warning("[webhook] Invalid HMAC signature")
                return web.json_response(
                    {"error": "Invalid signature"}, status=401
                )

        # Parse JSON body
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON body"}, status=400
            )

        if not isinstance(payload, dict):
            return web.json_response(
                {"error": "Body must be a JSON object"}, status=400
            )

        # Extract reply URL from header or payload
        reply_url = (
            request.headers.get("X-Reply-URL", "")
            or payload.get("reply_url", "")
            or ""
        )

        # Build message text from the payload
        text = payload.get("text", "") or payload.get("message", "") or json.dumps(payload, indent=2)  # noqa: E501

        # Use reply_url as chat_id so send() knows where to POST responses
        chat_id = reply_url
        user_id = payload.get("user_id", "") or payload.get("sender", "") or ""
        message_id = (
            request.headers.get("X-Request-ID", "")
            or payload.get("message_id", "")
            or str(int(time.time() * 1000))
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            raw=payload,
        )

        self.dispatch_message(event)

        task = asyncio.create_task(self._process_chat(chat_id, text))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return web.json_response(
            {"status": "accepted", "message_id": message_id},
            status=202,
        )

    # ── Processing ─────────────────────────────────────────────────────────

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and send the response.

        Uses the base class :meth:`process_with_stream` which handles
        :class:`TextDelta` streaming and final :class:`Finish` delivery.
        """
        session_id = self.get_session(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)
