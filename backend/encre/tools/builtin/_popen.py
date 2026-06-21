#!/usr/bin/env python3

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

from __future__ import annotations

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
    _inject_creationflags(kwargs)
    return await asyncio.create_subprocess_exec(*args, **kwargs)


def create_subprocess_run(
    cmd_parts: list[str],
    timeout: float | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    _inject_creationflags(kwargs)
    return subprocess.run(cmd_parts, timeout=timeout, **kwargs)
