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


async def _device_battery_execute(**kwargs: Any) -> str:
    from encre.device_context.providers.battery import BatteryInfoProvider
    p = BatteryInfoProvider()
    data = await p.collect_async()
    if data is None:
        return "No battery detected on this device."
    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceBatteryTool = build_tool(
    name="device_battery",
    description=(
        "WHAT: Returns the current battery state -- charge percentage, whether AC "
        "power is plugged in, and estimated seconds remaining (when the OS provides "
        "it). "
        "WHEN: Use to decide whether to defer expensive work, gate long-running "
        "tasks, or warn the user before a critical shutdown. "
        "WHEN NOT: Not for measuring power consumption over time -- use a profiling "
        "tool. On desktops without a UPS the call returns 'No battery detected'. "
        "TIPS: Poll periodically rather than in a tight loop; battery state changes "
        "slowly and frequent reads add no value. "
        "PITFALLS: 'seconds remaining' is an estimate and can jump when the load "
        "changes; treat it as advisory, not exact."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_device_battery_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)