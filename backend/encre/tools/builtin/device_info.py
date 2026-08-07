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


async def _device_info_execute(**kwargs: Any) -> str:
    detail = kwargs.get("detail", False)
    from encre.device_context.providers.hardware import HardwareInfoProvider
    from encre.device_context.providers.gpu import GPUInfoProvider
    from encre.device_context.providers.platform_ import PlatformInfoProvider

    data: dict[str, Any] = {}

    platform_p = PlatformInfoProvider()
    hw = HardwareInfoProvider()
    gpu = GPUInfoProvider()

    data["platform"] = await platform_p.collect_async()
    data["hardware"] = await hw.collect_async()
    data["gpu"] = await gpu.collect_async()

    if not detail:
        hw_d = data.get("hardware") or {}
        cpu = hw_d.get("cpu", {})
        mem = hw_d.get("memory", {})
        disk = hw_d.get("disk", {})
        parts = disk.get("partitions", [])
        total = sum(p.get("total_gb", 0) for p in parts)
        cwd = disk.get("current_working_directory", "")
        return json.dumps({
            "cpu": f"{cpu.get('model', '')} ({cpu.get('logical_cores', '')} cores)",
            "ram": f"{mem.get('total_gb', '')} GB",
            "disk": f"{total:.0f} GB total across {len(parts)} partition(s)",
            "current_directory": cwd,
        }, ensure_ascii=False)

    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceInfoTool = build_tool(
    name="device_info",
    description=(
        "WHAT: Returns system hardware information -- CPU model and core count, "
        "total RAM, aggregate disk capacity, and the current working directory "
        "(or full GPU/partition specs when detail=true). "
        "WHEN: Use to answer 'what kind of machine am I on', to size workloads to "
        "the available RAM/CPU, or to verify disk space before large writes. "
        "WHEN NOT: Do not use for live metrics like CPU load or free RAM -- use a "
        "monitoring tool instead. Network and display details live in device_network "
        "and device_display respectively. "
        "TIPS: Start with the default summary (detail=false) for a one-line overview; "
        "set detail=true only when you need GPU names or per-partition breakdowns. "
        "PITFALLS: GPU info may be empty when no driver is exposed, and disk totals "
        "aggregate only visible partitions (network mounts are excluded)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "detail": {
                "type": "boolean",
                "description": (
                    "When true, return the full hardware report including GPU name, "
                    "per-partition disk stats, and CPU flags. When false (default), "
                    "return a short summary with one line each for CPU, RAM, disk, "
                    "and the current working directory."
                ),
            },
        },
    },
    execute=_device_info_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)