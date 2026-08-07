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

"""SSH / remote command and file-transfer tool.

Runs commands on and transfers files to/from remote hosts over SSH/SCP using
configured credentials or an agent.
"""

import asyncio
import contextlib
import json
import os
import tempfile
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin._encoding import decode_bytes


def _ssh_base_args(kwargs: dict[str, Any]) -> list[str]:
    """Ssh base args.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    host = kwargs.get("host", "")
    port = kwargs.get("port", 22)
    user = kwargs.get("user", "root")
    key_file = kwargs.get("key_file", "")
    password = kwargs.get("password", "")

    args = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]

    if port and port != 22:
        args.extend(["-p", str(port)])
    if key_file:
        args.extend(["-i", key_file])

    if password:
        args = ["sshpass", "-p", password, *args]

    args.append(f"{user}@{host}")
    return args


async def _ssh_execute(**kwargs: Any) -> str:
    """Ssh execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "exec")
    host = kwargs.get("host", "")
    if not host:
        return "Error: 'host' is required."

    # ── Execute remote command ────────────────────────────────────
    if action == "exec":
        command = kwargs.get("command", "")
        if not command:
            return "Error: 'command' is required for exec action."
        timeout = kwargs.get("timeout", 60)

        args = [*_ssh_base_args(kwargs), command]
        try:
            from encre.tools.builtin._suppress_window import (
                hidden_subprocess_kwargs as _hidden,
            )
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: SSH command timed out after {timeout}s"
            out = decode_bytes(stdout) if stdout else ""
            if stderr:
                err = decode_bytes(stderr)
                if err:
                    out += f"\n[stderr]\n{err}"
            exit_code = proc.returncode if proc.returncode is not None else -1
            result = {"exit_code": exit_code, "stdout": out.strip()}
            return json.dumps(result, indent=2)
        except FileNotFoundError:
            return "Error: ssh (or sshpass) not found in PATH"
        except Exception as e:
            return f"Error executing SSH command: {e}"

    # ── Upload file via SCP ───────────────────────────────────────
    elif action == "upload":
        local_path = kwargs.get("local_path", "")
        remote_path = kwargs.get("remote_path", "")
        if not local_path or not remote_path:
            return "Error: 'local_path' and 'remote_path' are required for upload."

        if not os.path.isfile(local_path):
            return f"Error: Local file not found: {local_path}"

        port = kwargs.get("port", 22)
        user = kwargs.get("user", "root")
        key_file = kwargs.get("key_file", "")
        password = kwargs.get("password", "")

        scp_args = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]
        if port and port != 22:
            scp_args.extend(["-P", str(port)])
        if key_file:
            scp_args.extend(["-i", key_file])

        if password:
            scp_args = ["sshpass", "-p", password, *scp_args]

        scp_args.extend([local_path, f"{user}@{host}:{remote_path}"])

        try:
            from encre.tools.builtin._suppress_window import (
                hidden_subprocess_kwargs as _hidden,
            )
            proc = await asyncio.create_subprocess_exec(
                *scp_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: SCP upload timed out after 120s"
            if proc.returncode != 0:
                err = decode_bytes(stderr) if stderr else ""
                return f"SCP upload failed (exit {proc.returncode}): {err[:500]}"
            return f"File uploaded: {local_path} -> {user}@{host}:{remote_path}"
        except FileNotFoundError:
            return "Error: scp (or sshpass) not found in PATH"
        except Exception as e:
            return f"Error during SCP upload: {e}"

    # ── Download file via SCP ─────────────────────────────────────
    elif action == "download":
        remote_path = kwargs.get("remote_path", "")
        local_path = kwargs.get("local_path", "")
        if not remote_path:
            return "Error: 'remote_path' is required for download."
        if not local_path:
            local_path = os.path.basename(remote_path)

        port = kwargs.get("port", 22)
        user = kwargs.get("user", "root")
        key_file = kwargs.get("key_file", "")
        password = kwargs.get("password", "")

        scp_args = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]
        if port and port != 22:
            scp_args.extend(["-P", str(port)])
        if key_file:
            scp_args.extend(["-i", key_file])

        if password:
            scp_args = ["sshpass", "-p", password, *scp_args]

        scp_args.extend([f"{user}@{host}:{remote_path}", local_path])

        try:
            from encre.tools.builtin._suppress_window import (
                hidden_subprocess_kwargs as _hidden,
            )
            proc = await asyncio.create_subprocess_exec(
                *scp_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: SCP download timed out after 120s"
            if proc.returncode != 0:
                err = decode_bytes(stderr) if stderr else ""
                return f"SCP download failed (exit {proc.returncode}): {err[:500]}"
            local_abs = os.path.abspath(local_path)
            return f"File downloaded: {user}@{host}:{remote_path} -> {local_abs}"
        except FileNotFoundError:
            return "Error: scp (or sshpass) not found in PATH"
        except Exception as e:
            return f"Error during SCP download: {e}"

    # ── Test SSH connection ──────────────────────────────────────
    elif action == "ping":
        args = [*_ssh_base_args(kwargs), "echo", "pong"]
        try:
            from encre.tools.builtin._suppress_window import (
                hidden_subprocess_kwargs as _hidden,
            )
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return f"SSH connection to {host} timed out"
            if proc.returncode == 0:
                return f"SSH connection to {user}@{host}:{port} OK"
            err = decode_bytes(stderr) if stderr else ""
            return f"SSH connection to {host} failed (exit {proc.returncode}): {err[:300]}"
        except FileNotFoundError:
            return "Error: ssh not found in PATH"
        except Exception as e:
            return f"Error testing SSH connection: {e}"

    # ── Run script from content ───────────────────────────────────
    elif action == "script":
        content = kwargs.get("content", "")
        if not content:
            return "Error: 'content' is required for script action."
        timeout = kwargs.get("timeout", 120)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, encoding="utf-8") as f:
            f.write("#!/bin/bash\nset -e\n")
            f.write(content)
            f.flush()
            script_path = f.name

        try:
            remote_path = f"/tmp/_encre_script_{os.getpid()}.sh"

            from encre.tools.builtin._suppress_window import (
                hidden_subprocess_kwargs as _hidden,
            )

            cat_proc = await asyncio.create_subprocess_exec(
                *_ssh_base_args(kwargs), f"cat > {remote_path} && chmod +x {remote_path}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            _cat_stdout, _cat_stderr = await cat_proc.communicate(input=content.encode())

            exec_proc = await asyncio.create_subprocess_exec(
                *_ssh_base_args(kwargs), f"bash {remote_path} && rm -f {remote_path} || (rm -f {remote_path}; exit 1)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_hidden(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(exec_proc.communicate(), timeout=timeout)
            except TimeoutError:
                exec_proc.kill()
                await exec_proc.wait()
                return f"Error: Remote script timed out after {timeout}s"
            out = decode_bytes(stdout) if stdout else ""
            if stderr:
                err = decode_bytes(stderr)
                if err:
                    out += f"\n[stderr]\n{err}"
            return json.dumps({
                "exit_code": exec_proc.returncode,
                "output": out.strip(),
            }, indent=2)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(script_path)


    else:
        return f"Error: Unknown action '{action}'. Available actions: exec, upload, download, ping, script."


EncreSSHTool = build_tool(
    name="ssh",
    description=(
        "Run commands, transfer files, or execute multi-line scripts on a remote host "
        "via SSH/SCP using the system ssh and scp clients. "
        "Use this for remote server operations: `exec` a single command, `upload`/"
        "`download` files with SCP, `ping` to verify connectivity, or `script` to run "
        "a multi-line bash script remotely. "
        "Do NOT use this for interactive shells, port forwarding, or long-running "
        "daemons; prefer a persistent session or dedicated tool. "
        "Tips: prefer key-based auth via `key_file` over `password` (which requires "
        "sshpass); tune `timeout` for slow commands. "
        "Pitfalls: StrictHostKeyChecking is disabled and ConnectTimeout is 15s; large "
        "SCP transfers may hit the 120s timeout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["exec", "upload", "download", "ping", "script"],
                "description": "SSH operation to perform: exec (run a remote command), upload (SCP local->remote), download (SCP remote->local), ping (test connectivity), or script (upload+run a bash script).",
            },
            "host": {
                "type": "string",
                "description": "Remote host as hostname, FQDN, or IP address.",
            },
            "port": {
                "type": "integer",
                "description": "TCP port for the SSH service; defaults to 22.",
            },
            "user": {
                "type": "string",
                "description": "SSH login username; defaults to 'root' if omitted.",
            },
            "key_file": {
                "type": "string",
                "description": "Path to a private key file passed via ssh -i; preferred over password auth.",
            },
            "password": {
                "type": "string",
                "description": "SSH password; only used when sshpass is installed on the host system.",
            },
            "command": {
                "type": "string",
                "description": "Shell command string to execute on the remote host (required for exec).",
            },
            "local_path": {
                "type": "string",
                "description": "Local filesystem path of the file to upload or download target.",
            },
            "remote_path": {
                "type": "string",
                "description": "Remote filesystem path of the upload destination or download source.",
            },
            "content": {
                "type": "string",
                "description": "Bash script body to upload and execute remotely (required for script).",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum runtime in seconds before killing the process; defaults to 60 (exec) or 120 (script).",
            },
        },
        "required": ["action", "host"],
    },
    execute=_ssh_execute,
    intents=["coding", "system", "general"],
    is_concurrency_safe=lambda data: data.get("action") == "ping",
    is_destructive=True,
    category="infra",
    semantic_type="exec",
)
