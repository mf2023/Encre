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

"""WebSocket bridge for remote/plugin adapters.

This subpackage contains the WebSocket bridge server and client that let remote
adapters -- code running in a separate process, a plugin host, or a different
machine -- attach to the Encre gateway over a WebSocket connection. Core
adapters run in-process and therefore never use this bridge; it exists purely to
extend the gateway beyond the local process boundary.

Architecture at a glance::

    remote adapter (plugin)  <--WebSocket-->  WsBridgeServer  <--in-process-->  gateway
            |                                      |
    GatewayClient (SDK)                  RemotePlatformAdapter (server-side wrapper)

Modules:
    server.py         - ``WsBridgeServer``: accepts inbound remote-adapter
        WebSocket connections and manages their lifecycle.
    client.py         - ``GatewayClient``: the SDK a remote adapter uses to
        connect to the server and exchange messages.
    protocol.py       - Wire protocol: ``GatewayOp`` (message opcodes) and
        ``GatewayMessage`` (the envelope sent over the socket).
    remote_adapter.py - ``RemotePlatformAdapter``: server-side object that
        wraps a single WS connection as if it were a normal platform adapter.

The wire protocol is defined once in ``protocol.py`` and shared by both ends so
the client and server can never drift apart.
"""

from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp
from encre.gateway.ws_bridge.server import WsBridgeServer

__all__ = [
    "GatewayMessage",
    "GatewayOp",
    "WsBridgeServer",
]
