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

QQBot platform package.

This is the top-level re-export module for all QQ Bot functionality. It provides
flat imports so callers never need to reference sub-modules directly::

    from encre.gateway.platforms.qqbot import QQAdapter          # adapter
    from encre.gateway.platforms.qqbot import qr_register         # onboard
    from encre.gateway.platforms.qqbot import ChunkedUploader     # upload
    from encre.gateway.platforms.qqbot import build_approval_text # keyboards

Package structure:
    - ``adapter`` — :class:`QQAdapter` implements the full message lifecycle
      (WebSocket connect, event dispatch, REST send, media upload, STT).
    - ``constants`` — API URLs, timeouts, message/media type codes, limits.
    - ``utils`` — User-Agent builder, HTTP header factory, config coercion.
    - ``crypto`` — AES-256-GCM key generation and credential decryption
      for the QR-code scan-to-configure flow.
    - ``onboard`` — Synchronous QR-code registration: create task → display QR
      → poll for scan → decrypt bot credentials.
    - ``chunked_upload`` — Three-step chunked upload (prepare → PUT parts →
      complete) for files between 10 MB and ~100 MB.
    - ``keyboards`` — Inline keyboard dataclasses, button builders, approval
      request rendering, INTERACTION_CREATE event parsing.

Configuration:
    Set environment variables ``QQ_APP_ID`` and ``QQ_CLIENT_SECRET``, or provide
    them in the platform config under ``channels.qqbot``.

Reference: https://bot.q.qq.com/wiki/develop/api-v2/
"""

# -- Adapter ----------------------------------------------------------------
# Re-export the main adapter class, close-error exception, requirements checker,
# and internal helpers used by other sub-modules.
from .adapter import (  # noqa: F401
    QQAdapter,
    QQCloseError,
    check_qq_requirements,
    _coerce_list,
)

# -- Onboard (QR-code scan-to-configure) -----------------------------------
# QR registration flow: creates a bind task, polls for scan completion, returns
# decrypted bot credentials (app_id + client_secret) and scanner's openid.
from .onboard import (  # noqa: F401
    BindStatus,
    build_connect_url,
    qr_register,
)
# AES-256-GCM utilities used by the onboard flow.
from .crypto import decrypt_secret, generate_bind_key  # noqa: F401

# -- Utils -----------------------------------------------------------------
# User-Agent string builder for HTTP requests, standard header factory, and
# config coercion helper (accepts strings/lists/tuples/sets → list[str]).
from .utils import build_user_agent, get_api_headers, coerce_list  # noqa: F401

# -- Chunked upload --------------------------------------------------------
# Three-step chunked upload for large files (>10 MB) via Tencent COS pre-signed URLs.
from .chunked_upload import (  # noqa: F401
    ChunkedUploader,
    UploadDailyLimitExceededError,
    UploadFileTooLargeError,
)

# -- Inline keyboards ------------------------------------------------------
# Keyboard dataclasses, builders for approval/update-prompt flows, button-data
# parsers, and the ApprovalSender helper for posting approval messages.
from .keyboards import (  # noqa: F401
    ApprovalRequest,
    ApprovalSender,
    InlineKeyboard,
    InteractionEvent,
    build_approval_keyboard,
    build_approval_text,
    build_update_prompt_keyboard,
    parse_approval_button_data,
    parse_interaction_event,
    parse_update_prompt_button_data,
)

# Explicit public API surface for ``dir()`` and star-import safety.
__all__ = [
    # adapter
    "QQAdapter",
    "QQCloseError",
    "check_qq_requirements",
    "_coerce_list",
    # onboard
    "BindStatus",
    "build_connect_url",
    "qr_register",
    # crypto
    "decrypt_secret",
    "generate_bind_key",
    # utils
    "build_user_agent",
    "get_api_headers",
    "coerce_list",
    # chunked upload
    "ChunkedUploader",
    "UploadDailyLimitExceededError",
    "UploadFileTooLargeError",
    # keyboards
    "ApprovalRequest",
    "ApprovalSender",
    "InlineKeyboard",
    "InteractionEvent",
    "build_approval_keyboard",
    "build_approval_text",
    "build_update_prompt_keyboard",
    "parse_approval_button_data",
    "parse_interaction_event",
    "parse_update_prompt_button_data",
]
