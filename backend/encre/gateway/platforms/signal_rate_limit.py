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

"""Signal attachment rate-limit scheduler.

This module implements a process-wide token-bucket simulator that mirrors the
per-account attachment rate limit enforced by signal-cli / Signal-Server. It is
a *model* of server-side capacity, not an enforcement mechanism: the Signal
server remains the source of truth and will still raise rate-limit responses
when the model drifts.

Producers — ``SignalAdapter.send_multiple_images`` and the ``send_message``
tool's Signal path — call :meth:`SignalAttachmentScheduler.acquire` before an
attachment send; on a 429 they call :meth:`SignalAttachmentScheduler.feedback`
so the model recalibrates from the server's authoritative ``Retry-After`` hint.

Concurrency model: the scheduler serialises concurrent ``acquire`` calls through
an :class:`asyncio.Lock`, giving FIFO fairness across the agent sessions that
share a single signal-cli daemon within one process.

Key collaborators:
    * :func:`get_scheduler` returns the shared process-wide singleton.
    * :func:`_extract_retry_after_seconds` / :func:`_is_signal_rate_limit_error`
      translate signal-cli's varied error shapes into a uniform signal.
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per-message attachment cap (source: Signal-{Android,Desktop} source code).
SIGNAL_MAX_ATTACHMENTS_PER_MSG = 32
# Server-side token-bucket capacity for attachments rate limiting.
SIGNAL_RATE_LIMIT_BUCKET_CAPACITY = 50
# Fallback token refill interval used when signal-cli is older than v0.14.3
# and does not surface the authoritative Retry-After value.
SIGNAL_RATE_LIMIT_DEFAULT_RETRY_AFTER = 4
# Number of attempts: the initial attempt plus one retry.
SIGNAL_RATE_LIMIT_MAX_ATTEMPTS = 2
# When the estimated wait exceeds this many seconds, the user is warned about
# the pacing delay before the send is committed.
SIGNAL_BATCH_PACING_NOTICE_THRESHOLD = 10.0
# signal-cli (v0.14.3+) JSON-RPC error code reported for a RateLimitException.
SIGNAL_RPC_ERROR_RATELIMIT = -5


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SignalRateLimitError(Exception):
    """Exception raised by rate-limit responses.

    ``SignalAdapter._rpc`` raises this error for rate-limit responses when the
    caller has opted in via ``raise_on_rate_limit=True``. It carries the
    server-supplied per-token Retry-After window (in seconds) when signal-cli
    reports it (signal-cli ≥ v0.14.3). ``retry_after`` is ``None`` when the
    running version does not expose that field.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        """Initialise the error with a message and optional retry window.

        Args:
            message: Human-readable description of the rate-limit failure.
            retry_after: Per-token Retry-After seconds reported by the server,
                or ``None`` when unavailable.
        """
        super().__init__(message)
        self.retry_after = retry_after


class SignalSchedulerError(Exception):
    """Error raised for invalid use of the attachment scheduler.

    Currently used when :meth:`SignalAttachmentScheduler.acquire` is asked for
    more tokens than the bucket capacity can ever satisfy.
    """


# ---------------------------------------------------------------------------
# Detection helpers — used to fish a 429 out of signal-cli's various error
# shapes (typed code, [429] substring, libsignal-net RetryLaterException
# leaked through AttachmentInvalidException).
# ---------------------------------------------------------------------------

# Matches libsignal-net's RetryLaterException string form ("Retry after N
# seconds" / "Retry after N second"), surfaced when 429s hit during attachment
# upload. signal-cli wraps these as AttachmentInvalidException rather than
# RateLimitException, so the typed error path never fires and we must parse the
# message text instead.
_RETRY_AFTER_RE = re.compile(r"Retry after (\d+(?:\.\d+)?)\s*second", re.IGNORECASE)


