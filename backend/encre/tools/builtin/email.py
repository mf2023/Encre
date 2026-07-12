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

"""Email tool (SMTP / IMAP).

Composes and sends email via SMTP and reads the inbox via IMAP, with optional
attachment handling.
"""


import asyncio
import email
import imaplib
import json
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parsedate_to_datetime
from typing import Any

from encre.tools.base import build_tool


def _decode_mime(s: str | None) -> str:
    """Decode mime.

    Args:
        s: Description of the s parameter.
    """
    if not s:
        return ""
    parts = decode_header(s)
    return "".join(
        part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, charset in parts
    )


async def _email_execute(**kwargs: Any) -> str:
    """Email execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")

    if action == "send":
        host = kwargs.get("host", "")
        port = kwargs.get("port", 587)
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        use_tls = kwargs.get("use_tls", True)
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        cc = kwargs.get("cc", "")
        bcc = kwargs.get("bcc", "")

        if not all([host, username, password, to, subject]):
            return "Missing required fields: host, username, password, to, subject"

        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((username, username))
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain", "utf-8"))

        recipients = [to]
        if cc:
            recipients.extend([addr.strip() for addr in cc.split(",") if addr.strip()])
        if bcc:
            recipients.extend([addr.strip() for addr in bcc.split(",") if addr.strip()])

        loop = asyncio.get_event_loop()

        def _send() -> str:
            """Send."""
            try:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    if use_tls:
                        server.starttls()
                    server.login(username, password)
                    server.sendmail(username, recipients, msg.as_string())
                return "Email sent successfully"
            except Exception as e:
                return f"Failed to send email: {e}"

        return await loop.run_in_executor(None, _send)

    elif action == "read":
        host = kwargs.get("host", "")
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        folder = kwargs.get("folder", "INBOX")
        max_emails = kwargs.get("max_emails", 10)
        mark_seen = kwargs.get("mark_seen", False)

        if not all([host, username, password]):
            return "Missing required fields: host, username, password"

        loop = asyncio.get_event_loop()

        def _read() -> str:
            """Read."""
            try:
                conn = imaplib.IMAP4_SSL(host, timeout=30)
                conn.login(username, password)
                conn.select(folder, readonly=not mark_seen)
                _, data = conn.search(None, "ALL")
                if not data or not data[0]:
                    conn.logout()
                    return "No emails found"
                msg_ids = data[0].split()[-max_emails:]
                results = []
                for mid in reversed(msg_ids):
                    _, msg_data = conn.fetch(mid, "(RFC822)")
                    if not msg_data or msg_data[0] is None:
                        continue
                    raw_email = msg_data[0][1]
                    em = email.message_from_bytes(raw_email)
                    subject = _decode_mime(em["Subject"])
                    sender = _decode_mime(em["From"])
                    date = str(parsedate_to_datetime(em["Date"]) if em["Date"] else "")
                    body_text = ""
                    if em.is_multipart():
                        for part in em.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body_text = payload.decode("utf-8", errors="replace")[:2000]
                                    break
                    else:
                        payload = em.get_payload(decode=True)
                        if payload:
                            body_text = payload.decode("utf-8", errors="replace")[:2000]
                    results.append({
                        "subject": subject,
                        "from": sender,
                        "date": date,
                        "body_preview": body_text[:500],
                    })
                conn.logout()
                return json.dumps(results, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to read emails: {e}"

        return await loop.run_in_executor(None, _read)

    elif action == "search":
        host = kwargs.get("host", "")
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        folder = kwargs.get("folder", "INBOX")
        criteria = kwargs.get("criteria", "ALL")
        max_results = kwargs.get("max_results", 10)

        if not all([host, username, password]):
            return "Missing required fields: host, username, password"

        loop = asyncio.get_event_loop()

        def _search() -> str:
            """Search."""
            try:
                conn = imaplib.IMAP4_SSL(host, timeout=30)
                conn.login(username, password)
                conn.select(folder, readonly=True)
                _, data = conn.search(None, criteria)
                if not data or not data[0]:
                    conn.logout()
                    return "No emails matching criteria"
                msg_ids = data[0].split()[-max_results:]
                results = []
                for mid in reversed(msg_ids):
                    _, msg_data = conn.fetch(mid, "(RFC822)")
                    if not msg_data or msg_data[0] is None:
                        continue
                    raw_email = msg_data[0][1]
                    em = email.message_from_bytes(raw_email)
                    results.append({
                        "subject": _decode_mime(em["Subject"]),
                        "from": _decode_mime(em["From"]),
                        "date": str(parsedate_to_datetime(em["Date"]) if em["Date"] else ""),
                    })
                conn.logout()
                return json.dumps(results, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to search emails: {e}"

        return await loop.run_in_executor(None, _search)

    elif action == "list_folders":
        host = kwargs.get("host", "")
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")

        if not all([host, username, password]):
            return "Missing required fields: host, username, password"

        loop = asyncio.get_event_loop()

        def _list_folders() -> str:
            """List folders."""
            try:
                conn = imaplib.IMAP4_SSL(host, timeout=30)
                conn.login(username, password)
                _, folders = conn.list()
                conn.logout()
                names = []
                for folder_data in (folders or []):
                    parts = folder_data.decode().split(' "/" ')
                    if len(parts) == 2:
                        names.append(parts[1].strip('"'))
                return json.dumps(names, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to list folders: {e}"

        return await loop.run_in_executor(None, _list_folders)

    return f"Unknown action: {action}. Supported: send, read, search, list_folders"


EncreEmailTool = build_tool(
    name="email",
    description="Send and read emails via SMTP/IMAP. Send, read inbox, search, list folders.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "read", "search", "list_folders"],
                "description": "Action to perform",
            },
            "host": {"type": "string", "description": "SMTP/IMAP server hostname"},
            "port": {"type": "integer", "description": "Server port (587 for SMTP TLS, 993 for IMAP SSL)"},
            "username": {"type": "string", "description": "Email account username"},
            "password": {"type": "string", "description": "Email account password or app password"},
            "use_tls": {"type": "boolean", "description": "Use STARTTLS for SMTP (default true)"},
            "to": {"type": "string", "description": "Recipient email address (for send)"},
            "cc": {"type": "string", "description": "CC recipients, comma-separated (for send)"},
            "bcc": {"type": "string", "description": "BCC recipients, comma-separated (for send)"},
            "subject": {"type": "string", "description": "Email subject (for send)"},
            "body": {"type": "string", "description": "Email body text (for send)"},
            "folder": {"type": "string", "description": "IMAP folder name (default INBOX)"},
            "max_emails": {"type": "integer", "description": "Max emails to fetch (default 10)"},
            "mark_seen": {"type": "boolean", "description": "Mark fetched emails as seen (default false)"},
            "criteria": {"type": "string", "description": "IMAP search criteria e.g. 'FROM user@example.com' (for search)"},
            "max_results": {"type": "integer", "description": "Max search results (default 10)"},
        },
        "required": ["action"],
    },
    execute=_email_execute,
    intents=["general", "system"],
    category="communication",
    semantic_type="network",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_destructive=lambda args: args.get("action", "") == "send",
)
