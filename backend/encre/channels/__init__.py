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

"""Encre agent channels package.

A *channel* is a transport surface that connects a client (or adapter) to the
shared agent runtime via :class:`encre.channels.base.EventRouter`.  This
package re-exports the channel implementations and the routing base:

    * :class:`Channel`        -- abstract channel interface.
    * :class:`EventRouter`     -- multi-session router backed by the SessionManager.
    * :class:`WebSocketChannel` -- RFC 6455 WebSocket channel (primary).
    * :class:`HTTPChannel`     -- REST / NDJSON channel (headless / CI).
    * :class:`TerminalChannel`  -- interactive stdin/stdout REPL (deprecated).
"""

from encre.channels.base import Channel, EventRouter
from encre.channels.http_api import HTTPChannel
from encre.channels.terminal import TerminalChannel
from encre.channels.websocket import WebSocketChannel

__all__ = [
    "Channel",
    "EventRouter",
    "HTTPChannel",
    "TerminalChannel",
    "WebSocketChannel",
]
