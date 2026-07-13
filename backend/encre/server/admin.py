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

"""Lightweight HTTP admin endpoints for the Encre server.

These endpoints are served alongside the WebSocket upgrade by
:func:`encre.server.app.EncreServer.start` via the ``process_request`` hook.
They expose read-only operational data (health, config, session counts, stats)
and a single control action (cancel a running session).  All responses are JSON
with permissive CORS headers so local tooling can consume them.
"""

import json
import os
import time
from typing import Any
from urllib.parse import urlparse, parse_qs

from encre.server.session_manager import SessionManager

_start_time = time.time()


def _json_response(data: dict[str, Any], status: int = 200) -> tuple[int, str, list[tuple[str, str]]]:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    headers = [("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*")]
    return status, body, headers


def handle_admin(path: str, manager: SessionManager) -> tuple[int, str, list[tuple[str, str]]] | None:
    parsed = urlparse(path)
    base_path = parsed.path
    query = parse_qs(parsed.query)

    if base_path == "/health" or base_path == "/":
        uptime = time.time() - _start_time
        return _json_response({
            "status": "ok",
            "uptime_seconds": round(uptime, 1),
            "active_sessions": manager.active_count,
        })

    if base_path == "/config":
        from encre.config import _get_config_path
        config_path = str(_get_config_path())
        if os.path.exists(config_path):
            try:
                import tomllib
                with open(config_path, "rb") as f:
                    config_data = tomllib.load(f)
            except (ImportError, Exception):
                config_data = {}
        else:
            config_data = {}
        return _json_response(config_data)

    if base_path == "/sessions":
        return _json_response({
            "sessions": manager.list_sessions(),
            "total": manager.active_count,
        })

    if base_path == "/stats":
        sessions = manager.list_sessions()
        running = sum(1 for s in sessions if s["is_running"])
        uptime = time.time() - _start_time
        return _json_response({
            "uptime_seconds": round(uptime, 1),
            "total_sessions": len(sessions),
            "running_sessions": running,
            "idle_sessions": len(sessions) - running,
        })

    if base_path.startswith("/sessions/") and base_path.endswith("/cancel"):
        session_id = base_path.split("/")[2]
        info = manager.get_session(session_id)
        if info is None:
            return _json_response({"error": "Session not found"}, 404)
        if info.agent_task and not info.agent_task.done():
            info.agent_task.cancel()
        info.is_running = False
        return _json_response({"ok": True, "session_id": session_id})

    if base_path == "/git/status":
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        try:
            from encre.git.repo import EncreGitRepo
            repo = EncreGitRepo(workspace=workspace)
            output = repo.get_porcelain_status()
            return _json_response({"output": output})
        except Exception as e:
            return _json_response({"error": str(e)})

    if base_path == "/git/diff":
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        filter_type = query.get("filter", ["all"])[0]
        file_path = query.get("file", [None])[0]
        try:
            from encre.git.repo import EncreGitRepo
            repo = EncreGitRepo(workspace=workspace)
            output = repo.get_diff_ex(filter_type=filter_type, file_path=file_path)
            return _json_response({"output": output})
        except Exception as e:
            return _json_response({"error": str(e)})

    if base_path == "/git/commit":
        import subprocess
        workspace = query.get("workspace", [""])[0]
        message = query.get("message", [""])[0]
        if not workspace or not message:
            return _json_response({"error": "workspace and message required"}, 400)
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=15,
            )
            if result.returncode != 0:
                return _json_response({"error": result.stderr.strip()})
            return _json_response({"output": result.stdout})
        except Exception as e:
            return _json_response({"error": str(e)})

    if base_path == "/git/push":
        import subprocess
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        try:
            # If no upstream tracking is set, auto-configure origin/HEAD.
            check = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=15,
            )
            if check.returncode != 0:
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=workspace, timeout=10,
                ).stdout.strip()
                if branch:
                    subprocess.run(
                        ["git", "push", "--set-upstream", "origin", branch],
                        capture_output=True, cwd=workspace, timeout=60,
                    )
            result = subprocess.run(
                ["git", "push"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=60,
            )
            if result.returncode != 0:
                return _json_response({"error": result.stderr.strip()})
            return _json_response({"output": result.stdout or "Pushed."})
        except Exception as e:
            return _json_response({"error": str(e)})

    if base_path == "/git/pull":
        import subprocess
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        try:
            # If no upstream tracking is set, auto-configure origin/HEAD.
            check = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=15,
            )
            if check.returncode != 0:
                # No upstream → branch-branch=origin/HEAD else origin/<branch>
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=workspace, timeout=10,
                ).stdout.strip()
                if branch:
                    subprocess.run(
                        ["git", "branch", "--set-upstream-to", f"origin/{branch}", branch],
                        capture_output=True, cwd=workspace, timeout=15,
                    )
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=60,
            )
            if result.returncode != 0:
                return _json_response({"error": result.stderr.strip()})
            return _json_response({"output": result.stdout or "Pulled."})
        except Exception as e:
            return _json_response({"error": str(e)})

    if base_path == "/git/behind":
        import subprocess
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        try:
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=10,
            )
            branch = branch_res.stdout.strip() if branch_res.returncode == 0 else ""
            if not branch:
                return _json_response({"behind": -1, "error": "no branch"})
            remote_res = subprocess.run(
                ["git", "ls-remote", "--heads", "origin", branch],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=30,
            )
            if remote_res.returncode != 0 or not remote_res.stdout.strip():
                return _json_response({"behind": -1, "error": "no remote"})
            subprocess.run(
                ["git", "fetch", "origin", branch],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=30,
            )
            behind_res = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=15,
            )
            behind = int(behind_res.stdout.strip()) if behind_res.returncode == 0 else 0
            return _json_response({"behind": behind})
        except Exception as e:
            return _json_response({"behind": -1, "error": str(e)})

    if base_path == "/git/pr":
        import subprocess
        workspace = query.get("workspace", [""])[0]
        if not workspace:
            return _json_response({"error": "workspace required"}, 400)
        try:
            # Push first so the remote branch exists.
            push_res = subprocess.run(
                ["git", "push"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=60,
            )
            # Resolve the origin URL and current branch to build a compare link.
            url_res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=10,
            )
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=workspace, timeout=10,
            )
            origin = url_res.stdout.strip() if url_res.returncode == 0 else ""
            branch = branch_res.stdout.strip() if branch_res.returncode == 0 else ""
            # Translate an SSH/SCP-style origin into a browsable compare URL.
            compare_url = _build_compare_url(origin, branch)
            if push_res.returncode != 0 and "Everything up-to-date" not in (push_res.stderr or ""):
                return _json_response({
                    "error": push_res.stderr.strip(),
                    "compare_url": compare_url,
                })
            return _json_response({
                "output": push_res.stdout or "Pushed.",
                "compare_url": compare_url,
            })
        except Exception as e:
            return _json_response({"error": str(e)})

    return None


def _build_compare_url(origin: str, branch: str) -> str:
    """Turn a git origin URL + branch into a web compare/pull-request URL."""
    if not origin or not branch:
        return ""
    url = origin.strip()
    # git@github.com:owner/repo.git -> https://github.com/owner/repo
    if url.startswith("git@"):
        url = url.replace(":", "/").replace("git@", "https://")
    if url.endswith(".git"):
        url = url[:-4]
    if not url.startswith("http"):
        return ""
    sep = "" if url.endswith("/") else "/"
    return f"{url}{sep}compare/{branch}?expand=1"
