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

"""Credential pool for API key rotation on rate limits.

Inspired by Hermes Agent's ``credential_pool.py``.  When a provider
returns 429 (rate limit), the pool automatically rotates to the next
available credential entry so the agent can continue without waiting
for the rate-limit window.

Each entry tracks health (consecutive failures) and is temporarily
suspended after ``MAX_CONSECUTIVE_FAILURES`` errors.
"""

import copy
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_BASE_URLS: dict[str, list[str]] = {
    "openai": ["https://api.openai.com/v1"],
    "anthropic": ["https://api.anthropic.com/v1"],
    "google": ["https://generativelanguage.googleapis.com/v1beta"],
    "deepseek": ["https://api.deepseek.com/v1"],
    "groq": ["https://api.groq.com/openai/v1"],
    "together": ["https://api.together.xyz/v1"],
    "openrouter": ["https://openrouter.ai/api/v1"],
}


MAX_CONSECUTIVE_FAILURES = 3
HEALTH_RESET_AFTER_SECONDS = 300.0


@dataclass
class CredentialEntry:
    """A single API credential (key + optional base URL + backend type)."""
    api_key: str
    base_url: str = ""
    backend_type: str = ""
    # Health tracking
    consecutive_failures: int = 0
    last_failure_at: float = 0.0
    suspended_until: float = 0.0


@dataclass
class PoolSnapshot:
    """Read-only snapshot of pool state for logging / telemetry."""
    entries: list[dict[str, Any]]
    current_index: int
    degraded: bool


class CredentialPool:
    """Rotating pool of API credentials with health tracking.

    Usage::

        pool = CredentialPool(api_keys=["key1", "key2"], base_urls=[...])
        entry = pool.get()           # current active entry
        entry = pool.rotate(exc)     # rotate on error, returns next entry
        pool.mark_success()          # reset failure counter on success
    """

    def __init__(
        self,
        api_keys: list[str],
        *,
        base_urls: list[str] | None = None,
        backend_types: list[str] | None = None,
        provider: str = "",
    ) -> None:
        if not api_keys:
            raise ValueError("CredentialPool requires at least one API key")

        defaults = DEFAULT_BASE_URLS.get(provider.lower(), [])
        self._entries: list[CredentialEntry] = []
        for i, key in enumerate(api_keys):
            self._entries.append(CredentialEntry(
                api_key=key,
                base_url=base_urls[i] if base_urls and i < len(base_urls) else (
                    defaults[i] if i < len(defaults) else defaults[0]
                ) if defaults else "",
                backend_type=backend_types[i] if backend_types and i < len(backend_types) else "",
            ))
        self._current = 0
        self._degraded = len(api_keys) == 1

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def get(self) -> CredentialEntry:
        """Return the current active entry (no side effects)."""
        self._prune_suspended()
        return self._entries[self._current]

    def rotate(self, exc: BaseException | None = None) -> CredentialEntry:
        """Record a failure on the current entry and advance to the next.

        If *exc* is provided, the current entry's failure counter is
        incremented.  Returns the new active entry.
        """
        now = time.time()
        current = self._entries[self._current]

        if exc is not None:
            current.consecutive_failures += 1
            current.last_failure_at = now
            if current.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                current.suspended_until = now + HEALTH_RESET_AFTER_SECONDS

        # Find the next healthy entry
        start = self._current
        for offset in range(1, len(self._entries)):
            idx = (start + offset) % len(self._entries)
            candidate = self._entries[idx]
            if candidate.suspended_until <= now:
                self._current = idx
                self._degraded = False
                return self._entries[idx]

        # All entries suspended; use the least-recently-failed one
        best = min(self._entries, key=lambda e: e.last_failure_at)
        self._current = self._entries.index(best)
        self._degraded = True
        return best

    def mark_success(self) -> None:
        """Reset the failure counter on the current entry."""
        entry = self._entries[self._current]
        entry.consecutive_failures = 0

    def _prune_suspended(self) -> None:
        """Clear suspension on entries whose cooldown has expired."""
        now = time.time()
        for entry in self._entries:
            if entry.suspended_until > 0 and entry.suspended_until <= now:
                entry.suspended_until = 0.0
                entry.consecutive_failures = 0

    def snapshot(self) -> PoolSnapshot:
        """Return a diagnostic snapshot of pool state."""
        return PoolSnapshot(
            entries=[{
                "api_key": e.api_key[:8] + "...",
                "consecutive_failures": e.consecutive_failures,
                "suspended": e.suspended_until > time.time(),
            } for e in self._entries],
            current_index=self._current,
            degraded=self._degraded,
        )
