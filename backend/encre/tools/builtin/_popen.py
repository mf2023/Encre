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

"""Single source of truth for ALL subprocess spawning in Encre.

Instead of monkey-patching the standard library, this module provides
explicit wrappers that callers use directly.  This avoids the debugging
and maintenance risks of global monkey-patches.

Usage::

    from encre.tools.builtin._popen import create_subprocess

    proc = await create_subprocess("rg", "pattern")
    stdout, stderr = await proc.communicate()

    # Or for synchronous subprocess calls:
    proc = create_subprocess_sync("git", "status")
    stdout, stderr = proc.communicate()

The wrappers automatically inject platform-specific window-suppression
flags (``CREATE_NO_WINDOW`` on Windows, ``start_new_session`` on Unix).
"""

import asyncio
import os
import subprocess
from typing import Any

# ── Platform flags ─────────────────────────────────────────────────────

if os.name == "nt":
    _CREATION_FLAGS: int = 0x08000000
    _STARTUPINFO: subprocess.STARTUPINFO | None = subprocess.STARTUPINFO(
        dwFlags=subprocess.STARTF_USESHOWWINDOW,
        wShowWindow=subprocess.SW_HIDE,
    )
else:
    _CREATION_FLAGS = 0
    _STARTUPINFO = None


def _inject_creationflags(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Inject creationflags.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    if os.name == "nt":
        kwargs.setdefault("creationflags", _CREATION_FLAGS)
        if _STARTUPINFO is not None:
            kwargs.setdefault("startupinfo", _STARTUPINFO)
    else:
        kwargs.setdefault("start_new_session", True)
    return kwargs


async def create_subprocess_exec(
    *args: Any, **kwargs: Any
) -> asyncio.subprocess.Process:
    """Create subprocess exec.

    Args:
        args: Description of the args parameter.
        kwargs: Description of the kwargs parameter.
    """
    _inject_creationflags(kwargs)
    return await asyncio.create_subprocess_exec(*args, **kwargs)


def create_subprocess_run(
    cmd_parts: list[str],
    timeout: float | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Create subprocess run.

    Args:
        cmd_parts: Description of the cmd_parts parameter.
        timeout: Description of the timeout parameter.
        kwargs: Description of the kwargs parameter.
    """
    _inject_creationflags(kwargs)
    return subprocess.run(cmd_parts, timeout=timeout, **kwargs)
