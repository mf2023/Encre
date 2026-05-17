#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from yim.agent import YmiAgent
from yim.config import YmiConfig, get_data_dir
from yim.session import YmiSession
from yim.tools.registry import ToolRegistry
from yim.tools.builtin import (
    YmiFileReadTool,
    YmiFileWriteTool,
    YmiFileEditTool,
    YmiBashTool,
    YmiGrepTool,
    YmiGlobTool,
    YmiWebFetchTool,
    YmiWebSearchTool,
    YmiTodoTool,
    YmiTaskCreateTool,
    YmiTaskGetTool,
    YmiTaskListTool,
    YmiTaskUpdateTool,
    YmiAgentTool,
    YmiLSPTool,
    YmiBrowserTool,
    YmiNotebookTool,
    YmiDatabaseTool,
    YmiDockerTool,
    YmiGitTool,
    YmiRESTTool,
    YmiPDFTool,
    YmiSpreadsheetTool,
    YmiImageTool,
    YmiDeployTool,
)


@dataclass
class SessionInfo:
    session_id: str
    agent: YmiAgent
    agent_task: asyncio.Task[None] | None = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    is_running: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_many([
        YmiFileReadTool(),
        YmiFileWriteTool(),
        YmiFileEditTool(),
        YmiBashTool(),
        YmiGrepTool(),
        YmiGlobTool(),
        YmiWebFetchTool(),
        YmiWebSearchTool(),
        YmiTodoTool(),
        YmiTaskCreateTool(),
        YmiTaskGetTool(),
        YmiTaskListTool(),
        YmiTaskUpdateTool(),
        YmiAgentTool(),
        YmiLSPTool(),
        YmiBrowserTool(),
        YmiNotebookTool(),
        YmiDatabaseTool(),
        YmiDockerTool(),
        YmiGitTool(),
        YmiRESTTool(),
        YmiPDFTool(),
        YmiSpreadsheetTool(),
        YmiImageTool(),
        YmiDeployTool(),
    ])
    return registry


class SessionManager:
    def __init__(self, max_concurrent: int = 20, idle_timeout: float = 3600.0) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        self._max_concurrent = max_concurrent
        self._idle_timeout = idle_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._sessions_dir: str | None = None

    def _get_sessions_dir(self) -> str:
        if self._sessions_dir is None:
            _dir = get_data_dir() / "sessions"
            _dir.mkdir(parents=True, exist_ok=True)
            self._sessions_dir = str(_dir)
        return self._sessions_dir

    def _save_session(self, info: SessionInfo) -> None:
        import logging
        _log = logging.getLogger("yim.server.session")
        try:
            sess = info.agent.session
            real_msgs = [m for m in sess.messages if m.get("role") != "system"]
            if not real_msgs:
                return
            session_path = os.path.join(self._get_sessions_dir(), f"{info.session_id}.json")
            data = sess.to_dict()
            data["messages"] = real_msgs
            data["_session_meta"] = {
                "session_id": info.session_id,
                "created_at": info.created_at,
                "last_active": info.last_active,
                "metadata": info.metadata,
            }
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            _log.exception("Failed to save session %s", info.session_id)

    def create_session(self, config: YmiConfig | None = None) -> SessionInfo:
        config = config or YmiConfig()
        session_id = str(uuid.uuid4())
        tool_registry = _create_default_tool_registry()
        agent = YmiAgent(config=config, tool_registry=tool_registry)
        agent.telemetry.session_id = session_id
        info = SessionInfo(session_id=session_id, agent=agent)
        self._sessions[session_id] = info
        return info

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    def load_or_create_session(self, session_id: str, config: YmiConfig | None = None) -> SessionInfo:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        import json, os
        fpath = os.path.join(self._get_sessions_dir(), f"{session_id}.json")
        if not os.path.exists(fpath):
            return self.create_session(config=config)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = config or YmiConfig()
            tool_registry = _create_default_tool_registry()
            agent = YmiAgent(config=cfg, tool_registry=tool_registry)
            agent.telemetry.session_id = session_id
            agent.session = YmiSession.from_dict(data, cfg)
            agent.loop.session = agent.session
            info = SessionInfo(session_id=session_id, agent=agent)
            meta = data.get("_session_meta", {})
            info.created_at = meta.get("created_at", time.time())
            info.last_active = meta.get("last_active", time.time())
            self._sessions[session_id] = info
            return info
        except Exception:
            return self.create_session(config=config)

    def remove_session(self, session_id: str) -> None:
        info = self._sessions.pop(session_id, None)
        if info is not None:
            if info.agent_task and not info.agent_task.done():
                info.agent_task.cancel()
            info.agent.telemetry.flush()
            self._save_session(info)

    def try_resume_most_recent(self, config: YmiConfig | None = None) -> SessionInfo | None:
        sessions_dir = self._get_sessions_dir()
        import os, json
        best_sid = None
        best_time = 0.0
        try:
            for fname in os.listdir(sessions_dir):
                if not fname.endswith(".json"):
                    continue
                sid = fname[:-5]
                fpath = os.path.join(sessions_dir, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    if mtime > best_time:
                        best_time = mtime
                        best_sid = sid
                except OSError:
                    continue
        except Exception:
            pass
        if best_sid is None:
            return None
        return self.load_or_create_session(best_sid, config=config)

    def touch(self, session_id: str) -> None:
        info = self._sessions.get(session_id)
        if info:
            info.last_active = time.time()

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def list_sessions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for info in self._sessions.values():
            msg_count = 0
            preview = ""
            if hasattr(info.agent, 'session') and info.agent.session:
                msgs = info.agent.session.messages
                msg_count = len([m for m in msgs if m.get("role") not in ("tool", "system")])
                for m in msgs:
                    if m.get("role") == "user":
                        c = m.get("content", "")
                        if isinstance(c, str) and c.strip():
                            preview = c.strip()[:80]
                            break
                        elif isinstance(c, list):
                            for b in c:
                                if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                                    preview = b["text"].strip()[:80]
                                    break
                            if preview:
                                break
            result.append({
                "session_id": info.session_id,
                "created_at": info.created_at,
                "last_active": info.last_active,
                "is_running": info.is_running,
                "metadata": info.metadata,
                "preview": preview,
                "message_count": msg_count,
            })
        return result

    async def cleanup_idle(self) -> int:
        now = time.time()
        to_remove: list[str] = []
        for sid, info in self._sessions.items():
            if now - info.last_active > self._idle_timeout and not info.is_running:
                to_remove.append(sid)
        for sid in to_remove:
            self.remove_session(sid)
        return len(to_remove)

    async def acquire_slot(self) -> bool:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=30.0)
            return True
        except asyncio.TimeoutError:
            return False

    def release_slot(self) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass

    async def shutdown(self) -> None:
        for sid in list(self._sessions.keys()):
            self.remove_session(sid)
