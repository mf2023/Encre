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

"""Unified recovery state machine for the agent main loop.

The main loop's error recovery was scattered across three inline paths
(reactive-compact, model-fallback, max-output-tokens) each with its own
ad-hoc guard flags (``_reactive_compacted``, ``_slot_escalated``,
``_max_output_tokens_recovery_count`` ...).  Without a single owner it was
hard to reason about which recoveries had already been attempted, and easy
to introduce a retry loop when a new path was added.

``RecoveryStateMachine`` is the single owner of "have we tried X" state and
the allowed state transitions:

    NORMAL  --error-->  RECOVERING  --recovered-->  NORMAL
                       RECOVERING  --exhausted-->  FALLBACK
                       RECOVERING  --needs-compact-->  COMPACTING  --done-->  NORMAL
                       FALLBACK  --exhausted-->  NORMAL (terminal: error released)

Each transition checks the per-kind attempt limit and the global loop guard
(no more than ``MAX_TOTAL_RECOVERIES`` recoveries per turn), so a bug that
causes an exception every turn can never spin the loop forever.

This module is opt-in: the loop only consults the RSM when
``config.enable_unified_recovery`` is True.  The existing inline guards keep
working when the flag is off, so the flag can be flipped back without code
changes if a regression appears.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from encre.logging_config import get_logger

logger = get_logger("encre.recovery")


# Per-kind recovery attempt limits.  Mirrors the constants the inline guards
# used (max-output = 3, empty/truncated = 2, unknown = 1) so behavior does
# not change when the flag flips.
MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
EMPTY_RESPONSE_RETRY_LIMIT = 2
TRUNCATED_TOOL_CALL_RETRY_LIMIT = 2
UNKNOWN_ERROR_RETRY_LIMIT = 1
NETWORK_RETRY_LIMIT = 2

# Hard ceiling on total recoveries per user turn.  Independent of per-kind
# limits, this stops a pathological error pattern that cycles through every
# recovery kind from looping indefinitely.
MAX_TOTAL_RECOVERIES_PER_TURN = 6


class RecoveryState(Enum):
    NORMAL = auto()
    RECOVERING = auto()
    FALLBACK = auto()
    COMPACTING = auto()


class RecoveryKind(Enum):
    REACTIVE_COMPACT = "reactive_compact"
    MODEL_FALLBACK = "model_fallback"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    SLOT_ESCALATION = "slot_escalation"
    NETWORK_RETRY = "network_retry"
    AUTH_RELEASE = "auth_release"
    UNKNOWN_RETRY = "unknown_retry"
    EMPTY_RESPONSE = "empty_response"
    TRUNCATED_TOOL_CALL = "truncated_tool_call"


@dataclass
class RecoveryDecision:
    """What the RSM decided to do with an error."""

    kind: RecoveryKind | None  # None when no recovery applies (terminal)
    allowed: bool  # True if the attempt is permitted by the guards
    state: RecoveryState
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value if self.kind else None,
            "allowed": self.allowed,
            "state": self.state.name,
            "reason": self.reason,
        }


@dataclass
class RecoveryStateMachine:
    """Single owner of loop recovery state and transition rules.

    The loop holds one instance per run.  ``reset_for_new_turn`` clears the
    per-turn counters (called at the top of each user turn); the fallback
    transition deliberately clears the reactive-compact guard so a fallback
    model gets its own fresh compact attempt.
    """

    state: RecoveryState = RecoveryState.NORMAL
    reactive_compact_attempted: bool = False
    model_fallback_attempted: bool = False
    slot_escalated: bool = False
    max_output_tokens_recovery_count: int = 0
    network_retry_count: int = 0
    unknown_error_retry_count: int = 0
    empty_response_retry_count: int = 0
    truncated_tool_call_retry_count: int = 0
    auth_released: bool = False
    total_recoveries_this_turn: int = 0
    # Transition history for diagnostics / post-mortem.
    history: list[tuple[RecoveryKind, bool]] = field(default_factory=list)

    # ── guards ──────────────────────────────────────────────────────

    def _limit_for(self, kind: RecoveryKind) -> int | None:
        return {
            RecoveryKind.MAX_OUTPUT_TOKENS: MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
            RecoveryKind.EMPTY_RESPONSE: EMPTY_RESPONSE_RETRY_LIMIT,
            RecoveryKind.TRUNCATED_TOOL_CALL: TRUNCATED_TOOL_CALL_RETRY_LIMIT,
            RecoveryKind.UNKNOWN_RETRY: UNKNOWN_ERROR_RETRY_LIMIT,
            RecoveryKind.NETWORK_RETRY: NETWORK_RETRY_LIMIT,
            RecoveryKind.REACTIVE_COMPACT: 1,
            RecoveryKind.MODEL_FALLBACK: 1,
            RecoveryKind.AUTH_RELEASE: 1,
            RecoveryKind.SLOT_ESCALATION: 1,
        }.get(kind)

    def _count_for(self, kind: RecoveryKind) -> int:
        return {
            RecoveryKind.MAX_OUTPUT_TOKENS: self.max_output_tokens_recovery_count,
            RecoveryKind.EMPTY_RESPONSE: self.empty_response_retry_count,
            RecoveryKind.TRUNCATED_TOOL_CALL: self.truncated_tool_call_retry_count,
            RecoveryKind.UNKNOWN_RETRY: self.unknown_error_retry_count,
            RecoveryKind.NETWORK_RETRY: self.network_retry_count,
            RecoveryKind.REACTIVE_COMPACT: int(self.reactive_compact_attempted),
            RecoveryKind.MODEL_FALLBACK: int(self.model_fallback_attempted),
            RecoveryKind.AUTH_RELEASE: int(self.auth_released),
            RecoveryKind.SLOT_ESCALATION: int(self.slot_escalated),
        }.get(kind, 0)

    def can_attempt(self, kind: RecoveryKind) -> bool:
        """Return True if *kind* may be attempted given current guard state."""
        if self.total_recoveries_this_turn >= MAX_TOTAL_RECOVERIES_PER_TURN:
            return False
        limit = self._limit_for(kind)
        if limit is None:
            return False
        return self._count_for(kind) < limit

    # ── transitions ──────────────────────────────────────────────────

    def record_attempt(self, kind: RecoveryKind) -> RecoveryDecision:
        """Mark *kind* as attempted and advance state.

        Returns a decision the caller acts on: ``allowed`` reflects whether
        the guard permitted it.  When not allowed, the caller should fall
        through to the terminal failure path rather than retry.
        """
        allowed = self.can_attempt(kind)
        self.history.append((kind, allowed))
        if not allowed:
            self.state = RecoveryState.NORMAL
            return RecoveryDecision(
                kind=None, allowed=False, state=self.state,
                reason=f"{kind.value} attempt limit reached or turn recovery cap hit",
            )
        # Advance per-kind counter.
        if kind == RecoveryKind.MAX_OUTPUT_TOKENS:
            self.max_output_tokens_recovery_count += 1
        elif kind == RecoveryKind.EMPTY_RESPONSE:
            self.empty_response_retry_count += 1
        elif kind == RecoveryKind.TRUNCATED_TOOL_CALL:
            self.truncated_tool_call_retry_count += 1
        elif kind == RecoveryKind.UNKNOWN_RETRY:
            self.unknown_error_retry_count += 1
        elif kind == RecoveryKind.NETWORK_RETRY:
            self.network_retry_count += 1
        elif kind == RecoveryKind.REACTIVE_COMPACT:
            self.reactive_compact_attempted = True
        elif kind == RecoveryKind.MODEL_FALLBACK:
            self.model_fallback_attempted = True
        elif kind == RecoveryKind.AUTH_RELEASE:
            self.auth_released = True
        elif kind == RecoveryKind.SLOT_ESCALATION:
            self.slot_escalated = True
        self.total_recoveries_this_turn += 1
        self.state = (
            RecoveryState.COMPACTING
            if kind == RecoveryKind.REACTIVE_COMPACT
            else RecoveryState.FALLBACK
            if kind == RecoveryKind.MODEL_FALLBACK
            else RecoveryState.RECOVERING
        )
        return RecoveryDecision(kind=kind, allowed=True, state=self.state)

    def mark_recovered(self) -> None:
        """Signal that a recovery completed and the loop is healthy again."""
        self.state = RecoveryState.NORMAL

    def reset_for_new_turn(self) -> None:
        """Clear per-turn recovery state at the start of a new user turn.

        Keeps cross-turn signals (active fallback model) which the loop owns
        separately; this only resets the "have we tried X" guards.
        """
        self.state = RecoveryState.NORMAL
        self.reactive_compact_attempted = False
        self.total_recoveries_this_turn = 0
        self.network_retry_count = 0
        self.unknown_error_retry_count = 0
        self.empty_response_retry_count = 0
        self.truncated_tool_call_retry_count = 0
        # max_output_tokens + slot_escalation persist across turns by design
        # (they escalate the slot once per run, not per turn).

    def reset_for_fallback(self) -> None:
        """Clear the reactive-compact guard after a model fallback.

        The fallback model starts from a fresh state and deserves its own
        compact attempt if it also hits a context overflow.  Mirrors the
        inline ``_reactive_compacted = False`` reset on the fallback path.
        """
        self.reactive_compact_attempted = False
        self.state = RecoveryState.NORMAL

    # ── error routing ───────────────────────────────────────────────

    def classify(self, exc: BaseException, context: dict[str, Any] | None = None) -> RecoveryKind | None:
        """Map an exception to the recovery kind that should handle it.

        Best-effort classification by error string; the loop already has
        richer type-based predicates (``_is_context_overflow``,
        ``is_rate_limit_or_overload``) and should prefer those when
        available -- this is the fallback classification used when the RSM
        is asked to route an error it didn't get a predicate for.
        """
        context = context or {}
        msg = str(exc).lower()
        if "context" in msg and ("overflow" in msg or "too long" in msg or "413" in msg):
            return RecoveryKind.REACTIVE_COMPACT
        if "rate limit" in msg or "overload" in msg or "429" in msg or "503" in msg:
            return RecoveryKind.MODEL_FALLBACK
        if "max output" in msg or "max tokens" in msg or "max_output" in msg:
            return RecoveryKind.MAX_OUTPUT_TOKENS
        if "timeout" in msg or "timed out" in msg or "connection" in msg:
            return RecoveryKind.NETWORK_RETRY
        if "auth" in msg or "unauthorized" in msg or "api key" in msg or "401" in msg:
            return RecoveryKind.AUTH_RELEASE
        return RecoveryKind.UNKNOWN_RETRY

    def handle_error(self, exc: BaseException, context: dict[str, Any] | None = None) -> RecoveryDecision:
        """Classify an error and decide whether its recovery may proceed.

        Returns a ``RecoveryDecision``; callers check ``.allowed`` and
        ``.kind`` to decide whether to perform the recovery action or fall
        through to terminal failure.  Does not perform the recovery itself
        -- the loop owns the actual compact / fallback / retry side effects.
        """
        kind = self.classify(exc, context)
        if kind is None:
            self.state = RecoveryState.NORMAL
            return RecoveryDecision(kind=None, allowed=False, state=self.state, reason="unclassifiable error")
        return self.record_attempt(kind)

    def snapshot(self) -> dict[str, Any]:
        """Return a diagnostic snapshot of the current guard state."""
        return {
            "state": self.state.name,
            "reactive_compact_attempted": self.reactive_compact_attempted,
            "model_fallback_attempted": self.model_fallback_attempted,
            "slot_escalated": self.slot_escalated,
            "max_output_tokens_recovery_count": self.max_output_tokens_recovery_count,
            "network_retry_count": self.network_retry_count,
            "unknown_error_retry_count": self.unknown_error_retry_count,
            "empty_response_retry_count": self.empty_response_retry_count,
            "truncated_tool_call_retry_count": self.truncated_tool_call_retry_count,
            "total_recoveries_this_turn": self.total_recoveries_this_turn,
        }
