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
# sms.py
#
# Adapter integration module for the Encre agent framework.
# Provides classes and helpers that connect an external
# platform/channel to the Encre message adapter pipeline,
# enabling inbound event handling and outbound message delivery.
#
# Exported classes:
#   - SmsAdapter
#
# Module-level helpers:
#   - _strip_markdown
#   - _redact_phone
#
import asyncio
import base64
import hashlib
import hmac
import logging
import re
import urllib.parse
from typing import Any

try:
    import aiohttp
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None
    web = None

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult, SessionSource

logger = logging.getLogger("encre.adapters.sms")

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
MAX_SMS_LENGTH = 1600
DEFAULT_WEBHOOK_PORT = 8080
DEFAULT_WEBHOOK_HOST = "127.0.0.1"


def _strip_markdown(text: str) -> str:
    """Strip common markdown formatting for plain SMS rendering."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _redact_phone(phone: str) -> str:
    """Partially mask a phone number for logging."""
    if len(phone) >= 4:
        return phone[:2] + "***" + phone[-2:]
    return "***"


class SmsAdapter(BaseAdapter):
    """Twilio SMS adapter.

    Connects to the Twilio REST API for outbound SMS and runs an aiohttp
    webhook server to receive inbound messages. Incoming SMS is dispatched
    as :class:`MessageEvent` instances and responses are streamed back
    via the Twilio REST API.

    Requires the ``aiohttp`` package::

        pip install aiohttp

    Args:
        account_sid: Twilio Account SID.
        auth_token: Twilio Auth Token.
        from_number: The Twilio phone number (E.164) to send from.
        gateway_url: Encre gateway WebSocket URL.
        port: Port for the webhook server.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.sms import SmsAdapter  # noqa: E402

        async def main():
            adapter = SmsAdapter(
                account_sid="ACxxxxx",
                auth_token="your_auth_token",
                from_number="+15551234567",
            )
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "sms"

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        *,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
        port: int = 8080,
    ) -> None:
        """
        Initialize the instance..

        Args:
            account_sid (str):
            auth_token (str):
            from_number (str):
            gateway_url (str):
            port (int):

        Returns:
            None
        """
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._webhook_port = port
        self._webhook_host = DEFAULT_WEBHOOK_HOST
        self._webhook_url: str = ""
        self._insecure_no_signature = False
        self._runner: Any = None
        self._http_session: Any = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Start the webhook server and initialize the HTTP client."""
        if not AIOHTTP_AVAILABLE:
            logger.error(
                "[sms] aiohttp is required. Install with: pip install aiohttp"
            )
            return False

        if not self._account_sid or not self._auth_token:
            logger.error("[sms] account_sid and auth_token are required")
            return False

        if not self._from_number:
            logger.error("[sms] from_number is required")
            return False

        logger.info("[sms] Starting webhook server on %s:%d...", self._webhook_host, self._webhook_port)
        app = web.Application()
        app.router.add_post("/webhooks/twilio", self._handle_webhook)
        app.router.add_get("/health", lambda _: web.Response(text="ok"))

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._webhook_host, self._webhook_port)
        await site.start()

        logger.info("[sms] Creating HTTP client session...")
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            trust_env=True,
        )

        logger.info("[sms] Connecting to gateway...")
        result = await super().connect()
        if result:
            logger.info(
                "[sms] Webhook server listening on %s:%d, from: %s",
                self._webhook_host,
                self._webhook_port,
                _redact_phone(self._from_number),
            )
        return result

    async def disconnect(self) -> None:
        """Stop the webhook server and close the HTTP client."""
        if self._http_session is not None:
            try:
                await self._http_session.close()
            except Exception as e:
                logger.warning("[sms] HTTP session close error: %s", e)
            self._http_session = None

        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception as e:
                logger.warning("[sms] Webhook server cleanup error: %s", e)
            self._runner = None

        await super().disconnect()
        logger.info("[sms] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        _reply_to: str | None = None,
        _metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send an SMS via the Twilio REST API.

        Strips markdown formatting and truncates to the maximum SMS length.
        Long messages are sent as multiple SMS segments.

        Args:
            chat_id: The recipient phone number (E.164).
            content: The message text.
            reply_to: Ignored for SMS; Twilio does not support reply-to via REST.
            metadata: Optional metadata (ignored).

        Returns:
            A :class:`SendResult` indicating success or failure.
        """
        formatted = _strip_markdown(content)
        truncated = formatted[:MAX_SMS_LENGTH]

        if self._http_session is None:
            return SendResult(success=False, error="HTTP client not connected")

        url = f"{TWILIO_API_BASE}/{self._account_sid}/Messages.json"
        headers = {
            "Authorization": self._basic_auth_header(),
            "User-Agent": "Encre/1.0.0",
        }

        form_data = aiohttp.FormData()
        form_data.add_field("From", self._from_number)
        form_data.add_field("To", chat_id)
        form_data.add_field("Body", truncated)

        try:
            async with self._http_session.post(
                url, data=form_data, headers=headers
            ) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    error_msg = body.get("message", str(body))
                    logger.error(
                        "[sms] Send failed to %s: %s %s",
                        _redact_phone(chat_id),
                        resp.status,
                        error_msg,
                    )
                    return SendResult(
                        success=False,
                        error=f"Twilio {resp.status}: {error_msg}",
                        raw=body,
                        retryable=resp.status >= 500,
                    )
                msg_sid = body.get("sid", "")
                logger.info(
                    "[sms] Sent to %s (sid=%s)",
                    _redact_phone(chat_id),
                    msg_sid,
                )
                return SendResult(
                    success=True,
                    message_id=msg_sid,
                    raw=body,
                )
        except Exception as e:
            logger.error("[sms] Send request failed: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ── Webhook ────────────────────────────────────────────────────────────

    async def handle_callback(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> bytes:
        """Handle an incoming Twilio SMS webhook callback.

        Validates the ``X-Twilio-Signature`` header, parses the form-encoded
        body, creates a :class:`MessageEvent`, and dispatches it via
        :meth:`dispatch_message`.

        Args:
            body: The raw request body (form-encoded).
            headers: The request headers.

        Returns:
            An empty TwiML response as bytes.
        """
        twiml = b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

        try:
            form = urllib.parse.parse_qs(
                body.decode("utf-8"), keep_blank_values=True
            )
        except Exception as e:
            logger.error("[sms] Webhook parse error: %s", e)
            return twiml

        if self._webhook_url and not self._insecure_no_signature:
            twilio_sig = headers.get("X-Twilio-Signature", "")
            if not twilio_sig:
                logger.warning("[sms] Rejected: missing X-Twilio-Signature")
                return twiml
            flat_params = {k: v[0] for k, v in form.items() if v}
            if not self._validate_twilio_signature(
                self._webhook_url, flat_params, twilio_sig
            ):
                logger.warning("[sms] Rejected: invalid Twilio signature")
                return twiml

        from_number = (form.get("From", [""]))[0].strip()
        text = (form.get("Body", [""]))[0].strip()
        message_sid = (form.get("MessageSid", [""]))[0].strip()

        if not from_number or not text:
            return twiml

        if from_number == self._from_number:
            logger.debug(
                "[sms] Ignoring echo from own number %s",
                _redact_phone(from_number),
            )
            return twiml

        logger.info(
            "[sms] Inbound from %s: %s",
            _redact_phone(from_number),
            text[:80],
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=message_sid,
            chat_id=from_number,
            user_id=from_number,
            raw=form,
            source=SessionSource(
                platform=self.name,
                chat_id=from_number,
                chat_type="dm",
                user_id=from_number,
            ),
        )

        task = asyncio.create_task(self._dispatch_event(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return twiml

    async def _dispatch_event(self, event: MessageEvent) -> None:
        if event.chat_id:
            try:
                await self.send_typing(event.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response to chat."""
        session_id = self.get_session(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    # ── Twilio webhook handler (aiohttp) ───────────────────────────────────

    async def _handle_webhook(self, request: Any) -> Any:
        """aiohttp handler for incoming Twilio SMS webhooks."""
        try:
            raw = await request.read()
            urllib.parse.parse_qs(
                raw.decode("utf-8"), keep_blank_values=True
            )
        except Exception as e:
            logger.error("[sms] Webhook parse error: %s", e)
            return web.Response(
                text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                content_type="application/xml",
                status=400,
            )

        headers = dict(request.headers)
        twiml = await self.handle_callback(raw, headers)
        return web.Response(
            body=twiml,
            content_type="application/xml",
        )

    # ── Twilio signature validation ───────────────────────────────────────

    def _validate_twilio_signature(
        self,
        url: str,
        post_params: dict[str, str],
        signature: str,
    ) -> bool:
        """Validate ``X-Twilio-Signature`` header (HMAC-SHA1, base64).

        Tries both with and without the default port for the URL scheme,
        since Twilio may sign with either variant.

        See: https://www.twilio.com/docs/usage/security#validating-requests
        """
        if self._check_signature(url, post_params, signature):
            return True

        variant = self._port_variant_url(url)
        return bool(variant is not None and self._check_signature(variant, post_params, signature))

    def _check_signature(
        self,
        url: str,
        post_params: dict[str, str],
        signature: str,
    ) -> bool:
        """Compute and compare a single Twilio signature."""
        data_to_sign = url
        for key in sorted(post_params.keys()):
            data_to_sign += key + post_params[key]
        mac = hmac.new(
            self._auth_token.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        computed = base64.b64encode(mac.digest()).decode("utf-8")
        return hmac.compare_digest(computed, signature)

    @staticmethod
    def _port_variant_url(url: str) -> str | None:
        """Return the URL with the default port toggled, or None.

        Only toggles default ports (443 for https, 80 for http).
        Non-standard ports are never modified.
        """
        parsed = urllib.parse.urlparse(url)
        default_ports = {"https": 443, "http": 80}
        default_port = default_ports.get(parsed.scheme)
        if default_port is None:
            return None

        if parsed.port == default_port:
            return urllib.parse.urlunparse(
                (
                    parsed.scheme,
                    parsed.hostname,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
            )
        elif parsed.port is None:
            netloc = f"{parsed.hostname}:{default_port}"
            return urllib.parse.urlunparse(
                (
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
            )

        return None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _basic_auth_header(self) -> str:
        """Build HTTP Basic auth header value for Twilio."""
        creds = f"{self._account_sid}:{self._auth_token}"
        encoded = base64.b64encode(creds.encode("ascii")).decode("ascii")
        return f"Basic {encoded}"
