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
# wecom.py
#
# WeCom (企业微信) platform adapter for the Encre gateway.
# Provides callback-mode integration with WeCom enterprise applications.
#
# Exported classes:
#   - WeComCryptoError
#   - PKCS7Encoder
#   - WXBizMsgCrypt
#   - WeComAdapter
#
# Module-level helpers:
#   - _sha1_signature
#

import asyncio
import base64
import hashlib
import logging
import os
import secrets
import socket as _socket
import struct
import time
from typing import Any
from xml.etree import ElementTree as ET

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    web = None
    AIOHTTP_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPX_AVAILABLE = False

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.wecom")

DEFAULT_PORT = 18795
ACCESS_TOKEN_TTL_SECONDS = 7200
MESSAGE_DEDUP_TTL_SECONDS = 300

# ---------------------------------------------------------------------------
# WeCom callback crypto (WXBizMsgCrypt-compatible)
# ---------------------------------------------------------------------------


class WeComCryptoError(Exception):
    """WeCom callback crypto error."""
    pass


class PKCS7Encoder:
    """PKCS7 padding encoder/decoder for WeCom AES-CBC crypto."""
    block_size = 32

    @classmethod
    def encode(cls, text: bytes) -> bytes:
        amount_to_pad = cls.block_size - (len(text) % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        pad = bytes([amount_to_pad]) * amount_to_pad
        return text + pad

    @classmethod
    def decode(cls, decrypted: bytes) -> bytes:
        if not decrypted:
            raise WeComCryptoError("empty decrypted payload")
        pad = decrypted[-1]
        if pad < 1 or pad > cls.block_size:
            raise WeComCryptoError("invalid PKCS7 padding")
        if decrypted[-pad:] != bytes([pad]) * pad:
            raise WeComCryptoError("malformed PKCS7 padding")
        return decrypted[:-pad]


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    parts = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


class WXBizMsgCrypt:
    """Minimal WeCom callback crypto helper compatible with BizMsgCrypt semantics."""

    def __init__(self, token: str, encoding_aes_key: str, receive_id: str) -> None:
        if not token:
            raise ValueError("token is required")
        if not encoding_aes_key:
            raise ValueError("encoding_aes_key is required")
        if len(encoding_aes_key) != 43:
            raise ValueError("encoding_aes_key must be 43 chars")
        if not receive_id:
            raise ValueError("receive_id is required")

        self.token = token
        self.receive_id = receive_id
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        plain = self.decrypt(msg_signature, timestamp, nonce, echostr)
        return plain.decode("utf-8")

    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes:
        expected = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if expected != msg_signature:
            raise WeComCryptoError("signature mismatch")
        try:
            cipher_text = base64.b64decode(encrypt)
        except Exception as exc:
            raise WeComCryptoError(f"invalid base64 payload: {exc}") from exc
        try:
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded = decryptor.update(cipher_text) + decryptor.finalize()
            plain = PKCS7Encoder.decode(padded)
            content = plain[16:]
            xml_length = _socket.ntohl(struct.unpack("I", content[:4])[0])
            xml_content = content[4:4 + xml_length]
            receive_id = content[4 + xml_length:].decode("utf-8")
        except WeComCryptoError:
            raise
        except Exception as exc:
            raise WeComCryptoError(f"decrypt failed: {exc}") from exc

        if receive_id != self.receive_id:
            raise WeComCryptoError("receive_id mismatch")
        return xml_content

    def encrypt(self, plaintext: str, nonce: str | None = None, timestamp: str | None = None) -> str:
        nonce = nonce or self._random_nonce()
        timestamp = timestamp or str(int(time.time()))
        encrypt = self._encrypt_bytes(plaintext.encode("utf-8"))
        signature = _sha1_signature(self.token, timestamp, nonce, encrypt)
        root = ET.Element("xml")
        ET.SubElement(root, "Encrypt").text = encrypt
        ET.SubElement(root, "MsgSignature").text = signature
        ET.SubElement(root, "TimeStamp").text = timestamp
        ET.SubElement(root, "Nonce").text = nonce
        return ET.tostring(root, encoding="unicode")

    def _encrypt_bytes(self, raw: bytes) -> str:
        try:
            random_prefix = os.urandom(16)
            msg_len = struct.pack("I", _socket.htonl(len(raw)))
            payload = random_prefix + msg_len + raw + self.receive_id.encode("utf-8")
            padded = PKCS7Encoder.encode(payload)
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(padded) + encryptor.finalize()
            return base64.b64encode(encrypted).decode("utf-8")
        except Exception as exc:
            raise WeComCryptoError(f"encrypt failed: {exc}") from exc

    @staticmethod
    def _random_nonce(length: int = 10) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# WeCom Adapter
# ---------------------------------------------------------------------------


class WeComAdapter(BasePlatformAdapter):
    """WeCom (企业微信) callback-mode adapter for self-built enterprise applications.

    Uses the standard WeCom callback flow: WeCom POSTs encrypted XML to an HTTP
    endpoint, the adapter decrypts it, dispatches the message for agent processing,
    and immediately acknowledges. The agent's reply is delivered later via the
    proactive ``message/send`` API using an access token.

    Supports text, markdown, and image message types.
    """

    def __init__(self, config: PlatformConfig, platform: Platform = Platform.WECOM) -> None:
        super().__init__(config=config, platform=platform)
        self._corp_id = config.extra.get("corp_id", "")
        self._agent_id = int(config.extra.get("agent_id", 0))
        self._secret = config.token
        self._token = config.extra.get("callback_token", "")
        self._encoding_aes_key = config.extra.get("encoding_aes_key", "")
        self._port = int(config.extra.get("port", DEFAULT_PORT))

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._app: web.Application | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0
        self._seen_messages: dict[str, float] = {}

        self._crypt: WXBizMsgCrypt | None = None
        if self._token and self._encoding_aes_key and self._corp_id:
            self._crypt = WXBizMsgCrypt(self._token, self._encoding_aes_key, self._corp_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.error("[%s] aiohttp not installed. Run: pip install aiohttp", self.name)
            return False
        if not HTTPX_AVAILABLE:
            logger.error("[%s] httpx not installed. Run: pip install httpx", self.name)
            return False
        if not CRYPTO_AVAILABLE:
            logger.error(
                "[%s] cryptography not installed. Run: pip install cryptography",
                self.name,
            )
            return False

        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", self._port))
            logger.error("[%s] Port %d already in use", self.name, self._port)
            return False
        except (ConnectionRefusedError, OSError):
            pass

        try:
            logger.info("[%s] Step 1/3: Starting HTTP server on port %d...", self.name, self._port)
            proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None
            client_kwargs: dict[str, Any] = {"timeout": 20.0, "follow_redirects": True}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
            self._http_client = httpx.AsyncClient(**client_kwargs)
            self._app = web.Application()
            self._app.router.add_get("/", self._handle_verify)
            self._app.router.add_post("/", self._handle_callback)
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
            await self._site.start()
            logger.info("[%s] Step 1/3: HTTP server started", self.name)

            logger.info("[%s] Step 2/3: Refreshing access token...", self.name)
            await self._refresh_token()
            logger.info("[%s] Step 2/3: Token refreshed", self.name)

            self._mark_connected()
            logger.info("[%s] Step 3/3: Webhook server listening on 0.0.0.0:%d", self.name, self._port)
            return True
        except Exception:
            await self._cleanup()
            logger.exception("[%s] Failed to start webhook server", self.name)
            return False

    async def disconnect(self) -> None:
        self._running = False
        await self._cleanup()
        await self._cancel_background_tasks()
        self._mark_disconnected()
        logger.info("[%s] Disconnected", self.name)

    async def _cleanup(self) -> None:
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Outbound: send via WeCom Open API
    # ------------------------------------------------------------------

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        msg_type = "text"
        if metadata and metadata.get("msgtype") == "markdown":
            msg_type = "markdown"

        payload: dict[str, Any] = {
            "touser": chat_id,
            "msgtype": msg_type,
            "agentid": self._agent_id,
            msg_type: {"content": content[:2048]},
            "safe": 0,
        }

        if reply_to:
            payload["enable_id_trans"] = 0

        return await self._do_send(payload)

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        _caption: str | None = None,
    ) -> SendResult:
        if not self._http_client:
            return SendResult(success=False, error="adapter not connected")

        token = await self._get_valid_token()
        if not token:
            return SendResult(success=False, error="no access token")

        try:
            media_id = await self._upload_media(file_path, "image", token)
            if not media_id:
                return SendResult(success=False, error="media upload failed")

            payload: dict[str, Any] = {
                "touser": chat_id,
                "msgtype": "image",
                "agentid": self._agent_id,
                "image": {"media_id": media_id},
                "safe": 0,
            }
            result = await self._do_send(payload)
            return result
        except Exception as exc:
            logger.error("[%s] send_image error: %s", self.name, exc)
            return SendResult(success=False, error=str(exc))

    async def _upload_media(self, file_path: str, media_type: str, token: str) -> str | None:
        if not self._http_client:
            return None
        try:
            with open(file_path, "rb") as f:
                files = {"media": (os.path.basename(file_path), f, "application/octet-stream")}
                resp = await self._http_client.post(
                    f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type={media_type}",
                    headers={"User-Agent": "Encre/1.0.0"},
                    files=files,
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    return data.get("media_id")
                logger.error("[%s] Media upload error: %s", self.name, data)
                return None
        except Exception as exc:
            logger.error("[%s] Media upload exception: %s", self.name, exc)
            return None

    async def _do_send(self, payload: dict[str, Any]) -> SendResult:
        if not self._http_client:
            return SendResult(success=False, error="adapter not connected")

        for _attempt in range(2):
            token = await self._get_valid_token()
            if not token:
                return SendResult(success=False, error="no access token")

            try:
                resp = await self._http_client.post(
                    f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                    headers={"User-Agent": "Encre/1.0.0"},
                    json=payload,
                )
                data = resp.json()
                errcode = data.get("errcode")
                if errcode in {40001, 42001} and _attempt == 0:
                    self._access_token = None
                    logger.warning("[%s] Token expired, refreshing", self.name)
                    continue
                if errcode != 0:
                    return SendResult(success=False, error=str(data), raw=data)
                return SendResult(
                    success=True,
                    message_id=str(data.get("msgid", "")),
                    raw=data,
                )
            except Exception as exc:
                if _attempt == 0:
                    logger.warning("[%s] Send attempt failed: %s", self.name, exc)
                    continue
                return SendResult(success=False, error=str(exc))

        return SendResult(success=False, error="send failed after retry")

    # ------------------------------------------------------------------
    # Access token management
    # ------------------------------------------------------------------

    async def _get_valid_token(self) -> str | None:
        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token
        await self._refresh_token()
        return self._access_token

    async def _refresh_token(self) -> None:
        if not self._http_client:
            logger.warning("[%s] No HTTP client for token refresh", self.name)
            return

        try:
            resp = await self._http_client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": self._corp_id, "corpsecret": self._secret},
                headers={"User-Agent": "Encre/1.0.0"},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                logger.error("[%s] Token refresh failed: %s", self.name, data)
                self._access_token = None
                return
            self._access_token = data["access_token"]
            expires_in = int(data.get("expires_in", ACCESS_TOKEN_TTL_SECONDS))
            self._access_token_expires_at = time.time() + expires_in
            logger.info("[%s] Access token refreshed, expires in %ds", self.name, expires_in)
        except Exception as exc:
            logger.error("[%s] Token refresh error: %s", self.name, exc)
            self._access_token = None

    # ------------------------------------------------------------------
    # Chat info
    # ------------------------------------------------------------------

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"id": chat_id, "platform": self.name}

    # ------------------------------------------------------------------
    # Callback handler (public API for external webhook integration)
    # ------------------------------------------------------------------

    async def handle_callback(
        self,
        body: bytes,
        _query_params: dict[str, str],
        msg_signature: str,
        timestamp: str,
        nonce: str,
    ) -> bytes:
        """Handle an incoming WeCom encrypted callback.

        Decrypts the XML payload, dispatches the message event to the agent,
        and returns an acknowledgement response.
        """
        if not self._crypt:
            logger.warning("[%s] Crypto not configured, cannot process callback", self.name)
            return b"invalid: crypto not configured"

        try:
            body_str = body.decode("utf-8") if isinstance(body, bytes) else str(body)
            root = ET.fromstring(body_str)
            encrypt_elem = root.findtext("Encrypt", default="")
            decrypted = self._crypt.decrypt(msg_signature, timestamp, nonce, encrypt_elem)
        except WeComCryptoError as exc:
            logger.warning("[%s] Decryption failed: %s", self.name, exc)
            return b"invalid: decrypt failed"
        except Exception as exc:
            logger.warning("[%s] XML parse error: %s", self.name, exc)
            return b"invalid: xml error"

        event = self._build_event(decrypted.decode("utf-8"))
        if event is not None:
            if event.message_id:
                now = time.time()
                if event.message_id in self._seen_messages and now - self._seen_messages[event.message_id] < MESSAGE_DEDUP_TTL_SECONDS:
                    logger.debug("[%s] Duplicate MsgId %s, skipping", self.name, event.message_id)
                    return b"success"
                self._seen_messages[event.message_id] = now
                if len(self._seen_messages) > 2000:
                    cutoff = now - MESSAGE_DEDUP_TTL_SECONDS
                    self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}

            self._spawn_task(self._dispatch_event(event))

        return b"success"

    def _build_event(self, xml_text: str) -> MessageEvent | None:
        root = ET.fromstring(xml_text)
        msg_type = (root.findtext("MsgType") or "").lower()

        if msg_type == "event":
            event_name = (root.findtext("Event") or "").lower()
            if event_name in {"enter_agent", "subscribe"}:
                return None
            if event_name == "unsubscribe":
                return None

        if msg_type not in {"text", "event", "image", "voice"}:
            return None

        user_id = root.findtext("FromUserName", default="")
        content = root.findtext("Content", default="").strip()
        if not content and msg_type == "event":
            content = "/start"

        msg_id = root.findtext("MsgId") or f"{user_id}:{root.findtext('CreateTime', default='0')}"

        message_type = MessageType.TEXT
        if msg_type == "image":
            message_type = MessageType.IMAGE
        elif msg_type == "voice":
            message_type = MessageType.VOICE

        media_urls: list[str] = []
        media_types: list[str] = []
        if msg_type == "image":
            media_url = root.findtext("PicUrl", default="")
            if media_url:
                media_urls.append(media_url)
                media_types.append("image")
        elif msg_type == "voice":
            media_id = root.findtext("MediaId", default="")
            if media_id:
                media_urls.append(media_id)
                media_types.append("voice")

        return MessageEvent(
            text=content,
            message_type=message_type,
            message_id=msg_id,
            media_urls=media_urls,
            media_types=media_types,
            raw_message=xml_text,
            source=SessionSource(
                platform=self.name,
                chat_id=user_id,
                chat_type="dm",
                user_id=user_id,
            ),
        )

    async def _dispatch_event(self, event: MessageEvent) -> None:
        try:
            if event.source and event.source.chat_id:
                try:
                    await self.send_typing(event.source.chat_id)
                except Exception:
                    pass
            await self.handle_message(event)
        except Exception as exc:
            logger.error("[%s] Event dispatch error: %s", self.name, exc)

    # ------------------------------------------------------------------
    # Webhook HTTP handlers
    # ------------------------------------------------------------------

    async def _handle_verify(self, request: "web.Request") -> "web.Response":
        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        echostr = request.query.get("echostr", "")
        if not self._crypt:
            return web.Response(status=403, text="crypto not configured")
        try:
            plain = self._crypt.verify_url(msg_signature, timestamp, nonce, echostr)
            return web.Response(text=plain, content_type="text/plain")
        except WeComCryptoError:
            return web.Response(status=403, text="signature verification failed")

    async def _handle_callback(self, request: "web.Request") -> "web.Response":
        msg_signature = request.query.get("msg_signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        body = await request.text()

        if not self._crypt:
            return web.Response(status=403, text="crypto not configured")

        try:
            root = ET.fromstring(body)
            encrypt = root.findtext("Encrypt", default="")
            decrypted = self._crypt.decrypt(msg_signature, timestamp, nonce, encrypt)
        except WeComCryptoError:
            return web.Response(status=400, text="decrypt failed")
        except Exception:
            logger.exception("[%s] Error handling callback", self.name)
            return web.Response(status=400, text="invalid callback payload")

        event = self._build_event(decrypted.decode("utf-8"))
        if event is not None:
            if event.message_id:
                now = time.time()
                if event.message_id in self._seen_messages and now - self._seen_messages[event.message_id] < MESSAGE_DEDUP_TTL_SECONDS:
                    logger.debug("[%s] Duplicate MsgId %s, skipping", self.name, event.message_id)
                    return web.Response(text="success", content_type="text/plain")
                self._seen_messages[event.message_id] = now
                if len(self._seen_messages) > 2000:
                    cutoff = now - MESSAGE_DEDUP_TTL_SECONDS
                    self._seen_messages = {k: v for k, v in self._seen_messages.items() if v > cutoff}

            self._spawn_task(self._dispatch_event(event))

        return web.Response(text="success", content_type="text/plain")


# ---------------------------------------------------------------------------
# Platform registration
# ---------------------------------------------------------------------------

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return AIOHTTP_AVAILABLE and HTTPX_AVAILABLE and CRYPTO_AVAILABLE


platform_registry.register(PlatformEntry(
    name="wecom",
    label="WeCom",
    platform=Platform.WECOM,
    adapter_factory=lambda cfg: WeComAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["WECOM_CORP_SECRET"],
))
