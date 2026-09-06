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

"""Typed session-lifecycle events published on the loop's event stream.

These events mirror the session/turn lifecycle the hook system observes
(``on_session_start``, ``on_turn_start``, ``on_checkpoint``, ``on_turn_end``,
``on_session_end``, ``on_user_message_persisted``) but are delivered on the
typed :class:`~encre.events.EventStream`, so every consumer of agent output
-- frontend transport, plugin taps, telemetry -- sees the full lifecycle
through the single event contract.
"""

from dataclasses import dataclass
from typing import Union


@dataclass
class SessionStarted:
    """A run started for a session (after the system prompt is built)."""
    session_id: str


@dataclass
class SessionEnded:
    """A run finished; ``reason`` is ``"cancelled"`` or ``"max_tokens"``."""
    session_id: str
    reason: str


@dataclass
class TurnStarted:
    """A turn iteration began (before the pre-model compaction phase)."""
    turn: int


@dataclass
class TurnEnded:
    """A turn iteration finished; ``event_count`` is the AgentEvent count."""
    turn: int
    event_count: int


@dataclass
class CheckpointCreated:
    """A session checkpoint was persisted for the turn."""
    turn: int
    label: str


@dataclass
class UserMessagePersisted:
    """The user message was flushed to durable storage."""
    session_id: str


SessionEvent = Union[
    SessionStarted,
    SessionEnded,
    TurnStarted,
    TurnEnded,
    CheckpointCreated,
    UserMessagePersisted,
]
