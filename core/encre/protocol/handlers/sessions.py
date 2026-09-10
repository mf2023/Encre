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

"""Session domain handlers: list / new / delete / archive / export / rename.

Also hosts the unified session-list snapshot builder used by broadcasts
and the full-data push.  Extracted verbatim from ``encre.transport.ws``
(architecture refactor Stage 3 / Task 5.2); behaviour is unchanged, only
the layout moved.  Outer-loop ``continue`` statements of the original
dispatch chain became ``return`` inside the extracted methods.
"""

import asyncio
import base64
import contextlib
import json
import logging
import os
import shutil
from dataclasses import replace
from typing import Any

from encre.config import get_data_dir
from encre.protocol.handlers.workspace_store import (
    _get_workspace_dir,
    _load_workspaces,
    _make_workspace_id,
    _remove_session_from_workspace_indices,
)
from encre.server.protocol import (
    ClientArchiveSession,
    ClientDeleteSession,
    ClientExportSession,
    ClientExportSessionsBatch,
    ClientIclawResume,
    ClientListAllSessions,
    ClientListArchivedSessions,
    ClientListSessions,
    ClientNewSession,
    ClientRenameSession,
    ClientUnarchiveSession,
    encode_server_message,
)

logger = logging.getLogger("encre.transport.ws")


