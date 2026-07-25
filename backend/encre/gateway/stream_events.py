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

"""Structured streaming events -- the agent-to-gateway delivery contract.

Defines a typed event vocabulary that names *what happened* without prescribing
*how it is delivered*.  The gateway's stream consumer is the single sink; the
platform adapter decides how to render each event.

These are intentionally plain frozen dataclasses -- no behavior, no platform
knowledge, no I/O.  They are cheap to construct and safe to hand across the
thread/async boundary into the consumer queue.

Aligns with Hermes ``gateway/stream_events.py``.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


# -- Message (assistant text) events -------------------------------------------


@dataclass(frozen=True)
class MessageChunk:
    """A delta of streamed assistant text.

    ``text`` is the incremental content as it arrives from the model.  The
    consumer accumulates chunks and progressively renders them.
    """

    text: str


@dataclass(frozen=True)
class MessageStop:
    """The current assistant message segment is complete.

    ``final`` is True only for the terminal stop of the whole turn.
    """

    final: bool = False


@dataclass(frozen=True)
class Commentary:
    """A complete interim assistant message emitted between tool iterations.

    Unlike a MessageChunk this is already-complete text (not a delta); the
    consumer renders it as its own message so it reads as a distinct beat.
    """

    text: str


# -- Tool-call events ----------------------------------------------------------


@dataclass(frozen=True)
class ToolCallChunk:
    """A tool invocation has started (or its in-progress state changed).

    Carries the raw facts about the call -- name, a short argument preview,
    and the full args dict -- letting the gateway decide presentation.
    """

    tool_name: str
    preview: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    index: int = 0


@dataclass(frozen=True)
class ToolCallFinished:
    """A tool invocation completed.

    ``duration`` is wall-clock seconds.  ``ok`` reflects whether the tool
    returned without raising.
    """

    tool_name: str
    duration: float = 0.0
    ok: bool = True
    index: int = 0


# -- Gateway control / lifecycle events ----------------------------------------


@dataclass(frozen=True)
class LongToolHint:
    """One-shot onboarding nudge when a tool runs longer than the threshold."""

    tool_name: str = ""
    duration: float = 0.0


@dataclass(frozen=True)
class GatewayNotice:
    """A gateway-originated control message (restart, online, long-run notice).

    ``kind`` is a stable string the adapter can switch on.  ``text`` is the
    human-readable default rendered when an adapter has no platform-specific
    treatment.
    """

    kind: str
    text: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# -- Union type ----------------------------------------------------------------

StreamEvent = Union[
    MessageChunk,
    MessageStop,
    Commentary,
    ToolCallChunk,
    ToolCallFinished,
    LongToolHint,
    GatewayNotice,
]


__all__ = [
    "MessageChunk",
    "MessageStop",
    "Commentary",
    "ToolCallChunk",
    "ToolCallFinished",
    "LongToolHint",
    "GatewayNotice",
    "StreamEvent",
]
