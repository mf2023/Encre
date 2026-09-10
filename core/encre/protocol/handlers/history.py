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

"""History domain handlers: search / rollback log+checkout / branches / replay.

Extracted verbatim from ``encre.transport.ws`` (architecture refactor
Stage 3 / Task 5.2); behaviour is unchanged, only the layout moved.
Outer-loop ``continue`` statements of the original dispatch chain became
``return`` inside the extracted methods.
"""

import asyncio
import contextlib
import json
import logging
import os
from typing import Any

from encre.server.protocol import (
    ClientReplayGetSession,
    ClientRollbackBranch,
    ClientRollbackCheckout,
    ClientRollbackLog,
    ClientSearch,
    ClientSwitchBranch,
)
from encre.server.session_manager import SessionState

logger = logging.getLogger("encre.transport.ws")


def _build_search_texts(dpath: str) -> list[dict[str, Any]]:
    """Extract user/assistant message texts from a session directory."""
    import pathlib

    from encre.crypto import decrypt

    msgs: list[dict[str, Any]] = []
    for fpath in sorted(pathlib.Path(dpath).iterdir()):
        if not fpath.name.startswith("turn_"):
            continue
        try:
            raw = fpath.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw:
            continue
        if not raw.startswith("["):
            with contextlib.suppress(Exception):
                raw = decrypt(raw)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        for m in data:
            role = m.get("role", "")
            if role not in ("user", "assistant"):
                continue
            content = m.get("content")
            if content is None:
                continue
            text = content if isinstance(content, str) else " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if text:
                msgs.append({"role": role, "text": text, "low": text.lower()})
    return msgs


