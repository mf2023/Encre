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

"""Encre session manager.

The :class:`SessionManager` is the single source of truth for agent sessions.
It keeps sessions in memory (so the agent's async task runs against a live
:class:`~encre.agent.EncreAgent`) and persists them to disk under the
Encre data directory (``~/.dunimd/encre/sessions`` by default, or a
per-workspace / per-iClaw subdirectory).

Key responsibilities:

    * create / get / load-or-create / delete sessions
    * an encrypted ``index.json`` for fast sidebar listing across modes
    * a concurrency semaphore (``acquire_slot`` / ``release_slot``)
    * debounced, executor-based async persistence (``_save_session_async``)
    * idle cleanup and graceful shutdown

A session is represented by the :class:`SessionInfo` dataclass, which
links a session id, its agent, the running task, and metadata.
"""

import asyncio
import threading
import contextlib
import json
import logging
import os
import pathlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from encre.config import EncreConfig, get_data_dir
from encre.crypto import decrypt, encrypt
from encre.session import EncreSession, _atomic_write_text
from encre.tools.defaults import register_default_tools
from encre.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from encre.agent import EncreAgent


class SessionState(str, Enum):
    """Unified session state machine.

    ``IDLE``               鈥?session exists but not running.
    ``RUNNING``            鈥?agent loop is actively processing.
    ``AWAITING_APPROVAL``  鈥?agent loop is blocked waiting for user permission.
    """

    IDLE = "idle"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"


@dataclass
class SessionInfo:
    """In-memory record for one agent session.

    Links the session id to its :class:`~encre.agent.EncreAgent`, the
    running asyncio task (if any), and bookkeeping fields used for idle
    cleanup, persistence and channel tagging.
    """

    session_id: str
    agent: EncreAgent
    agent_task: asyncio.Task[None] | None = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    state: SessionState = SessionState.IDLE
    pending_runs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    sessions_dir: str = ""


def _create_default_tool_registry() -> ToolRegistry:
    """Build a fresh ToolRegistry populated with the built-in tools."""
    registry = ToolRegistry()
    return register_default_tools(registry)


_SHARED_DEFAULT_TOOL_REGISTRY: ToolRegistry | None = None


def _get_shared_default_tool_registry() -> ToolRegistry:
    global _SHARED_DEFAULT_TOOL_REGISTRY
    if _SHARED_DEFAULT_TOOL_REGISTRY is None:
        _SHARED_DEFAULT_TOOL_REGISTRY = _create_default_tool_registry()
    return _SHARED_DEFAULT_TOOL_REGISTRY


def _clone_tool_registry() -> ToolRegistry:
    """Clone the shared default tool registry for a new session.

    Each session gets its own copy so per-session tool state (unlocks,
    overrides) does not leak between conversations.
    """
    registry = ToolRegistry()
    registry._tools = dict(_get_shared_default_tool_registry()._tools)
    return registry


