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

"""
Inspired by the Hermes Agent project (https://github.com/NousResearch/hermes-agent.git).
Thanks to Hermes Agent for the inspiration on this module.

WeCom callback-mode adapter for self-built enterprise applications.

This module implements the inbound side of the WeCom (Enterprise WeChat)
"self-built application" integration. Unlike the bot/WebSocket adapter in
``wecom.py``, this adapter exposes a small aiohttp HTTP server that receives
WeCom's encrypted XML callbacks, verifies their signature, decrypts the
payload, normalises it into Encre's internal :class:`MessageEvent`, and
queues it for the agent loop. The server acknowledges every callback
immediately with the literal body ``success`` so that WeCom does not retry,
while the agent's reply is delivered later through WeCom's proactive
``message/send`` API using a cached access token.

Key design points:

* Security-first parsing -- untrusted, pre-authentication request bodies are
  parsed with ``defusedxml`` to neutralise XML entity-expansion (billion
  laughs) and XXE attacks. Outbound response XML is built with the standard
  library in :mod:`wecom_crypto` and is never parsed back into this module.
* Multi-app scoping -- several self-built apps may be served by one gateway
  instance. Inbound messages are namespaced by ``corp_id:user_id`` to avoid
  cross-corp collisions, and each app keeps its own access token cache.
* DoS hardening -- request bodies are capped at :data:`_MAX_BODY` by both the
  aiohttp ``client_max_size`` limit and an explicit in-handler guard, so an
  unauthenticated POST cannot force unbounded parsing before the signature
  check runs.
* Deduplication -- WeCom retries callbacks on timeout, so inbound message ids
  are tracked in a bounded, time-windowed cache to suppress duplicates.

This adapter depends on ``aiohttp`` (HTTP server), ``httpx`` (outbound token
and message calls) and ``defusedxml`` (safe parsing). When any of these are
missing, :func:`check_wecom_callback_requirements` returns ``False`` and the
adapter refuses to start.
"""

import asyncio
import logging
import socket as _socket
import threading
import time
from typing import Any, Dict, List, Optional

# Security: parse untrusted, pre-auth request bodies (WeCom callbacks) with
# defusedxml to block billion-laughs / entity-expansion (and XXE) DoS. The
# parsing API (fromstring) is a drop-in for the stdlib calls used below;
# response-building XML lives in wecom_crypto.py and is not parsed here.
try:
    import defusedxml.ElementTree as ET

    DEFUSEDXML_AVAILABLE = True
except ImportError:
    ET = None  # type: ignore[assignment]
    DEFUSEDXML_AVAILABLE = False

try:
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    web = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    HTTPX_AVAILABLE = False

from encre.gateway.config import Platform, PlatformConfig
from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from .wecom_crypto import WXBizMsgCrypt, WeComCryptoError

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8645
DEFAULT_PATH = "/wecom/callback"
# Cap pre-auth request bodies. WeCom callbacks are small encrypted XML
# envelopes (media is delivered out-of-band via MediaId, never inline), so
# 64 KiB is ample for any legitimate message while bounding the work an
# unauthenticated POST can force before signature verification.
_MAX_BODY = 65_536
# WeCom access tokens are documented with a ~7200s lifetime; we use the same
# value as a safe default when the token endpoint omits ``expires_in``.
ACCESS_TOKEN_TTL_SECONDS = 7200
# Duplicate callbacks within this window (WeCom retries on timeout) are
# dropped. Also used as the cache-eviction horizon for seen message ids.
MESSAGE_DEDUP_TTL_SECONDS = 300


def check_wecom_callback_requirements() -> bool:
    """Return whether all optional dependencies for the callback adapter are present.

    The adapter requires ``aiohttp`` for the HTTP server, ``httpx`` for
    outbound token and message calls, and ``defusedxml`` for safe XML
    parsing. If any one is missing the adapter cannot operate.

    Returns:
        bool: ``True`` when aiohttp, httpx and defusedxml are all importable,
        ``False`` otherwise.
    """
    return AIOHTTP_AVAILABLE and HTTPX_AVAILABLE and DEFUSEDXML_AVAILABLE


