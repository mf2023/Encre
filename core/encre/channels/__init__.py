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
shared agent runtime via :class:`encre.protocol.session_router.EventRouter`.
This package re-exports the channel implementations and the routing base:

    * :class:`Channel`         -- abstract channel interface.
    * :class:`EventRouter`     -- multi-session router backed by the SessionManager
      (implemented in :mod:`encre.protocol.session_router`; re-exported here
      for backwards-compatible imports).
    * :class:`TerminalChannel`  -- interactive stdin/stdout REPL (deprecated).

The WebSocket and HTTP channel transports moved to :mod:`encre.transport`
(:class:`encre.transport.websocket_channel.WebSocketChannel` and
:class:`encre.transport.http.channel.HTTPChannel`).
"""

from encre.channels.base import Channel
from encre.channels.terminal import TerminalChannel
from encre.protocol.session_router import EventRouter

__all__ = [
    "Channel",
    "EventRouter",
    "TerminalChannel",
]
