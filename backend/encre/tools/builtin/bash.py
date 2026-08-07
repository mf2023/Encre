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

"""Bash execution — ALL commands go through Rust ``sandbox_execute``.

There is **one** execution path for every bash command:

    Python  bash._bash_execute()
        └── Rust  sandbox::sandbox_execute(command, timeout, workspace)
                ├── Linux (Landlock): fork → landlock_restrict_self → exec
                │     ↳ read/write workspace ONLY, no network, no exec outside
                ├── Windows:         cmd.exe /C with CREATE_NO_WINDOW
                └── macOS:           sh -c with process-group isolation

No Python-level container sandbox, no fallback chain, no duplicate logic.
The Rust function handles platform differences, timeout, and encoding.

When the user configures ``sandbox_enabled=true`` + a workspace, the
loop injects the workspace path into the contextvar below.  The Rust
layer picks it up automatically and applies Landlock when available.
"""

import asyncio
import contextvars
import functools
import json
import sys
import time
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin._encoding import decode_bytes
from encre.tools.builtin._shell_manager import BackgroundShellManager
from encre.tools.builtin._terminal_manager import TerminalSessionManager

# ── Workspace injection (set by the loop per turn) ────────────────
# The active loop injects its workspace path here before each turn.
# The Rust sandbox_execute receives it and applies Landlock when
# available (Linux 5.13+).  On non-Linux this is a no-op.
_current_workspace: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bash_workspace", default=None,
)


def set_workspace(ws: str | None) -> contextvars.Token:
    """Set the sandbox workspace path for the current turn.

    Called by the loop before each ``_run_impl`` turn.  The returned
    token restores the previous value via ``reset_workspace()``.
    """
    return _current_workspace.set(ws)


def reset_workspace(token: contextvars.Token) -> None:
    """Restore the workspace path to its previous value using a token from set_workspace()."""
    _current_workspace.reset(token)


def _get_workspace() -> str | None:
    """Return the current sandbox workspace path (set by the loop per turn)."""
    return _current_workspace.get()


# ── Constants ─────────────────────────────────────────────────────

DEFAULT_MAX_OUTPUT_CHARS = 30_000
_BINARY_PROBE_BYTES = 1024
_BINARY_THRESHOLD = 0.30


# ── Encoding helpers ──────────────────────────────────────────────

def _decode_for_model(value: Any) -> tuple[str, dict[str, Any]]:
    """Best-effort decode of a shell output stream to str + metadata."""
    if value is None:
        return "", {"encoding": "utf-8", "binary": False, "output_bytes": 0}
    if isinstance(value, str):
        raw_bytes = value.encode("utf-8", errors="replace")
    elif isinstance(value, bytes | bytearray | memoryview):
        raw_bytes = bytes(value)
    else:
        return str(value), {"encoding": "utf-8", "binary": False, "output_bytes": 0}
    n = len(raw_bytes)
    if n == 0:
        return "", {"encoding": "utf-8", "binary": False, "output_bytes": 0}
    sample = raw_bytes[:_BINARY_PROBE_BYTES]
    non_printable = sum(
        1 for b in sample if b < 0x09 or (0x0E <= b <= 0x1F) or b == 0x7F
    )
    binary = (non_printable / max(1, len(sample))) > _BINARY_THRESHOLD
    return decode_bytes(raw_bytes), {"encoding": "utf-8", "binary": binary, "output_bytes": n}


def _truncate(text: str, limit: int) -> tuple[str, bool, int]:
    """Truncate text to limit chars, returning (truncated_text, was_truncated, omitted_count)."""
    if limit <= 0 or len(text) <= limit:
        return text, False, 0
    return (
        text[:limit] + f"\n...(truncated, {len(text) - limit} chars omitted)",
        True,
        len(text) - limit,
    )


# ── Result envelope ───────────────────────────────────────────────

