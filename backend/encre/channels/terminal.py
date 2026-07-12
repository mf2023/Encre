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

"""Encre agent channels: interactive terminal REPL.

Implements :class:`TerminalChannel`, a stdin/stdout REPL used for headless /
CI smoke tests.  It is disabled when ``ENCRE_DESKTOP_ONLY`` is set (see the
class docstring) in favour of the desktop UI.  Slash commands such as
``/new`` and ``/exit`` are parsed by
:func:`encre.channels.slash_commands.parse_terminal_slash_command`.
"""

import asyncio
import sys

from encre.channels.base import Channel, EventRouter
from encre.channels.slash_commands import parse_terminal_slash_command
from encre.utils.types import Finish, TextDelta, ToolResult


class TerminalChannel(Channel):
    """Interactive terminal REPL channel (stdin/stdout).

    .. deprecated::
        The Encre project ships a desktop-only presentation layer
        (Electron + React).  This terminal REPL is kept for headless
        server deployments and CI smoke tests but is not a
        user-facing surface.  Running ``start()`` will print a
        notice and exit without entering the REPL loop when the
        ``ENCRE_DESKTOP_ONLY`` environment variable is set.

    Each connected terminal session maintains a persistent agent session
    for conversation continuity. Special commands:
      /new, /clear  - start a fresh session
      /exit, /quit  - quit the terminal channel
    """

    name = "terminal"

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self, router: EventRouter) -> None:
        import os
        if os.environ.get("ENCRE_DESKTOP_ONLY", "").strip().lower() in ("1", "true", "yes"):
            print(
                "Encre: terminal channel is disabled in desktop-only mode. "
                "Use the desktop UI to interact with the agent.",
                flush=True,
            )
            return
        self._running = True
        loop = asyncio.get_event_loop()

        info = router.session_manager.create_session()
        session_id = info.session_id

        print(f"iClaw terminal -- session {session_id[:8]}", flush=True)
        print("Type /new for fresh session, /exit to quit", flush=True)

        while self._running:
            try:
                prompt = await loop.run_in_executor(None, sys.stdin.readline)
                if not prompt:
                    self._running = False
                    break
                prompt = prompt.strip()
                if not prompt:
                    continue

                slash_command = parse_terminal_slash_command(prompt)
                if slash_command:
                    if slash_command.name == "exit":
                        self._running = False
                        break
                    if slash_command.name == "new":
                        router.session_manager.remove_session(session_id)
                        info = router.session_manager.create_session()
                        session_id = info.session_id
                        print(f"[new session: {session_id[:8]}]", flush=True)
                    continue

                async for event in router.submit_stream(
                    self.name, prompt, session_id=session_id
                ):
                    if isinstance(event, TextDelta) and event.text:
                        sys.stdout.write(event.text)
                        sys.stdout.flush()
                    elif isinstance(event, ToolResult):
                        preview = event.content[:200].replace("\n", " ")
                        sys.stdout.write(f"\n[Tool: {preview}]\n")
                        sys.stdout.flush()
                    elif isinstance(event, Finish):
                        if event.reason not in ("stop",):
                            sys.stdout.write(f"\n[{event.reason}]\n")
                        else:
                            sys.stdout.write("\n")
                        sys.stdout.flush()
            except EOFError:
                self._running = False
                break
            except Exception:
                continue

        # Clean up terminal session
        router.session_manager.remove_session(session_id)

    async def stop(self) -> None:
        self._running = False
