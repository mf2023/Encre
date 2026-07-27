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

QQBot scan-to-configure (QR code onboard) module.

Follows the Feishu onboarding pattern: synchronous HTTP with a single public
entry-point qr_register() that handles the full flow (create task →
display QR code → poll → decrypt credentials).

Flow overview::

    1. Generate random AES-256 key (generate_bind_key)
    2. POST /lite/create_bind_task with key → get task_id
    3. Display QR code URL to user
    4. User scans QR with QQ app → server encrypts client_secret with key
    5. Poll /lite/poll_bind_result until status=COMPLETED
    6. Decrypt bot_encrypt_secret with AES-256-GCM → get client_secret
    7. Return {app_id, client_secret, user_openid}

APIs called:
    - ``create_bind_task`` — creates a bind task and returns task_id + encrypted response.
    - ``poll_bind_result`` — polls for scan completion; returns decrypted credentials.

QR code URL template::

    https://q.qq.com/qqbot/openclaw/connect.html?task_id=<TASK_ID>&_wv=2&source=encre

The QR code is opened in the QQ mobile app where the user confirms binding.
After scanning, poll_bind_result returns:
    - bot_appid: The bot's application ID
    - bot_encrypt_secret: AES-256-GCM encrypted client_secret (encrypted with the bind key)
    - user_openid: OpenID of the user who scanned the QR code