def _envelope(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    cwd: str | None,
    elapsed_ms: int,
    stdout_meta: dict[str, Any],
    stderr_meta: dict[str, Any],
    max_chars: int,
) -> str:
    """Build the model-facing JSON envelope (same shape as Claude Code / Codex)."""
    stdout_clean, stdout_truncated, stdout_saved = _truncate(stdout, max_chars)
    stderr_clean, stderr_truncated, stderr_saved = _truncate(stderr, max_chars)
    success = exit_code == 0
    summary = (
        f"command exited with code {exit_code}"
        if not success
        else "command succeeded"
    )
    if stdout_truncated or stderr_truncated:
        summary += (
            f" (output truncated: {stdout_saved + stderr_saved} chars omitted; "
            "raise max_output_chars to see more)"
        )
    if stdout_meta.get("binary") or stderr_meta.get("binary"):
        summary += " [binary stream detected -- decoded with errors=replace]"
    envelope = {
        "success": success,
        "exit_code": exit_code,
        "command": command,
        "cwd": cwd or "",
        "elapsed_ms": elapsed_ms,
        "stdout": stdout_clean,
        "stderr": stderr_clean,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_bytes": stdout_meta.get("output_bytes", 0),
        "stderr_bytes": stderr_meta.get("output_bytes", 0),
        "stdout_binary": stdout_meta.get("binary", False),
        "stderr_binary": stderr_meta.get("binary", False),
        "summary": summary,
    }
    return json.dumps(envelope, ensure_ascii=False)


# ── Main execute function ─────────────────────────────────────────

async def _bash_execute(**kwargs: Any) -> str:
    """Execute a shell command. Returns a JSON envelope with stdout/stderr/exit_code."""
    command = kwargs.get("command", "")
    if not command:
        return json.dumps({
            "success": False,
            "error": "command is required",
            "summary": "no command provided",
        }, ensure_ascii=False)

    terminal = str(kwargs.get("terminal", "auto")).lower()
    cwd = kwargs.get("cwd") or None
    try:
        timeout = int(kwargs.get("timeout", 120))
    except (TypeError, ValueError):
        timeout = 120
    max_chars = _resolve_max_chars(kwargs)

    # Background shells still use BackgroundShellManager (Python async)
    if bool(kwargs.get("run_in_background", False)):
        mgr = BackgroundShellManager.instance()
        try:
            rec = await mgr.spawn(command, cwd=cwd)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"spawn failed: {exc}",
                "summary": "background spawn failed",
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "id": rec.id,
            "running": True,
            "command": rec.command,
            "cwd": rec.cwd,
            "started_at": rec.started_at,
            "terminal": terminal,
            "summary": f"background shell started as {rec.id}",
            "hint": "Use bash_output with this id to read output, bash_kill to stop.",
        }, ensure_ascii=False)

    # ── Persistent terminal session path ─────────────────────────
    # When a specific terminal type is given, use the session manager
    # so state (cwd, env, shell state) carries across calls.
    if terminal != "auto":
        started = time.monotonic()
        mgr = TerminalSessionManager.instance()
        try:
            result = await mgr.execute(terminal, command, cwd=cwd, timeout=timeout)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"terminal execution failed: {exc}",
                "command": command,
                "terminal": terminal,
                "cwd": cwd or "",
                "summary": "terminal execution error",
            }, ensure_ascii=False)

        elapsed_ms = result.get("elapsed_ms", 0)
        stdout_text, stdout_meta = _decode_for_model(result.get("stdout", ""))
        stderr_text, stderr_meta = _decode_for_model(result.get("stderr", ""))

        return _envelope(
            command=command,
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=result.get("exit_code", 0),
            cwd=cwd,
            elapsed_ms=elapsed_ms,
            stdout_meta=stdout_meta,
            stderr_meta=stderr_meta,
            max_chars=max_chars,
        )

    # ── Legacy one-shot path (auto terminal) via Rust sandbox ───
    from encre import native as _native

    started = asyncio.get_running_loop().time()
    workspace = _get_workspace()
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            functools.partial(
                _native.sandbox_execute,
                command,
                timeout,
                workspace,
            ),
        )
    except Exception as exc:
        return json.dumps({
            "success": False,
            "error": f"execution failed: {exc}",
            "command": command,
            "cwd": cwd or "",
            "summary": "execution error",
        }, ensure_ascii=False)

    elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)
    stdout_text, stdout_meta = _decode_for_model(result.get("stdout", ""))
    stderr_text, stderr_meta = _decode_for_model(result.get("stderr", ""))
    exit_code = int(result.get("exit_code", -1))

    return _envelope(
        command=command,
        stdout=stdout_text,
        stderr=stderr_text,
        exit_code=exit_code,
        cwd=cwd,
        elapsed_ms=elapsed_ms,
        stdout_meta=stdout_meta,
        stderr_meta=stderr_meta,
        max_chars=max_chars,
    )


def _resolve_max_chars(kwargs: dict[str, Any]) -> int:
    """Extract and validate max_output_chars from kwargs, returning the default (30000) if absent or invalid."""
    raw = kwargs.get("max_output_chars")
    if raw is None:
        return DEFAULT_MAX_OUTPUT_CHARS
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_OUTPUT_CHARS
    return v if v >= 0 else 0


