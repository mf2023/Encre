#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 漏 2025-2026 Wenze Wei. All Rights Reserved.
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


    def to_dict(self) -> dict[str, Any]:


class ReplayPlayer:


    def __init__(self, session_id: str, telemetry_dir: str | None = None) -> None:

    @staticmethod
    def _default_telemetry_dir() -> str:

    def _jsonl_path(self) -> str:

    def _load(self) -> None:
        if not os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
        except OSError as exc:
        for line in lines:
            if not line.strip():
            if data is not None:
        # Stable sort by timestamp preserves write order for equal timestamps.

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any] | None:
        try:
            try:
            except Exception:
        except Exception:

    @staticmethod
    def _build_event(index: int, data: dict[str, Any]) -> ReplayEvent:
        # tool_call / retry events aren't turn-scoped in the log; leave 0.
        if evt_type != "turn":

    # 鈹€鈹€ navigation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def __len__(self) -> int:

    @property
    def cursor(self) -> int:

    def current(self) -> ReplayEvent | None:
        if 0 <= self._cursor < len(self.events):

    def step_forward(self) -> ReplayEvent | None:
        if self._cursor + 1 >= len(self.events):
            # Already at or past the last event: clamp to last, signal end.

    def step_backward(self) -> ReplayEvent | None:
        if self._cursor <= 0:

    def jump_to_index(self, index: int) -> ReplayEvent | None:
        if not self.events or index < 0 or index >= len(self.events):

    def jump_to_turn(self, turn_number: int) -> ReplayEvent | None:

        for ev in self.events:
            if ev.event_type == "turn" and ev.turn_number == turn_number:

    def reset(self) -> None:

    # 鈹€鈹€ views 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def event_stream(self) -> list[ReplayEvent]:

    def turn_boundaries(self) -> list[int]:


    def summary(self) -> dict[str, Any]:
            for ev in turn_events