Reference: https://bot.q.qq.com/wiki/develop/api-v2/
"""

import logging
import time
from enum import IntEnum
from typing import Optional, Tuple
from urllib.parse import quote

from .constants import (
    ONBOARD_API_TIMEOUT,
    ONBOARD_CREATE_PATH,
    ONBOARD_POLL_INTERVAL,
    ONBOARD_POLL_PATH,
    PORTAL_HOST,
    QR_URL_TEMPLATE,
)
from .crypto import decrypt_secret, generate_bind_key
from .utils import get_api_headers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BindStatus — result codes from poll_bind_result
# ---------------------------------------------------------------------------

class BindStatus(IntEnum):
    """Status codes returned by ``_poll_bind_result``.

    These values come directly from the QQ Bot API's bind status field.

    Attributes:
        NONE: No bind result yet (still polling).
        PENDING: User has scanned the QR but not yet confirmed.
        COMPLETED: User has confirmed — credentials are ready.
        EXPIRED: QR code has expired — need to create a new task.
    """

    NONE = 0
    PENDING = 1
    COMPLETED = 2
    EXPIRED = 3


# ---------------------------------------------------------------------------
# QR rendering — terminal display helper
# ---------------------------------------------------------------------------

import qrcode as _qrcode_mod  # optional — QR rendering falls back to URL if missing


def _render_qr(url: str) -> bool:
    """Try to render a QR code in the terminal. Returns True if successful.

    Uses the ``qrcode`` library to print an ASCII QR code to stdout.
    Falls back gracefully if the library is not installed or rendering fails.

    Args:
        url: The QR code target URL.

    Returns:
        True if the QR code was rendered successfully, False otherwise.
    """
    if _qrcode_mod is None:
        return False
    try:
        qr = _qrcode_mod.QRCode(
            error_correction=_qrcode_mod.constants.ERROR_CORRECT_M,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Synchronous HTTP helpers
# ---------------------------------------------------------------------------

def _create_bind_task(timeout: float = ONBOARD_API_TIMEOUT) -> Tuple[str, str]:
    """Create a bind task and return *(task_id, aes_key_base64)*.

    Generates a random AES-256 key, sends it to the QQ portal via
    ``create_bind_task``, and returns the assigned task_id along with
    the key (needed later for decryption).

    Flow:
        1. Generate random AES-256 key via :func:`generate_bind_key`.
        2. POST {portal_host}/lite/create_bind_task with {"key": key}.
        3. Validate retcode == 0 and extract task_id.

    Args:
        timeout: HTTP request timeout in seconds.

    Returns:
        Tuple of ``(task_id, aes_key_base64)``.

    Raises:
        RuntimeError: If the API returns a non-zero ``retcode`` or
            the response is missing ``task_id``.
    """
    import httpx

    url = f"https://{PORTAL_HOST}{ONBOARD_CREATE_PATH}"
    key = generate_bind_key()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(url, json={"key": key}, headers=get_api_headers())
        resp.raise_for_status()
        data = resp.json()

    if data.get("retcode") != 0:
        raise RuntimeError(data.get("msg", "create_bind_task failed"))

    task_id = data.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError("create_bind_task: missing task_id in response")

    logger.debug("create_bind_task ok: task_id=%s", task_id)
    return task_id, key


def _poll_bind_result(
    task_id: str,
    timeout: float = ONBOARD_API_TIMEOUT,
) -> Tuple[BindStatus, str, str, str]:
    """Poll the bind result for *task_id*.

    Sends a single ``poll_bind_result`` request and returns the parsed
    result. Callers should loop until status changes from NONE/PENDING
    to COMPLETED or EXPIRED.

    Args:
        task_id: The task ID returned by ``create_bind_task``.
        timeout: HTTP request timeout in seconds.

    Returns:
        A 4-tuple of ``(status, bot_appid, bot_encrypt_secret, user_openid)``:
            - status: BindStatus enum value.
            - bot_appid: The bot's application ID.
            - bot_encrypt_secret: Encrypted client_secret (base64-encoded AES-GCM ciphertext).
            - user_openid: OpenID of the user who scanned the QR code.

    Raises:
        RuntimeError: If the API returns a non-zero ``retcode``.
    """
    import httpx

    url = f"https://{PORTAL_HOST}{ONBOARD_POLL_PATH}"

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(url, json={"task_id": task_id}, headers=get_api_headers())
        resp.raise_for_status()
        data = resp.json()

    if data.get("retcode") != 0:
        raise RuntimeError(data.get("msg", "poll_bind_result failed"))

    d = data.get("data", {})
    return (
        BindStatus(d.get("status", 0)),
        str(d.get("bot_appid", "")),
        d.get("bot_encrypt_secret", ""),
        d.get("user_openid", ""),
    )


def build_connect_url(task_id: str) -> str:
    """Build the QR-code target URL for a given *task_id*.

    URL-encodes the task_id and inserts it into the QR URL template.
    The resulting URL opens in the QQ mobile app where the user can
    scan and confirm the bot binding.

    Args:
        task_id: Task ID returned by ``create_bind_task``.

    Returns:
        Full QR code URL string.
    """
    return QR_URL_TEMPLATE.format(task_id=quote(task_id))


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

# Maximum number of times to refresh the QR code before giving up.
_MAX_REFRESHES = 3


def qr_register(timeout_seconds: int = 600) -> Optional[dict]:
    """Run the QQBot scan-to-configure QR registration flow.

    This is the main public entry-point for configuring a QQ Bot. It handles
    the complete lifecycle: create bind task → display QR code → poll for
    scan completion → decrypt credentials.

    Flow::

        for attempt in range(_MAX_REFRESHES + 1):
            1. Create bind task → (task_id, aes_key)
            2. Build and display QR code URL
            3. Poll poll_bind_result until:
               - COMPLETED → decrypt and return credentials
               - EXPIRED → break to next iteration (refresh QR)
               - deadline exceeded → return None

    Args:
        timeout_seconds: Maximum time to wait for the user to scan the QR code.
            Default 600 seconds (10 minutes).

    Returns:
        Dict with keys ``"app_id"``, ``"client_secret"``, ``"user_openid"``
        on success, or ``None`` on failure/expiry/cancellation.

    Example::

        >>> result = qr_register(timeout_seconds=300)
        >>> if result:
        ...     print(f"App ID: {result['app_id']}")
        ...     print(f"Client Secret: {result['client_secret']}")
    """
    deadline = time.monotonic() + timeout_seconds

    for refresh_count in range(_MAX_REFRESHES + 1):
        # ── Create bind task ──
        try:
            task_id, aes_key = _create_bind_task()
        except Exception as exc:
            logger.warning("[QQBot onboard] Failed to create bind task: %s", exc)
            return None

        url = build_connect_url(task_id)

        # ── Display QR code + URL ──
        print()
        if _render_qr(url):
            print(f"  Scan the QR code above, or open this URL directly:\n  {url}")
        else:
            print(f"  Open this URL in QQ on your phone:\n  {url}")
            print("  Tip: pip install qrcode  to display a scannable QR code here")
        print()

        # ── Poll loop ──
        while time.monotonic() < deadline:
            try:
                status, app_id, encrypted_secret, user_openid = _poll_bind_result(task_id)
            except Exception:
                time.sleep(ONBOARD_POLL_INTERVAL)
                continue

            if status == BindStatus.COMPLETED:
                client_secret = decrypt_secret(encrypted_secret, aes_key)
                print()
                print(f"  QR scan complete! (App ID: {app_id})")
                if user_openid:
                    print(f"  Scanner's OpenID: {user_openid}")
                return {
                    "app_id": app_id,
                    "client_secret": client_secret,
                    "user_openid": user_openid,
                }

            if status == BindStatus.EXPIRED:
                if refresh_count >= _MAX_REFRESHES:
                    logger.warning("[QQBot onboard] QR code expired %d times — giving up", _MAX_REFRESHES)
                    return None
                print(f"\n  QR code expired, refreshing... ({refresh_count + 1}/{_MAX_REFRESHES})")
                break  # next for-loop iteration creates a new task

            time.sleep(ONBOARD_POLL_INTERVAL)
        else:
            # deadline reached without completing
            logger.warning("[QQBot onboard] Poll timed out after %ds", timeout_seconds)
            return None

    return None