class WecomCallbackAdapter(BasePlatformAdapter):
    """WeCom self-built-app callback adapter backed by a local HTTP server.

    Responsibilities:

    * Bind an aiohttp HTTP server on a configurable host/port/path that
      receives WeCom encrypted XML callbacks and URL-verification handshakes.
    * Verify each callback signature, decrypt the body, and convert it into a
      :class:`MessageEvent` placed on an internal asyncio queue.
    * Deduplicate retried callbacks and remember which app (corp) each user
      belongs to so outbound replies can be routed correctly.
    * Proactively send agent replies through WeCom's ``message/send`` API,
      managing a per-app access-token cache with lazy refresh.

    Configuration is taken from :class:`PlatformConfig.extra`, which may
    contain either a single-app mapping (``corp_id``/``corp_secret``/...) or a
    list under ``apps``.
    """

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.WECOM_CALLBACK)
        extra = config.extra or {}
        self._host = str(extra.get("host") or DEFAULT_HOST)
        self._port = int(extra.get("port") or DEFAULT_PORT)
        self._path = str(extra.get("path") or DEFAULT_PATH)
        self._apps: List[Dict[str, Any]] = self._normalize_apps(extra)
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._app: Optional[web.Application] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._message_queue: asyncio.Queue[MessageEvent] = asyncio.Queue()
        self._poll_task: Optional[asyncio.Task] = None
        self._seen_messages: Dict[str, float] = {}
        self._seen_lock = threading.Lock()
        self._user_app_map: Dict[str, str] = {}
        self._access_tokens: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # App normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _user_app_key(corp_id: str, user_id: str) -> str:
        """Build the cross-corp scoping key for a user.

        Args:
            corp_id: The WeCom corp id, or an empty string for single-app
                setups that do not scope by corp.
            user_id: The WeCom user id.

        Returns:
            str: ``"{corp_id}:{user_id}"`` when a corp id is present, else the
            bare ``user_id``.
        """
        return f"{corp_id}:{user_id}" if corp_id else user_id

    @staticmethod
    def _normalize_apps(extra: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Coerce the raw ``extra`` config into a list of app dictionaries.

        Two shapes are supported. If ``extra["apps"]`` is a non-empty list of
        dicts, those are returned verbatim. Otherwise, a single-app mapping
        expressed through top-level keys (``corp_id``, ``corp_secret``,
        ``agent_id``, ``token``, ``encoding_aes_key``) is wrapped into one
        dict. Anything else yields an empty list, which makes ``connect`` bail
        out later.

        Args:
            extra: The ``PlatformConfig.extra`` mapping.

        Returns:
            List[Dict[str, Any]]: One entry per configured self-built app.
        """
        apps = extra.get("apps")
        if isinstance(apps, list) and apps:
            return [dict(app) for app in apps if isinstance(app, dict)]
        if extra.get("corp_id"):
            return [
                {
                    "name": extra.get("name") or "default",
                    "corp_id": extra.get("corp_id", ""),
                    "corp_secret": extra.get("corp_secret", ""),
                    "agent_id": str(extra.get("agent_id", "")),
                    "token": extra.get("token", ""),
                    "encoding_aes_key": extra.get("encoding_aes_key", ""),
                }
            ]
        return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Start the HTTP server and begin polling for inbound callbacks.

        Args:
            is_reconnect: Forwarded by :class:`GatewayRunner` on every retry
                per the :class:`BasePlatformAdapter` contract. Callback
                adapters keep no server-side queue to preserve, so the flag is
                accepted and ignored -- but the keyword argument must remain
                present or the reconnect watcher dies with ``TypeError``.

        Returns:
            bool: ``True`` when the server started and is listening, ``False``
            when no apps are configured, a dependency is missing, the port is
            taken, or startup otherwise failed.
        """
        # ``is_reconnect`` is forwarded by GatewayRunner on every retry per
        # the BasePlatformAdapter.connect contract. Callback adapters have
        # no server-side queue to preserve, so the flag is accepted-and-
        # ignored -- but the kwarg MUST be present or the reconnect watcher
        # dies with TypeError and the platform silently stays offline.
        del is_reconnect
        if not self._apps:
            logger.warning("[WecomCallback] No callback apps configured")
            return False
        if not check_wecom_callback_requirements():
            logger.warning("[WecomCallback] aiohttp/httpx not installed")
            return False

        # Quick port-in-use check.
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", self._port))
            logger.error("[WecomCallback] Port %d already in use", self._port)
            return False
        except (ConnectionRefusedError, OSError):
            pass

        try:
            # Tighter keepalive so idle CLOSE_WAIT drains promptly (#18451).
            from encre.gateway.platforms._http_client_limits import platform_httpx_limits
            self._http_client = httpx.AsyncClient(timeout=20.0, limits=platform_httpx_limits())
            # client_max_size rejects oversized bodies at the aiohttp layer
            # (413) before our handler -- and before any signature work -- runs.
            self._app = web.Application(client_max_size=_MAX_BODY)
            self._app.router.add_get("/health", self._handle_health)
            self._app.router.add_get(self._path, self._handle_verify)
            self._app.router.add_post(self._path, self._handle_callback)
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
            self._poll_task = asyncio.create_task(self._poll_loop())
            self._mark_connected()
            logger.info(
                "[WecomCallback] HTTP server listening on %s:%s%s",
                self._host, self._port, self._path,
            )
            for app in self._apps:
                try:
                    await self._refresh_access_token(app)
                except Exception as exc:
                    logger.warning(
                        "[WecomCallback] Initial token refresh failed for app '%s': %s",
                        app.get("name", "default"), exc,
                    )
            return True
        except Exception:
            await self._cleanup()
            logger.exception("[WecomCallback] Failed to start")
            return False

    async def disconnect(self) -> None:
        """Stop the server, cancel the poll loop, and release resources.

        Returns:
            None
        """
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        await self._cleanup()
        self._mark_disconnected()
        logger.info("[WecomCallback] Disconnected")

    async def _cleanup(self) -> None:
        """Tear down the aiohttp runner and httpx client.

        Idempotent: safe to call multiple times. The runner and client are
        torn down independently so a failure in one does not leak the other.

        Returns:
            None
        """
        self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Outbound: proactive send via access-token API
    # ------------------------------------------------------------------

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a text reply to a WeCom user via the proactive ``message/send`` API.

        The reply is addressed to the user extracted from ``chat_id`` (the part
        after an optional ``corp_id:`` prefix). On the first attempt, if WeCom
        rejects the access token (errcode 40001/42001), the cached token is
        evicted and the send is retried once with a freshly fetched token.

        Args:
            chat_id: Scoped chat id, optionally of the form ``corp_id:user_id``.
            content: Plain-text message body; truncated to 2048 chars per the
                WeCom text-message limit.
            reply_to: Optional upstream message id being replied to (unused by
                this adapter but kept for the base signature).
            metadata: Optional extra per-call data (unused here).

        Returns:
            SendResult: Success/failure plus the WeCom ``msgid`` on success.
        """
        app = self._resolve_app_for_chat(chat_id)
        touser = chat_id.split(":", 1)[1] if ":" in chat_id else chat_id
        try:
            payload = {
                "touser": touser,
                "msgtype": "text",
                "agentid": int(str(app.get("agent_id") or 0)),
                "text": {"content": content[:2048]},
                "safe": 0,
            }
            for _attempt in range(2):
                token = await self._get_access_token(app)
                resp = await self._http_client.post(
                    f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                    json=payload,
                )
                data = resp.json()
                errcode = data.get("errcode")
                if errcode in {40001, 42001} and _attempt == 0:
                    # WeCom rejected the token -- evict the cached entry so
                    # the next _get_access_token call forces a fresh fetch.
                    logger.warning(
                        "[WecomCallback] Token rejected for app '%s' (errcode=%s), refreshing",
                        app.get("name", "default"), errcode,
                    )
                    self._access_tokens.pop(app["name"], None)
                    continue
                if errcode != 0:
                    return SendResult(success=False, error=str(data))
                return SendResult(
                    success=True,
                    message_id=str(data.get("msgid", "")),
                    raw_response=data,
                )
            return SendResult(success=False, error="send failed after token refresh")
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    def _resolve_app_for_chat(self, chat_id: str) -> Dict[str, Any]:
        """Pick the app associated with *chat_id*, falling back sensibly.

        Looks up the app name recorded for this scoped chat id; for a legacy
        bare ``user_id`` with no corp prefix it tries to find a unique matching
        user. Falls back to the first configured app when nothing matches.

        Args:
            chat_id: Scoped chat id (``corp_id:user_id``) or bare ``user_id``.

        Returns:
            Dict[str, Any]: The matched app dict, or ``self._apps[0]`` as a
            last resort.
        """
        app_name = self._user_app_map.get(chat_id)
        if not app_name and ":" not in chat_id:
            # Legacy bare user_id -- try to find a unique match.
            matching = [k for k in self._user_app_map if k.endswith(f":{chat_id}")]
            if len(matching) == 1:
                app_name = self._user_app_map.get(matching[0])
        app = self._get_app_by_name(app_name) if app_name else None
        return app or self._apps[0]

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return minimal chat metadata for a WeCom direct message.

        WeCom callback-mode conversations are always one-to-one, so this
        returns a fixed shape describing a direct message.

        Args:
            chat_id: The scoped chat id.

        Returns:
            Dict[str, Any]: ``{"name": chat_id, "type": "dm"}``.
        """
        return {"name": chat_id, "type": "dm"}

    # ------------------------------------------------------------------
    # Inbound: HTTP callback handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET ``/health`` endpoint used by liveness checks.

        Args:
            request: The incoming aiohttp request (unused).

        Returns:
            web.Response: A JSON ``{"status": "ok", "platform": ...}`` body.
        """
        return web.json_response({"status": "ok", "platform": "wecom_callback"})

    async def _handle_verify(self, request: web.Request) -> web.Response:
        """GET endpoint -- WeCom URL verification handshake.

        WeCom sends ``msg_signature``, ``timestamp``, ``nonce`` and an
        ``echostr`` query parameters. We try each configured app's crypto
        until one verifies and decrypts ``echostr``; the decrypted plaintext is
        returned verbatim to prove ownership of the callback URL.

        Args:
            request: The aiohttp request carrying the handshake query params.

        Returns:
            web.Response: The decrypted ``echostr`` on success, or 403 when no
            app can verify the signature.
        """
        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        echostr = request.query.get("echostr", "")
        for app in self._apps:
            try:
                crypt = self._crypt_for_app(app)
                plain = crypt.verify_url(msg_signature, timestamp, nonce, echostr)
                return web.Response(text=plain, content_type="text/plain")
            except Exception:
                continue
        return web.Response(status=403, text="signature verification failed")

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """POST endpoint -- receive an encrypted message callback.

        Reads the body (after an explicit size guard), then for each configured
        app attempts to verify and decrypt it, build a :class:`MessageEvent`,
        deduplicate it, remember which app the user belongs to, and enqueue it.
        The callback is acknowledged with ``success`` immediately so WeCom does
        not retry, regardless of downstream processing.

        Args:
            request: The aiohttp request with the encrypted XML body.

        Returns:
            web.Response: ``success`` (200) when handled/acked, 413 when the
            payload is too large, or 400 when no app can decrypt the payload.
        """
        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        # Explicit guard in addition to client_max_size: rejects oversized
        # payloads before any XML parse / signature check (DoS, zip bombs).
        body_bytes = await request.read()
        if len(body_bytes) > _MAX_BODY:
            logger.warning("[WecomCallback] Payload too large (%d bytes) -- rejected", len(body_bytes))
            return web.Response(status=413, text="payload too large")
        body = body_bytes.decode("utf-8", errors="replace")

        for app in self._apps:
            try:
                decrypted = self._decrypt_request(
                    app, body, msg_signature, timestamp, nonce,
                )
                event = self._build_event(app, decrypted)
                if event is not None:
                    # Deduplicate: WeCom retries callbacks on timeout,
                    # producing duplicate inbound messages (#10305).
                    if event.message_id:
                        now = time.time()
                        with self._seen_lock:
                            if event.message_id in self._seen_messages:
                                if now - self._seen_messages[event.message_id] < MESSAGE_DEDUP_TTL_SECONDS:
                                    logger.debug("[WecomCallback] Duplicate MsgId %s, skipping", event.message_id)
                                    return web.Response(text="success", content_type="text/plain")
                                del self._seen_messages[event.message_id]
                            self._seen_messages[event.message_id] = now
                            if len(self._seen_messages) > 2000:
                                cutoff = now - MESSAGE_DEDUP_TTL_SECONDS
                                self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}
                    # Record which app this user belongs to.
                    if event.source and event.source.user_id:
                        map_key = self._user_app_key(
                            str(app.get("corp_id") or ""), event.source.user_id,
                        )
                        self._user_app_map[map_key] = app["name"]
                    await self._message_queue.put(event)
                # Immediately acknowledge -- the agent's reply will arrive
                # later via the proactive message/send API.
                return web.Response(text="success", content_type="text/plain")
            except WeComCryptoError:
                continue
            except Exception:
                logger.exception("[WecomCallback] Error handling message")
                break
        return web.Response(status=400, text="invalid callback payload")

    async def _poll_loop(self) -> None:
        """Drain the message queue and dispatch each event to the gateway.

        Runs forever (until cancelled). Each dequeued :class:`MessageEvent` is
        handed to ``handle_message`` in a background task tracked by
        ``_background_tasks`` so a slow handler cannot block the queue.

        Returns:
            None
        """
        while True:
            event = await self._message_queue.get()
            try:
                task = asyncio.create_task(self.handle_message(event))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            except Exception:
                logger.exception("[WecomCallback] Failed to enqueue event")

    # ------------------------------------------------------------------
    # XML / crypto helpers
    # ------------------------------------------------------------------

    def _decrypt_request(
        self, app: Dict[str, Any], body: str,
        msg_signature: str, timestamp: str, nonce: str,
    ) -> str:
        """Parse the encrypted XML envelope and decrypt the ``Encrypt`` blob.

        Args:
            app: The app dict whose crypto credentials to use.
            body: The raw callback XML body as text.
            msg_signature: WeCom-supplied signature query parameter.
            timestamp: WeCom-supplied timestamp query parameter.
            nonce: WeCom-supplied nonce query parameter.

        Returns:
            str: The decrypted plaintext XML.

        Raises:
            WeComCryptoError: When signature verification or decryption fails.
        """
        root = ET.fromstring(body)
        encrypt = root.findtext("Encrypt", default="")
        crypt = self._crypt_for_app(app)
        return crypt.decrypt(msg_signature, timestamp, nonce, encrypt).decode("utf-8")

    def _build_event(self, app: Dict[str, Any], xml_text: str) -> Optional[MessageEvent]:
        """Convert decrypted WeCom XML into an Encre :class:`MessageEvent`.

        Lifecycle ``event`` messages such as ``enter_agent``/``subscribe`` are
        acknowledged silently by returning ``None``. Only ``text`` and ``event``
        message types are materialised; other types are ignored. A missing
        message id is synthesised from the user id and create time so later
        deduplication still has a key.

        Args:
            app: The app dict that received the message (provides a fallback
                corp id).
            xml_text: The decrypted XML plaintext.

        Returns:
            Optional[MessageEvent]: The constructed event, or ``None`` when the
            message should be silently acknowledged/ignored.
        """
        root = ET.fromstring(xml_text)
        msg_type = (root.findtext("MsgType") or "").lower()
        # Silently acknowledge lifecycle events.
        if msg_type == "event":
            event_name = (root.findtext("Event") or "").lower()
            if event_name in {"enter_agent", "subscribe"}:
                return None
        if msg_type not in {"text", "event"}:
            return None

        user_id = root.findtext("FromUserName", default="")
        corp_id = root.findtext("ToUserName", default=app.get("corp_id", ""))
        scoped_chat_id = self._user_app_key(corp_id, user_id)
        content = root.findtext("Content", default="").strip()
        if not content and msg_type == "event":
            content = "/start"
        msg_id = (
            root.findtext("MsgId")
            or f"{user_id}:{root.findtext('CreateTime', default='0')}"
        )
        source = self.build_source(
            chat_id=scoped_chat_id,
            chat_name=user_id,
            chat_type="dm",
            user_id=user_id,
            user_name=user_id,
        )
        return MessageEvent(
            text=content,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=xml_text,
            message_id=msg_id,
        )

    def _crypt_for_app(self, app: Dict[str, Any]) -> WXBizMsgCrypt:
        """Construct a :class:`WXBizMsgCrypt` for the given app.

        Args:
            app: The app dict holding ``token``, ``encoding_aes_key`` and
                ``corp_id``.

        Returns:
            WXBizMsgCrypt: A crypto helper bound to the app's credentials.
        """
        return WXBizMsgCrypt(
            token=str(app.get("token") or ""),
            encoding_aes_key=str(app.get("encoding_aes_key") or ""),
            receive_id=str(app.get("corp_id") or ""),
        )

    def _get_app_by_name(self, name: Optional[str]) -> Optional[Dict[str, Any]]:
        """Look up a configured app by its ``name``.

        Args:
            name: The app name to find, or ``None``.

        Returns:
            Optional[Dict[str, Any]]: The matching app dict, or ``None``.
        """
        if not name:
            return None
        for app in self._apps:
            if app.get("name") == name:
                return app
        return None

    # ------------------------------------------------------------------
    # Access-token management
    # ------------------------------------------------------------------

    async def _get_access_token(self, app: Dict[str, Any]) -> str:
        """Return a valid access token for ``app``, refreshing if stale.

        Uses the in-memory cache; if the cached token is missing or expires
        within the next 60 seconds it is refreshed immediately.

        Args:
            app: The app dict whose token is requested.

        Returns:
            str: A usable access token.
        """
        cached = self._access_tokens.get(app["name"])
        now = time.time()
        if cached and cached.get("expires_at", 0) > now + 60:
            return cached["token"]
        return await self._refresh_access_token(app)

    async def _refresh_access_token(self, app: Dict[str, Any]) -> str:
        """Fetch a fresh access token from WeCom's ``gettoken`` endpoint.

        Args:
            app: The app dict providing ``corp_id``/``corp_secret``.

        Returns:
            str: The newly issued access token.

        Raises:
            RuntimeError: When WeCom returns a non-zero ``errcode``.
        """
        resp = await self._http_client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={
                "corpid": app.get("corp_id"),
                "corpsecret": app.get("corp_secret"),
            },
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"WeCom token refresh failed: {data}")
        token = data["access_token"]
        expires_in = int(data.get("expires_in", ACCESS_TOKEN_TTL_SECONDS))
        self._access_tokens[app["name"]] = {
            "token": token,
            "expires_at": time.time() + expires_in,
        }
        logger.info(
            "[WecomCallback] Token refreshed for app '%s' (corp=%s), expires in %ss",
            app.get("name", "default"),
            app.get("corp_id", ""),
            expires_in,
        )
        return token