class SessionManager:
    """In-memory + on-disk store for all agent sessions.

    See the module docstring (:mod:`encre.server.session_manager`) for the
    full responsibility overview.  Instances are shared by the WebSocket
    handler, the channel EventRouter, and the gateway adapters.
    """

    def __init__(self, max_concurrent: int = 20, idle_timeout: float = 3600.0, sessions_dir: str | None = None) -> None:
        self._sessions: dict[str, SessionInfo] = {}
        self._lock = threading.RLock()
        self._max_concurrent = max_concurrent
        self._idle_timeout = idle_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._sessions_dir: str | None = None
        self._index: dict[str, dict[str, Any]] = {}
        self._index_dirty = False
        self._bootstrapped = False
        self._sessions_changed_callbacks: list[Callable[[], None]] = []
        self._dir_sessions: dict[str, dict[str, SessionInfo]] = {}
        self._dir_bootstrapped: dict[str, bool] = {}
        self._unnamed_counter = 0
        if sessions_dir:
            self._sessions_dir = sessions_dir
            pathlib.Path(sessions_dir).mkdir(parents=True, exist_ok=True)
            self._load_index()
            # Clean up any temp-chat leftovers from a previous run (index
            # entries + on-disk directories) so they never appear in the
            # sidebar after a restart.
            self._purge_temp_chat_leftovers()

    # 鈹€鈹€ session change callbacks 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def on_sessions_changed(self, callback: Callable[[], None]) -> None:
        """Register a callback fired when any session is created, updated, or deleted."""
        self._sessions_changed_callbacks.append(callback)

    def notify_session_completed(self) -> None:
        """Notify listeners that an agent run has finished (session saved with new content)."""
        _fire_logger = logging.getLogger("encre.server.session")
        _fire_logger.info("[sessions_changed] notify_session_completed, %d callback(s)",
                          len(self._sessions_changed_callbacks))
        self._fire_sessions_changed()

    def _fire_sessions_changed(self) -> None:
        _fire_logger = logging.getLogger("encre.server.session")
        _fire_logger.info("[sessions_changed] firing %d callbacks",
                          len(self._sessions_changed_callbacks))
        for cb in self._sessions_changed_callbacks:
            try:
                cb()
            except Exception as exc:
                _fire_logger.warning("[sessions_changed] callback error: %s", exc)

    # 鈹€鈹€ paths 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _get_sessions_dir(self) -> str:
        if self._sessions_dir is None:
            _dir = get_data_dir() / "sessions"
            _dir.mkdir(parents=True, exist_ok=True)
            self._sessions_dir = str(_dir)
            self._load_index()
        return self._sessions_dir

    async def _switch_sessions_dir(self, _dir: pathlib.Path) -> None:
        """Swap to a different sessions directory without stopping running agents.

        Sessions for the previous directory are kept in memory so that agent
        tasks continue to execute in the background. When the user switches
        back, the same in-memory pool (and any running tasks) is restored.
        """
        _dir_str = str(_dir)
        current_dir = self._get_sessions_dir()
        if current_dir == _dir_str:
            return
        _dir.mkdir(parents=True, exist_ok=True)

        # Persist the current directory's index before leaving.
        self._save_index()

        # Stash current in-memory sessions; their tasks keep running.
        self._dir_sessions[current_dir] = self._sessions
        self._dir_bootstrapped[current_dir] = self._bootstrapped

        # Activate the target directory.
        self._sessions_dir = _dir_str
        self._sessions = self._dir_sessions.get(_dir_str, {})
        self._index = {}
        self._index_dirty = False
        self._bootstrapped = self._dir_bootstrapped.get(_dir_str, False)
        self._load_index()
        self._bootstrap_index_from_disk()

    async def set_workspace(self, ws_id: str | None) -> None:
        """Switch session storage to the given workspace (or global if None)."""
        _dir = get_data_dir() / "iwork" / ws_id / "sessions" if ws_id else get_data_dir() / "sessions"
        await self._switch_sessions_dir(_dir)

    async def set_iclaw(self, active: bool) -> None:
        """Switch session storage to iClaw directory (or back to global)."""
        _dir = get_data_dir() / "iclaw" / "sessions" if active else get_data_dir() / "sessions"
        await self._switch_sessions_dir(_dir)

    def _index_path(self) -> pathlib.Path:
        return pathlib.Path(self._get_sessions_dir()) / "index.json"

    def _session_dir_path(self, session_id: str) -> pathlib.Path:
        sessions_dir = self._get_sessions_dir()
        info = self._sessions.get(session_id)
        if info is not None and info.sessions_dir:
            sessions_dir = info.sessions_dir
        else:
            resolved = None
            for sess_dict in self._dir_sessions.values():
                cached = sess_dict.get(session_id)
                if cached is not None and cached.sessions_dir:
                    resolved = cached.sessions_dir
                    break
            if resolved is None:
                # The session is not tracked in memory, so it may live in a
                # different workspace's directory (or the global one). iWork
                # mode shows every workspace's history in one flat list, so
                # resolve the directory across all of them instead of falling
                # back to creating a fresh empty session under the active
                # workspace (which would shadow the real one and make it
                # vanish from the sidebar).
                resolved = self._find_session_dir_anywhere(session_id, sessions_dir)
            if resolved is not None:
                sessions_dir = resolved
        return pathlib.Path(sessions_dir) / session_id

    def _find_session_dir_anywhere(
        self, session_id: str, current_sessions_dir: str
    ) -> str | None:
        """Locate a session directory across every workspace and the global dir.

        Returns the parent sessions directory that contains *session_id*, or
        None if the session does not exist anywhere on disk.
        """
        candidates: list[str] = []
        try:
            iwork_root = get_data_dir() / "iwork"
            if iwork_root.is_dir():
                candidates.extend(
                    str(ws_dir / "sessions")
                    for ws_dir in iwork_root.iterdir()
                    if ws_dir.is_dir()
                )
        except Exception:
            pass
        # iClaw desktop sessions live under their own directory tree.
        try:
            iclaw_dir = get_data_dir() / "iclaw" / "sessions"
            if iclaw_dir.is_dir():
                candidates.append(str(iclaw_dir))
        except Exception:
            pass
        global_dir = str(get_data_dir() / "sessions")
        if global_dir != current_sessions_dir:
            candidates.append(global_dir)
        for sess_dir in candidates:
            if (pathlib.Path(sess_dir) / session_id).is_dir():
                return sess_dir
        return None

    # 鈹€鈹€ index 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _load_index_for_dir(self, sessions_dir: str) -> dict[str, Any]:
        ip = pathlib.Path(sessions_dir) / "index.json"
        try:
            if ip.exists():
                raw = ip.read_text(encoding="utf-8").strip()
                if raw and not raw.startswith("{"):
                    with contextlib.suppress(Exception):
                        raw = decrypt(raw)
                index = json.loads(raw)
                if isinstance(index, dict):
                    return index
        except Exception:
            pass
        return {}

    def _save_index_for_dir(self, sessions_dir: str, index: dict[str, Any]) -> None:
        ip = pathlib.Path(sessions_dir) / "index.json"
        try:
            payload = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
            encrypted = encrypt(payload)
            ip.write_text(encrypted, encoding="utf-8")
        except Exception:
            pass

    def _load_index(self) -> None:
        self._index = self._load_index_for_dir(self._get_sessions_dir())

    def _purge_temp_chat_leftovers(self) -> None:
        """Remove any temp-chat directories and index entries left from a previous run.

        This is called once during startup so stale ephemeral sessions never
        appear in the sidebar after a restart.
        """
        import shutil
        sessions_dir = self._get_sessions_dir()
        repaired = False
        # Remove stray temp-chat directories on disk.
        try:
            for entry in os.scandir(sessions_dir):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                meta = EncreSession.read_meta(entry.path)
                if meta and isinstance(meta, dict):
                    meta_metadata = meta.get("metadata", {}) or {}
                    if meta_metadata.get("temp_chat"):
                        shutil.rmtree(entry.path, ignore_errors=True)
                        if entry.name in self._index:
                            self._index.pop(entry.name, None)
                            repaired = True
        except Exception:
            pass
        # Purge any temp_chat index entries that no longer have a directory.
        stale = [sid for sid, idx in list(self._index.items())
                 if idx.get("metadata", {}).get("temp_chat") or idx.get("temp_chat")]
        for sid in stale:
            self._index.pop(sid, None)
            repaired = True
        if repaired:
            self._save_index()

    def _save_index(self) -> None:
        with self._lock:
            if not self._index_dirty:
                return
            self._save_index_for_dir(self._get_sessions_dir(), self._index)
            self._index_dirty = False

    def _make_index_entry(self, info: SessionInfo, preview: str = "") -> dict[str, Any]:
        sess = info.agent.session
        existing = self._index.get(info.session_id, {})
        msg_count, cached_preview = sess.get_summary()
        channel = sess.metadata.get("channel", info.metadata.get("channel", "normal"))
        # Persist workspace path so iWork sessions can be re-entered from disk.
        workspace = info.metadata.get("workspace") or sess.metadata.get("workspace", "")
        # Archived flag: hidden from normal lists, visible in the archive view.
        archived = bool(
            info.metadata.get("archived")
            or sess.metadata.get("archived")
            or existing.get("archived", False)
        )
        # The sidebar ordering time MUST reflect the real last conversation,
        # not the session creation time or any "touch" on click.  For sessions
        # that actually contain messages we use the session's last_message_at;
        # brand-new empty sessions fall back to info.last_active so they still
        # appear in the list at a sensible position.
        last_active = (
            getattr(sess, "last_message_at", 0)
            or sess.updated_at
            or info.last_active
        )
        return {
            "session_id": info.session_id,
            "created_at": info.created_at,
            "last_active": last_active,
            "preview": preview or cached_preview,
            "channel": channel,
            "workspace": workspace,
            "message_count": msg_count,
            "turn_count": sess.turn_count,
            # A title is user-managed metadata, not something derived from the
            # conversation. Preserve it whenever a normal session save refreshes
            # the rest of this index entry.
            "name": info.metadata.get("name", existing.get("name", "")),
            "archived": archived,
        }

    def _index_add(self, info: SessionInfo, preview: str = "") -> None:
        self._index[info.session_id] = self._make_index_entry(info, preview)
        self._index_dirty = True

    def _index_remove(self, session_id: str) -> None:
        if session_id in self._index:
            self._index.pop(session_id, None)
            self._index_dirty = True

    @staticmethod
    def _extract_preview_from_messages(messages: list[dict[str, Any]]) -> str:
        for m in messages:
            if m.get("role") != "user":
                continue
            c = m.get("content", "")
            if isinstance(c, str) and c.strip():
                return c.strip()[:80]
            if isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    text = b.get("text", "")
                    if isinstance(text, str) and text.strip() and b.get("type") == "text":
                        return text.strip()[:80]
        return ""

    def _bootstrap_index_from_disk(self) -> None:
        """Scan sessions_dir for existing session directories and rebuild/repair index."""
        if self._bootstrapped:
            return
        try:
            sessions_dir = self._get_sessions_dir()
            repaired = False
            for entry in os.scandir(sessions_dir):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                sid = entry.name
                meta = EncreSession.read_meta(entry.path)
                meta_metadata = meta.get("metadata", {}) if isinstance(meta, dict) else {}
                # Temp chats are ephemeral: remove any leftover directories
                # and index entries from previous versions/crashes.
                if meta_metadata.get("temp_chat"):
                    shutil.rmtree(entry.path, ignore_errors=True)
                    if sid in self._index:
                        self._index.pop(sid, None)
                        repaired = True
                    continue
                # Repair existing index entries with empty preview, or whose
                # message_count was previously computed from turn_count and is
                # now stale after the backend started persisting user-message
                # counts in meta.json.
                existing = self._index.get(sid)
                meta_message_count = meta.get("message_count") if isinstance(meta, dict) else None
                needs_repair = (
                    existing is None
                    or not existing.get("preview", "")
                    or (
                        meta_message_count is not None
                        and existing.get("message_count") != meta_message_count
                    )
                )
                if not needs_repair:
                    continue
                # Try to extract channel from session metadata (saved meta.json or in-memory)
                channel = "normal"
                if meta:
                    ch = meta_metadata.get("channel") or ""
                    if ch:
                        channel = ch
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
                        "channel": channel,
                        "workspace": "",
                        "archived": False,
                    }
                    repaired = True
                    continue
                preview = EncreSession.load_preview(entry.path) or ""
                # Recover workspace path from saved session metadata.
                ws_path = (
                    meta_metadata.get("workspace", "")
                    if isinstance(meta_metadata, dict)
                    else ""
                )
                if meta.get("message_count") is not None:
                    msg_count = meta.get("message_count")
                else:
                    msg_count = EncreSession.count_user_messages(entry.path)
                self._index[sid] = {
                    "session_id": sid,
                    "created_at": meta.get("created_at", time.time()),
                    "last_active": meta.get("updated_at", time.time()),
                    "preview": preview,
                    "message_count": msg_count,
                    "turn_count": meta.get("turn_count", 0),
                    "channel": channel,
                    "workspace": ws_path,
                    # Restore the archived flag from meta.json so an index
                    # rebuild never resurrects an archived session into the
                    # normal sidebar.
                    "archived": bool(meta_metadata.get("archived", False)),
                }
                repaired = True
            # Also purge stale temp_chat entries that no longer have a directory.
            stale_temp_sids = [
                sid for sid in list(self._index.keys())
                if self._index[sid].get("metadata", {}).get("temp_chat") or self._index[sid].get("temp_chat")
            ]
            for sid in stale_temp_sids:
                self._index.pop(sid, None)
                repaired = True
            if repaired:
                self._save_index()
            self._bootstrapped = True
        except Exception:
            pass

    # 鈹€鈹€ session CRUD 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _save_session(self, info: SessionInfo) -> None:
        import logging
        _log = logging.getLogger("encre.server.session")
        try:
            sess = info.agent.session
            # Temp chats are ephemeral and must never touch disk or the index.
            if sess.metadata.get("temp_chat"):
                return

            sessions_dir = info.sessions_dir or self._get_sessions_dir()
            dir_path = pathlib.Path(sessions_dir) / info.session_id
            sess.save_to_dir(str(dir_path))
            _, preview = sess.get_summary()

            # Update the directory-specific index so background sessions save
            # to their own storage even when another mode is currently active.
            index = self._load_index_for_dir(sessions_dir)
            entry = self._make_index_entry(info, preview)
            # A background session can save while another directory is active,
            # so preserve the title from that directory's own index as well.
            if not entry.get("name"):
                entry["name"] = index.get(info.session_id, {}).get("name", "")
            index[info.session_id] = entry
            self._save_index_for_dir(sessions_dir, index)
        except Exception:
            _log.exception("Failed to save session %s", info.session_id)

    def create_session(self, config: EncreConfig | None = None, session_id: str | None = None, mode: Any = None) -> SessionInfo:
        """Create a brand-new in-memory session with a cloned tool registry.

        Args:
            config: Optional config override.
            session_id: Optional explicit session ID. When None (default),
                a new UUID is generated. This lets callers like
                ``load_or_create_session`` reuse a known adapter session_id
                instead of generating a new one on every fallback, avoiding
                "one-time session" behavior for gateway adapters.
            mode: Optional capability profile (``AgentMode``). When None the
                profile is auto-derived: a session bound to a workspace runs
                in WORKSPACE mode (production-grade gating + planner/architect
                contract loop); a session without a workspace runs in GENERAL
                mode. This keeps every workspace-session creation path
                (40+ call sites) consistent without touching each one.
        """
        config = replace(config) if config is not None else EncreConfig()
        if session_id is None:
            session_id = str(uuid.uuid4())
        if mode is None:
            from encre.modes.mode_profiles import AgentMode
            mode = AgentMode.WORKSPACE if (config.workspace or "").strip() else AgentMode.GENERAL
        tool_registry = _clone_tool_registry()
        from encre.agent import EncreAgent
        agent = EncreAgent(config=config, tool_registry=tool_registry, mode=mode)
        agent.telemetry.session_id = session_id
        info = SessionInfo(session_id=session_id, agent=agent)
        info.sessions_dir = self._get_sessions_dir()
        # Assign a placeholder name immediately so the sidebar shows
        # "Unnamed" / "Unnamed 2" / ... instead of the raw first message.
        self._unnamed_counter += 1
        placeholder_name = "Unnamed" if self._unnamed_counter == 1 else f"Unnamed {self._unnamed_counter}"
        info.metadata["name"] = placeholder_name
        self._sessions[session_id] = info
        self._fire_sessions_changed()

        # Register a hook that flushes the session to disk the moment a user
        # message is added, so a process kill before the model responds still
        # leaves a resumable transcript.  Mirrors Claude Code's
        # QueryEngine.ts:450-463 (await user-message write before query loop).
        self._register_user_message_persist_hook(info)
        return info

    def _register_user_message_persist_hook(self, info: SessionInfo) -> None:
        """Register an ``on_user_message_persisted`` handler that saves the
        session immediately.  Uses a fire-and-forget async task so the loop
        is never blocked on disk I/O -- the await in the loop only waits for
        the hook dispatch, not the write itself.
        """
        import asyncio

        async def _persist(_session_id: str, _ctx: dict, _result: dict | None) -> dict:
            try:
                # Fire-and-forget: don't block the model loop on disk I/O.
                asyncio.ensure_future(self._save_session_async(info))
            except Exception:
                pass
            return {}

        try:
            info.agent.hook_system.register_handler(
                "on_user_message_persisted", _persist,
            )
        except Exception:
            pass

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    def get_session_state(self, session_id: str) -> str:
        """Return the current state of a session (value of ``SessionState``)."""
        info = self._sessions.get(session_id)
        if info is None:
            for sess_dict in self._dir_sessions.values():
                info = sess_dict.get(session_id)
                if info is not None:
                    break
        if info is None:
            return SessionState.IDLE.value
        task_alive = info.agent_task is not None and not info.agent_task.done()
        if info.state == SessionState.RUNNING and not task_alive:
            return SessionState.IDLE.value
        return info.state.value

    def set_session_state(self, session_id: str, new_state: SessionState) -> None:
        """Transition a session to a new state (no-op if session not found)."""
        info = self._sessions.get(session_id)
        if info is not None:
            info.state = new_state

    def is_session_running(self, session_id: str) -> bool:
        """Return True if the session is in memory and its agent task is alive."""
        info = self._sessions.get(session_id)
        if info is None:
            for sess_dict in self._dir_sessions.values():
                info = sess_dict.get(session_id)
                if info is not None:
                    break
        if info is None:
            return False
        return info.state in (SessionState.RUNNING, SessionState.AWAITING_APPROVAL) or (info.agent_task is not None and not info.agent_task.done())

    def load_or_create_session(self, session_id: str, config: EncreConfig | None = None, mode: Any = None) -> SessionInfo:
        """Return the live session for *session_id*, loading it from disk if needed.

        Looks up the active pool first (to preserve running agent state), then
        any stashed per-directory pools, then the on-disk session directory.
        Falls back to a fresh session when nothing is found.
        """
        # First search the active pool so we hand back the live in-memory
        # instance (which preserves the running agent's session object).
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        # Next search stashed pools from other session directories 鈥?when the
        # user is in workspace mode but resumes a normal-mode session (or vice
        # versa) the live instance lives in a different pool.  Returning it
        # keeps the streaming task bound to the same session object so the
        # disk view never diverges from in-memory progress.
        for sess_dict in self._dir_sessions.values():
            stashed = sess_dict.get(session_id)
            if stashed is not None:
                # Promote to the active pool so subsequent lookups are cheap.
                self._sessions[session_id] = stashed
                return stashed

        dir_path = self._session_dir_path(session_id)
        if dir_path.is_dir():
            try:
                cfg = replace(config) if config is not None else EncreConfig()
                tool_registry = _clone_tool_registry()
                # Restore workspace context from session metadata before
                # deriving the mode so resumed workspace sessions resume in
                # WORKSPACE mode (not GENERAL).
                meta = EncreSession.read_meta(str(dir_path))
                ws_path = (meta.get("metadata", {}) or {}).get("workspace") or meta.get("workspace") or ""
                if ws_path and os.path.isdir(ws_path):
                    cfg.workspace = ws_path
                if mode is None:
                    from encre.modes.mode_profiles import AgentMode
                    mode = AgentMode.WORKSPACE if (cfg.workspace or "").strip() else AgentMode.GENERAL
                from encre.agent import EncreAgent
                agent = EncreAgent(config=cfg, tool_registry=tool_registry, mode=mode)
                agent.telemetry.session_id = session_id
                agent.session = EncreSession.load_from_dir(str(dir_path), cfg)
                agent.loop.session = agent.session
                agent.telemetry.session_id = session_id
                # Restore the session's cumulative cost from its JSONL log so
                # get_summary() reflects the full session, not just post-resume
                # activity.  Best-effort: never blocks session load on failure.
                with contextlib.suppress(Exception):
                    agent.telemetry.restore_session_cost_from_jsonl()
                info = SessionInfo(session_id=session_id, agent=agent)
                # Persist back to the directory the session was actually
                # loaded from 鈥?it may be a different workspace's directory
                # when resumed from the flat iWork session list.
                info.sessions_dir = str(dir_path.parent)
                if meta:
                    info.created_at = meta.get("created_at", time.time())
                    info.last_active = meta.get("updated_at", time.time())
                    if ws_path and os.path.isdir(ws_path):
                        info.metadata["workspace"] = ws_path
                    sess_channel = agent.session.metadata.get("channel") or ""
                    if sess_channel:
                        info.metadata["channel"] = sess_channel
                self._sessions[session_id] = info
                # Sync the on-disk index with the freshly-loaded session so
                # query_index() / _list_all_sessions() report the same
                # last_active time as list_sessions(). Without this, sidebar
                # ordering would use a stale value from the previous index
                # write and clicking the session would appear to "reset" the
                # timestamp.
                #
                # CRITICAL: write into the session's OWN directory index, not
                # the currently-active one.  The session may have been loaded
                # from a different workspace's directory (flat iWork list), and
                # writing it into the active workspace's index would leak a
                # foreign session into that workspace's sidebar (data mismatch).
                target_dir = info.sessions_dir or self._get_sessions_dir()
                index = self._load_index_for_dir(target_dir)
                index[session_id] = self._make_index_entry(info)
                self._save_index_for_dir(target_dir, index)
                if target_dir == self._get_sessions_dir():
                    self._index = index
                    self._index_dirty = False
                self._register_user_message_persist_hook(info)
                return info
            except Exception:
                return self.create_session(config=config, session_id=session_id, mode=mode)

        return self.create_session(config=config, session_id=session_id, mode=mode)

    async def remove_session(self, session_id: str) -> None:
        info = self._sessions.pop(session_id, None)
        if info is not None:
            if info.agent_task and not info.agent_task.done():
                info.agent_task.cancel()
            info.agent.telemetry.flush()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._save_session, info)

    def delete_session_from_disk(self, session_id: str) -> bool:
        """Physically delete a session from memory, disk, and index."""
        import shutil
        removed = False
        # Cancel any pending debounced save so it cannot recreate the entry.
        pending_save = self._save_tasks.pop(session_id, None)
        if pending_save is not None and not pending_save.done():
            pending_save.cancel()

        sessions_dir = ""
        info = self._sessions.pop(session_id, None)
        if info is not None:
            removed = True
            sessions_dir = info.sessions_dir
            if info.agent_task and not info.agent_task.done():
                info.agent_task.cancel()

        # Search stashed pools if the session was not in the active directory.
        if not sessions_dir:
            for sess_dict in self._dir_sessions.values():
                cached = sess_dict.pop(session_id, None)
                if cached is not None:
                    removed = True
                    sessions_dir = cached.sessions_dir
                    if cached.agent_task and not cached.agent_task.done():
                        cached.agent_task.cancel()
                    break

        if not sessions_dir:
            sessions_dir = self._get_sessions_dir()

        dir_path = pathlib.Path(sessions_dir) / session_id
        if dir_path.exists():
            shutil.rmtree(str(dir_path), ignore_errors=True)
            removed = True

        # Remove from EVERY directory index that carries the session 鈥?a
        # session can appear in multiple workspace indexes (stale entries),
        # and leaving any behind would resurrect it in that sidebar.
        active_dir = self._get_sessions_dir()
        for dir_path in self._all_sessions_dirs():
            index = self._load_index_for_dir(dir_path)
            if session_id not in index:
                continue
            index.pop(session_id, None)
            self._save_index_for_dir(dir_path, index)
            if dir_path == active_dir:
                self._index = index
                self._index_dirty = False
            had_index = True
            removed = True

        self._fire_sessions_changed()
        # If the session existed anywhere (memory, disk, or index), treat as success.
        if had_index:
            removed = True
        if not removed:
            import logging
            logging.getLogger("encre.server.session").warning(
                "delete_session_from_disk: session %s not found anywhere", session_id
            )
        return removed

    # 鈹€鈹€ archive / unarchive 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def archive_session(self, session_id: str) -> bool:
        """Hide a session from the normal sidebar by flagging it as archived.

        Archiving never touches the session data 鈥?it only flips a flag that
        is persisted in BOTH the session's meta.json metadata (survives index
        rebuilds and restarts) and the owning directory's index entry (so
        listing paths can filter cheaply).  Returns True when the session was
        found and flagged.
        """
        return self._set_archived(session_id, True)

    def unarchive_session(self, session_id: str) -> bool:
        """Restore a previously archived session back into the normal lists."""
        return self._set_archived(session_id, False)

    def _set_archived(self, session_id: str, archived: bool) -> bool:
        """Core flag flip shared by archive_session / unarchive_session."""
        import json as _json

        from encre.crypto import encrypt as _encrypt

        found = False
        sessions_dir = ""
        # 1) In-memory session (active or stashed pool): keep the live object
        #    in sync so a later _save_session() flush preserves the flag.
        info = self._sessions.get(session_id)
        if info is None:
            for sess_dict in self._dir_sessions.values():
                info = sess_dict.get(session_id)
                if info is not None:
                    break
        if info is not None:
            found = True
            sessions_dir = info.sessions_dir or self._get_sessions_dir()
            info.metadata["archived"] = archived
            if hasattr(info.agent, "session") and info.agent.session is not None:
                info.agent.session.metadata["archived"] = archived

        # 2) Resolve the owning directory on disk if not already known.
        if not sessions_dir:
            # Check the active directory itself first 鈥?a disk-only session in
            # the global (normal-mode) directory is NOT covered by
            # _find_session_dir_anywhere, which only scans the *other*
            # directories (workspaces / iclaw / alternate global).
            active_dir = self._get_sessions_dir()
            if (pathlib.Path(active_dir) / session_id).is_dir():
                sessions_dir = active_dir
                found = True
            else:
                resolved = self._find_session_dir_anywhere(session_id, active_dir)
                if resolved is None:
                    return False
                sessions_dir = resolved
                found = True

        # 3) Persist the flag into the session's meta.json metadata so the
        #    index rebuild (bootstrap) can restore it after a restart.
        dir_path = pathlib.Path(sessions_dir) / session_id
        if dir_path.is_dir():
            meta = EncreSession.read_meta(str(dir_path))
            if meta is not None:
                meta_metadata = meta.get("metadata") or {}
                if bool(meta_metadata.get("archived", False)) != archived:
                    meta_metadata["archived"] = archived
                    meta["metadata"] = meta_metadata
                    payload = _json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
                    with contextlib.suppress(Exception):
                        payload = _encrypt(payload)
                    _atomic_write_text(dir_path / "meta.json", payload)
                found = True

        # 4) Update the flag in EVERY directory index that carries this
        #    session.  A session can legitimately appear in more than one
        #    workspace index (stale entries written before a workspace switch),
        #    so updating only the owning directory leaks the archived session
        #    back into the normal lists via the other index.
        active_dir = self._get_sessions_dir()
        for dir_path in self._all_sessions_dirs():
            index = self._load_index_for_dir(dir_path)
            if session_id not in index:
                continue
            index[session_id]["archived"] = archived
            self._save_index_for_dir(dir_path, index)
            # Keep the active in-memory index in sync when archiving the
            # active directory.
            if dir_path == active_dir:
                self._index = index
                self._index_dirty = False
        self._fire_sessions_changed()
        return found

    def list_archived_sessions(self) -> list[dict[str, Any]]:
        """Return archived sessions across every session directory.

        Mirrors the cross-directory scan used by the sidebar listing but keeps
        only entries flagged ``archived`` (in-memory + on-disk), sorted by
        last activity, newest first.
        """
        result: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _entry(info: SessionInfo | None, idx: dict[str, Any]) -> None:
            sid = idx.get("session_id", "")
            if not sid or sid in seen:
                return
            seen.add(sid)
            # Mirror the canonical workspace path into metadata so the archive
            # manager can render the owning-workspace icon (same shape as the
            # sidebar session rows).
            meta = dict(idx.get("metadata", {}) or {})
            ws = idx.get("workspace") or meta.get("workspace") or meta.get("workspace_path") or ""
            if ws:
                meta["workspace"] = ws
                meta["workspace_path"] = ws
            result.append({
                "session_id": sid,
                "created_at": idx.get("created_at", 0),
                "last_active": idx.get("last_active", 0),
                "state": self.get_session_state(sid) if info is not None else SessionState.IDLE.value,
                "metadata": meta,
                "preview": idx.get("preview", ""),
                "name": idx.get("name", ""),
                "channel": idx.get("channel", "normal"),
                "message_count": idx.get("message_count", 0),
            })

        # In-memory archived sessions (active + stashed pools).
        for pool in [self._sessions, *self._dir_sessions.values()]:
            for sid, info in pool.items():
                if not (info.metadata.get("archived") or (
                    hasattr(info.agent, "session")
                    and info.agent.session
                    and info.agent.session.metadata.get("archived")
                )):
                    continue
                idx = self._make_index_entry(info)
                _entry(info, idx)

        # On-disk archived entries across every directory.
        for dir_path in self._all_sessions_dirs():
            index = self._load_index_for_dir(dir_path)
            for sid, entry in index.items():
                if not entry.get("archived"):
                    continue
                # Skip orphan entries whose session directory does not live
                # in this directory 鈥?a session belongs to exactly one
                # workspace, and an orphan entry would report the wrong
                # workspace (wrong icon).
                if not os.path.isdir(os.path.join(dir_path, sid)):
                    continue
                fallback_active = entry.get("last_active", 0)
                last_active = EncreSession.read_meta_last_active(
                    os.path.join(dir_path, sid), fallback_active
                )
                entry = dict(entry)
                entry["last_active"] = last_active
                entry["metadata"] = {"workspace": entry.get("workspace", "")} if entry.get("workspace") else {}
                _entry(None, entry)

        result.sort(key=lambda e: e.get("last_active", e.get("created_at", 0)), reverse=True)
        return result

    def _all_sessions_dirs(self) -> list[str]:
        """Every sessions directory that can hold desktop sessions:
        the active one, the global one, iClaw, and every registered workspace.
        """
        dirs: list[str] = []
        active = self._get_sessions_dir()
        for d in (active, str(get_data_dir() / "sessions"), str(get_data_dir() / "iclaw" / "sessions")):
            if d not in dirs:
                dirs.append(d)
        try:
            iwork_root = get_data_dir() / "iwork"
            if iwork_root.is_dir():
                for ws_dir in iwork_root.iterdir():
                    if not ws_dir.is_dir():
                        continue
                    d = str(ws_dir / "sessions")
                    if d not in dirs:
                        dirs.append(d)
        except Exception:
            pass
        return dirs

    def rename_session(self, session_id: str, new_name: str, *, manual: bool = True) -> bool:
        """Rename a session by updating its display name in the index.

        The index entry lives in the session's OWN directory (the workspace
        or global dir it belongs to), so the rename must be written there 鈥?        never into the currently-active directory, which may be a different
        workspace and would create a foreign entry (data mismatch in the
        sidebar).
        """
        target_dir = ""
        info = self._sessions.get(session_id)
        if info is not None:
            target_dir = info.sessions_dir or self._get_sessions_dir()
        else:
            for sess_dict in self._dir_sessions.values():
                cached = sess_dict.get(session_id)
                if cached is not None:
                    target_dir = cached.sessions_dir or self._get_sessions_dir()
                    info = cached
                    break
        if not target_dir:
            active_dir = self._get_sessions_dir()
            if (pathlib.Path(active_dir) / session_id).is_dir():
                target_dir = active_dir
            else:
                resolved = self._find_session_dir_anywhere(session_id, active_dir)
                if resolved is None:
                    return False
                target_dir = resolved
        index = self._load_index_for_dir(target_dir)
        if session_id not in index:
            # Session may be in-memory only (not yet persisted to disk index).
            # Create a minimal index entry so the name persists.
            if info is None:
                return False
            index[session_id] = self._make_index_entry(info)
        index[session_id]["name"] = new_name
        self._save_index_for_dir(target_dir, index)
        if target_dir == self._get_sessions_dir():
            self._index = index
            self._index_dirty = False
        if info is not None:
            info.metadata["name"] = new_name
            if manual:
                info.metadata["name_manually_renamed"] = True
        self._fire_sessions_changed()
        return True

    def try_resume_most_recent(self, config: EncreConfig | None = None) -> SessionInfo | None:
        """Return the most-recently-active session, or None if the store is empty."""
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
        # Snapshot under the lock: the startup resume runs in a worker thread
        # and may insert into _sessions while we iterate.
        with self._lock:
            infos = list(self._sessions.values())
        for info in infos:
            # Skip temp chat sessions 鈥?they are ephemeral and must never
            # appear in the sidebar or any session listing.
            if hasattr(info.agent, "session") and info.agent.session and info.agent.session.metadata.get("temp_chat"):
                continue
            # Archived sessions are hidden from the normal sidebar; they are
            # only reachable through the archive manager view.
            if info.metadata.get("archived") or (
                hasattr(info.agent, "session")
                and info.agent.session
                and info.agent.session.metadata.get("archived")
            ):
                continue
            msg_count = 0
            preview = ""
            if hasattr(info.agent, "session") and info.agent.session:
                msg_count, preview = info.agent.session.get_summary()
            # Mirror the canonical workspace path into `workspace_path` so the
            # frontend's iWork sidebar filter can attribute this in-memory
            # session to exactly one workspace.  Some flows set
            # metadata["workspace"] but not workspace_path; without this,
            # a still-active session from ANOTHER workspace would be let
            # through (`!workspace_path` 鈫?show) into every workspace list.
            meta = dict(info.metadata)
            ws = meta.get("workspace") or (
                info.agent.session.metadata.get("workspace")
                if hasattr(info.agent, "session") and info.agent.session
                else None
            )
            if not ws:
                # Best-effort disk fallback: in-memory metadata can miss the
                # workspace when the session was loaded with a stale path; the
                # on-disk meta.json is the canonical record.  Only consulted
                # for sessions whose workspace is unknown (rare).
                try:
                    sid_dir = self._session_dir_path(info.session_id)
                    if sid_dir.is_dir():
                        _meta = EncreSession.read_meta(str(sid_dir))
                        if isinstance(_meta, dict):
                            ws = (
                                ((_meta.get("metadata", {}) or {}).get("workspace"))
                                or _meta.get("workspace")
                                or ""
                            )
                except Exception:
                    ws = ""
            if ws and "workspace_path" not in meta:
                meta["workspace"] = ws
                meta["workspace_path"] = ws
            result.append({
                "session_id": info.session_id,
                "created_at": info.created_at,
                "last_active": getattr(info.agent.session, "last_message_at", info.agent.session.updated_at) if hasattr(info.agent, "session") and info.agent.session else info.last_active,
                "state": info.state.value,
                "metadata": meta,
                "preview": preview,
                "name": info.metadata.get("name", self._index.get(info.session_id, {}).get("name", "")),
                "channel": (info.agent.session.metadata.get("channel") if hasattr(info.agent, "session") and info.agent.session and info.agent.session.metadata
                            else info.metadata.get("channel", "normal")),
                # Structured routing origin (Phase 5): set by the gateway
                # resolve_session() when an adapter forwards a SessionSource.
                # None for desktop/normal sessions (no platform origin).  The
                # frontend renders a platform badge when present.
                "source": info.metadata.get("source"),
                "message_count": msg_count,
            })
        return result

    def query_index(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """Return all sessions known from the on-disk index.

        Archived sessions are excluded by default; pass ``include_archived=True``
        to receive the full index (used by the archive manager view).
        """
        self._get_sessions_dir()
        if not self._index:
            self._bootstrap_index_from_disk()
        sessions_dir = self._get_sessions_dir()
        entries: list[dict[str, Any]] = []
        # Snapshot under the lock so a concurrent background session load
        # (startup resume in a worker thread) cannot resize the dict while we
        # iterate it.
        with self._lock:
            index_items = list(self._index.items())
        for sid, entry in index_items:
            # Always prefer the canonical last_message_at from meta.json so
            # the displayed timestamp does not get rewritten on every click.
            # Fall back to the persisted index value, then to 0.
            fallback_active = entry.get("last_active", 0)
            last_active = EncreSession.read_meta_last_active(
                os.path.join(sessions_dir, sid), fallback_active
            )
            entries.append({
                "session_id": sid,
                "created_at": entry.get("created_at", 0),
                "last_active": last_active,
                "state": SessionState.IDLE.value,
                "metadata": (
                    {"workspace": entry.get("workspace", "")}
                    if entry.get("workspace")
                    else {}
                ),
                "preview": entry.get("preview", ""),
                "name": entry.get("name", ""),
                "channel": entry.get("channel", "normal"),
                "message_count": entry.get("message_count", 0),
                "archived": entry.get("archived", False),
            })
        entries.sort(key=lambda e: e.get("last_active", e.get("created_at", 0)), reverse=True)
        if not include_archived:
            entries = [e for e in entries if not e.get("archived")]
        entries = [e for e in entries if (e.get("message_count") or 0) > 0]
        return entries

    async def cleanup_idle(self) -> int:
        """Drop in-memory sessions that have been idle past the timeout.

        Returns the number of sessions removed.  Running sessions are never
        evicted from memory.
        """
        now = time.time()
        to_remove: list[str] = []
        for sid, info in self._sessions.items():
            if now - info.last_active > self._idle_timeout and info.state == SessionState.IDLE:
                to_remove.append(sid)
        for sid in to_remove:
            await self.remove_session(sid)
        return len(to_remove)

    async def acquire_slot(self) -> bool:
        """Acquire a concurrency slot, waiting up to 30s.

        Returns True if a slot was obtained (the caller must later call
        :meth:`release_slot`), False on timeout (server at capacity).
        """
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=30.0)
            return True
        except TimeoutError:
            return False

    def release_slot(self) -> None:
        """Release a previously acquired concurrency slot."""
        with contextlib.suppress(ValueError):
            self._semaphore.release()

    # 鈹€鈹€ Async session persistence 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    _save_tasks: ClassVar[dict[str, asyncio.Task[None]]] = {}

    async def _save_session_async(self, info: SessionInfo) -> None:
        """Save session in an executor thread to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_session, info)

    def _schedule_save(self, info: SessionInfo) -> None:
        """Schedule a debounced save (coalesces rapid saves within 2s window)."""
        sid = info.session_id
        existing = self._save_tasks.get(sid)
        if existing and not existing.done():
            existing.cancel()
        self._save_tasks[sid] = asyncio.create_task(self._debounced_save(sid, info))

    async def _debounced_save(self, sid: str, info: SessionInfo) -> None:
        """Wait 2 seconds then persist. Cancelling the previous task for this
        session ID resets the timer, so rapid mutations only hit disk once."""
        try:
            await asyncio.sleep(2.0)
            self._save_tasks.pop(sid, None)
            await self._save_session_async(info)
        except asyncio.CancelledError:
            pass  # A newer save request superseded this one

    async def shutdown(self) -> None:
        """Flush pending saves and persist every session (active + stashed)."""
        # Flush any pending saves
        pending = [t for t in self._save_tasks.values() if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._save_tasks.clear()

        # Collect every session from the active pool and all stashed pools so
        # background sessions are persisted before the process exits.
        all_infos: list[SessionInfo] = list(self._sessions.values())
        seen_ids: set[str] = {info.session_id for info in all_infos}
        for sess_dict in self._dir_sessions.values():
            for info in sess_dict.values():
                if info.session_id not in seen_ids:
                    seen_ids.add(info.session_id)
                    all_infos.append(info)

        loop = asyncio.get_running_loop()
        for info in all_infos:
            if info.agent_task and not info.agent_task.done():
                info.agent_task.cancel()
            info.agent.telemetry.flush()
            await loop.run_in_executor(None, self._save_session, info)
