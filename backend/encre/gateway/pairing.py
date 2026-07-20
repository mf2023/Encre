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

"""DM pairing flow for gateway user authorization.

Aligns with Hermes' ``gateway/pairing.py``: an already-authorized user (or
the gateway operator) mints a short-lived pairing code; a new user redeems it
by DMing the bot ``/pair <code>``, which binds their platform ``user_id`` to
the authorized set.  Pairing state persists across restarts.

Flow::

    Operator: /pair            ->  PairingStore.create_code()  ->  "ABC123"
    New user:  /pair ABC123     ->  PairingStore.redeem(...)    ->  "Paired!"

State lives in ``<data_dir>/gateway_pairing.json`` (two maps: pending codes
and redeemed user bindings).  The store is thread-safe via a single lock; the
inbound path calls :meth:`is_paired` on every message, so lookups are cheap.
"""

import json
import logging
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from encre.config import get_data_dir

logger = logging.getLogger("encre.gateway.pairing")

# Pairing code lifetime (seconds).  Mirrors Hermes' default 10-minute window.
PAIRING_CODE_TTL = 600.0
# Length of the human-friendly pairing code (no ambiguous chars).
PAIRING_CODE_LEN = 6
# Alphabet without look-alikes (no 0/O, 1/I/L).
_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class PairingCode:
    """A pending (un-redeemed) pairing code."""

    code: str
    created_at: float
    expires_at: float
    redeemed: bool = False


@dataclass
class PairedUser:
    """A user binding created by redeeming a pairing code."""

    platform: str
    user_id: str
    paired_at: float


def _binding_key(platform: str, user_id: str) -> str:
    return f"{platform}:{user_id}"


class PairingStore:
    """Persisted pairing state: pending codes + authorized user bindings.

    The store is the source of truth for "which users paired themselves via a
    code".  It is one input to the authorization check (the third layer, see
    :mod:`encre.gateway.authz`); allow-all / allowlist / global flags are
    evaluated separately.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(get_data_dir()) / "gateway_pairing.json"
        self._path = Path(path)
        self._lock = threading.Lock()
        self._codes: dict[str, PairingCode] = {}
        self._paired: dict[str, PairedUser] = {}
        self._load()

    # ── persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._codes = {
                    str(k): PairingCode(**v) for k, v in (data.get("codes") or {}).items()
                }
                self._paired = {
                    str(k): PairedUser(**v) for k, v in (data.get("paired") or {}).items()
                }
            except Exception as e:
                logger.warning("[pairing] failed to load %s: %s", self._path, e)
                self._codes = {}
                self._paired = {}

    def _save(self) -> None:
        # Caller holds self._lock.
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "codes": {k: asdict(v) for k, v in self._codes.items()},
                "paired": {k: asdict(v) for k, v in self._paired.items()},
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning("[pairing] failed to save %s: %s", self._path, e)

    # ── code lifecycle ────────────────────────────────────────────────

    def create_code(self, ttl: float = PAIRING_CODE_TTL) -> str:
        """Mint a fresh pairing code valid for ``ttl`` seconds.

        Returns the human-friendly code string.  Existing pending codes are
        left in place (an operator may mint several for different users).
        """
        code = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LEN))
        now = time.time()
        with self._lock:
            self._codes[code] = PairingCode(code, now, now + ttl)
            self._save()
        logger.info("[pairing] minted code (ttl=%.0fs)", ttl)
        return code

    def redeem(self, code: str, platform: str, user_id: str) -> bool:
        """Redeem a pending code, binding ``(platform, user_id)``.

        Returns True on success, False if the code is unknown / expired /
        already redeemed.  A successful redeem is idempotent for the binding:
        re-redeeming an already-paired user's code is a no-op success only if
        the code is still pending.
        """
        if not code or not platform or not user_id:
            return False
        code = code.strip().upper()
        with self._lock:
            entry = self._codes.get(code)
            if entry is None:
                return False
            if entry.redeemed:
                return False
            if time.time() > entry.expires_at:
                self._codes.pop(code, None)
                self._save()
                return False
            entry.redeemed = True
            key = _binding_key(platform, user_id)
            self._paired[key] = PairedUser(platform, user_id, time.time())
            self._save()
            logger.info("[pairing] redeemed code for %s", key)
            return True

    def is_paired(self, platform: str, user_id: str) -> bool:
        """True if ``(platform, user_id)`` was bound by a prior redeem."""
        if not platform or not user_id:
            return False
        with self._lock:
            return _binding_key(platform, user_id) in self._paired

    def unpair(self, platform: str, user_id: str) -> bool:
        """Remove a user binding.  Returns True if a binding was removed."""
        if not platform or not user_id:
            return False
        with self._lock:
            existed = self._paired.pop(_binding_key(platform, user_id), None) is not None
            if existed:
                self._save()
            return existed

    def list_paired(self) -> list[PairedUser]:
        """Return all authorized user bindings (for status/debug)."""
        with self._lock:
            return list(self._paired.values())

    def list_pending_codes(self) -> list[PairingCode]:
        """Return all pending (un-redeemed, un-expired) codes."""
        now = time.time()
        with self._lock:
            return [c for c in self._codes.values() if not c.redeemed and c.expires_at > now]

    def close(self) -> None:
        """No-op (state is persisted on every mutation)."""
