#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Encre gateway session routing: structured source identity + persistence.

This module aligns Encre's inbound routing with the Hermes gateway contract
(``gateway-internals.md`` / ``relay-connector-contract.md``):

- :class:`SessionSource` -- the structured origin of a message (platform,
  chat_id, chat_type, user, thread, scope).  Replaces the opaque ``session_id``
  routing Encre used before, so a conversation is identified by *where* it
  came from rather than by an adapter-chosen id.
- :func:`build_session_key` -- the single source of truth that turns a
  :class:`SessionSource` into a deterministic key
  (``agent:main:{platform}:{chat_type}:{chat_id}[:{thread_id}][:{user_id}]``).
  Mirrors ``gateway.session.build_session_key`` in Hermes so the wire contract
  matches.
- :class:`SessionStore` -- a SQLite-backed map from session_key to the agent
  loop's ``session_id`` (the transcript identity).  This is Encre's equivalent
  of Hermes' ``gateway_routing`` table: it persists the routing decision so a
  follow-up message from the same conversation resumes the same agent session.

Design notes:

- Encre's adapters identify their platform by a plain ``name`` string (not a
  ``Platform`` enum), so :attr:`SessionSource.platform` is ``str`` here.  The
  key format is otherwise byte-identical to Hermes for the common cases.
- Platform-specific canonicalization (e.g. WhatsApp JID/LID flip) is deferred;
  the contract leaves room for it via :meth:`SessionSource.canonicalize`.
- :class:`SessionStore` is sync (a single locked connection) -- the inbound
  path is not hot enough to justify aiosqlite, and keeping it sync avoids
  event-loop coupling for a routing lookup.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from encre.config import get_data_dir

logger = logging.getLogger("encre.gateway.session")

# Default session-key namespace.  Mirrors Hermes ``agent:main``; a non-default
# profile namespaces multiplexed gateways (``agent:{profile}``).
_DEFAULT_NAMESPACE = "agent:main"


def _session_key_namespace(profile: str | None) -> str:
    """Resolve the session-key namespace for a profile.

    ``None`` (the common case) yields the legacy ``agent:main`` namespace so
    non-multiplexing gateways produce byte-identical keys.
    """
    if profile is None:
        return _DEFAULT_NAMESPACE
    return f"agent:{profile}"


