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

"""
Durable state store for Discord reconnect message recovery.

This module provides a small, profile-scoped SQLite ledger that records
completed Discord messages and the state of recovery scans and cursors. It
lets the Discord gateway resume normal operation after an outage by tracking
which messages have been processed and which still need a response.

The primary collaborator is :class:`DiscordRecoveryStore`, which owns a
single SQLite database file located under the Encre data directory. All
access is serialised through a threading lock so the store is safe to use
from the gateway's worker threads.
"""

import datetime as dt
import logging
import os
import sqlite3
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable

from encre.config import get_data_dir

logger = logging.getLogger(__name__)

# Name of the SQLite database file persisted in the gateway data directory.
_DB_FILENAME = "discord_message_recovery.db"
# How many days of history to retain before pruning during initialization.
_RETENTION_DAYS = 30


class DiscordRecoveryStore:
    """Profile-scoped SQLite ledger for completed Discord messages.

    The store keeps three tables: a per-message ledger of outbound Discord
    messages, a log of recovery scan runs, and a set of per-channel cursors
    used to resume scanning after an interruption. The database is created
    lazily on first use and access is guarded by a threading lock, so the
    store can be shared across the gateway's worker threads.

    Attributes:
        _lock: Serialises all database access to avoid concurrent writes.
        _initialized: Tracks whether the schema has been created yet.
        _encre_home: Root data directory resolved from Encre's config.
    """

    def __init__(self, encre_home: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._initialized = False
        # Resolve the data directory; the encre_home argument is accepted
        # for backwards compatibility but the canonical location always
        # comes from the configured Encre data directory.
        self._encre_home = Path(get_data_dir())

    def path(self) -> Path:
        """Return the absolute path of the SQLite database file.

        The parent ``gateway`` directory is created on demand so callers can
        open the database without checking existence first.

        Returns:
            Path: Absolute path to ``discord_message_recovery.db``.
        """
        directory = self._encre_home / "gateway"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / _DB_FILENAME

    def call(self, fn: Callable[[sqlite3.Connection], Any], default: Any = None) -> Any:
        """Execute a callable inside a locked, short-lived SQLite session.

        The connection is opened with a small timeout and the schema is
        initialised lazily on the first successful call. Any exception raised
        while opening the connection or running ``fn`` is logged and swallowed
        so that a corrupt or unavailable ledger degrades gracefully into the
        provided ``default`` value instead of crashing the caller.

        Args:
            fn: Callable receiving the live connection and returning a result.
            default: Value returned when the operation cannot complete.

        Returns:
            Any: The return value of ``fn`` on success, otherwise ``default``.
        """
        try:
            with self._lock:
                path = self.path()
                # A short timeout prevents a stuck reader from blocking the
                # gateway indefinitely; the lock already serialises writers.
                conn = sqlite3.connect(path, timeout=0.1)
                try:
                    if not self._initialized:
                        self._initialize(conn)
                        self._initialized = True
                        # Restrict the database file to the owning user only.
                        with suppress(OSError):
                            os.chmod(path, 0o600)
                    result = fn(conn)
                    conn.commit()
                    return result
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning("Discord recovery ledger unavailable: %s", exc)
            return default

    def _initialize(self, conn: sqlite3.Connection) -> None:
        """Create the ledger schema and prune stale rows.

        Enables WAL journal mode for better concurrency, creates the three
        core tables if they do not already exist, and deletes any rows older
        than the retention window so the database does not grow without bound.

        Args:
            conn: An open SQLite connection (transaction managed by caller).
        """
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_messages (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT,
                thread_id TEXT,
                parent_channel_id TEXT,
                author_id TEXT,
                created_at TEXT,
                status TEXT NOT NULL,
                replied INTEGER NOT NULL DEFAULT 0,
                emoji_ack INTEGER NOT NULL DEFAULT 0,
                outage_response INTEGER NOT NULL DEFAULT 0,
                response_message_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_recovery_scans (
                scan_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                channels TEXT NOT NULL,
                window_seconds REAL NOT NULL,
                limit_count INTEGER NOT NULL,
                scanned INTEGER NOT NULL DEFAULT 0,
                missed INTEGER NOT NULL DEFAULT 0,
                dispatched INTEGER NOT NULL DEFAULT 0,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_recovery_cursors (
                channel_id TEXT PRIMARY KEY,
                last_message_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Compute the oldest timestamp we keep and drop everything older.
        cutoff = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=_RETENTION_DAYS)
        ).isoformat()
        conn.execute("DELETE FROM discord_messages WHERE updated_at < ?", (cutoff,))
        conn.execute(
            "DELETE FROM discord_recovery_scans "
            "WHERE COALESCE(completed_at, started_at) < ?",
            (cutoff,),
        )
        conn.execute(
            "DELETE FROM discord_recovery_cursors WHERE updated_at < ?",
            (cutoff,),
        )
