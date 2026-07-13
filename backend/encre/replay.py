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

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from encre.crypto import decrypt
from encre.logging_config import get_logger

logger = get_logger("encre.replay")


@dataclass
class ReplayEvent:
    """A single recorded telemetry event positioned in the timeline."""

    index: int  # 0-based position in the sorted event list
    timestamp: float
    event_type: str  # "turn" | "tool_call" | "retry" | "session_summary"
    turn_number: int  # associated turn number, 0 when the event isn't turn-scoped
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for transport to the frontend."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "turn_number": self.turn_number,
            "data": self.data,
        }


class ReplayPlayer:
    """Cursor-based scrubber over a session's telemetry event stream.

    The cursor starts *before* the first event (``index = -1``); callers
    advance it with :meth:`step_forward`.  ``step_backward`` / ``jump_to_turn``
    move it arbitrarily.  Every navigation method returns the event now under
    the cursor, or ``None`` when the move runs off either end.
    """

    def __init__(self, session_id: str, telemetry_dir: str | None = None) -> None:
        self.session_id = session_id
        self.events: list[ReplayEvent] = []
        self._cursor: int = -1  # -1 = before first event
        self._telemetry_dir = telemetry_dir or self._default_telemetry_dir()
        self._load()

    @staticmethod
    def _default_telemetry_dir() -> str:
        from encre.config import get_data_dir
        return str(get_data_dir() / "telemetry")

    def _jsonl_path(self) -> str:
        return os.path.join(self._telemetry_dir, f"{self.session_id}.jsonl")

    def _load(self) -> None:
        """Read, decrypt, parse, and timestamp-sort the session's events."""
        path = self._jsonl_path()
        if not os.path.exists(path):
            logger.debug(f"[replay] no telemetry log for session {self.session_id}")
            self.events = []
            return
        raw_events: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as exc:
            logger.warning(f"[replay] failed to read {path}: {exc}")
            return
        for line in lines:
            if not line.strip():
                continue
            data = self._parse_line(line.strip())
            if data is not None:
                raw_events.append(data)
        # Stable sort by timestamp preserves write order for equal timestamps.
        raw_events.sort(key=lambda d: d.get("timestamp", 0.0) or 0.0)
        self.events = [self._build_event(i, d) for i, d in enumerate(raw_events)]

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any] | None:
        """Decrypt (if needed) and JSON-parse a single JSONL line."""
        try:
            try:
                return json.loads(decrypt(line))
            except Exception:
                return json.loads(line)
        except Exception:
            return None

    @staticmethod
    def _build_event(index: int, data: dict[str, Any]) -> ReplayEvent:
        evt_type = str(data.get("event", "") or "unknown")
        ts = float(data.get("timestamp", 0.0) or 0.0)
        turn_number = int(data.get("turn_number", 0) or 0)
        # tool_call / retry events aren't turn-scoped in the log; leave 0.
        if evt_type != "turn":
            turn_number = 0
        return ReplayEvent(
            index=index,
            timestamp=ts,
            event_type=evt_type,
            turn_number=turn_number,
            data=data,
        )

    # ── navigation ──────────────────────────────────────────────────────

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
        """Advance the cursor by one; return the event, or None at the end."""
        if self._cursor + 1 >= len(self.events):
            # Already at or past the last event: clamp to last, signal end.
            self._cursor = len(self.events) - 1 if self.events else -1
            return None
        self._cursor += 1
        return self.events[self._cursor]

    def step_backward(self) -> ReplayEvent | None:
        """Move the cursor back by one; return the event, or None at the start."""
        if self._cursor <= 0:
            self._cursor = -1
            return None
        self._cursor -= 1
        return self.events[self._cursor]

    def jump_to_index(self, index: int) -> ReplayEvent | None:
        """Move the cursor to *index* (0-based); None when out of range."""
        if not self.events or index < 0 or index >= len(self.events):
            return None
        self._cursor = index
        return self.events[self._cursor]

    def jump_to_turn(self, turn_number: int) -> ReplayEvent | None:
        """Jump to the first event recorded for turn *turn_number*.

        The ``turn`` event itself carries ``turn_number``; tool_call and
        retry events in the log are not turn-labeled, so this jumps to the
        turn marker rather than the first tool call within it.
        """
        for ev in self.events:
            if ev.event_type == "turn" and ev.turn_number == turn_number:
                self._cursor = ev.index
                return ev
        return None

    def reset(self) -> None:
        """Return the cursor to before the first event."""
        self._cursor = -1

    # ── views ───────────────────────────────────────────────────────────

    def event_stream(self) -> list[ReplayEvent]:
        """Return the full ordered event list (does not move the cursor)."""
        return list(self.events)

    def turn_boundaries(self) -> list[int]:
        """Return the indices of ``turn`` events, in order.

        Useful for a timeline scrubber that wants snap points.
        """
        return [ev.index for ev in self.events if ev.event_type == "turn"]

    def summary(self) -> dict[str, Any]:
        """Return a compact overview of the loaded session."""
        turn_events = [ev for ev in self.events if ev.event_type == "turn"]
        tool_events = [ev for ev in self.events if ev.event_type == "tool_call"]
        retry_events = [ev for ev in self.events if ev.event_type == "retry"]
        total_cost = sum(
            float(ev.data.get("cost_usd", 0.0) or 0.0)
            for ev in turn_events
        )
        return {
            "session_id": self.session_id,
            "event_count": len(self.events),
            "turn_count": len(turn_events),
            "tool_call_count": len(tool_events),
            "retry_count": len(retry_events),
            "total_cost_usd": round(total_cost, 6),
            "first_timestamp": self.events[0].timestamp if self.events else 0.0,
            "last_timestamp": self.events[-1].timestamp if self.events else 0.0,
        }
