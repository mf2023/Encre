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

"""Git鈥憇tyle conversation rollback with SHA鈥?56 content鈥慳ddressable commits.

Layout
======

Each session gets a directory under ``<data_dir>/rollback/<session_id>/``::

    refs/heads/master       ->  HEAD commit hash (plain text)
    objects/ab/cdef1234...  ->  single commit blob (encrypted JSON)

The commit graph is a singly鈥憀inked list (parent -> parent -> ... -> root).

A commit blob contains::

    {
        "parent":  "hex hash of parent commit or null",
        "timestamp": 1716200000.0,
        "turn_count": 5,
        "message":  "turn_5",
        "state":    { ... full EncreSession.to_dict() output ... }
    }

The commit hash is ``SHA鈥?56(compact鈥慗SON(commit_blob))`` truncated to 40 hex
chars (like a git abbreviated hash) -- unique per content, reproducible.

Usage::

    rb = EncreRollbackGit()
    head = rb.commit(session)             # returns commit hash
    log_entries = rb.log(session_id)      # list the chain
    rb.checkout(session, "a1b2c3d4...")  # restore session state
"""

import contextlib
import hashlib
import json
import logging
import pathlib
import time
from typing import Any

from encre import secure_io

_log = logging.getLogger("encre.rollback")

__all__ = ["CommitEntry", "EncreRollbackGit"]


# 鈹€鈹€ storage layout 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _resolve_base() -> pathlib.Path:
    """Rollback store root -- declared in ``encre.lifecycle``.

    The root used to be a second, independent hard-coded path living under a
    *different* data root (``~/.encre``) than everything else
    (``~/.dunimd/encre``), which is why rollback survived session deletion
    unnoticed.  Resolving it through the lifecycle module keeps the on-disk
    layout defined in exactly one place.
    """
    from encre.lifecycle import rollback_root

    return rollback_root()


_BASE = _resolve_base()
_HASH_LEN = 40  # characters -- like a full git hash
_INDEX_FILE = _BASE / "index.json"


def _session_dir(session_id: str) -> pathlib.Path:
    return _BASE / session_id


def _objects_dir(session_id: str) -> pathlib.Path:
    return _session_dir(session_id) / "objects"


def _refs_dir(session_id: str) -> pathlib.Path:
    return _session_dir(session_id) / "refs" / "heads"


def _head_path(session_id: str) -> pathlib.Path:
    return _refs_dir(session_id) / "master"


def _obj_path(session_id: str, commit_hash: str) -> pathlib.Path:
    """``objects/<hash[:2]>/<hash[2:]>``"""
    return _objects_dir(session_id) / commit_hash[:2] / commit_hash[2:]


# 鈹€鈹€ commit object 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class CommitEntry:
    """A lightweight snapshot of a commit, suitable for log output."""

    __slots__ = ("commit_hash", "message", "parent", "timestamp", "turn_count")

    def __init__(
        self,
        commit_hash: str,
        parent: str | None,
        timestamp: float,
        turn_count: int,
        message: str,
    ) -> None:
        self.commit_hash = commit_hash
        self.parent = parent
        self.timestamp = timestamp
        self.turn_count = turn_count
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "hash": self.commit_hash,
            "parent": self.parent,
            "timestamp": self.timestamp,
            "turn_count": self.turn_count,
            "message": self.message,
        }


