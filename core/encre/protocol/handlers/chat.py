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

"""Chat-domain handlers.

Question responses, cancel, steer and chat-history message editing.
Extracted verbatim from ``encre.transport.ws`` (architecture refactor
Stage 3 / Task 5.2); behaviour is unchanged, only the layout moved.
Outer-loop ``continue`` statements of the original dispatch chain became
``return`` inside the extracted methods.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

from encre.server.protocol import (
    ClientCancel,
    ClientDeleteMessage,
    ClientEditMessage,
    ClientRespondQuestion,
    ClientSteer,
)
from encre.server.session_manager import SessionState

logger = logging.getLogger("encre.transport.ws")


class ChatHandlers:
    """Interactive chat control and history-editing handlers."""

    async def _h_respond_question(self, ws: Any, msg: ClientRespondQuestion) -> None:
        session = (
            self._manager.get_session(self._current_session_id)
            if self._current_session_id else None
        )
        if session is None:
            session = self._get_or_create_session()
        self._manager.touch(session.session_id)
        session.agent.loop.resolve_question(msg.answers)

    async def _h_cancel(self, ws: Any, msg: ClientCancel) -> None:
        # iClaw task cancel (runs concurrently in its own task)
        if self._iclaw_task and not self._iclaw_task.done():
            # Also cancel the agent loop so the EventRouter stops promptly
            sid = msg.session_id or self._current_session_id or ""
            if sid and self._adapter_manager and self._adapter_manager.router:
                info = self._adapter_manager.router.session_manager.get_session(sid)
                if info and info.agent.loop:
                    info.agent.loop.cancel()
            self._iclaw_task.cancel()
            await self._send(ws, "finish", reason="cancelled", session_id=sid)
            return

        # Try EventRouter cancel_session as fallback (for adapter/gateway flows)
        if self._adapter_manager and self._adapter_manager.router:
            sid = msg.session_id or self._current_session_id or ""
            if sid and self._adapter_manager.router.cancel_session(sid):
                await self._send(ws, "finish", reason="cancelled", session_id=sid)
                return

        session = None
        if msg.session_id:
            session = self._manager.get_session(msg.session_id)
        if session is None and self._current_session_id:
            session = self._manager.get_session(self._current_session_id)
        if session is None:
            return
        self._manager.touch(session.session_id)
        if session.agent_task and not session.agent_task.done():
            self._manager.set_session_state(session.session_id, SessionState.IDLE)
            session.agent.loop.cancel()
            session.agent_task.cancel()
            # Force-close the backend HTTP client so any in-flight
            # API request is aborted immediately instead of blocking
            # until the 120s timeout.  This lets the old task unwind
            # promptly.  The backend will be rebuilt on the next run.
            with contextlib.suppress(Exception):
                await session.agent.loop.backend.aclose()
            self._manager.release_slot()
            await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)
        else:
            self._manager.set_session_state(session.session_id, SessionState.IDLE)
            self._manager.release_slot()
            await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)

    async def _h_steer(self, ws: Any, msg: ClientSteer) -> None:
        sid = msg.session_id or self._current_session_id or ""
        if sid:
            info = self._manager.get_session(sid)
        else:
            info = self._get_or_create_session()
        if info and info.agent and info.agent.loop:
            info.agent.loop._steer_queue.push(msg.prompt or "")
            logger.info("[steer] queued instruction for session=%s", info.session_id)
            await self._send(ws, "steer_queued", session_id=info.session_id)
        else:
            await self._send(ws, "steer_queued", session_id=sid, error="no_active_session")

    async def _h_edit_message(self, ws: Any, msg: ClientEditMessage) -> None:
        session = self._get_or_create_session()
        self._manager.touch(session.session_id)
        try:
            await self._edit_message(session, msg.message_index, msg.new_content)
            msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]
            head = session.agent.loop.rollback.head(session.agent.session.id) or ""
            await self._send(ws, "messages_updated", messages=msgs,
                             session_id=session.session_id, commit_hash=head,
                             plan_items=session.agent.session.plan_items,
                             artifacts=session.agent.session.artifacts,
                             references=session.agent.session.references)
        except Exception as e:
            logger.error(f"Edit message failed: {e}")
            await self._send(ws, "error", message=str(e), code="edit_error",
                             session_id=session.session_id)

    async def _h_delete_message(self, ws: Any, msg: ClientDeleteMessage) -> None:
        session = self._get_or_create_session()
        self._manager.touch(session.session_id)
        if session.state != SessionState.IDLE:
            await self._send(ws, "error", message="Session is running, cannot delete messages", code="busy",
                             session_id=session.session_id)
            return
        try:
            await self._delete_message(session, msg.message_index)
            # If the session is now empty after deleting the last
            # message, remove it entirely so it does not reappear
            # as a ghost entry in the sidebar after restart.
            if not session.agent.session.messages:
                sid = session.session_id
                self._manager.delete_session_from_disk(sid)
                self._current_session_id = None
                self._info = None
                await self._send(ws, "session_deleted", session_id=sid)
                return
            msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]
            head = session.agent.loop.rollback.head(session.agent.session.id) or ""
            await self._send(ws, "messages_updated", messages=msgs,
                             session_id=session.session_id, commit_hash=head,
                             plan_items=session.agent.session.plan_items,
                             artifacts=session.agent.session.artifacts,
                             references=session.agent.session.references)
        except Exception as e:
            logger.error(f"Delete message failed: {e}")
            await self._send(ws, "error", message=str(e), code="delete_error",
                             session_id=session.session_id)

    async def _edit_message(self, session: Any, index: int, new_content: str) -> None:
        """Edit a user message -- commit current state, modify, truncate subsequent.

        ``index`` is the user-role-only index (0 = first user message),
        matching the frontend's ``data-user-idx``.
        """
        sess = session.agent.session
        msgs = list(sess.messages)
        user_idx = -1
        for i, m in enumerate(msgs):
            if m.get("role") == "user":
                user_idx += 1
                if user_idx == index:
                    from encre.session import _extract_file_paths_from_messages
                    session.agent.loop.rollback.commit(
                        sess, f"before_edit_msg_{index}")
                    # Restore only file snapshots from the truncated turns;
                    # leave files touched by kept messages untouched.
                    removed_files = _extract_file_paths_from_messages(msgs[i + 1:])
                    kept_files = _extract_file_paths_from_messages(msgs[:i + 1])
                    files_to_restore = removed_files - kept_files
                    restored = sess.restore_file_snapshots_for_paths(files_to_restore)
                    if restored:
                        logger.info("[edit_msg] restored %d file(s) from snapshots", restored)
                    m["content"] = new_content
                    sess.messages = msgs[:i + 1]
                    sess.turn_count = max(1, index + 1)
                    sess.updated_at = time.time()
                    sess.rebuild_runtime_caches()
                    session.agent.loop.rollback.commit(
                        sess, f"edit_msg_{index}")
                    if not sess.metadata.get("temp_chat"):
                        await self._manager._save_session_async(session)
                    return
        raise ValueError(f"Message index {index} not found")

    async def _delete_message(self, session: Any, index: int) -> None:
        """Delete a user message and all subsequent -- commit current state first.

        ``index`` is the user-role-only index (0 = first user message),
        matching the frontend's ``data-user-idx``.
        """
        sess = session.agent.session
        msgs = list(sess.messages)
        user_idx = -1
        for i, m in enumerate(msgs):
            if m.get("role") == "user":
                user_idx += 1
                if user_idx == index:
                    from encre.session import _extract_file_paths_from_messages
                    session.agent.loop.rollback.commit(
                        sess, f"before_delete_msg_{index}")
                    # Restore only file snapshots from the deleted turns;
                    # leave files touched by kept messages untouched.
                    removed_files = _extract_file_paths_from_messages(msgs[i:])
                    kept_files = _extract_file_paths_from_messages(msgs[:i])
                    files_to_restore = removed_files - kept_files
                    restored = sess.restore_file_snapshots_for_paths(files_to_restore)
                    if restored:
                        logger.info("[delete_msg] restored %d file(s) from snapshots", restored)
                    sess.messages = msgs[:i]
                    sess.turn_count = max(1, index)
                    sess.updated_at = time.time()
                    sess.rebuild_runtime_caches()
                    session.agent.loop.rollback.commit(
                        sess, f"delete_msg_{index}")
                    if not sess.metadata.get("temp_chat"):
                        await self._manager._save_session_async(session)
                    return
        raise ValueError(f"Message index {index} not found")