# ── Tool definition ───────────────────────────────────────────────

EncreBashTool = build_tool(
    name="bash",
    description=(
        "Execute a shell command in a sandboxed terminal. Use this only when "
        "no dedicated tool fits the task. Prefer dedicated tools first:\n\n"
        "| Instead of bash | Use this |\n"
        "|---|---|\n"
        "| cat / read a file | file_read |\n"
        "| write &#8594; file (new/overwrite) | file_write |\n"
        "| edit / modify a file | file_edit |\n"
        "| grep / search code | grep |\n"
        "| ls / find a file | glob |\n"
        "| curl / fetch URL | web_fetch |\n"
        "| web search | web_search |\n"
        "| git commands | git |\n"
        "| npm install / pip | native args; bash only for build scripts |\n"
        "| docker | docker |\n"
        "| pytest / run tests | test_runner |\n"
        "| lint / format | lint_format |\n"
        "| database queries | database |\n"
        "| multi-step workflows | workflow |\n"
        "| cron / scheduled tasks | cron_create |\n"
        "| PDF | pdf |\n"
        "| CSV / spreadsheets | spreadsheet |\n"
        "| images | image |\n"
        "| browser automation | browser |\n"
        "| Jupyter notebooks | notebook |\n"
        "\n"
        "**terminal** -- choose which shell to run in (required):\n"
        "- **auto** -- platform default (cmd on Windows, bash on Unix; one-shot)\n"
        "- **powershell** -- persistent PowerShell (Windows) session\n"
        "- **pwsh** -- persistent PowerShell Core (cross-platform) session\n"
        "- **cmd** -- persistent cmd.exe session (Windows)\n"
        "- **bash** -- persistent Bash session (Git Bash on Windows)\n"
        "- **python** -- persistent Python interactive REPL\n"
        "- **node** -- persistent Node.js REPL\n"
        "- **irb** -- persistent Ruby (irb) REPL\n"
        "- **julia** -- persistent Julia REPL\n"
        "- **lua** -- persistent Lua REPL\n"
        "- **php** -- persistent PHP interactive shell\n"
        "- **R** -- persistent R REPL\n"
        "\n"
        "Persistent terminals keep state (cwd, env) across calls until the "
        "turn ends. Use run_in_background=true for dev servers / watchers. "
        "Returns JSON: {success, exit_code, stdout, stderr, stdout_truncated, "
        "stderr_truncated, elapsed_ms, summary}. "
        "TIP: Use a persistent terminal (e.g. terminal='bash') when later "
        "commands depend on cwd/env changes from earlier ones. "
        "AVOID: Long-running commands without run_in_background=true -- they "
        "block the turn and may hit the timeout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (required).",
            },
            "terminal": {
                "type": "string",
                "description": (
                    "Which terminal to run in (required): auto, powershell, "
                    "pwsh, cmd, bash, python, node, irb, julia, lua, php, R. "
                    "'auto' uses the Rust sandbox (one-shot). Specific "
                    "terminals create persistent sessions that preserve cwd/env "
                    "across calls."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (optional, default 120). Ignored in background mode.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command (optional, absolute or relative).",
            },
            "run_in_background": {
                "type": "boolean",
                "description": (
                    "If true, spawn as a backgrounded shell and return a shell "
                    "id. Use bash_output to read output and bash_kill to stop "
                    "it (optional, default false)."
                ),
            },
            "dangerous": {
                "type": "boolean",
                "description": "Explicitly mark the command as dangerous to bypass safety checks (optional).",
            },
            "max_output_chars": {
                "type": "integer",
                "description": (
                    "Max chars per stream (stdout/stderr). Truncated output "
                    "gets a '...(truncated, N chars omitted)' marker plus "
                    "stdout_truncated/stderr_truncated flags. Default 30000; "
                    "set 0 for unlimited."
                ),
            },
        },
        "required": ["command", "terminal"],
    },
    execute=_bash_execute,
    intents=["general", "coding", "data"],
    category="shell",
    triggers=["shell", "terminal", "command", "run", "execute", "cmd", "powershell", "npm", "pip", "cargo", "bash"],
    semantic_type="exec",
    is_destructive=True,
    cost_level="high",
    retryability="guarded",
    safe_fallback="Prefer a dedicated tool, or inspect command preconditions and the current workspace state before retrying bash.",
    get_effective_path=lambda self, args: args.get("command") or None,
)
