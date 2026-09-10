#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2025-2026 Wenze Wei. All Rights Reserved.
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


"""Session replay player.

Reads a session's encrypted telemetry JSONL log, decrypts each line, and
exposes a cursor-based interface for scrubbing through the recorded event
stream (``step_forward`` / ``step_backward`` / ``jump_to_turn``).  Used by
the observability layer to reconstruct what an agent did during a past
session -- for debugging, audit, and cost/token review.

The JSONL is written by :class:`encre.telemetry.EncreTelemetry`: one event
per line, each line encrypted via ``encre.crypto.encrypt`` (with a plaintext
fallback when encryption fails).  Events are timestamped; the player sorts
by timestamp on load so out-of-order writes (e.g. from concurrent tool
prefetch) still produce a linear timeline.
"""


import json
import os
from dataclasses import dataclass, field
from typing import Any

from encre.crypto import decrypt
from encre.logging_config import get_logger

logger = get_logger("encre.replay")


@dataclass
class ReplayEvent:
    """A single decrypted telemetry event for replay."""

    index: int
    event_type: str
    data: dict[str, Any]
    timestamp: float = 0.0
    turn_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "turn_number": self.turn_number,
        }


class ReplayPlayer:
    """Cursor-based player over a session's encrypted telemetry log."""

    def __init__(self, session_id: str, telemetry_dir: str | None = None) -> None:
        self.session_id = session_id
        self._telemetry_dir = telemetry_dir or self._default_telemetry_dir()
        self.events: list[ReplayEvent] = []
        self._cursor = -1
        self._load()

    @staticmethod
    def _default_telemetry_dir() -> str:
        # Telemetry belongs with the rest of the session data.  The old
        # ``~/.encre/telemetry`` split meant replay read a directory that
        # backups never contained, and that ``purge_session`` never cleaned.
        try:
            from encre.paths import get_data_dir

            return str(get_data_dir("telemetry", ensure=False))
        except Exception:  # pragma: no cover - defensive
            return os.path.expanduser(
                os.path.join("~", ".dunimd", "encre", "telemetry")
            )

    def _jsonl_path(self) -> str:
        return os.path.join(self._telemetry_dir, f"{self.session_id}.jsonl")

    def _load(self) -> None:
        path = self._jsonl_path()
        if not os.path.exists(path):
            logger.warning("No telemetry log found at %s", path)
            return
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as exc:
            logger.error("Failed to read telemetry log %s: %s", path, exc)
            return
        events = []
        for idx, line in enumerate(lines):
            if not line.strip():
                continue
            data = self._parse_line(line)
            if data is not None:
                events.append(self._build_event(idx, data))
        # Stable sort by timestamp preserves write order for equal timestamps.
        events.sort(key=lambda e: (e.timestamp, e.index))
        self.events = events
        self._cursor = -1

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any] | None:
        try:
            try:
                text = decrypt(line)
            except Exception:
                text = line
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _build_event(index: int, data: dict[str, Any]) -> ReplayEvent:
        evt_type = str(data.get("type") or data.get("event") or "unknown")
        ts = float(data.get("timestamp") or data.get("ts") or 0.0)
        turn = int(data.get("turn") or data.get("turn_number") or 0)
        # tool_call / retry events aren't turn-scoped in the log; leave 0.
        if evt_type != "turn":
            turn = 0
        return ReplayEvent(
            index=index, event_type=evt_type, data=data, timestamp=ts, turn_number=turn
        )

    # -------------------------------------------------------------------------
    # navigation
    # -------------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.events)

    @property
    def cursor(self) -> int:
        return self._cursor

    def current(self) -> ReplayEvent | None:
        if 0 <= self._cursor < len(self.events):
            return self.events[self._cursor]
        return None

    def step_forward(self) -> ReplayEvent | None:
        if self._cursor + 1 >= len(self.events):
            # Already at or past the last event: clamp to last, signal end.
            if self.events:
                self._cursor = len(self.events) - 1
            return None
        self._cursor += 1
        return self.events[self._cursor]

    def step_backward(self) -> ReplayEvent | None:
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        return self.events[self._cursor]

    def jump_to_index(self, index: int) -> ReplayEvent | None:
        if not self.events or index < 0 or index >= len(self.events):
            return None
        self._cursor = index
        return self.events[self._cursor]

    def jump_to_turn(self, turn_number: int) -> ReplayEvent | None:
        if turn_number <= 0:
            self._cursor = -1
            return None
        for ev in self.events:
            if ev.event_type == "turn" and ev.turn_number == turn_number:
                self._cursor = ev.index if 0 <= ev.index < len(self.events) else self.events.index(ev)
                return self.events[self._cursor]
        return None

    def reset(self) -> None:
        self._cursor = -1

    # -------------------------------------------------------------------------
    # views
    # -------------------------------------------------------------------------

    def event_stream(self) -> list[ReplayEvent]:
        return list(self.events)

    def turn_boundaries(self) -> list[int]:
        """Return the event indexes where a new turn begins."""
        boundaries = []
        for i, ev in enumerate(self.events):
            if ev.event_type == "turn":
                boundaries.append(i)
        return boundaries

    def summary(self) -> dict[str, Any]:
        turn_events = [ev for ev in self.events if ev.event_type == "turn"]
        return {
            "session_id": self.session_id,
            "total_events": len(self.events),
            "turns": len(turn_events),
            "first_timestamp": self.events[0].timestamp if self.events else None,
            "last_timestamp": self.events[-1].timestamp if self.events else None,
        }
