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



import asyncio
from typing import Any

from encre.tools.base import build_tool


async def _docker_execute(**kwargs: Any) -> str:
    command = kwargs.get("command", "ps")
    image_or_container = kwargs.get("image_or_container", "")
    options = kwargs.get("options", "")

    cmd_parts = ["docker", command]

    if options:
        cmd_parts.extend(options.split())

    if image_or_container:
        cmd_parts.append(image_or_container)

    try:
        from encre.tools.builtin._suppress_window import (
            hidden_subprocess_kwargs as _hidden,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_hidden(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=300
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: Docker command timed out after 300 seconds"
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if stderr:
            err_text = stderr.decode("utf-8", errors="replace")
            if err_text:
                output += "\n" + err_text
        if proc.returncode and proc.returncode != 0:
            output += f"\nDocker command exited with code {proc.returncode}"
        return output or "(no output)"
    except FileNotFoundError:
        return "Error: Docker CLI not found. Is Docker installed and in PATH?"
    except Exception as e:
        return f"Error executing docker command: {e}"


EncreDockerTool = build_tool(
    name="docker",
    description=(
        "Manage Docker containers, images, and compose stacks. "
        "Note: this tool has direct container access and should be used carefully."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["ps", "run", "stop", "logs", "build", "pull", "push", "rm", "rmi", "compose"],  # noqa: E501
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
    },
    execute=_docker_execute,
    intents=["coding", "system"],
    is_concurrency_safe=lambda data: data.get("command") in ("ps", "logs"),
)
