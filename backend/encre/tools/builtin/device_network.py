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

import json
from typing import Any

from encre.tools.base import build_tool


async def _device_network_execute(**kwargs: Any) -> str:
    from encre.device_context.providers.network import NetworkInfoProvider
    p = NetworkInfoProvider()
    data = await p.collect_async()
    if data is None:
        return "Network information unavailable on this device."
    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceNetworkTool = build_tool(
    name="device_network",
    description=(
        "WHAT: Reports live network interface information -- hostname, IPv4/IPv6 "
        "addresses, MAC addresses, link speed, and per-interface connection state. "
        "WHEN: Use when diagnosing connectivity, picking a bind address, or "
        "inventorying the host's network adapters. "
        "WHEN NOT: Not for measuring bandwidth or latency (run a speed test or "
        "ping instead) and not for managing firewall rules -- use the OS network "
        "CLI for those. "
        "TIPS: Multiple interfaces (Ethernet, Wi-Fi, virtual) are returned together; "
        "filter client-side by interface name or by the 'is_up' flag. "
        "PITFALLS: Returns 'Network information unavailable' on hosts where the "
        "provider cannot enumerate adapters; MAC addresses may be hidden on hardened "
        "systems and virtual adapters can clutter the list."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_device_network_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)