class HistoryHandlers:
    """Conversation history search, rollback and replay handlers."""

    def _do_search(self, query: str) -> list[dict[str, Any]]:
        """Search sessions by message content.

        Returns at most ~60 results tagged ``conversation`` so the desktop
        search box can jump to a past turn. Workspace *file* search is handled
        entirely on the client side against **registered** workspaces only 鈥?        the backend never walks ``os.getcwd()`` so it can't surface files from
        unregistered directories.
        """
        import pathlib

        from encre.session import EncreSession

        q = query.strip().lower()
        if not q:
            return []

        sessions_dir = self._manager._get_sessions_dir()
        entries: list[tuple[float, str, str]] = []
        for entry in os.scandir(sessions_dir):
            if entry.is_dir() and not entry.name.startswith("."):
                last = EncreSession.read_meta_last_active(entry.path, 0.0)
                entries.append((last, entry.name, entry.path))
        entries.sort(key=lambda x: x[0], reverse=True)

        results: list[dict[str, Any]] = []
        for _last, sid, dpath in entries:
            if len(results) >= 60:
                break
            # User-managed session name lives in the manager's session index
            # (not in turn files), so it must be matched explicitly 鈥?this is
            # what makes "search by session name" work.
            name = ""
            try:
                name = str((self._manager._index.get(sid) or {}).get("name", "") or "")
            except Exception:
                name = ""
            if name and q in name.lower():
                preview = EncreSession.load_preview(dpath) or "Empty session"
                results.append({
                    "kind": "conversation",
                    "session_id": sid,
                    "role": "user",
                    "name": name,
                    "snippet": preview[:120],
                    "preview": preview,
                })
                continue
            msgs = _build_search_texts(dpath)
            hit: dict[str, Any] | None = None
            for msg in msgs:
                if q in msg["low"]:
                    idx = msg["low"].index(q)
                    text = msg["text"]
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(q) + 80)
                    hit = {
                        "kind": "conversation",
                        "session_id": sid,
                        "role": msg["role"],
                        "name": name,
                        "snippet": text[start:end].strip()[:120],
                    }
                    break
            if hit:
                hit["preview"] = EncreSession.load_preview(dpath) or "Empty session"
                results.append(hit)
        return results[:60]

    async def _h_search(self, ws: Any, msg: ClientSearch) -> None:
        # Echo the client's seq back so the frontend can drop
        # stale (out-of-order) responses.
        results = self._do_search(msg.query)
        await self._send(ws, "search_results", results=results, seq=msg.seq)

    async def _h_rollback_log(self, ws: Any, msg: ClientRollbackLog) -> None:
        sid = msg.session_id or self._current_session_id
        if not sid:
            await self._send(ws, "error", message="No active session", code="no_session")
            return
        from encre.rollback import EncreRollbackGit
        rb = EncreRollbackGit()
        commits = rb.tree(sid)
        await self._send(ws, "rollback_log", session_id=sid, commits=commits)

    async def _h_rollback_checkout(self, ws: Any, msg: ClientRollbackCheckout) -> None:
        sid = msg.session_id or self._current_session_id
        if not sid or not msg.commit_hash:
            await self._send(ws, "error",
                message="Missing session_id or commit_hash",
                code="invalid_request", session_id=sid or "")
            return
        session = self._manager.load_or_create_session(sid, config=self._default_config)
        # Cancel any running agent task before rollback to prevent
        # session state corruption (the running task's finally block
        # could overwrite the rollback's restored state).
        if session.agent_task and not session.agent_task.done():
            self._manager.set_session_state(session.session_id, SessionState.IDLE)
            session.agent.loop.cancel()
            session.agent_task.cancel()
            with contextlib.suppress(Exception):
                await session.agent.loop.backend.aclose()
            self._manager.release_slot()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(session.agent_task, timeout=0.5)
            session.agent_task = None
        from encre.rollback import EncreRollbackGit
        rb = EncreRollbackGit()
        ok = rb.checkout(session.agent.loop.session, msg.commit_hash)
        if not ok:
            await self._send(ws, "error",
                message=f"Commit not found: {msg.commit_hash[:8]}...",
                code="not_found", session_id=sid)
            return
        self._current_session_id = sid
        self._info = session
        await self._manager._save_session_async(session)
        s = session.agent.loop.session
        msgs = [m for m in s.messages if m.get("role") != "system"]
        # Find last user message text for input restoration
        user_input = ""
        for m in reversed(s.messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                user_input = c if isinstance(c, str) else ""
                break
        await self._send(ws, "rollback_checkout",
            session_id=sid, commit_hash=msg.commit_hash, messages=msgs,
            turn_count=s.turn_count,
            plan_items=s.plan_items,
            artifacts=s.artifacts,
            references=s.references,
            user_input=user_input)

    async def _h_switch_branch(self, ws: Any, msg: ClientSwitchBranch) -> None:
        sid = msg.session_id or self._current_session_id
        if not sid:
            await self._send(ws, "error", message="No active session", code="no_session")
            return
        info = self._manager.get_session(sid)
        if info is None:
            info = self._manager.load_or_create_session(sid, config=self._default_config)
        self._manager.touch(sid)
        sess = info.agent.session
        if msg.branch_id not in sess.branches:
            await self._send(ws, "error", message=f"Branch not found: {msg.branch_id}", code="branch_not_found",
                             session_id=sid)
            return
        sess.switch_branch(msg.branch_id)
        msgs = self._renderer_session_messages(sess)
        branches_list = [b.__dict__ for b in sess.branches.values()]
        await self._send(ws, "branch_switched",
            session_id=sid,
            branch_id=sess.active_branch_id,
            messages=msgs,
            branches=branches_list,
            artifacts=sess.artifacts,
            references=sess.references,
            tokens={"input": 0, "output": 0, "total": 0},
        )

    async def _h_rollback_branch(self, ws: Any, msg: ClientRollbackBranch) -> None:
        sid = msg.session_id or self._current_session_id
        if not sid:
            await self._send(ws, "error", message="No active session", code="no_session")
            return
        info = self._manager.get_session(sid)
        if info is None:
            info = self._manager.load_or_create_session(sid, config=self._default_config)
        self._manager.touch(sid)
        # Cancel any running agent task before rollback to prevent
        # session state corruption.
        if info.agent_task and not info.agent_task.done():
            self._manager.set_session_state(sid, SessionState.IDLE)
            info.agent.loop.cancel()
            info.agent_task.cancel()
            with contextlib.suppress(Exception):
                await info.agent.loop.backend.aclose()
            self._manager.release_slot()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(info.agent_task, timeout=0.5)
            info.agent_task = None
        self._info = info
        self._current_session_id = sid
        sess = info.agent.session
        removed, target_branch_id, target_found = sess.rollback_to(msg.branch_id, msg.message_id)
        if not target_found:
            await self._send(ws, "error", message="Message not found", code="rollback_error",
                             session_id=sid)
            return
        # Rollback restores the conversation to a previous state.
        # The compact summary (which summarised "future" work) is
        # now misleading 鈥?clear it so the next compact regenerates.
        sess.metadata.pop("user_requirements_summary", None)
        # rollback_to keeps the target message but the frontend
        # removes it locally (its content goes into the input box
        # for re-editing).  Remove it here too so that a page
        # refresh does NOT resurrect the rolled-back message.
        sess.messages = [
            m for m in sess.messages
            if not (
                m.get("branch_id") == target_branch_id
                and (
                    m.get("id", "").endswith(":M:" + msg.message_id)
                    or m.get("id") == msg.message_id
                )
            )
        ]
        # If the session is now empty after rollback, delete it
        # entirely so it does not reappear as a ghost entry in the
        # sidebar after restart.
        if not sess.messages:
            self._manager.delete_session_from_disk(sid)
            await self._send(ws, "session_deleted", session_id=sid)
            return
        try:
            _t = asyncio.ensure_future(self._manager._save_session_async(info))
            self._tasks.add(_t)
        except Exception:
            pass
        msgs = self._renderer_session_messages(sess)
        branches_list = [b.__dict__ for b in sess.branches.values()]
        await self._send(ws, "branch_switched",
            session_id=sid,
            branch_id=sess.active_branch_id,
            messages=msgs,
            branches=branches_list,
            artifacts=sess.artifacts,
            references=sess.references,
            tokens={"input": 0, "output": 0, "total": 0},
        )

    async def _h_replay_get_session(self, ws: Any, msg: ClientReplayGetSession) -> None:
        # Session replay: load the recorded telemetry JSONL and
        # return the full event stream + summary + turn boundaries
        # so the frontend can scrub through what the agent did.
        try:
            from encre.replay import ReplayPlayer
            _player = ReplayPlayer(msg.session_id)
            await self._send(ws, "replay_session",
                session_id=msg.session_id,
                summary=_player.summary(),
                events=[ev.to_dict() for ev in _player.event_stream()],
                turn_boundaries=_player.turn_boundaries(),
            )
        except Exception as _replay_exc:
            logger.warning("[ws] replay failed: %s", _replay_exc, exc_info=True)
            await self._send(ws, "replay_session",
                session_id=getattr(msg, "session_id", ""),
                summary={},
                events=[],
                turn_boundaries=[],
                error=str(_replay_exc),
            )
