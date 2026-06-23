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
import contextlib
import email
import email.mime.base
import email.mime.image
import email.mime.multipart
import email.mime.text
import email.utils
import logging
import mimetypes
import os
from email.header import decode_header
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.email")

try:
    import aioimaplib

    AIOIMAPLIB_AVAILABLE = True
except ImportError:
    AIOIMAPLIB_AVAILABLE = False
    aioimaplib = None

try:
    import aiosmtplib

    AIOSMTPLIB_AVAILABLE = True
except ImportError:
    AIOSMTPLIB_AVAILABLE = False
    aiosmtplib = None


class EmailAdapter(BaseAdapter):
    """Email adapter using SMTP for sending and IMAP for receiving.

    Connects to an email server via SMTP+IMAP, polls the IMAP INBOX for
    new messages, and relays them to the Encre gateway for AI processing.
    Outgoing messages are sent via SMTP with support for text, image, and
    document attachments. Email threading is supported via ``In-Reply-To``
    and ``References`` headers.

    To use:
        1. Install ``aiosmtplib`` and ``aioimaplib``
        2. Configure SMTP and IMAP server credentials
        3. Run the adapter as a standalone process

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.email import EmailAdapter  # noqa: E402

        async def main():
            adapter = EmailAdapter(
                smtp_host="smtp.example.com",
                smtp_user="user@example.com",
                smtp_pass="password",
                imap_host="imap.example.com",
                imap_user="user@example.com",
                imap_pass="password",
            )
            await adapter.start()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.stop()

        asyncio.run(main())
    """

    name = "email"

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_pass: str = "",
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_pass: str = "",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
        poll_interval: int = 30,
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text", "image", "file"])
        if not AIOIMAPLIB_AVAILABLE:
            raise ImportError(
                "aioimaplib is required. Install with: pip install aioimaplib"
            )
        if not AIOSMTPLIB_AVAILABLE:
            raise ImportError(
                "aiosmtplib is required. Install with: pip install aiosmtplib"
            )
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_pass = smtp_pass
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._imap_user = imap_user
        self._imap_pass = imap_pass
        self._poll_interval = poll_interval
        self._smtp_client: aiosmtplib.SMTP | None = None
        self._imap_client: aioimaplib.IMAP4_SSL | None = None
        self._poll_task: asyncio.Task[Any] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._last_seen_uids: set[str] = set()
        self._ready = asyncio.Event()
        self._from_addr: str = smtp_user

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Initialize SMTP and IMAP connections and start the polling loop."""
        if not self._smtp_host:
            logger.warning("[email] No SMTP host configured, skipping SMTP connection")
        else:
            logger.info("[email] Connecting to SMTP server %s:%d...", self._smtp_host, self._smtp_port)
            await self._connect_smtp()

        if not self._imap_host:
            logger.warning("[email] No IMAP host configured, skipping IMAP connection")
        else:
            logger.info("[email] Connecting to IMAP server %s:%d...", self._imap_host, self._imap_port)
            await self._connect_imap()

        logger.info("[email] Marking connected state...")
        self._mark_connected()
        self._ready.set()
        logger.info("[email] Starting inbox poll loop...")
        self._poll_task = asyncio.create_task(self._poll_inbox())
        self._background_tasks.add(self._poll_task)
        self._poll_task.add_done_callback(self._background_tasks.discard)
        logger.info(
            "[email] Connected (SMTP=%s:%d, IMAP=%s:%d, poll=%ds)",
            self._smtp_host or "(none)",
            self._smtp_port,
            self._imap_host or "(none)",
            self._imap_port,
            self._poll_interval,
        )
        return True

    async def disconnect(self) -> None:
        """Close SMTP and IMAP connections and stop polling."""
        await super().disconnect()
        self._ready.clear()
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self._disconnect_imap()
        await self._disconnect_smtp()
        logger.info("[email] Disconnected")

    async def _connect_smtp(self) -> None:
        """Establish the SMTP connection and authenticate."""
        if not self._smtp_host:
            return
        try:
            self._smtp_client = aiosmtplib.SMTP(
                hostname=self._smtp_host,
                port=self._smtp_port,
                use_tls=self._smtp_port == 465,
            )
            await self._smtp_client.connect()
            if self._smtp_port == 587:
                await self._smtp_client.starttls()
            if self._smtp_user and self._smtp_pass:
                await self._smtp_client.login(self._smtp_user, self._smtp_pass)
            logger.info("[email] SMTP connected to %s:%d", self._smtp_host, self._smtp_port)
        except Exception as e:
            logger.error("[email] SMTP connection failed: %s", e)
            self._smtp_client = None
            raise

    async def _disconnect_smtp(self) -> None:
        """Close the SMTP connection."""
        if self._smtp_client is not None:
            try:
                await self._smtp_client.quit()
            except Exception as e:
                logger.warning("[email] SMTP quit error: %s", e)
            self._smtp_client = None

    async def _connect_imap(self) -> None:
        """Establish the IMAP connection and authenticate."""
        if not self._imap_host:
            return
        try:
            self._imap_client = aioimaplib.IMAP4_SSL(
                host=self._imap_host,
                port=self._imap_port,
            )
            await self._imap_client.wait_hello_from_server()
            await self._imap_client.login(self._imap_user, self._imap_pass)
            await self._imap_client.select("INBOX")
            logger.info("[email] IMAP connected to %s:%d", self._imap_host, self._imap_port)
        except Exception as e:
            logger.error("[email] IMAP connection failed: %s", e)
            self._imap_client = None
            raise

    async def _disconnect_imap(self) -> None:
        """Close the IMAP connection."""
        if self._imap_client is not None:
            try:
                await self._imap_client.logout()
            except Exception as e:
                logger.warning("[email] IMAP logout error: %s", e)
            self._imap_client = None

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text email to the specified recipient.

        ``chat_id`` is the recipient's email address.
        ``reply_to`` is the ``Message-ID`` of the email being replied to.
        """
        if self._smtp_client is None:
            return SendResult(success=False, error="SMTP not connected")
        try:
            msg = email.mime.text.MIMEText(content, _charset="utf-8")
            msg["From"] = self._from_addr
            msg["To"] = chat_id
            msg["Subject"] = self._build_subject(content, metadata)
            msg["Message-ID"] = email.utils.make_msgid(domain=self._from_addr.split("@")[-1] if "@" in self._from_addr else None)
            msg["Date"] = email.utils.formatdate(localtime=True)

            if reply_to is not None:
                msg["In-Reply-To"] = reply_to
                msg["References"] = reply_to

            await self._smtp_client.send_message(msg)
            message_id = msg["Message-ID"]
            logger.info("[email] Sent text to %s (msg_id=%s)", chat_id, message_id)
            return SendResult(success=True, message_id=message_id, raw=msg)
        except Exception as e:
            logger.error("[email] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_image(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Send an email with an image attachment."""
        if self._smtp_client is None:
            return SendResult(success=False, error="SMTP not connected")
        try:
            msg = email.mime.multipart.MIMEMultipart()
            msg["From"] = self._from_addr
            msg["To"] = chat_id
            msg["Subject"] = caption or "Image"
            msg["Message-ID"] = email.utils.make_msgid(domain=self._from_addr.split("@")[-1] if "@" in self._from_addr else None)
            msg["Date"] = email.utils.formatdate(localtime=True)

            if caption:
                msg.attach(email.mime.text.MIMEText(caption, _charset="utf-8"))

            maintype, subtype = self._guess_mime(file_path, default=("image", "png"))
            with open(file_path, "rb") as f:
                attachment = email.mime.base.MIMEBase(maintype, subtype)
                attachment.set_payload(f.read())
            email.encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=os.path.basename(file_path),
            )
            msg.attach(attachment)

            await self._smtp_client.send_message(msg)
            message_id = msg["Message-ID"]
            logger.info("[email] Sent image to %s (msg_id=%s)", chat_id, message_id)
            return SendResult(success=True, message_id=message_id, raw=msg)
        except Exception as e:
            logger.error("[email] send_image error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        *,
        caption: str | None = None,
    ) -> SendResult:
        """Send an email with a document attachment."""
        if self._smtp_client is None:
            return SendResult(success=False, error="SMTP not connected")
        try:
            msg = email.mime.multipart.MIMEMultipart()
            msg["From"] = self._from_addr
            msg["To"] = chat_id
            msg["Subject"] = caption or "Document"
            msg["Message-ID"] = email.utils.make_msgid(domain=self._from_addr.split("@")[-1] if "@" in self._from_addr else None)
            msg["Date"] = email.utils.formatdate(localtime=True)

            if caption:
                msg.attach(email.mime.text.MIMEText(caption, _charset="utf-8"))

            maintype, subtype = self._guess_mime(file_path, default=("application", "octet-stream"))
            with open(file_path, "rb") as f:
                attachment = email.mime.base.MIMEBase(maintype, subtype)
                attachment.set_payload(f.read())
            email.encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=os.path.basename(file_path),
            )
            msg.attach(attachment)

            await self._smtp_client.send_message(msg)
            message_id = msg["Message-ID"]
            logger.info("[email] Sent document to %s (msg_id=%s)", chat_id, message_id)
            return SendResult(success=True, message_id=message_id, raw=msg)
        except Exception as e:
            logger.error("[email] send_document error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    # ── IMAP Polling ───────────────────────────────────────────────────────

    async def _poll_inbox(self) -> None:
        """Continuously poll the IMAP INBOX for new messages.

        Runs indefinitely until the adapter is disconnected. New messages
        are parsed into :class:`MessageEvent` instances and dispatched via
        :meth:`dispatch_message`.
        """
        if self._imap_client is None:
            logger.warning("[email] IMAP not connected, polling disabled")
            return

        while self._running:
            try:
                await self._check_new_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[email] Poll error: %s", e)
                try:
                    await self._reconnect_imap()
                except Exception as reconnect_error:
                    logger.error("[email] IMAP reconnect failed: %s", reconnect_error)

            await asyncio.sleep(self._poll_interval)

    async def _check_new_messages(self) -> None:
        """Search for unseen messages in the INBOX and process them."""
        if self._imap_client is None:
            return

        status, data = await self._imap_client.search("UNSEEN")
        if status != "OK":
            return

        uids = data[0].split() if isinstance(data[0], bytes) else []
        if not uids:
            return

        uid_set = set(uid.decode() if isinstance(uid, bytes) else str(uid) for uid in uids)
        new_uids = uid_set - self._last_seen_uids
        self._last_seen_uids = uid_set

        for uid in uids:
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
            if uid_str not in new_uids:
                continue
            try:
                await self._fetch_and_process(uid)
            except Exception as e:
                logger.error("[email] Failed to process UID %s: %s", uid_str, e)

    async def _fetch_and_process(self, uid: bytes | str) -> None:
        """Fetch a single email by UID, parse it, and dispatch as MessageEvent."""
        if self._imap_client is None:
            return

        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        status, data = await self._imap_client.uid("FETCH", uid_str, "(RFC822 FLAGS)")
        if status != "OK" or not data:
            return

        raw_email = data[0]
        if isinstance(raw_email, tuple):
            raw_bytes = raw_email[1] if len(raw_email) > 1 and isinstance(raw_email[1], bytes) else raw_email[0]
        elif isinstance(raw_email, bytes):
            raw_bytes = raw_email
        else:
            return

        if not isinstance(raw_bytes, bytes):
            return

        msg = email.message_from_bytes(raw_bytes)
        event = self._parse_email(msg, uid_str)
        if event is None:
            return

        self.dispatch_message(event)

        task = asyncio.create_task(self._process_chat(chat_id=event.chat_id or "", content=event.text))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        await self._imap_client.uid("STORE", uid_str, "+FLAGS", "(\\Seen)")

    def _parse_email(self, msg: email.message.Message, uid: str) -> MessageEvent | None:
        """Parse an email.message.Message into a MessageEvent."""
        subject_raw = msg.get("Subject", "")
        subject = self._decode_header_value(subject_raw) if subject_raw else "(No Subject)"

        from_raw = msg.get("From", "")
        from_addr = email.utils.parseaddr(from_raw)[1] or from_raw

        to_raw = msg.get("To", "")
        email.utils.parseaddr(to_raw)[1] or to_raw

        message_id = msg.get("Message-ID", uid)

        in_reply_to = msg.get("In-Reply-To")
        references = msg.get("References")

        text_body = ""
        media_urls: list[str] = []
        media_types: list[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        media_urls.append(filename)
                        media_types.append(content_type)
                    continue

                if content_type == "text/plain" or (content_type == "text/html" and not text_body):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            text_body += payload.decode(charset, errors="replace")
                    except Exception:
                        pass
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain" or content_type == "text/html":
                charset = msg.get_content_charset() or "utf-8"
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        text_body = payload.decode(charset, errors="replace")
                except Exception:
                    pass

        text_body = text_body.strip()
        if not text_body:
            text_body = subject

        display_text = f"[Email from {from_addr}]\nSubject: {subject}\n\n{text_body}"

        return MessageEvent(
            text=display_text,
            message_type=MessageType.TEXT,
            message_id=message_id,
            chat_id=from_addr,
            user_id=from_addr,
            reply_to_message_id=in_reply_to,
            reply_to_text=references,
            media_urls=media_urls if media_urls else [],
            media_types=media_types if media_types else [],
            raw=msg,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response."""
        session_id = self.get_session(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    async def _reconnect_imap(self) -> None:
        """Reconnect to the IMAP server after a connection loss."""
        await self._disconnect_imap()
        await asyncio.sleep(1)
        await self._connect_imap()
        self._last_seen_uids.clear()

    def _build_subject(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Build an email subject line from content and optional metadata."""
        if metadata and "subject" in metadata:
            return str(metadata["subject"])
        first_line = content.split("\n")[0].strip()
        if len(first_line) > 80:
            first_line = first_line[:77] + "..."
        return first_line if first_line else "Message from Encre AI"

    @staticmethod
    def _decode_header_value(value: str) -> str:
        """Decode an email header value, handling encoded words."""
        decoded_parts = decode_header(value)
        result: list[str] = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(str(part))
        return " ".join(result)

    @staticmethod
    def _guess_mime(file_path: str, default: tuple[str, str] = ("application", "octet-stream")) -> tuple[str, str]:
        """Guess MIME type from file extension."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            parts = mime_type.split("/", 1)
            return (parts[0], parts[1]) if len(parts) == 2 else default
        return default
