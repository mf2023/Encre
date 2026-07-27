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

"""Gateway authorization: the 5-layer user-allow check.

Evaluated in order, first match wins:

1. **Per-platform allow-all** -- ``adapter_<name>_allow_all`` (settings) or
   ``<NAME>_ALLOW_ALL_USERS`` (env).  If set, every user on that platform is
   authorized.
2. **Platform allowlist** -- ``adapter_<name>_allowed_users`` (settings) or
   ``<NAME>_ALLOWED_USERS`` (env), a comma-separated list of platform user ids.
   The message's ``user_id`` (or ``user_id_alt``) must be present.
3. **DM pairing** -- the user previously redeemed a pairing code (see
   :mod:`encre.gateway.pairing`), binding their ``(platform, user_id)``.
4. **Global allow-all** -- ``gateway_allow_all_users`` (settings) or
   ``GATEWAY_ALLOW_ALL_USERS`` (env).  If set, every user on every platform is
   authorized.
5. **Default: deny** -- unauthorized users are rejected.

Config sources: the encrypted ``settings.json`` (loaded via
:func:`encre.settings_manager.load_settings`) provides ``adapter_<name>_*``
and ``gateway_*`` keys; environment variables override settings and use the
``<NAME>_ALLOWED_USERS`` / ``<NAME>_ALLOW_ALL_USERS`` names so a
deployment can drive authorization purely from env.

Design: stateless per-call -- the checker reads the latest config + pairing
state on every :meth:`is_authorized` call, so a config change or a fresh
pairing takes effect immediately without a restart.
"""

import logging
import os
from dataclasses import dataclass
from typing import Callable

from encre.gateway.pairing import PairingStore
from encre.gateway.session import SessionSource
from encre.settings_manager import load_settings

logger = logging.getLogger("encre.gateway.authz")

# Layer names surfaced in AuthzResult.layer / logs.
LAYER_PLATFORM_ALLOW_ALL = "platform_allow_all"
LAYER_ALLOWLIST = "allowlist"
LAYER_PAIRING = "pairing"
LAYER_GLOBAL_ALLOW_ALL = "global_allow_all"
LAYER_DENY = "deny"
LAYER_DEFAULT_ALLOW = "default_allow"

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthzResult:
    """Outcome of an authorization check.

    Attributes:
        authorized: Whether the user is allowed to talk to the bot.
        reason: Human-readable one-line reason (for logs / the reject notice).
        layer: Which layer decided (one of the ``LAYER_*`` constants).
    """

    authorized: bool
    reason: str
    layer: str


class AuthorizationChecker:
    """5-layer authorization check.

    Constructed once per gateway (owned by :class:`~encre.gateway.run.GatewayRunner`)
    and injected into each adapter via :meth:`BasePlatformAdapter.set_authz`.  The check
    is evaluated in :meth:`BasePlatformAdapter.handle_message` *before* the two-level
    guard, so unauthorized messages never reach the agent loop.
    """

    def __init__(
        self,
        pairing: PairingStore | None = None,
        config_fn: Callable[[], dict] | None = None,
    ) -> None:
        self._pairing = pairing
        self._config_fn = config_fn or load_settings

    # ── config helpers ─────────────────────────────────────────────────

    def _settings(self) -> dict:
        try:
            return self._config_fn() or {}
        except Exception:
            return {}

    @staticmethod
    def _truthy(value: str | None) -> bool:
        return bool(value) and str(value).strip().lower() in _TRUE

    @staticmethod
    def _split_ids(raw: str) -> list[str]:
        return [s.strip() for s in str(raw).split(",") if s.strip()]

    def _cfg(self, key: str, default: str = "") -> str:
        """Read a config value: env var (uppercased key) overrides settings."""
        env = os.environ.get(key.upper())
        if env is not None and env != "":
            return env
        return str(self._settings().get(key, default))

    def _any_auth_configured(self, adapter_name: str, upper: str) -> bool:
        """True when at least one authorization setting or env var is present.

        Layer 0 of the check: when nothing is configured, the default is
        "allow all" (legacy backward-compatible behaviour).  Authorization
        only activates once the user explicitly sets a flag or list.
        """
        # Per-platform settings
        if self._truthy(self._cfg(f"adapter_{adapter_name}_allow_all")):
            return True
        if self._cfg(f"adapter_{adapter_name}_allowed_users"):
            return True
        # Per-platform env vars
        if self._truthy(os.environ.get(f"{upper}_ALLOW_ALL_USERS")):
            return True
        if os.environ.get(f"{upper}_ALLOWED_USERS"):
            return True
        # Global settings/env
        if self._truthy(self._cfg("gateway_allow_all_users")):
            return True
        if self._truthy(os.environ.get("GATEWAY_ALLOW_ALL_USERS")):
            return True
        # Pairing store with at least one paired user
        if self._pairing is not None and self._pairing.list_paired():
            return True
        return False

    # ── the check ──────────────────────────────────────────────────────

    def is_authorized(self, source: SessionSource, adapter_name: str) -> AuthzResult:
        """Evaluate the 5-layer check for a message source.

        Args:
            source: The structured message origin (carries ``user_id`` /
                ``user_id_alt`` for allowlist + pairing).
            adapter_name: The adapter's ``name`` (platform id).

        Returns:
            An :class:`AuthzResult` describing the first matching layer.
        """
        upper = adapter_name.upper()
        user_ids = {source.user_id, source.user_id_alt}
        user_ids.discard(None)

        # Layer 0: if no authorization is configured at all (no allow-all, no
        # allowlist, no global flag), allow everything.  This preserves the
        # legacy behaviour where every user is authorized by default.
        if not self._any_auth_configured(adapter_name, upper):
            return AuthzResult(True, "no auth configured", "default_allow")

        # 1. Per-platform allow-all.
        if self._truthy(self._cfg(f"adapter_{adapter_name}_allow_all")):
            return AuthzResult(True, f"platform {adapter_name} allow-all", LAYER_PLATFORM_ALLOW_ALL)
        env_allow_all = os.environ.get(f"{upper}_ALLOW_ALL_USERS")
        if self._truthy(env_allow_all):
            return AuthzResult(True, f"platform {adapter_name} allow-all (env)", LAYER_PLATFORM_ALLOW_ALL)

        # 2. Platform allowlist.
        allowed_raw = self._cfg(f"adapter_{adapter_name}_allowed_users") or os.environ.get(
            f"{upper}_ALLOWED_USERS", ""
        )
        if allowed_raw:
            allowed = set(self._split_ids(allowed_raw))
            matched = next((u for u in user_ids if u and u in allowed), None)
            if matched is not None:
                return AuthzResult(True, f"allowlist ({adapter_name})", LAYER_ALLOWLIST)

        # 3. DM pairing.
        if self._pairing is not None:
            for uid in user_ids:
                if uid and self._pairing.is_paired(source.platform, uid):
                    return AuthzResult(True, "paired", LAYER_PAIRING)

        # 4. Global allow-all.
        if self._truthy(self._cfg("gateway_allow_all_users")):
            return AuthzResult(True, "global allow-all", LAYER_GLOBAL_ALLOW_ALL)
        if self._truthy(os.environ.get("GATEWAY_ALLOW_ALL_USERS")):
            return AuthzResult(True, "global allow-all (env)", LAYER_GLOBAL_ALLOW_ALL)

        # 5. Default: deny.
        return AuthzResult(False, "not authorized", LAYER_DENY)
