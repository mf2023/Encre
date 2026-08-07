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

"""Module: builtin/bash_io.py

Bash io implementation for the Encre tool system.
"""
import asyncio
import json
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin._shell_manager import BackgroundShellManager


async def _bash_output_execute(**kwargs: Any) -> str:
    """Bash output execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    shell_id = str(kwargs.get("id", "")).strip()
    if not shell_id:
        return "Error: id is required"

    mgr = BackgroundShellManager.instance()

    wait = bool(kwargs.get("wait", False))
    if wait:
        try:
            timeout = max(0.0, min(60.0, float(kwargs.get("wait_seconds", 5.0))))
        except (TypeError, ValueError):
            timeout = 5.0
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            snap = mgr.read_new_output(shell_id)
            if "error" in snap:
                return f"Error: {snap['error']}"
            if snap["stdout"] or snap["stderr"] or not snap["running"]:
                return json.dumps(snap, ensure_ascii=False)
            if asyncio.get_running_loop().time() >= deadline:
                return json.dumps(snap, ensure_ascii=False)
            await asyncio.sleep(0.15)

    snap = mgr.read_new_output(shell_id)
    if "error" in snap:
        return f"Error: {snap['error']}"
    return json.dumps(snap, ensure_ascii=False)


async def _bash_kill_execute(**kwargs: Any) -> str:
    """Bash kill execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    shell_id = str(kwargs.get("id", "")).strip()
    if not shell_id:
        return "Error: id is required"
    force = bool(kwargs.get("force", False))
    result = await BackgroundShellManager.instance().kill(shell_id, force=force)
    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result, ensure_ascii=False)


async def _bash_list_execute(**_kwargs: Any) -> str:
    """Bash list execute.

    Args:
        _kwargs: Description of the _kwargs parameter.
    """
    shells = BackgroundShellManager.instance().list_shells()
    return json.dumps(shells, ensure_ascii=False)


EncreBashOutputTool = build_tool(
    name="bash_output",
    description=(
        "Read new output from a backgrounded shell started via bash with "
        "run_in_background=true. Returns only bytes accumulated since the "
        "last read for that shell id; call repeatedly to stream progress. "
        "With wait=true, blocks up to wait_seconds for new output or for "
        "the shell to exit. "
        "WHEN to use: streaming progress from long-running builds, tests, or "
        "dev servers started in the background. "
        "WHEN NOT to use: for foreground commands (they return directly); "
        "for one-shot commands (use bash without run_in_background). "
        "TIP: Use wait=true for long-running builds/tests so you do not have "
        "to poll repeatedly. "
        "PITFALLS: polling in a tight loop with wait=false returns empty and "
        "burns tokens; output is incremental -- once read, it is not returned "
        "again on the next call."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Shell id returned from bash(run_in_background=true) (required).",
            },
            "wait": {
                "type": "boolean",
                "description": "If true, poll until new bytes arrive or the shell exits (optional, default false).",
            },
            "wait_seconds": {
                "type": "number",
                "description": "Max seconds to wait when wait=true (optional, default 5, capped at 60).",
            },
        },
        "required": ["id"],
    },
    execute=_bash_output_execute,
    intents=["general", "coding"],
    is_concurrency_safe=lambda _: True,
    category="system",
    semantic_type="exec",
)

EncreBashKillTool = build_tool(
    name="bash_kill",
    description=(
        "Stop a backgrounded shell started via bash(run_in_background=true). "
        "By default sends SIGTERM (or terminate on Windows). Pass force=true "
        "to escalate to SIGKILL / hard-terminate after a short grace period. "
        "WHEN to use: dev servers, watchers, or long-running builds that "
        "no longer need to run. "
        "WHEN NOT to use: for foreground commands (they block until done); "
        "for system services (use the service manager); for Docker containers "
        "(use docker stop). "
        "TIP: Try force=false first for a clean shutdown; escalate to "
        "force=true only if the shell ignores SIGTERM. "
        "PITFALLS: force=true skips cleanup hooks and may leave temp files "
        "behind; on Windows, child processes may survive a non-force kill."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Shell id to kill (required).",
            },
            "force": {
                "type": "boolean",
                "description": "Use SIGKILL / hard-terminate instead of graceful SIGTERM (optional, default false).",
            },
        },
        "required": ["id"],
    },
    execute=_bash_kill_execute,
    intents=["general", "coding"],
    is_concurrency_safe=lambda _: True,
    category="system",
    semantic_type="exec",
)

EncreBashListTool = build_tool(
    name="bash_list",
    description=(
        "List all backgrounded shells (running and exited) tracked in this "
        "session. Returns ids, commands, running flags, and exit codes. "
        "WHEN to use: before calling bash_output or bash_kill when you forgot "
        "the shell id; to check whether a background process is still running. "
        "WHEN NOT to use: for foreground commands (they return directly); "
        "for system-wide process listing (use bash with `ps` or `tasklist`). "
        "TIP: Call this first if you lost track of which background shells "
        "are active. "
        "PITFALLS: exited shells remain in the list until the session ends; "
        "shell ids are session-scoped and not portable across sessions."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=_bash_list_execute,
    intents=["general", "coding"],
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
    category="system",
    semantic_type="exec",
)
