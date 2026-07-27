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

Shared constants for the QQBot platform adapter.

All values in this module are import-free (only ``os.getenv``), so they can be
safely imported by any sub-module — including ``crypto.py`` which is used at
module level by ``onboard.py``.

Categories:
    - Version: ``QQBOT_VERSION``
    - API endpoints: ``API_BASE``, ``TOKEN_URL``, gateway path, onboard paths, QR URL
    - Timeouts: API, file upload, WebSocket connect, reconnect backoff
    - Message limits: max length, dedup window/size
    - Message types: text(0), markdown(2), media(7), input_notify(6)
    - Media types: image(1), video(2), voice(3), file(4)
"""

import os

# ---------------------------------------------------------------------------
# QQBot adapter version — bump on functional changes to the adapter package.
# ---------------------------------------------------------------------------

QQBOT_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

# The portal domain is configurable via QQ_API_HOST for corporate proxies
# or test environments.  Default: q.qq.com (production).
PORTAL_HOST = os.getenv("QQ_PORTAL_HOST", "q.qq.com")

# Base URL for the QQ Bot REST API v2. All REST calls are relative to this.
API_BASE = "https://api.sgroup.qq.com"

# OAuth2 token endpoint — POST appId + clientSecret → access_token.
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

# WebSocket gateway URL path — GET /gateway with auth header → gateway URL.
GATEWAY_URL_PATH = "/gateway"

# QR-code onboard endpoints (on the portal host).
ONBOARD_CREATE_PATH = "/lite/create_bind_task"
ONBOARD_POLL_PATH = "/lite/poll_bind_result"

# QR code redirect URL template.
# {task_id} is substituted by build_connect_url(). source=encre identifies
# the QR code as coming from Encre (vs other QQ bot clients).
QR_URL_TEMPLATE = (
    "https://q.qq.com/qqbot/openclaw/connect.html"
    "?task_id={task_id}&_wv=2&source=encre"
)

# ---------------------------------------------------------------------------
# Timeouts & retry
# ---------------------------------------------------------------------------

# Default timeout for REST API calls (seconds).
DEFAULT_API_TIMEOUT = 30.0

# Timeout for file upload requests (longer due to large payloads).
FILE_UPLOAD_TIMEOUT = 120.0

# WebSocket connection establishment timeout (seconds).
CONNECT_TIMEOUT_SECONDS = 20.0

# Exponential backoff delays for reconnection attempts (seconds).
# Applied as delay[min(backoff_idx, len(delays)-1)].
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]

# Maximum number of reconnect attempts before giving up.
MAX_RECONNECT_ATTEMPTS = 100

# Delay before retrying after rate limit (4008) close code (seconds).
RATE_LIMIT_DELAY = 60  # seconds

# Duration threshold (seconds) below which a disconnect counts as "quick".
QUICK_DISCONNECT_THRESHOLD = 5.0  # seconds

# Max consecutive quick disconnects before flagging misconfiguration.
MAX_QUICK_DISCONNECT_COUNT = 3

# Onboarding: interval between poll_bind_result calls (seconds).
ONBOARD_POLL_INTERVAL = 2.0  # seconds between poll_bind_result calls

# Onboarding: HTTP timeout for create_bind_task and poll_bind_result calls.
ONBOARD_API_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# Message limits
# ---------------------------------------------------------------------------

# Maximum characters per QQ message (before chunking).
MAX_MESSAGE_LENGTH = 4000

# Dedup window: messages older than this are purged from _seen_messages.
DEDUP_WINDOW_SECONDS = 300

# Max entries in _seen_messages before pruning old entries.
DEDUP_MAX_SIZE = 1000

# Content-based dedup window (short): QQ Bot may dispatch the same message
# under multiple event types with different IDs within seconds.
DEDUP_CONTENT_WINDOW_SECONDS = 5

# ---------------------------------------------------------------------------
# QQ Bot message types (msg_type field in outbound messages)
# ---------------------------------------------------------------------------

MSG_TYPE_TEXT = 0         # Plain text message
MSG_TYPE_MARKDOWN = 2     # QQ markdown message (rich formatting)
MSG_TYPE_MEDIA = 7        # RichMedia message (image/video/voice/file with file_info)
MSG_TYPE_INPUT_NOTIFY = 6 # Typing indicator (input_notify)

# ---------------------------------------------------------------------------
# QQ Bot file media types (file_type field in upload requests)
# ---------------------------------------------------------------------------

MEDIA_TYPE_IMAGE = 1      # Image file (jpg, png, gif, etc.)
MEDIA_TYPE_VIDEO = 2      # Video file (mp4, mov, etc.)
MEDIA_TYPE_VOICE = 3      # Voice file (silk, amr, wav, etc.)
MEDIA_TYPE_FILE = 4       # Generic file (doc, zip, pdf, etc.)
