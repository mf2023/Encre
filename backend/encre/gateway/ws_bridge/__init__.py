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

This subpackage contains the WS bridge server and client that allow remote
adapters (running in separate processes or on different hosts) to connect to
the Encre gateway over WebSocket.  Core adapters run in-process and do NOT
use this bridge.

Modules:
    server.py       - WsBridgeServer (accepts remote adapter connections)
    client.py       - GatewayClient (SDK for remote adapters)
    protocol.py     - Wire protocol (GatewayOp, GatewayMessage)
    remote_adapter.py - RemotePlatformAdapter (wraps a WS connection)
"""

from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp
from encre.gateway.ws_bridge.server import WsBridgeServer

__all__ = [
    "GatewayMessage",
    "GatewayOp",
    "WsBridgeServer",
]
