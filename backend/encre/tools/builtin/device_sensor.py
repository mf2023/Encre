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


async def _device_sensor_execute(**kwargs: Any) -> str:
    from encre.device_context.providers.sensors import SensorInfoProvider
    p = SensorInfoProvider()
    data = await p.collect_async()
    if data is None:
        return "No sensor data available on this device."
    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceSensorTool = build_tool(
    name="device_sensor",
    description=(
        "WHAT: Returns live readings from device sensors such as accelerometer, "
        "gyroscope, magnetometer, and ambient light when the hardware exposes them. "
        "WHEN: Use on laptops, tablets, or phones to detect orientation, motion, or "
        "ambient lighting for adaptive behaviour. "
        "WHEN NOT: Not applicable on most desktop servers or VMs that lack sensor "
        "hardware -- the call returns 'No sensor data available'. "
        "TIPS: Treat readings as instantaneous snapshots; sample repeatedly if you "
        "need trends or gesture detection. "
        "PITFALLS: Availability and units vary widely by platform and driver; some "
        "sensors may report zeros or stale values when the OS has suspended them."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_device_sensor_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)