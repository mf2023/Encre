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

"""Unified error orchestrator for the agent loop.

Replaces the inline error recovery logic scattered across
``_run_impl()`` with a single ``ErrorOrchestrator`` that owns all
recovery state and produces typed ``RecoveryAction`` values.

Priority order (first-match wins):
  1. Reactive compact    (context overflow)
  2. Model fallback      (rate limit / overload)
  3. Retryable           (network retry with backoff, credential rotate)
  4. Auth                (surface immediately)
  5. Unknown             (one silent retry)
  6. Consumed            (recovery exhausted -- withhold)
  7. Terminal            (unrecoverable -- surface to user)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Recovery limits ──────────────────────────────────────────────────────

MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
EMPTY_RESPONSE_RETRY_LIMIT = 2
TRUNCATED_TOOL_CALL_RETRY_LIMIT = 2
UNKNOWN_ERROR_RETRY_LIMIT = 1
NETWORK_RETRY_LIMIT = 2
MAX_TOTAL_RECOVERIES_PER_TURN = 6
ESCALATED_MAX_TOKENS = 64_000


class RecoveryAction(str, Enum):
    """What the caller (``_run_impl``) should do next."""
    CONTINUE = "continue"                 # retry the turn
    FALLBACK_CONTINUE = "fallback_continue"  # switch model and retry
    COMPACT_CONTINUE = "compact_continue"    # compact and retry
    CONSUMED = "consumed"                 # error withheld, continue silently
    RELEASE = "release"                   # surface error to user (terminal)
    RETRY = "retry"                       # retry after delay


@dataclass
class RecoveryDecision:
    """Result of an error classification and recovery attempt."""
    action: RecoveryAction
    delay: float = 0.0
    message: str = ""
    error_code: str = "unknown"
    error_category: str = "unknown"
    detail: str = ""


# ── Post-stream recovery decisions ───────────────────────────────────────


class PostStreamAction(str, Enum):
    """What to do after the model finishes streaming."""
    CONTINUE = "continue"           # retry the model call
    FALL_THROUGH = "fall_through"   # proceed with normal turn processing
    STOP = "stop"                   # end the session gracefully


@dataclass
class PostStreamDecision:
    """Result of post-stream recovery classification."""
    action: PostStreamAction
    message: str = ""
    detail: str = ""


# ── The orchestrator ─────────────────────────────────────────────────────


class ErrorOrchestrator:
    """Single owner of error recovery state for one agent loop.

    Usage in ``_run_impl``::

        # Before the backend call:
        result = orchestrator.handle_backend_exception(exc, ...)
        if result.action == RecoveryAction.CONTINUE:
            continue
        elif result.action == RecoveryAction.CONSUMED:
            _error_consumed = True
            continue
        elif result.action == RecoveryAction.RELEASE:
            yield create_finish("error", error=result.message, ...)
            return

        # After streaming:
        result = orchestrator.handle_post_stream(...)
        if result.action == PostStreamAction.CONTINUE:
            continue
        elif result.action == PostStreamAction.STOP:
            yield create_finish("stop")
            return
    """

    def __init__(self, loop: Any = None) -> None:
        self.loop = loop

        # Reactive compact guard (once per turn)
        self._reactive_compacted = False

        # Max-output-tokens recovery
        self._slot_escalated = False
        self._max_output_tokens_recovery_count = 0

        # Empty response recovery
        self._empty_response_retry_count = 0

        # Truncated tool call recovery
        self._truncated_tool_call_retry_count = 0

        # Unknown error recovery
        self._unknown_error_retry_count = 0

        # Network error recovery
        self._network_retry_count = 0

        # Per-turn recovery counter (global cap)
        self._recoveries_this_turn = 0

        # Fallback tracking
        self._attempt_fallback = False

    # ── Turn lifecycle ───────────────────────────────────────────────

    def reset_for_new_turn(self) -> None:
        """Reset per-turn recovery counters."""
        self._reactive_compacted = False
        self._empty_response_retry_count = 0
        self._truncated_tool_call_retry_count = 0
        self._unknown_error_retry_count = 0
        self._network_retry_count = 0
        self._recoveries_this_turn = 0
        self._attempt_fallback = False

    def can_attempt_recovery(self) -> bool:
        return self._recoveries_this_turn < MAX_TOTAL_RECOVERIES_PER_TURN

    # ── Backend exception handling ───────────────────────────────────

    def handle_backend_exception(
        self,
        exc: BaseException,
        *,
        error_code: str = "unknown",
        error_category: str = "unknown",
        is_context_overflow: bool = False,
        is_rate_limit: bool = False,
        config: Any = None,
        compact_engine: Any = None,
        session: Any = None,
        backend: Any = None,
        system_prompt: str = "",
        tool_call_buffers: dict | None = None,
        turn_count: int = 0,
    ) -> RecoveryDecision:
        """Classify *exc* and decide what action the loop should take.

        Priority order:
          1. Context overflow   → compact and retry
          2. Rate limit         → fallback model if available
          3. Network error      → retry with backoff
          4. Auth error         → surface immediately
          5. Unknown error      → one silent retry
          6. Otherwise          → release to user
        """
        if not self.can_attempt_recovery():
            return RecoveryDecision(
                RecoveryAction.RELEASE,
                error_code=error_code,
                error_category=error_category,
            )

        # 1. Reactive compact
        if is_context_overflow and compact_engine is not None and backend is not None:
            self._recoveries_this_turn += 1
            return RecoveryDecision(
                RecoveryAction.COMPACT_CONTINUE,
                error_code=error_code,
                error_category=error_category,
                detail="context overflow",
            )

        # 2. Model fallback
        if is_rate_limit and config is not None:
            from encre.recovery_loop import can_fallback
            if can_fallback(config):
                self._recoveries_this_turn += 1
                self._attempt_fallback = True
                return RecoveryDecision(
                    RecoveryAction.FALLBACK_CONTINUE,
                    error_code=error_code,
                    error_category=error_category,
                    detail="rate_limit fallback",
                )

        # 3. Network retry
        if error_category == "network" and self._network_retry_count < NETWORK_RETRY_LIMIT:
            self._network_retry_count += 1
            self._recoveries_this_turn += 1
            return RecoveryDecision(
                RecoveryAction.RETRY,
                delay=1.0,
                error_code=error_code,
                error_category=error_category,
                detail=f"network retry {self._network_retry_count}/{NETWORK_RETRY_LIMIT}",
            )

        # 4. Auth → surface
        if error_category == "auth":
            return RecoveryDecision(
                RecoveryAction.RELEASE,
                error_code=error_code,
                error_category=error_category,
                detail="auth error",
            )

        # 5. Unknown → one silent retry
        if error_code == "unknown" and self._unknown_error_retry_count < UNKNOWN_ERROR_RETRY_LIMIT:
            self._unknown_error_retry_count += 1
            self._recoveries_this_turn += 1
            return RecoveryDecision(
                RecoveryAction.CONTINUE,
                error_code=error_code,
                error_category=error_category,
                detail=f"unknown retry {self._unknown_error_retry_count}/{UNKNOWN_ERROR_RETRY_LIMIT}",
            )

        # 6. Terminal
        return RecoveryDecision(
            RecoveryAction.RELEASE,
            error_code=error_code,
            error_category=error_category,
        )

    # ── Post-stream recovery ─────────────────────────────────────────

    def handle_post_stream(
        self,
        *,
        finish_reason: str | None = None,
        is_empty: bool = False,
        is_truncated: bool = False,
        tool_call_buffers: dict | None = None,
        text_parts: list[str] | None = None,
        thinking_parts: list[str] | None = None,
        config: Any = None,
        session: Any = None,
        turn_count: int = 0,
    ) -> PostStreamDecision:
        """Classify post-stream conditions and decide next action.

        Priority order:
          1. Max output tokens → slot escalation or recovery message
          2. Empty response    → retry prompt
          3. Truncated tool    → re-issue prompt
          4. Fall through      → normal turn processing
        """
        # 1. Max output tokens
        if finish_reason in ("max_tokens", "length"):
            if not self._slot_escalated:
                self._slot_escalated = True
                self._recoveries_this_turn += 1
                return PostStreamDecision(
                    PostStreamAction.CONTINUE,
                    detail="slot escalation",
                )
            if self._max_output_tokens_recovery_count < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
                self._max_output_tokens_recovery_count += 1
                self._recoveries_this_turn += 1
                return PostStreamDecision(
                    PostStreamAction.CONTINUE,
                    detail=f"max_tokens recovery {self._max_output_tokens_recovery_count}/{MAX_OUTPUT_TOKENS_RECOVERY_LIMIT}",
                )

        # 2. Empty response
        if is_empty and self._empty_response_retry_count < EMPTY_RESPONSE_RETRY_LIMIT:
            self._empty_response_retry_count += 1
            self._recoveries_this_turn += 1
            return PostStreamDecision(
                PostStreamAction.CONTINUE,
                detail=f"empty retry {self._empty_response_retry_count}/{EMPTY_RESPONSE_RETRY_LIMIT}",
            )

        # 3. Truncated tool call
        if is_truncated and self._truncated_tool_call_retry_count < TRUNCATED_TOOL_CALL_RETRY_LIMIT:
            self._truncated_tool_call_retry_count += 1
            self._recoveries_this_turn += 1
            return PostStreamDecision(
                PostStreamAction.CONTINUE,
                detail=f"truncated retry {self._truncated_tool_call_retry_count}/{TRUNCATED_TOOL_CALL_RETRY_LIMIT}",
            )

        # 4. Fall through (normal processing or exhausted retries)
        return PostStreamDecision(PostStreamAction.FALL_THROUGH)

    # ── Diagnostic ───────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        return {
            "reactive_compacted": self._reactive_compacted,
            "slot_escalated": self._slot_escalated,
            "max_output_tokens_count": self._max_output_tokens_recovery_count,
            "empty_response_count": self._empty_response_retry_count,
            "truncated_tool_call_count": self._truncated_tool_call_retry_count,
            "unknown_error_count": self._unknown_error_retry_count,
            "network_retry_count": self._network_retry_count,
            "recoveries_this_turn": self._recoveries_this_turn,
            "attempt_fallback": self._attempt_fallback,
        }
