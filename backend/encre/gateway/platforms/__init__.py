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

"""Platform adapters for messaging integrations.

Each adapter handles:
- Receiving messages from a platform
- Sending messages/responses back
- Platform-specific authentication
- Message formatting and media handling

All built-in adapters self-register into :data:`platform_registry` at import
time.  Call :func:`discover_platforms` once at gateway startup to trigger
registration of every built-in adapter.
"""

import importlib
import logging
from typing import List

from encre.gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    classify_send_error,
    SEND_ERROR_KINDS,
)

logger = logging.getLogger("encre.gateway.platforms")

# All built-in platform module names (relative to encre.gateway.platforms).
_BUILTIN_PLATFORMS = [
    "bluebubbles",
    "dingtalk",
    "discord",
    "email",
    "feishu",
    "homeassistant",
    "matrix",
    "msgraph",
    "qqbot",
    "signal",
    "slack",
    "sms",
    "telegram",
    "test_adapter",
    "webhook",
    "wecom",
    "weixin",
    "whatsapp",
    "yuanbao",
    "api_server",
    "google_chat",
    "irc",
    "line",
    "mattermost",
    "ntfy",
    "photon",
    "raft",
    "simplex",
    "teams",
]

_discovered = False


def discover_platforms() -> List[str]:
    """Import all built-in platform modules, triggering self-registration.

    Safe to call multiple times; only loads on the first invocation.
    Returns the list of successfully loaded module names.
    """
    global _discovered
    if _discovered:
        return _BUILTIN_PLATFORMS
    _discovered = True

    loaded: List[str] = []
    for name in _BUILTIN_PLATFORMS:
        try:
            importlib.import_module(f"encre.gateway.platforms.{name}")
            loaded.append(name)
        except Exception as e:
            logger.debug("Platform '%s' not loaded: %s", name, e)
    logger.info("Discovered %d/%d platform adapters", len(loaded), len(_BUILTIN_PLATFORMS))
    return loaded


__all__ = [
    "BasePlatformAdapter",
    "MessageEvent",
    "MessageType",
    "SendResult",
    "classify_send_error",
    "SEND_ERROR_KINDS",
    "discover_platforms",
]
