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


async def _device_location_execute(**kwargs: Any) -> str:
    from encre.device_context.providers.location import LocationInfoProvider
    p = LocationInfoProvider()
    data = await p.collect_async()
    if data is None:
        return "Location information unavailable on this device."
    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceLocationTool = build_tool(
    name="device_location",
    description=(
        "WHAT: Returns the device's geographic location via the OS-native location "
        "service -- timezone, UTC offset, and GPS coordinates (latitude/longitude) "
        "when available. "
        "WHEN: Use for locale-aware formatting, scheduling actions in the user's "
        "local time, or tagging events with an approximate location. "
        "WHEN NOT: Not for precise tracking or navigation -- accuracy depends on the "
        "OS location service (Wi-Fi/IP-based on laptops, GPS on phones). Do not use "
        "as a geofencing security control. "
        "TIPS: Timezone and UTC offset are almost always available even when GPS is "
        "denied; rely on those when coordinates are absent. "
        "PITFALLS: Returns 'Location information unavailable' when the user has "
        "disabled location services or denied the app permission; coordinates may be "
        "coarse (kilometre-level) on Wi-Fi-only devices."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_device_location_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)