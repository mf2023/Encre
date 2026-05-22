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
from yim.native import sandbox_execute as _native_sandbox


class YmiBashTool(YmiTool):
    name: ClassVar[str] = "bash"
    description: ClassVar[str] = (
        "Execute a shell command and get the output. "
        "Commands are analyzed for safety before execution."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120)",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command",
            },
            "dangerous": {
                "type": "boolean",
                "description": "Explicitly mark as dangerous to bypass safety checks",
            },
        },
        "required": ["command"],
    }
    intents: ClassVar[list[str]] = ["general", "coding", "data"]

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 120)

        try:
            result = _native_sandbox(command, timeout)
            output = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exit_code", 0)
            if stderr:
                if output:
                    output += "\n"
                output += stderr
            if exit_code != 0:
                output += f"\nCommand exited with code {exit_code}"
            return output
        except Exception as e:
            return f"Error executing command: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False