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

"""Embedded-terminal domain handlers: spawn / write / kill.

Manages the per-connection PTY-ish subprocess sessions exposed to the
desktop terminal panel.  Extracted verbatim from ``encre.transport.ws``
(architecture refactor Stage 3 / Task 5.2); behaviour is unchanged, only
the layout moved.  Outer-loop ``continue`` statements of the original
dispatch chain became ``return`` inside the extracted methods.
"""

import asyncio
import os
from typing import Any

from encre.server.protocol import (
    ClientTerminalKill,
    ClientTerminalListShells,
    ClientTerminalResize,
    ClientTerminalSpawn,
    ClientTerminalWrite,
)
from encre.tools.builtin._encoding import decode_bytes


class TerminalHandlers:
    """Embedded terminal lifecycle handlers (spawn/write/resize/kill)."""

    async def _h_terminal_list_shells(self, ws: Any, msg: ClientTerminalListShells) -> None:
        is_windows = os.name == "nt"
        shells = []
        if is_windows:
            shells.append({"name": "PowerShell", "path": "powershell.exe", "args": []})
            if os.path.isfile("C:/Program Files/PowerShell/7/pwsh.exe"):
                shells.append({"name": "pwsh", "path": "pwsh.exe", "args": []})
            shells.append({"name": "cmd", "path": "cmd.exe", "args": []})
            if os.path.isfile("C:/Windows/System32/wsl.exe"):
                shells.append({"name": "WSL", "path": "wsl.exe", "args": []})
        else:
            for sp in ["/bin/bash", "/bin/zsh", "/bin/sh"]:
                if os.path.isfile(sp):
                    shells.append({"name": os.path.basename(sp), "path": sp, "args": []})
            import shutil as _shutil
            for exe in ["pwsh", "irb", "julia", "lua", "php", "R"]:
                resolved = _shutil.which(exe)
                if resolved:
                    shells.append({"name": exe, "path": resolved, "args": []})
        await self._send(ws, "terminal_shells", shells=shells)

    async def _h_terminal_spawn(self, ws: Any, msg: ClientTerminalSpawn) -> None:
        shell = msg.shell or ("powershell.exe" if os.name == "nt" else "/bin/bash")
        shell_args = msg.shell_args or []
        try:
            from encre.capabilities.process import (
                hidden_subprocess_kwargs,
            )
            term_kwargs = hidden_subprocess_kwargs()
            proc = await asyncio.create_subprocess_exec(
                shell, *shell_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **term_kwargs,
            )
        except Exception as e:
            await self._send(ws, "error", message=f"Terminal spawn failed: {e}", code="terminal_error")
            return
        tid = self._term_seq
        self._term_seq += 1
        term_info: dict[str, Any] = {"proc": proc, "buf": b""}
        self._term_sessions[tid] = term_info
        await self._send(ws, "terminal_spawned", id=tid)

        async def _read_stdout(*, proc=proc, term_info=term_info, tid=tid):
            try:
                while True:
                    data = await proc.stdout.read(4096)
                    if not data:
                        break
                    term_info["buf"] += data
                    try:
                        decoded = decode_bytes(data)
                    except Exception:
                        decoded = data.decode("latin-1", errors="replace")
                    await self._send(ws, "terminal_data", id=tid, data=decoded)
            except Exception:
                pass
            finally:
                self._term_sessions.pop(tid, None)
                await self._send(ws, "terminal_data", id=tid, data="")

        _t = asyncio.ensure_future(_read_stdout())
        self._tasks.add(_t)

    async def _h_terminal_write(self, ws: Any, msg: ClientTerminalWrite) -> None:
        tinfo = self._term_sessions.get(msg.id)
        if tinfo is None:
            await self._send(ws, "error", message="Terminal not found", code="terminal_not_found")
            return
        proc = tinfo["proc"]
        if proc.stdin and not proc.stdin.is_closed():
            try:
                proc.stdin.write(msg.data.encode("utf-8", errors="replace"))
                await proc.stdin.drain()
            except Exception:
                pass

    async def _h_terminal_resize(self, ws: Any, msg: ClientTerminalResize) -> None:
        pass

    async def _h_terminal_kill(self, ws: Any, msg: ClientTerminalKill) -> None:
        tinfo = self._term_sessions.get(msg.id)
        if tinfo is None:
            return
        proc = tinfo["proc"]
        if proc.returncode is None:
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            except Exception:
                pass
        self._term_sessions.pop(msg.id, None)
