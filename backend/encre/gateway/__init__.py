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

"""Encre gateway package.

The gateway manages platform adapters (Telegram, Discord, QQ, etc.) and routes
messages between them and the agent runtime (EventRouter).  Core adapters run
in-process; an optional WS bridge serves remote/plugin adapters.

This package re-exports:
    * :class:`GatewayRunner` -- unified lifecycle manager (see :mod:`encre.gateway.run`).
    * :class:`PlatformRegistry` / :func:`platform_registry` -- adapter registry.
    * :class:`BasePlatformAdapter` -- abstract base for all adapters.
    * :class:`GatewayMessage` / :class:`GatewayOp` -- WS bridge wire protocol.
"""

from encre.gateway.config import GatewayConfig, Platform, PlatformConfig
from encre.gateway.platform_registry import PlatformEntry, PlatformRegistry, platform_registry
from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from encre.gateway.run import GatewayRunner
from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp

__all__ = [
    "BasePlatformAdapter",
    "GatewayConfig",
    "GatewayMessage",
    "GatewayOp",
    "GatewayRunner",
    "MessageEvent",
    "Platform",
    "PlatformConfig",
    "PlatformEntry",
    "PlatformRegistry",
    "SendResult",
    "platform_registry",
]
