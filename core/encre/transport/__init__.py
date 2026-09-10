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

"""Encre transport layer.

Consolidates the network transports for the server's OWN endpoints:

    * :mod:`encre.transport.ws`               -- :class:`EncreWSHandler`, the
      per-connection desktop WebSocket message handler.
    * :mod:`encre.transport.websocket_channel` -- :class:`WebSocketChannel`,
      the standalone RFC 6455 WebSocket channel.
    * :mod:`encre.transport.http`             -- the HTTP transports
      (:class:`~encre.transport.http.channel.HTTPChannel` and the
      OpenAI-compatible API server adapter).

Gateway PLATFORM adapters (telegram, discord, ...) are NOT part of this
package; they live under :mod:`encre.gateway.platforms` and follow each
platform's official protocol.
"""

from encre.transport.ws import EncreWSHandler
from encre.transport.websocket_channel import WebSocketChannel

__all__ = [
    "EncreWSHandler",
    "WebSocketChannel",
]
