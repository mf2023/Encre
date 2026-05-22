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
import pathlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from yim.agent import YmiAgent
from yim.config import YmiConfig, get_data_dir
from yim.crypto import encrypt, decrypt
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
        self._index: dict[str, dict[str, Any]] = {}

    # ── paths ───────────────────────────────────────────────────────────────

    def _get_sessions_dir(self) -> str:
        if self._sessions_dir is None:
            _dir = get_data_dir() / "sessions"
            _dir.mkdir(parents=True, exist_ok=True)
            self._sessions_dir = str(_dir)
            self._load_index()
        return self._sessions_dir

    def _index_path(self) -> pathlib.Path:
        return pathlib.Path(self._get_sessions_dir()) / "index.json"

    def _session_dir_path(self, session_id: str) -> pathlib.Path:
        return pathlib.Path(self._get_sessions_dir()) / session_id

    # ── index ───────────────────────────────────────────────────────────────

    def _load_index(self) -> None:
        ip = self._index_path()
        try:
            if ip.exists():
                raw = ip.read_text(encoding="utf-8").strip()
                if raw and not raw.startswith("{"):
                    try:
                        raw = decrypt(raw)
                    except Exception:
                        pass
                self._index = json.loads(raw)
                if not isinstance(self._index, dict):
                    self._index = {}
        except Exception:
            self._index = {}

    def _save_index(self) -> None:
        ip = self._index_path()
        try:
            payload = json.dumps(self._index, ensure_ascii=False, separators=(",", ":"))
            encrypted = encrypt(payload)
            ip.write_text(encrypted, encoding="utf-8")
        except Exception:
            pass

    def _index_add(self, info: SessionInfo, preview: str = "") -> None:
        sess = info.agent.session
        real_msgs = [m for m in sess.messages if m.get("role") != "system"]
        self._index[info.session_id] = {
            "session_id": info.session_id,
            "created_at": info.created_at,
            "last_active": info.last_active,
            "preview": preview,
            "message_count": len([m for m in real_msgs if m.get("role") not in ("tool", )]),
            "turn_count": sess.turn_count,
        }

    def _index_remove(self, session_id: str) -> None:
        self._index.pop(session_id, None)

    def _bootstrap_index_from_disk(self) -> None:
        """Scan sessions_dir for existing session directories and rebuild index."""
        try:
            sessions_dir = self._get_sessions_dir()
            for entry in os.scandir(sessions_dir):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                sid = entry.name
                if sid in self._index:
                    continue
                meta = YmiSession.read_meta(entry.path)
                if meta is None:
                    meta_path = os.path.join(entry.path, "meta.json")
                    mtime = os.path.getmtime(meta_path) if os.path.exists(meta_path) else time.time()
                    self._index[sid] = {
                        "session_id": sid,
                        "created_at": mtime,
                        "last_active": mtime,
                        "preview": "",
                        "message_count": 0,
                        "turn_count": 0,
                    }
                    continue
                preview = YmiSession.load_preview(entry.path) or ""
                self._index[sid] = {
                    "session_id": sid,
                    "created_at": meta.get("created_at", time.time()),
                    "last_active": meta.get("updated_at", time.time()),
                    "preview": preview,
                    "message_count": meta.get("turn_count", 0),
                    "turn_count": meta.get("turn_count", 0),
                }
            self._save_index()
        except Exception:
            pass

    # ── session CRUD ────────────────────────────────────────────────────────

    def _save_session(self, info: SessionInfo) -> None:
        import logging
        _log = logging.getLogger("yim.server.session")
        try:
            sess = info.agent.session
            real_msgs = [m for m in sess.messages if m.get("role") != "system"]
            if not real_msgs:
                return

            dir_path = self._session_dir_path(info.session_id)
            sess.save_to_dir(str(dir_path))

            # Update index
            self._index_add(info)
            self._save_index()
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

        dir_path = self._session_dir_path(session_id)
        if dir_path.is_dir():
            try:
                cfg = config or YmiConfig()
                tool_registry = _create_default_tool_registry()
                agent = YmiAgent(config=cfg, tool_registry=tool_registry)
                agent.telemetry.session_id = session_id
                agent.session = YmiSession.load_from_dir(str(dir_path), cfg)
                agent.loop.session = agent.session
                agent.telemetry.session_id = session_id
                info = SessionInfo(session_id=session_id, agent=agent)
                meta = YmiSession.read_meta(str(dir_path))
                if meta:
                    info.created_at = meta.get("created_at", time.time())
                    info.last_active = meta.get("updated_at", time.time())
                self._sessions[session_id] = info
                return info
            except Exception:
                return self.create_session(config=config)

        return self.create_session(config=config)

    def remove_session(self, session_id: str) -> None:
        info = self._sessions.pop(session_id, None)
        if info is not None:
            if info.agent_task and not info.agent_task.done():
                info.agent_task.cancel()
            info.agent.telemetry.flush()
            self._save_session(info)

    def try_resume_most_recent(self, config: YmiConfig | None = None) -> SessionInfo | None:
        self._get_sessions_dir()  # ensures index loaded
        if not self._index:
            self._bootstrap_index_from_disk()
        if not self._index:
            return None

        best_sid = max(
            self._index.keys(),
            key=lambda sid: self._index[sid].get("last_active", self._index[sid].get("created_at", 0)),
        )
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

    def query_index(self) -> list[dict[str, Any]]:
        """Return all sessions known from the on‑disk index."""
        self._get_sessions_dir()
        if not self._index:
            self._bootstrap_index_from_disk()
        entries: list[dict[str, Any]] = []
        for sid, entry in self._index.items():
            entries.append({
                "session_id": sid,
                "created_at": entry.get("created_at", 0),
                "last_active": entry.get("last_active", 0),
                "is_running": False,
                "metadata": {},
                "preview": entry.get("preview", ""),
                "message_count": entry.get("message_count", 0),
            })
        entries.sort(key=lambda e: e.get("last_active", e.get("created_at", 0)), reverse=True)
        entries = [e for e in entries if (e.get("message_count") or 0) > 0]
        return entries

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
