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

import subprocess
from typing import Any, ClassVar

from yim.tools.base import YmiTool


class YmiDockerTool(YmiTool):
    name: ClassVar[str] = "docker"
    description: ClassVar[str] = (
        "Manage Docker containers, images, and compose stacks. "
        "Note: this tool has direct container access and should be used carefully."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["ps", "run", "stop", "logs", "build", "pull", "push", "rm", "rmi", "compose"],
                "description": "Docker command to execute",
            },
            "image_or_container": {
                "type": "string",
                "description": "Image or container name (for run/stop/logs/rm)",
            },
            "options": {
                "type": "string",
                "description": "Additional CLI options and flags",
            },
        },
        "required": ["command"],
    }
    intents: ClassVar[list[str]] = ["coding", "system"]

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "ps")
        image_or_container = kwargs.get("image_or_container", "")
        options = kwargs.get("options", "")

        cmd_parts = ["docker", command]

        if options:
            cmd_parts.extend(options.split())

        if image_or_container:
            cmd_parts.append(image_or_container)

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if result.returncode != 0:
                output += f"\nDocker command exited with code {result.returncode}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Docker command timed out after 300 seconds"
        except FileNotFoundError:
            return "Error: Docker CLI not found. Is Docker installed and in PATH?"
        except Exception as e:
            return f"Error executing docker command: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