# 鈹€鈹€ manager 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class EncreRollbackGit:
    """Git鈥憇tyle versioned conversation history.

    Each ``commit()`` snapshots the full message list of a session and
    chains it via a parent hash.  ``checkout()`` restores any commit.
    """

    def __init__(self) -> None:
        self._session_index: dict[str, str] = {}  # session_id -> path
        self._load_index()

    # 鈹€鈹€ index (session cross鈥憆eference) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _load_index(self) -> None:
        try:
            if _INDEX_FILE.exists():
                self._session_index = secure_io.read_json(_INDEX_FILE, default={})
        except Exception:
            self._session_index = {}

    def _save_index(self) -> None:
        secure_io.write_json(_INDEX_FILE, self._session_index)

    # 鈹€鈹€ object I/O 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @staticmethod
    def _hash_object(obj: dict[str, Any]) -> str:
        """SHA鈥?56 of the compact JSON representation."""
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_LEN]

    @staticmethod
    def _read_head(session_id: str) -> str | None:
        p = _head_path(session_id)
        if not p.exists():
            return None
        return secure_io.read_text(p, default="").strip() or None

    @staticmethod
    def _write_head(session_id: str, commit_hash: str) -> None:
        secure_io.write_text(_head_path(session_id), commit_hash)

    @staticmethod
    def _write_object(session_id: str, commit_hash: str, data: dict[str, Any]) -> None:
        secure_io.write_json(_obj_path(session_id, commit_hash), data)

    @staticmethod
    def _read_object(session_id: str, commit_hash: str) -> dict[str, Any] | None:
        p = _obj_path(session_id, commit_hash)
        if not p.exists():
            return None
        return secure_io.read_json(p, default=None)

    # 鈹€鈹€ public API 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def commit(
        self,
        session: Any,  # EncreSession -- duck鈥憈yped for decoupling
        message: str = "",
    ) -> str:
        """Snapshot the current session state and append to the commit chain.

        Returns
        -------
        str
            40鈥慼ex鈥慶har commit hash.
        """
        session_id = session.id
        parent = self._read_head(session_id)

        blob: dict[str, Any] = {
            "parent": parent,
            "timestamp": time.time(),
            "turn_count": getattr(session, "turn_count", 0),
            "message": message or f"turn_{getattr(session, 'turn_count', 0)}",
            "state": getattr(session, "to_dict", lambda: {})(),
        }

        commit_hash = self._hash_object(blob)
        self._write_object(session_id, commit_hash, blob)
        self._write_head(session_id, commit_hash)

        # Update index
        self._session_index[session_id] = str(_session_dir(session_id))
        self._save_index()

        return commit_hash

    def log(self, session_id: str, max_count: int = 50) -> list[CommitEntry]:
        """Walk the commit chain from HEAD back to root."""
        entries: list[CommitEntry] = []
        current = self._read_head(session_id)
        visited: set[str] = set()

        while current and len(entries) < max_count:
            if current in visited:
                break
            visited.add(current)
            obj = self._read_object(session_id, current)
            if obj is None:
                break
            entries.append(CommitEntry(
                commit_hash=current,
                parent=obj.get("parent"),
                timestamp=obj.get("timestamp", 0),
                turn_count=obj.get("turn_count", 0),
                message=obj.get("message", ""),
            ))
            current = obj.get("parent")

        return entries

    def checkout(self, session: Any, commit_hash: str) -> bool:
        """Restore session state to a specific commit.

        The in鈥憁emory ``session.messages``, ``session.turn_count``, etc.
        are replaced with the values from the commit snapshot.

        After checkout the commit chain is NOT truncated -- the restored
        commit remains HEAD; a subsequent ``commit()`` will fork from it.

        Returns
        -------
        bool
            ``True`` if the commit was found and applied.
        """
        session_id = session.id
        obj = self._read_object(session_id, commit_hash)
        if obj is None:
            return False

        state = obj.get("state", {})
        if not state:
            return False

        # Restore file snapshots FIRST so disk state is reverted before
        # the frontend gets the updated session (it may trigger a re-render).
        restored = session.restore_file_snapshots()
        if restored:
            _log.info("[checkout] restored %d file(s) from snapshots", restored)

        # Restore session fields
        session.messages = state.get("messages", [])
        session.turn_count = state.get("turn_count", 0)
        session.tool_call_count = state.get("tool_call_count", 0)
        session.metadata = state.get("metadata", {})
        session.plan_items = state.get("plan_items", [])
        session.artifacts = state.get("artifacts", [])
        session.file_snapshots = dict(state.get("file_snapshots", {}))
        session.updated_at = time.time()

        return True

    def head(self, session_id: str) -> str | None:
        """Return the current HEAD commit hash (or None)."""
        return self._read_head(session_id)

    def head_entry(self, session_id: str) -> CommitEntry | None:
        """Return a ``CommitEntry`` for HEAD (or None)."""
        h = self._read_head(session_id)
        if h is None:
            return None
        obj = self._read_object(session_id, h)
        if obj is None:
            return None
        return CommitEntry(
            commit_hash=h,
            parent=obj.get("parent"),
            timestamp=obj.get("timestamp", 0),
            turn_count=obj.get("turn_count", 0),
            message=obj.get("message", ""),
        )

    def tree(self, session_id: str) -> list[dict[str, Any]]:
        """Return the full commit tree for a session (convenience)."""
        return [e.to_dict() for e in self.log(session_id)]

    def list_sessions_with_rollback(self) -> list[str]:
        """Return session IDs that have rollback history."""
        result: list[str] = []
        try:
            for entry in _BASE.iterdir():
                if entry.is_dir() and entry.name != "." and entry.name != "..":
                    h = self._read_head(entry.name)
                    if h:
                        result.append(entry.name)
        except OSError:
            pass
        return result
