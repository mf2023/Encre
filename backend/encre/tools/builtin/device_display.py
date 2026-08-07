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


async def _device_display_execute(**kwargs: Any) -> str:
    from encre.device_context.providers.display import DisplayInfoProvider
    p = DisplayInfoProvider()
    data = await p.collect_async()
    if data is None:
        return "Display information unavailable on this device."
    return json.dumps(data, ensure_ascii=False, default=str)


EncreDeviceDisplayTool = build_tool(
    name="device_display",
    description=(
        "WHAT: Lists all connected displays with resolution, refresh rate, DPI/scale, "
        "and primary/secondary layout information. "
        "WHEN: Use to position windows, choose screenshot regions, validate "
        "multi-monitor setups, or detect HiDPI scaling before desktop automation. "
        "WHEN NOT: For capturing pixels use the 'desktop' or 'computer_use' "
        "screenshot actions instead -- this tool returns metadata only, not images. "
        "TIPS: Pair with the 'desktop' screenshot output (which already includes DPI "
        "scale) to translate between physical and logical coordinates on HiDPI "
        "displays. "
        "PITFALLS: Disconnected or sleeping monitors may be omitted; virtual displays "
        "(RDP, headless sessions) can report zero resolution."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_device_display_execute,
    intents=["general", "system"],
    category="system",
    semantic_type="read",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)