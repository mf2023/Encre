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

from encre.server.session_manager import SessionManager

_start_time = time.time()


def _json_response(data: dict[str, Any], status: int = 200) -> tuple[int, str, list[tuple[str, str]]]:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    headers = [("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*")]
    return status, body, headers


def handle_admin(path: str, manager: SessionManager) -> tuple[int, str, list[tuple[str, str]]] | None:
    if path == "/health" or path == "/":
        uptime = time.time() - _start_time
        return _json_response({
            "status": "ok",
            "uptime_seconds": round(uptime, 1),
            "active_sessions": manager.active_count,
        })

    if path == "/config":
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

    if path == "/sessions":
        return _json_response({
            "sessions": manager.list_sessions(),
            "total": manager.active_count,
        })

    if path == "/stats":
        sessions = manager.list_sessions()
        running = sum(1 for s in sessions if s["is_running"])
        uptime = time.time() - _start_time
        return _json_response({
            "uptime_seconds": round(uptime, 1),
            "total_sessions": len(sessions),
            "running_sessions": running,
            "idle_sessions": len(sessions) - running,
        })

    if path.startswith("/sessions/") and path.endswith("/cancel"):
        session_id = path.split("/")[2]
        info = manager.get_session(session_id)
        if info is None:
            return _json_response({"error": "Session not found"}, 404)
        if info.agent_task and not info.agent_task.done():
            info.agent_task.cancel()
        info.is_running = False
        return _json_response({"ok": True, "session_id": session_id})

    return None