@dataclass
class SessionSource:
    """Structured origin of an inbound message.

    Replaces the flat ``chat_id``/``user_id`` fields on :class:`MessageEvent`
    with a single routing identity.  Used to:

    1. Build a deterministic :func:`build_session_key` for routing.
    2. Persist the routing decision in :class:`SessionStore`.
    3. Project platform origin into the system prompt and the desktop UI.

    Mirrors ``gateway.session.SessionSource`` in Hermes.  ``platform`` is a
    plain ``str`` in Encre (adapters use the class ``name`` attribute, not an
    enum).  ``is_bot`` is intentionally NOT serialized on the wire in v1 --
    it stays a gateway-side attribute only (see the relay connector contract).
    """

    platform: str
    chat_id: str
    chat_type: str = "dm"  # "dm" | "group" | "channel" | "thread" | "forum"
    chat_name: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    thread_id: str | None = None  # forum topics, Discord/Slack threads
    chat_topic: str | None = None  # channel description (Discord, Slack)
    user_id_alt: str | None = None  # stable alt id (Signal UUID, Feishu union_id)
    chat_id_alt: str | None = None  # alternate chat id (Signal group internal id)
    scope_id: str | None = None  # platform-neutral scope (Discord guild / Slack workspace)
    is_bot: bool = False  # gateway-side only; NOT serialized on the wire

    def canonicalize(self) -> "SessionSource":
        """Hook for platform-specific id canonicalization.

        Hermes canonicalizes WhatsApp JID/LID aliases here so a reshuffled
        alias form does not split one conversation into two sessions.  Encre
        returns ``self`` unchanged; adapters that need canonicalization can
        override this (or we add a per-platform hook later).
        """
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the wire / persistence.

        Always sends the discriminator fields (``platform``/``chat_id``/
        ``chat_type``/``chat_name``/``user_id``/``user_name``/``thread_id``/
        ``chat_topic``); the rest are included only when set.  ``is_bot`` is
        deliberately omitted (gateway-side attribute only).
        """
        d: dict[str, Any] = {
            "platform": self.platform,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "chat_name": self.chat_name,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "thread_id": self.thread_id,
            "chat_topic": self.chat_topic,
        }
        if self.user_id_alt is not None:
            d["user_id_alt"] = self.user_id_alt
        if self.chat_id_alt is not None:
            d["chat_id_alt"] = self.chat_id_alt
        if self.scope_id is not None:
            d["scope_id"] = self.scope_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionSource":
        """Reconstruct from a wire/persistence dict.

        Unknown keys are ignored (forward-compat).  Missing optional fields
        default to ``None``.
        """
        return cls(
            platform=str(d.get("platform", "")),
            chat_id=str(d.get("chat_id", "")),
            chat_type=str(d.get("chat_type", "dm")),
            chat_name=d.get("chat_name"),
            user_id=d.get("user_id"),
            user_name=d.get("user_name"),
            thread_id=d.get("thread_id"),
            chat_topic=d.get("chat_topic"),
            user_id_alt=d.get("user_id_alt"),
            chat_id_alt=d.get("chat_id_alt"),
            scope_id=d.get("scope_id"),
        )


def build_session_key(
    source: SessionSource,
    *,
    group_sessions_per_user: bool = True,
    thread_sessions_per_user: bool = False,
    profile: str | None = None,
) -> str:
    """Build a deterministic session key from a message source.

    This is the single source of truth for session-key construction -- the
    Encre conformance oracle for inbound routing.  Mirrors Hermes'
    ``build_session_key`` so the two produce byte-identical keys for the same
    source.

    Format: ``{ns}:{platform}:{chat_type}[:{chat_id}][:{thread_id}][:{user_id}]``

    DM rules:
      - DMs include ``chat_id`` when present (each private conversation isolated).
      - ``thread_id`` further differentiates threaded DMs.
      - Without ``chat_id``, falls back to the sender's id (``user_id_alt`` or
        ``user_id``) so DMs without a chat id stay per-user isolated.
      - Without either, a bare per-platform DM sink is used.

    Group/channel rules:
      - ``chat_id`` identifies the parent group/channel.
      - ``user_id``/``user_id_alt`` isolates participants when
        ``group_sessions_per_user`` is enabled.
      - ``thread_id`` differentiates threads within the parent chat.  When
        ``thread_sessions_per_user`` is False (default), threads are *shared*
        across participants -- ``user_id`` is NOT appended, so every user in
        the thread shares one session (the expected UX for forum topics /
        Discord / Slack threads).

    Args:
        source: The message origin.
        group_sessions_per_user: If True, isolate group sessions per user.
        thread_sessions_per_user: If True, isolate thread sessions per user
            (default False = shared threads).
        profile: Optional key-namespace profile (multiplexed gateways).

    Returns:
        A deterministic ``:``-delimited session key.
    """
    ns = _session_key_namespace(profile)
    platform = source.platform

    if source.chat_type == "dm":
        if source.chat_id:
            if source.thread_id:
                return f"{ns}:{platform}:dm:{source.chat_id}:{source.thread_id}"
            return f"{ns}:{platform}:dm:{source.chat_id}"
        # No chat_id -- fall back to the sender before the bare per-platform sink.
        participant = source.user_id_alt or source.user_id
        if participant:
            if source.thread_id:
                return f"{ns}:{platform}:dm:{participant}:{source.thread_id}"
            return f"{ns}:{platform}:dm:{participant}"
        if source.thread_id:
            return f"{ns}:{platform}:dm:{source.thread_id}"
        return f"{ns}:{platform}:dm"

    # group / channel / thread / forum
    participant = source.user_id_alt or source.user_id
    parts: list[str] = [ns, platform, source.chat_type]
    if source.chat_id:
        parts.append(source.chat_id)
    if source.thread_id:
        parts.append(source.thread_id)

    # In threads, default to shared sessions (all participants see the same
    # conversation).  Per-user isolation only applies when explicitly enabled,
    # or when there is no thread (regular group).
    isolate_user = group_sessions_per_user
    if source.thread_id and not thread_sessions_per_user:
        isolate_user = False
    if isolate_user and participant:
        parts.append(str(participant))

    return ":".join(parts)


@dataclass
class _RoutingRow:
    """A row in the session_routing table (for in-memory access)."""

    session_key: str
    session_id: str
    platform: str
    chat_id: str
    chat_type: str
    user_id: str | None
    thread_id: str | None
    scope_id: str | None
    created_at: float
    last_active: float


class SessionStore:
    """SQLite-backed map from session_key to agent session_id.

    Persists the routing decision so a follow-up message from the same
    conversation resumes the existing agent session rather than starting a new
    one.  This is Encre's equivalent of Hermes' ``gateway_routing`` table.

    The store is process-local (one ``gateway_routing.db`` under the Encre
    data dir) and thread-safe via a single connection guarded by a lock.  The
    agent session itself (the transcript) is owned by
    :class:`encre.server.session_manager.SessionManager`; this store only
    holds the *routing* mapping and delegates creation to a caller-supplied
    ``create_fn`` so it stays decoupled from the session manager.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(get_data_dir()) / "gateway_routing.db"
        self._path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            # check_same_thread=False: we guard all access with self._lock.
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        return self._conn

    def _ensure_table(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_routing (
                    session_key  TEXT PRIMARY KEY,
                    session_id   TEXT NOT NULL,
                    platform     TEXT,
                    chat_id      TEXT,
                    chat_type    TEXT,
                    user_id      TEXT,
                    thread_id    TEXT,
                    scope_id     TEXT,
                    created_at   REAL,
                    last_active  REAL
                )
                """
            )
            conn.commit()

    def get(self, source: SessionSource) -> str | None:
        """Look up the agent session_id for a source, or None if unmapped.

        Touches ``last_active`` on hit so the routing row reflects recent use.
        """
        key = build_session_key(source)
        now = time.time()
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "SELECT session_id FROM session_routing WHERE session_key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE session_routing SET last_active = ? WHERE session_key = ?",
                (now, key),
            )
            conn.commit()
            return str(row[0])

    def get_or_create(
        self,
        source: SessionSource,
        create_fn: Callable[[], str],
    ) -> str:
        """Return the session_id for ``source``, creating one if unmapped.

        ``create_fn`` is called only on a miss and must return a fresh agent
        session_id (typically ``SessionManager.create_session(...).session_id``).
        This keeps the store decoupled from the session manager.
        """
        existing = self.get(source)
        if existing is not None:
            return existing
        session_id = create_fn()
        if not session_id:
            logger.warning("[session-store] create_fn returned empty session_id for %s", source.platform)
        self.put(source, session_id)
        return session_id

    def put(self, source: SessionSource, session_id: str) -> None:
        """Insert or replace the routing mapping for ``source``."""
        key = build_session_key(source)
        now = time.time()
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                INSERT OR REPLACE INTO session_routing
                    (session_key, session_id, platform, chat_id, chat_type,
                     user_id, thread_id, scope_id, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    session_id,
                    source.platform,
                    source.chat_id,
                    source.chat_type,
                    source.user_id,
                    source.thread_id,
                    source.scope_id,
                    now,
                    now,
                ),
            )
            conn.commit()

    def touch(self, source: SessionSource) -> None:
        """Update ``last_active`` for the source's row (no-op if unmapped)."""
        key = build_session_key(source)
        with self._lock:
            conn = self._connect()
            conn.execute(
                "UPDATE session_routing SET last_active = ? WHERE session_key = ?",
                (time.time(), key),
            )
            conn.commit()

    def reset(self, source: SessionSource) -> None:
        """Drop the routing mapping for ``source`` (e.g. on ``/new``)."""
        key = build_session_key(source)
        with self._lock:
            conn = self._connect()
            conn.execute(
                "DELETE FROM session_routing WHERE session_key = ?",
                (key,),
            )
            conn.commit()

    def all_rows(self) -> list[_RoutingRow]:
        """Return every routing row (for status/debug)."""
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                """
                SELECT session_key, session_id, platform, chat_id, chat_type,
                       user_id, thread_id, scope_id, created_at, last_active
                FROM session_routing
                ORDER BY last_active DESC
                """
            )
            return [
                _RoutingRow(
                    session_key=str(r[0]),
                    session_id=str(r[1]),
                    platform=str(r[2]) if r[2] is not None else "",
                    chat_id=str(r[3]) if r[3] is not None else "",
                    chat_type=str(r[4]) if r[4] is not None else "dm",
                    user_id=r[5],
                    thread_id=r[6],
                    scope_id=r[7],
                    created_at=float(r[8]) if r[8] is not None else 0.0,
                    last_active=float(r[9]) if r[9] is not None else 0.0,
                )
                for r in cur.fetchall()
            ]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