class SessionsHandlers:
    """Session lifecycle and snapshot handlers."""

    # 鈹€鈹€ Unified session-list snapshot 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _list_all_sessions(self, channel_filter: str | None = None) -> list[dict[str, Any]]:
        """List sessions -- combines in鈥憁emory sessions with on鈥慸isk index.

        When ``channel_filter`` is None, the workspace-channel filter applies
        automatically (``iwork`` in workspace mode, ``normal`` otherwise).
        Pass an explicit channel string to override (used by the tray popup to
        fetch both groups at once).

        The iwork view intentionally lists EVERY un-archived session across
        ALL registered workspaces (each row carries its owning
        ``workspace_path`` so the sidebar renders the owning workspace icon).
        The "new task" welcome wizard's workspace picker only decides where a
        NEW task is created 鈥?it never filters the sidebar history.
        """
        channel = channel_filter
        if channel is None:
            channel = "iwork" if self._workspace_path else "normal"

        def _matches(s: dict[str, Any]) -> bool:
            """True when the session belongs to the requested channel view.

            iwork sessions are NOT filtered by workspace: the sidebar shows
            every un-archived workspace's history at once, each attributed to
            its own workspace via ``workspace_path``.
            """
            sch = s.get("channel", "normal")
            if sch != channel:
                return False
            return True

        result = [s for s in self._manager.list_sessions() if _matches(s)]
        active_ids = {s["session_id"] for s in result}
        for entry in self._manager.query_index():
            if entry["session_id"] in active_ids:
                continue
            if not _matches(entry):
                continue
            result.append(entry)
            active_ids.add(entry["session_id"])

        # Include sessions managed by the EventRouter (iClaw desktop + QQ/Telegram etc. adapters)
        if self._adapter_manager and self._adapter_manager.router:
            router = self._adapter_manager.router
            for s in router.session_manager.list_sessions():
                if s["session_id"] in active_ids:
                    continue
                if not _matches(s):
                    continue
                result.append(s)
                active_ids.add(s["session_id"])
            for entry in router.session_manager.query_index():
                if entry["session_id"] in active_ids:
                    continue
                if not _matches(entry):
                    continue
                result.append(entry)
                active_ids.add(entry["session_id"])

        # include workspace sessions from workspace directories
        if channel == "iwork":
            workspaces = _load_workspaces()
            for ws in workspaces:
                ws_id = ws.get("id") or _make_workspace_id(ws["path"])
                ws_dir = _get_workspace_dir(ws_id)
                sess_dir = os.path.join(ws_dir, "sessions")
                idx_file = os.path.join(sess_dir, "index.json")
                if not os.path.isfile(idx_file):
                    continue
                try:
                    with open(idx_file, encoding="utf-8") as f:
                        raw = f.read().strip()
                    if raw and not raw.startswith("{"):
                        from encre.crypto import decrypt as _decrypt
                        with contextlib.suppress(Exception):
                            raw = _decrypt(raw)
                    ws_index = json.loads(raw)
                    if not isinstance(ws_index, dict):
                        continue
                except Exception:
                    continue
                for sid, entry in ws_index.items():
                    if sid in active_ids:
                        continue
                    ech = entry.get("channel", "iwork") or "iwork"
                    if ech in ("automation", "sub_agent"):
                        continue
                    # Skip orphan index entries whose session directory does
                    # not exist in THIS workspace 鈥?a session physically
                    # belongs to exactly one workspace directory, and an
                    # orphan entry (written into the wrong workspace's index
                    # before a fix) would otherwise hijack the session's
                    # workspace attribution and show the wrong icon.
                    if not os.path.isdir(os.path.join(sess_dir, sid)):
                        continue
                    # Archived sessions only surface in the archive manager.
                    if entry.get("archived"):
                        continue
                    active_ids.add(sid)
                    ws_path = ws.get("path", "")
                    # Use meta.json's last_message_at (the canonical "when was
                    # the last conversation") instead of the index entry so
                    # clicking a session in the sidebar never resets the
                    # displayed time.
                    from encre.session import EncreSession as _EncreSession
                    fallback_active = entry.get("last_active", 0)
                    last_active = _EncreSession.read_meta_last_active(
                        os.path.join(sess_dir, sid),
                        fallback_active,
                    )
                    result.append({
                        "session_id": sid,
                        "created_at": entry.get("created_at", 0),
                        "last_active": last_active,
                        "state": self._manager.get_session_state(sid),
                        "metadata": {"workspace": ws_path, "workspace_path": ws_path},
                        "preview": entry.get("preview", ""),
                        "name": entry.get("name", ""),
                        "channel": ech,
                        "message_count": entry.get("message_count", 0),
                    })

        # When in workspace mode, normal sessions live in the GLOBAL session
        # directory (not the workspace one).  We must read it directly since
        # self._manager only points to the workspace directory.
        if self._workspace_path:
            # ensure=False: index.json is a file, never mkdir() it (the
            # default ensure=True raised WinError 183 once the file existed).
            global_idx = str(get_data_dir("sessions", "index.json", ensure=False))
            if os.path.isfile(global_idx):
                try:
                    with open(global_idx, encoding="utf-8") as f:
                        raw = f.read().strip()
                    if raw and not raw.startswith("{"):
                        from encre.crypto import decrypt as _decrypt
                        with contextlib.suppress(Exception):
                            raw = _decrypt(raw)
                    g_index = json.loads(raw)
                    if isinstance(g_index, dict):
                        global_sess_dir = str(get_data_dir("sessions"))
                        for sid, entry in g_index.items():
                            if sid in active_ids:
                                continue
                            ech = entry.get("channel", "normal") or "normal"
                            if ech in ("automation", "sub_agent"):
                                continue
                            # Skip orphan entries whose session directory is
                            # not actually in the global dir (same reasoning as
                            # the workspace branch).
                            if not os.path.isdir(os.path.join(global_sess_dir, sid)):
                                continue
                            # Archived sessions only surface in the archive manager.
                            if entry.get("archived"):
                                continue
                            active_ids.add(sid)
                            # Same reasoning as the workspace branch above:
                            # always read the canonical last_message_at from
                            # meta.json so clicking a sidebar entry cannot
                            # rewrite the timestamp to "now".
                            from encre.session import EncreSession as _EncreSession
                            fallback_active = entry.get("last_active", 0)
                            last_active = _EncreSession.read_meta_last_active(
                                os.path.join(global_sess_dir, sid),
                                fallback_active,
                            )
                            result.append({
                                "session_id": sid,
                                "created_at": entry.get("created_at", 0),
                                "last_active": last_active,
                                "state": self._manager.get_session_state(sid),
                                "metadata": {},
                                "preview": entry.get("preview", ""),
                                "name": entry.get("name", ""),
                                "channel": ech,
                                "message_count": entry.get("message_count", 0),
                            })
                except Exception:
                    pass

        result.sort(key=lambda s: s.get("last_active", s.get("created_at", 0)), reverse=True)
        result = [s for s in result if (s.get("message_count") or 0) > 0 and s.get("channel", "normal") not in ("automation", "sub_agent")]

        # 鈹€鈹€ Workspace-channel filter 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        expected_channel = ("iwork" if self._workspace_path else "normal") if channel_filter is None else channel_filter
        result = [s for s in result if s.get("channel", "normal") == expected_channel]

        # 鈹€鈹€ Exclude temp chats from the sidebar 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        result = [s for s in result if not s.get("temp_chat") and not s.get("metadata", {}).get("temp_chat")]

        # 鈹€鈹€ Exclude archived sessions (only visible in the archive view) 鈹€鈹€
        result = [s for s in result if not s.get("archived")]

        # 鈹€鈹€ Workspace attribution fallback (icon stability) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        # A session's workspace MUST be resolved from its physical directory
        # 鈥?the only authoritative source.  In-memory metadata or meta.json
        # can miss the workspace on legacy/archived sessions, which made the
        # sidebar icon flicker between surfaces (the same session resolving
        # to different workspaces on different list paths).  Fill any iwork
        # session that still lacks a workspace path by mapping its directory's
        # ws_id back to the registered workspace path.
        ws_id_to_path: dict[str, str] = {}
        try:
            for _w in _load_workspaces():
                _wid = _w.get("id") or _make_workspace_id(_w["path"])
                ws_id_to_path[_wid] = _w["path"]
        except Exception:
            pass
        for _s in result:
            if _s.get("channel") != "iwork":
                continue
            _meta = _s.get("metadata") or {}
            if _meta.get("workspace_path") or _meta.get("workspace"):
                continue
            _p = None
            try:
                _d = self._manager._session_dir_path(_s["session_id"])
                # <data>/iwork/{ws_id}/sessions/{sid} 鈫?ws_id = parent.parent.name
                _p = ws_id_to_path.get(_d.parent.parent.name)
            except Exception:
                _p = None
            if _p:
                _s["metadata"] = {**_meta, "workspace": _p, "workspace_path": _p}

        return result

    def _list_archived_sessions(self) -> list[dict[str, Any]]:
        """All archived sessions across the local manager and the EventRouter.

        Feeds the archive manager view in the workspace management dialog.
        Sorted by last activity, newest first.
        """
        result = self._manager.list_archived_sessions()
        seen = {s["session_id"] for s in result}
        if self._adapter_manager and self._adapter_manager.router:
            router = self._adapter_manager.router
            for s in router.session_manager.list_archived_sessions():
                if s["session_id"] not in seen:
                    result.append(s)
                    seen.add(s["session_id"])
        # Same physical-directory attribution fallback as _list_all_sessions,
        # so archived rows show the owning workspace's real icon too.
        ws_id_to_path: dict[str, str] = {}
        try:
            for _w in _load_workspaces():
                _wid = _w.get("id") or _make_workspace_id(_w["path"])
                ws_id_to_path[_wid] = _w["path"]
        except Exception:
            pass
        for _s in result:
            _meta = _s.get("metadata") or {}
            if _meta.get("workspace_path") or _meta.get("workspace"):
                continue
            _p = None
            try:
                _d = self._manager._session_dir_path(_s["session_id"])
                _p = ws_id_to_path.get(_d.parent.parent.name)
            except Exception:
                _p = None
            if _p:
                _s["metadata"] = {**_meta, "workspace": _p, "workspace_path": _p}
        result.sort(key=lambda s: s.get("last_active", s.get("created_at", 0)), reverse=True)
        return result

    async def _broadcast_archived_sessions(self) -> None:
        """Push the latest archived session list to all connected clients.

        Fired after archive / unarchive / delete so the archive manager view
        stays in sync in real time, mirroring ``_broadcast_sessions``.
        """
        if not self._connections:
            return
        sessions = await asyncio.to_thread(self._list_archived_sessions)

        async def _try_send(ws_conn: Any, payload_sessions: list) -> None:
            encrypt = self._client_encrypted if self._client_encrypted is not None else False
            try:
                payload = encode_server_message(
                    "archived_sessions_list",
                    encrypt=encrypt,
                    sessions=payload_sessions,
                )
                await ws_conn.send(payload)
            except Exception as exc:
                logger.warning("[broadcast] archived send failed (will remove connection): %s", exc)
                with contextlib.suppress(ValueError):
                    self._connections.remove(ws_conn)

        for ws in list(self._connections):
            try:
                _t = asyncio.ensure_future(_try_send(ws, sessions))
                self._tasks.add(_t)
            except Exception as exc:
                logger.warning("[broadcast] archived schedule send failed: %s", exc)

    def _broadcast_sessions(self) -> None:
        """Broadcast updated session list to all connected desktop clients.

        Registered as a callback on SessionManager so it fires whenever
        a session is created, updated, or deleted -- including from adapter
        (QQ/Telegram) and iClaw flows.
        """
        if not self._connections:
            logger.info("[broadcast] skipping -- no connections")
            return
        channel = "iwork" if self._workspace_path else "normal"
        sessions = self._list_all_sessions(channel_filter=channel)
        logger.info("[broadcast] %d sessions to %d connection(s)",
                    len(sessions), len(self._connections))

        async def _try_send(ws_conn: Any, payload_sessions: list, payload_channel: str) -> None:
            """Send sessions_list to one connection without cascading to _cancel_current_task."""
            encrypt = self._client_encrypted if self._client_encrypted is not None else False
            try:
                payload = encode_server_message(
                    "sessions_list",
                    encrypt=encrypt,
                    sessions=payload_sessions,
                    channel=payload_channel,
                )
                await ws_conn.send(payload)
            except Exception as exc:
                logger.warning("[broadcast] send failed (will remove connection): %s", exc)
                # Remove the dead connection so it doesn't accumulate.
                with contextlib.suppress(ValueError):
                    self._connections.remove(ws_conn)

        closed: list[Any] = []
        for ws in self._connections:
            try:
                _t = asyncio.ensure_future(_try_send(ws, sessions, channel))
                self._tasks.add(_t)
            except Exception as exc:
                logger.warning("[broadcast] schedule send failed: %s", exc)
                closed.append(ws)
        for ws in closed:
            with contextlib.suppress(ValueError):
                self._connections.remove(ws)

    # 鈹€鈹€ Client message handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _h_list_sessions(self, ws: Any, msg: ClientListSessions) -> None:
        # Disk I/O (per-session meta reads + workspace indexes)
        # must not block the dispatch loop -- other requests and
        # the background resume share this loop.
        sessions = await asyncio.to_thread(self._list_all_sessions)
        channel = "iwork" if self._workspace_path else "normal"
        await self._send(ws, "sessions_list", sessions=sessions, channel=channel)

    async def _h_list_all_sessions(self, ws: Any, msg: ClientListAllSessions) -> None:
        # Tray popup needs both modes' sessions at once.  Build
        # both lists in one worker thread (query_index results are
        # memoised, so the second pass is cheap).
        def _build_both():
            return (
                self._list_all_sessions(channel_filter="normal"),
                self._list_all_sessions(channel_filter="iwork"),
            )
        normal, iwork = await asyncio.to_thread(_build_both)
        await self._send(ws, "sessions_all", normal=normal, iwork=iwork)

    async def _h_new_session(self, ws: Any, msg: ClientNewSession) -> None:
        from encre.protocol.handlers.workspace_store import _apply_workspace_config
        if self._info:
            real_msgs = [m for m in self._info.agent.session.messages if m.get("role") != "system"]
            if not real_msgs:
                await self._manager.remove_session(self._info.session_id)
        # Use workspace config if currently in workspace mode
        if self._workspace_path and os.path.isdir(self._workspace_path):
            ws_config = replace(self._default_config, workspace=self._workspace_path)
            _apply_workspace_config(ws_config, self._workspace_path)
        else:
            ws_config = replace(self._default_config, workspace="")
        self._info = self._manager.create_session(config=ws_config)
        self._current_session_id = self._info.session_id
        # Tag the session with its channel immediately so
        # _list_all_sessions filters it into the correct sidebar
        self._info.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"
        await self._send(ws, "session_ready", session_id=self._info.session_id, plan_items=[], request_id=msg.request_id)
        # Authoritatively clear chip state for the brand-new session.  The
        # frontend clears its own chips optimistically on session_ready, but
        # this mode_changed("") is the backend's source of truth: without it
        # any in-flight or stale event could re-introduce the PREVIOUS
        # session's mode into the new conversation.
        await self._send_session_mode(ws, self._info)
        await self._send_session_command(ws, self._info)

    async def _h_delete_session(self, ws: Any, msg: ClientDeleteSession) -> None:
        if not msg.session_id:
            await self._send(ws, "error", message="No session_id provided", code="invalid_request")
            return
        if self._current_session_id == msg.session_id:
            self._current_session_id = None
            self._info = None
        # Drop the deleted session's spec engine so its state cannot be
        # resurrected if a new session ever reuses the id slot.
        self._spec_engines.pop(msg.session_id, None)
        from encre.config import get_data_dir as _get_data_dir
        ok = self._manager.delete_session_from_disk(msg.session_id)
        # Also clean up from EventRouter's session manager so the
        # session doesn't reappear when list_sessions is called.
        if self._adapter_manager and self._adapter_manager.router:
            self._adapter_manager.router.session_manager.delete_session_from_disk(msg.session_id)
        # Also clean up workspace session indices so the session
        # doesn't reappear when list_sessions reloads from workspace dirs.
        _remove_session_from_workspace_indices(msg.session_id)
        # Also clean up sub-agent session directory (automation history entries)
        sub_agent_dir = _get_data_dir() / "sub_agents" / msg.session_id
        had_sub_agent = sub_agent_dir.is_dir()
        if had_sub_agent:
            shutil.rmtree(str(sub_agent_dir))
            ok = True
        # Remove automation history entry if scheduler exists
        if self._scheduler:
            self._scheduler.delete_job_execution_by_session_id(msg.session_id)
        # Always broadcast automation update when a sub-agent session
        # is deleted so the history list refreshes immediately,
        # regardless of whether the scheduler found a matching entry.
        if self._scheduler and had_sub_agent:
            self.broadcast_automation_update()
        if ok:
            await self._send(ws, "session_deleted", session_id=msg.session_id)
        else:
            await self._send(ws, "error", message="Session not found", code="not_found")
        # The deleted session may have been archived; refresh the
        # archive view so it disappears from there too.
        await self._broadcast_archived_sessions()

    async def _h_archive_session(self, ws: Any, msg: ClientArchiveSession) -> None:
        if not msg.session_id:
            await self._send(ws, "error", message="No session_id provided", code="invalid_request")
            return
        ok = self._manager.archive_session(msg.session_id)
        # Keep the EventRouter's manager in sync for adapter sessions.
        if self._adapter_manager and self._adapter_manager.router:
            self._adapter_manager.router.session_manager.archive_session(msg.session_id)
        # Sidebar refreshes (the session drops out of the lists)
        # and the archive view refreshes.
        self._broadcast_sessions()
        await self._broadcast_archived_sessions()
        if not ok:
            await self._send(ws, "error", message="Session not found", code="not_found")

    async def _h_unarchive_session(self, ws: Any, msg: ClientUnarchiveSession) -> None:
        if not msg.session_id:
            await self._send(ws, "error", message="No session_id provided", code="invalid_request")
            return
        ok = self._manager.unarchive_session(msg.session_id)
        if self._adapter_manager and self._adapter_manager.router:
            self._adapter_manager.router.session_manager.unarchive_session(msg.session_id)
        # The session returns to the sidebar and leaves the archive view.
        self._broadcast_sessions()
        await self._broadcast_archived_sessions()
        if not ok:
            await self._send(ws, "error", message="Session not found", code="not_found")

    async def _h_list_archived_sessions(self, ws: Any, msg: ClientListArchivedSessions) -> None:
        sessions = await asyncio.to_thread(self._list_archived_sessions)
        await self._send(ws, "archived_sessions_list", sessions=sessions)

    async def _h_export_session(self, ws: Any, msg: ClientExportSession) -> None:
        if not msg.session_id:
            await self._send(ws, "error", message="No session_id provided", code="invalid_request")
            return
        from encre.session import EncreSession
        dir_path = self._manager._session_dir_path(msg.session_id)
        if not dir_path.is_dir():
            await self._send(ws, "error", message="Session not found", code="not_found")
            return
        try:
            md = EncreSession.export_to_markdown(str(dir_path))
            name = self._manager._index.get(msg.session_id, {}).get("name", msg.session_id[:8])
            filename = f"{name or msg.session_id[:8]}.md"
            await self._send(ws, "session_exported", session_id=msg.session_id, markdown=md, filename=filename)
        except Exception as e:
            logger.error(f"Export session failed: {e}")
            await self._send(ws, "error", message=str(e), code="export_error")

    async def _h_export_sessions_batch(self, ws: Any, msg: ClientExportSessionsBatch) -> None:
        if not msg.session_ids:
            await self._send(ws, "error", message="No session_ids provided", code="invalid_request")
            return
        from encre.session import EncreSession
        # NOTE: do not re-import base64 here -- a function-level
        # import would shadow the module-level name for the WHOLE
        # handle() scope and break earlier branches (e.g. icon
        # upload) with UnboundLocalError.
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for sid in msg.session_ids:
                dir_path = self._manager._session_dir_path(sid)
                if not dir_path or not dir_path.is_dir():
                    continue
                try:
                    md = EncreSession.export_to_markdown(str(dir_path))
                    name = self._manager._index.get(sid, {}).get("name", sid[:8])
                    # Organise into workspace subfolder if applicable
                    ws_path = self._manager._index.get(sid, {}).get("workspace", "") or ""
                    if ws_path:
                        ws_dir = os.path.basename(ws_path.rstrip("/\\"))
                        arcname = f"{ws_dir}/{name or sid[:8]}.md"
                    else:
                        arcname = f"{name or sid[:8]}.md"
                    zf.writestr(arcname, md)
                except Exception:
                    continue
        zip_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        fname = f"encre-export-{len(msg.session_ids)}-sessions.zip"
        await self._send(ws, "sessions_exported_zip", zip_base64=zip_b64, filename=fname)

    async def _h_rename_session(self, ws: Any, msg: ClientRenameSession) -> None:
        if not msg.session_id or not msg.new_name.strip():
            await self._send(ws, "error", message="Missing session_id or new_name", code="invalid_request")
            return
        new_name = msg.new_name.strip()
        ok = self._manager.rename_session(msg.session_id, new_name)
        if ok:
            await self._send(ws, "session_renamed", session_id=msg.session_id, new_name=new_name)
            # Sidebar + tray names come from the unified session
            # list 鈥?broadcast the refreshed snapshot.
            self._broadcast_sessions()
        else:
            await self._send(ws, "error", message="Session not found", code="not_found")

    async def _h_iclaw_resume(self, ws: Any, msg: ClientIclawResume) -> None:
        logger.info("[iclaw] resume requested")
        router = self._adapter_manager.router if self._adapter_manager else None
        if router:
            async with router.iclaw_context():
                existing = router.session_manager.try_resume_most_recent(
                    config=replace(self._default_config, workspace=""))
                if existing is not None:
                    msgs = self._renderer_session_messages(existing.agent.session)
                    self._current_session_id = existing.session_id
                    await self._send(ws, "session_ready",
                        session_id=existing.session_id, messages=msgs)
                    logger.info("[iclaw] resume sent session_ready with %d messages sid=%s",
                                len(msgs), existing.session_id)
                else:
                    logger.info("[iclaw] no session to resume")
        else:
            logger.warning("[iclaw] no router available for resume")