def _extract_retry_after_seconds(err: Any) -> Optional[float]:
    """Pull the per-token Retry-After window from a signal-cli rate-limit error.

    Two sources are tried, in order:
        1. ``error.data.response.results[*].retryAfterSeconds`` — the structured
           field signal-cli ≥ v0.14.3 surfaces for a plain RateLimitException.
        2. ``"Retry after N seconds"`` parsed out of the message — covers
           libsignal-net's RetryLaterException that gets wrapped as
           AttachmentInvalidException during attachment upload, where the
           structured field stays ``null``.

    Args:
        err: The signal-cli error, either a ``dict`` (JSON-RPC error shape) or
            an arbitrary exception object whose string form is inspected.

    Returns:
        The parsed Retry-After window in seconds, or ``None`` when neither
        source yields a value.
    """
    msg = ""
    if isinstance(err, dict):
        data = err.get("data") or {}
        response = data.get("response") or {}
        results = response.get("results") or []
        candidates = [
            r.get("retryAfterSeconds") for r in results
            if isinstance(r, dict) and r.get("retryAfterSeconds")
        ]
        if candidates:
            # The server reports per-result windows; take the largest as the
            # conservative upper bound for the whole batch.
            return float(max(candidates))
        msg = str(err.get("message", ""))
    else:
        msg = str(err)
    match = _RETRY_AFTER_RE.search(msg)
    return float(match.group(1)) if match else None


def _is_signal_rate_limit_error(err: Any) -> bool:
    """Return True if a signal-cli RPC error reflects a rate-limit failure.

    Three layers are matched:
        * typed ``RATELIMIT_ERROR`` code (signal-cli ≥ v0.14.3, plain
          RateLimitException);
        * legacy ``[429]`` / ``RateLimitException`` substrings;
        * libsignal-net's ``RetryLaterException`` / ``Retry after N seconds``
          surfaced inside ``AttachmentInvalidException`` when the rate limit is
          hit during attachment upload — signal-cli never re-tags these as
          RateLimitException, so the substring is the only available signal.

    Args:
        err: The signal-cli error, either a ``dict`` or an arbitrary exception
            object.

    Returns:
        ``True`` when the error is recognised as a rate-limit condition.
    """
    if isinstance(err, dict) and err.get("code") == SIGNAL_RPC_ERROR_RATELIMIT:
        return True

    message = (
        str(err.get("message", ""))
        if isinstance(err, dict)
        else str(err)
    )
    msg_lower = message.lower()
    return (
        "[429]" in message
        or "ratelimit" in msg_lower
        or "retrylaterexception" in msg_lower
        or "retry after" in msg_lower
    )


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _format_wait(seconds: float) -> str:
    """Format a wait duration for a user-facing pacing notice.

    Args:
        seconds: The wait duration in seconds.

    Returns:
        A compact human-readable label such as ``"42s"`` or ``"3 min"``.
    """
    s = max(0.0, seconds)
    if s < 90:
        return f"{int(round(s))}s"
    return f"{max(1, int(round(s / 60)))} min"


