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

"""Encre channel-adapter gateway package.

The gateway is a small, fast WebSocket server (localhost-only) that lets external
channel adapters -- QQ, Telegram, iClaw desktop, etc. -- connect and exchange
messages with the iClaw engine (EventRouter) without exposing the full agent
WebSocket protocol.

This package re-exports:
    * :class:`GatewayServer` -- accepts adapter connections (see :mod:`encre.gateway.server`).
    * :class:`GatewayClient` -- outbound client used by adapters (see :mod:`encre.gateway.client`).
    * :class:`GatewayMessage` / :class:`GatewayOp` -- wire protocol (see :mod:`encre.gateway.protocol`).
"""

from encre.gateway.client import GatewayClient
from encre.gateway.protocol import GatewayMessage, GatewayOp
from encre.gateway.server import GatewayServer

__all__ = [
    "GatewayClient",
    "GatewayMessage",
    "GatewayOp",
    "GatewayServer",
]
