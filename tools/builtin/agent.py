#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

from typing import Any, ClassVar

from yim.tools.base import YmiTool


class YmiAgentTool(YmiTool):
    name: ClassVar[str] = "agent"
    description: ClassVar[str] = "Spawn a sub-agent to complete a task, returning the result"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Instructions for the sub-agent",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of tool names available to the sub-agent",
            },
        },
        "required": ["prompt"],
    }

    _parent_loop: Any = None  # Set by agent during initialization

    @classmethod
    def set_parent_loop(cls, loop: Any) -> None:
        cls._parent_loop = loop

    async def execute(self, **kwargs: Any) -> str:
        prompt = kwargs.get("prompt", "")
        tool_names = kwargs.get("tools", [])

        if self._parent_loop is not None:
            return await self._parent_loop._run_sub_agent(prompt, tool_names)

        from yim.loop import YmiLoop
        from yim.session import YmiSession
        from yim.config import YmiConfig

        config = YmiConfig()
        session = YmiSession(config)
        loop = YmiLoop(config, session)
        return await loop._run_sub_agent(prompt, tool_names)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False