def _signal_send_timeout(num_attachments: int) -> float:
    """Compute the HTTP timeout for a Signal ``send`` RPC.

    signal-cli uploads attachments serially during the call, so the server-side
    time scales with batch size. The default 30s is fine for text-only sends but
    truncates large attachment batches mid-upload — which would otherwise log a
    phantom failure even though signal-cli completes the send a few seconds
    later. We scale at 5s per attachment with a 60s floor (and a 30s floor for
    text-only sends).

    Args:
        num_attachments: The number of attachments in the outgoing message.

    Returns:
        The timeout in seconds to use for the send RPC.
    """
    if num_attachments <= 0:
        return 30.0
    return max(60.0, 5.0 * num_attachments)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class SignalAttachmentScheduler:
    """Process-wide token-bucket simulator for Signal attachment sends.

    The bucket holds up to ``capacity`` tokens (default 50, matching Signal's
    server-side rate-limit bucket size). Each attachment consumes one token.
    Tokens refill at ``refill_rate`` tokens/second, calibrated from the
    per-token Retry-After hint received from the server when a 429 fires. Until
    a 429 has been observed, the documented default of 1 token / 4 seconds is
    used.

    Concurrent :meth:`acquire` calls serialise through an :class:`asyncio.Lock`,
    giving natural FIFO ordering across the agent sessions sharing one daemon.

    This is a *model*: it does not deduct tokens on ``acquire``; instead the
    caller reports the real RPC outcome via :meth:`report_rpc_duration` and
    :meth:`feedback` so the model stays aligned with the server's timeline.
    """

    def __init__(
        self,
        capacity: float = float(SIGNAL_RATE_LIMIT_BUCKET_CAPACITY),
        default_retry_after: float = float(SIGNAL_RATE_LIMIT_DEFAULT_RETRY_AFTER),
    ) -> None:
        """Initialise the token-bucket model.

        Args:
            capacity: Maximum number of tokens the bucket can hold. Defaults to
                :data:`SIGNAL_RATE_LIMIT_BUCKET_CAPACITY` (50).
            default_retry_after: Per-token refill window in seconds used before
                the server has supplied an authoritative value. Defaults to
                :data:`SIGNAL_RATE_LIMIT_DEFAULT_RETRY_AFTER` (4).
        """
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = 1.0 / float(default_retry_after)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Add tokens accrued since ``last_refill`` without exceeding capacity.

        Uses a monotonic clock so the bucket is unaffected by wall-clock
        adjustments. The caller is responsible for holding ``self._lock``.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0 and self.tokens < self.capacity:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_wait(self, n: int) -> float:
        """Best-effort estimate of seconds until ``n`` tokens would be free.

        Used to decide whether to emit a user-facing pacing notice *before*
        committing to an :meth:`acquire` that may block silently. This method is
        lock-free; small races against concurrent acquires are benign because
        the result is only used for an informational notice.

        Args:
            n: The number of tokens the caller intends to acquire.

        Returns:
            The estimated wait in seconds (``0.0`` when enough tokens already
            appear available).
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        projected = self.tokens
        if elapsed > 0 and projected < self.capacity:
            projected = min(self.capacity, projected + elapsed * self.refill_rate)
        deficit = n - projected
        if deficit <= 0:
            return 0.0
        return deficit / self.refill_rate

    async def acquire(self, n: int) -> float:
        """Block until at least ``n`` tokens are available; return seconds slept.

        This does **not** deduct tokens — the bucket is a read-only model of
        server-side capacity. After the RPC completes, call
        :meth:`report_rpc_duration` to synchronise the model with the server
        timeline, or :meth:`feedback` on a 429.

        The simulation is imperfect when many coroutines try to acquire for big
        uploads (``report_rpc_duration`` may lag), but the Signal server remains
        ground truth and will raise rate-limit exceptions that trigger requeues.

        The lock is released during ``asyncio.sleep`` so other callers can
        interleave. A retry loop re-checks after each sleep in case the deadline
        computed from the model was pessimistic.

        Args:
            n: The number of tokens required before the send may proceed.

        Returns:
            The total number of seconds spent sleeping while waiting.

        Raises:
            SignalSchedulerError: If ``n`` exceeds the bucket capacity, which can
                never be satisfied.
        """
        if n <= 0:
            return 0.0
        if n > self.capacity:
            raise SignalSchedulerError(
                f"Signal scheduler was called requesting {n} tokens "
                f"(max is {self.capacity})",
            )

        total_slept = 0.0
        first_pass = True
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= n:
                    if not first_pass or total_slept > 0:
                        logger.debug(
                            "Signal scheduler: tokens sufficient for %d "
                            "(remaining=%.1f, total_slept=%.1fs)",
                            n, self.tokens, total_slept,
                        )
                    return total_slept
                deficit = n - self.tokens
            wait = deficit / self.refill_rate
            if first_pass:
                logger.info(
                    "Signal scheduler: pausing %.1fs for %d tokens "
                    "(available=%.1f, deficit=%.1f, refill=%.4f/s ≈ %.1fs/token)",
                    wait, n, self.tokens, deficit,
                    self.refill_rate, 1.0 / self.refill_rate,
                )
                first_pass = False
            await asyncio.sleep(wait)
            total_slept += wait

    async def report_rpc_duration(self, rpc_duration: float, n_attachments: int) -> None:
        """Record an attachment-send RPC that just completed.

        Deducts ``n_attachments`` tokens *without* crediting refill during the
        upload window. Signal's server checks the bucket at RPC start and does
        not refill during request processing — refill resumes only after the
        response. Crediting upload-time refill would cause cumulative drift that
        eventually triggers 429s. ``last_refill`` is advanced so the next
        :meth:`acquire` / :meth:`_refill` starts counting from this point.

        Args:
            rpc_duration: Wall-clock seconds the just-completed RPC took.
            n_attachments: Number of attachments the RPC sent (tokens to deduct).
        """
        if n_attachments <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            token_before = self.tokens
            self.tokens = max(0.0, token_before - float(n_attachments))
            self.last_refill = now
        logger.log(
            logging.INFO if rpc_duration > 10 and n_attachments > 5 else logging.DEBUG,
            "Signal scheduler: RPC for %d att took %.1fs — "
            "tokens %.1f → %.1f (deducted=%d, no upload refill credited, refill=%.4fs⁻¹)",
            n_attachments, rpc_duration,
            token_before, self.tokens,
            n_attachments, self.refill_rate,
        )

    def feedback(self, retry_after: Optional[float], n_attempted: int) -> None:
        """Apply server feedback received after a 429 response.

        ``retry_after`` is the per-token refill window the server reports
        (``None`` when signal-cli is older than v0.14.3 and did not surface it).
        When present we recalibrate ``refill_rate`` from it, because the server
        is authoritative. The bucket is then reset so the next acquire waits for
        the server's implied drain to recover.

        Args:
            retry_after: Per-token Retry-After seconds from the server, or
                ``None`` if unavailable.
            n_attempted: Number of tokens (attachments) the failed attempt tried
                to send; retained for symmetry with callers.
        """
        if retry_after and retry_after > 0:
            new_rate = 1.0 / float(retry_after)
            if new_rate != self.refill_rate:
                logger.info(
                    "Signal scheduler: calibrating refill_rate to %.4f tokens/sec "
                    "(server retry_after=%.1fs per token)",
                    new_rate, retry_after,
                )
                self.refill_rate = new_rate
        self.tokens = 0.0
        self.last_refill = time.monotonic()

    def state(self) -> dict:
        """Return the current scheduler state for diagnostic logging.

        Read-only and side-effect free: it does not advance ``last_refill``, so
        it is safe to call from logging paths without perturbing the bucket. The
        returned token count is projected forward to ``now`` for accuracy.

        Returns:
            A dict with ``tokens``, ``capacity``, ``refill_rate`` and
            ``refill_seconds_per_token`` keys.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        projected = self.tokens
        if elapsed > 0 and projected < self.capacity:
            projected = min(self.capacity, projected + elapsed * self.refill_rate)
        return {
            "tokens": round(projected, 1),
            "capacity": int(self.capacity),
            "refill_rate": round(self.refill_rate, 4),
            "refill_seconds_per_token": round(1.0 / self.refill_rate, 1) if self.refill_rate > 0 else float("inf"),
        }


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[SignalAttachmentScheduler] = None


def get_scheduler() -> SignalAttachmentScheduler:
    """Return the process-wide scheduler, creating it on first access.

    Returns:
        The shared :class:`SignalAttachmentScheduler` singleton.
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = SignalAttachmentScheduler()
        logger.info(
            "Signal scheduler: created (capacity=%d tokens, refill=%.4f/s ≈ %.1fs/token)",
            int(_scheduler.capacity),
            _scheduler.refill_rate,
            1.0 / _scheduler.refill_rate,
        )
    return _scheduler


def _reset_scheduler() -> None:
    """Drop the cached scheduler so the next ``get_scheduler`` builds a fresh one.

    Test-only helper — never call from production paths, as it discards any
    calibrated rate state.
    """
    global _scheduler
    _scheduler = None
