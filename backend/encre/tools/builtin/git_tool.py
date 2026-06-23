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


async def _git_execute(**kwargs: Any) -> str:
    command = kwargs.get("command", "status")
    repo_path = kwargs.get("repo_path", ".")
    args = kwargs.get("args", "")

    cmd_parts = ["git", "-C", repo_path, command]

    if args:
        cmd_parts.extend(args.split())

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
                proc.communicate(), timeout=120
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: Git command timed out after 120 seconds"
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if stderr:
            err_text = stderr.decode("utf-8", errors="replace")
            if err_text:
                output += "\n" + err_text
        if proc.returncode and proc.returncode != 0:
            output += f"\nGit command exited with code {proc.returncode}"
        return output or "(no output)"
    except FileNotFoundError:
        return "Error: Git CLI not found. Is Git installed and in PATH?"
    except Exception as e:
        return f"Error executing git command: {e}"


EncreGitTool = build_tool(
    name="git",
    description="Full git operations: commit, branch, push, pull, log, diff, status",
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["status", "diff", "log", "branch", "commit", "add", "push", "pull", "stash", "checkout", "clone"],
                "description": "Git subcommand to execute",
            },
            "repo_path": {
                "type": "string",
                "description": "Path to the git repository (default: current directory)",
            },
            "args": {
                "type": "string",
                "description": "Additional arguments to pass to the git command",
            },
        },
        "required": ["command"],
    },
    execute=_git_execute,
    intents=["coding"],
    is_concurrency_safe=lambda data: data.get("command") in ("status", "diff", "log", "branch", "stash"),
)
