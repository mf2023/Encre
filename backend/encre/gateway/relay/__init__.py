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

"""Relay subsystem: connector-backed platform fronting (EXPERIMENTAL).

Aligns with Hermes' ``gateway/relay/__init__.py``.  The relay is an
**indirect** platform path: instead of a direct platform adapter
(:mod:`encre.adapters.*`), the gateway dials out to a connector over a
WebSocket and lets the connector front the real platform.  This lets a hosted
gateway (no public inbound IP) still serve platform traffic.

Activation is **config-driven, not a feature flag**: when
``GATEWAY_RELAY_URL`` (env) or ``gateway.relay_url`` (settings) is set, the
relay platform is registered; otherwise the gateway is a normal direct-connect
single-tenant gateway and this module is inert.  This means adding the relay
subsystem is non-breaking -- existing deployments that do not configure a
relay URL are unaffected.

Public surface:

- :func:`relay_url` / :func:`relay_gateway_id` / :func:`relay_upgrade_secret`
  / :func:`relay_wake_url` -- read the relay config.
- :func:`register_relay_adapter` -- build a :class:`RelayAdapter` from config
  and register it as the ``relay`` platform in an :class:`AdapterManager`.
- :func:`relay_relevance_policy` / :func:`send_relay_policy` -- declare the
  gateway's message-relevance policy to the connector at boot.
- :func:`self_provision_relay` -- (stub) self-provision with the connector.
"""

import logging
import os
from typing import Any

logger = logging.getLogger("encre.gateway.relay")

# ── config accessors ────────────────────────────────────────────────────


def _settings() -> dict[str, Any]:
    try:
        from encre.settings_manager import load_settings
        return load_settings() or {}
    except Exception:
        return {}


def relay_url() -> str | None:
    """The connector URL to dial (``https://``/``http://``/``ws://``/``wss://``).

    Reads ``GATEWAY_RELAY_URL`` (env, takes precedence) or
    ``gateway.relay_url`` (settings).  None when relay is not configured.
    """
    env = os.environ.get("GATEWAY_RELAY_URL", "").strip()
    if env:
        return env
    val = _settings().get("gateway_relay_url") or _settings().get("relay_url")
    return str(val).strip() if val else None


def relay_gateway_id() -> str | None:
    """This gateway's identifier (for the upgrade-token payload)."""
    env = os.environ.get("GATEWAY_RELAY_GATEWAY_ID", "").strip()
    if env:
        return env
    val = _settings().get("gateway_relay_gateway_id")
    return str(val).strip() if val else None


def relay_upgrade_secret() -> str | None:
    """The per-gateway HMAC secret authenticating the WS upgrade."""
    env = os.environ.get("GATEWAY_RELAY_SECRET", "").strip()
    if env:
        return env
    val = _settings().get("gateway_relay_secret")
    return str(val).strip() if val else None


def relay_wake_url() -> str | None:
    """An out-of-band wake URL the connector can GET to wake a scaled-to-zero
    gateway.  None when scale-to-zero is not used.
    """
    env = os.environ.get("GATEWAY_RELAY_WAKE_URL", "").strip()
    if env:
        return env
    val = _settings().get("gateway_relay_wake_url")
    return str(val).strip() if val else None


def relay_platform_identities() -> list[dict[str, Any]]:
    """The platform identities this gateway fronts via the connector
    (e.g. ``[{platform: "discord", bot_id: "..."}]``)."""
    import json
    env = os.environ.get("GATEWAY_RELAY_IDENTITIES", "").strip()
    if env:
        try:
            return list(json.loads(env))
        except Exception:
            return []
    val = _settings().get("gateway_relay_identities")
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return list(json.loads(val))
        except Exception:
            return []
    return []


# ── registration ───────────────────────────────────────────────────────


def relay_is_configured() -> bool:
    """True when a relay URL is set (the relay platform should register)."""
    return bool(relay_url())


async def register_relay_adapter(manager: Any) -> bool:
    """Build a :class:`RelayAdapter` from config and register it with ``manager``.

    Called by :class:`~encre.adapters.manager.AdapterManager` at async startup
    when :func:`relay_is_configured` is True.  Returns True on success; False
    (and a logged warning) when the relay is not configured or registration
    fails -- never raises, so a misconfigured relay never aborts gateway startup.

    The adapter + its transport are constructed lazily here (not at module
    import) so an unconfigured gateway pays no import cost for the relay stack.
    """
    url = relay_url()
    if not url:
        return False
    try:
        from encre.gateway.relay.adapter import RelayAdapter
        from encre.gateway.relay.ws_transport import WebSocketRelayTransport

        identities = relay_platform_identities()
        # Use the first identity's platform/bot_id as the transport's primary
        # identity (a single WS fronts N platforms, but the hello frame
        # advertises at least one).
        platform = identities[0].get("platform", "relay") if identities else "relay"
        bot_id = identities[0].get("bot_id") if identities else None

        transport = WebSocketRelayTransport(
            url=url,
            platform=platform,
            bot_id=bot_id,
            identities=identities,
            gateway_id=relay_gateway_id(),
            upgrade_secret=relay_upgrade_secret(),
        )
        adapter = RelayAdapter(transport=transport)

        # Register into the manager's instance map directly (the relay platform
        # is not in _ADAPTER_CLASSES, so start_adapter cannot construct it).
        manager._instances["relay"] = adapter
        # Inject authz/pairing like any other adapter (relay bypasses authz via
        # authorization_is_upstream, but the handler/hook wiring still applies).
        adapter.set_authz(getattr(manager, "_authz", None))
        adapter.set_pairing(getattr(manager, "_pairing", None))
        ok = await adapter.connect()
        if ok:
            logger.info("[relay] registered relay platform (fronting %d identity/ies)", len(identities) or 1)
            # Declare the relevance policy to the connector (fail-soft).
            await send_relay_policy()
        else:
            manager._instances.pop("relay", None)
            logger.warning("[relay] adapter connect failed -- relay platform not registered")
        return ok
    except Exception as e:
        logger.warning("[relay] registration failed: %s %s", type(e).__name__, e)
        # Clean up a half-registered instance.
        if isinstance(manager, dict):
            pass
        try:
            manager._instances.pop("relay", None)
        except Exception:
            pass
        return False


# ── relevance policy (Phase 7 of the relay contract) ───────────────────


def relay_relevance_policy() -> dict[str, Any] | None:
    """Project the gateway's relevance knobs into a platform-agnostic policy.

    Returns None when the policy is all-default (the connector's absent-row
    default already matches, so the gateway sends nothing).  Mirrors Hermes'
    ``relay_relevance_policy()``.
    """
    require_address = bool(_settings().get("gateway_require_mention"))
    free_scopes = _settings().get("gateway_free_response_channels")
    if isinstance(free_scopes, str):
        free_scopes = [s.strip() for s in free_scopes.split(",") if s.strip()]
    allow_bots = str(_settings().get("gateway_allow_bots", "")).lower() in ("all", "mentions")
    if not require_address and not free_scopes and not allow_bots:
        return None
    policy: dict[str, Any] = {"platform": "relay"}
    if require_address:
        policy["requireAddress"] = True
    if free_scopes:
        policy["freeResponseScopes"] = list(free_scopes)
    if allow_bots:
        policy["allowOtherBots"] = True
    return policy


async def send_relay_policy() -> bool:
    """POST the relevance policy to the connector at boot (fail-soft).

    A failure logs and boot proceeds -- relevance is an optimization layered on
    the authorization gate, never a boot dependency.  Returns True on success.
    """
    policy = relay_relevance_policy()
    if policy is None:
        # All-default: the connector's absent-row default already matches.
        return True
    # The actual POST lives in the connector's /relay/policy route; this stub
    # logs the intent.  A full implementation would use the upgrade token +
    # the relay host.  Fail-soft: never raise.
    logger.info("[relay] would POST relevance policy: %s", policy)
    return True


# ── self-provisioning (stub) ───────────────────────────────────────────


def self_provision_relay() -> bool:
    """Self-provision with the connector (``/relay/provision``).

    Stub -- a full implementation would POST to the connector's provision
    route with the wake URL + gateway id and store the returned per-gateway
    secret.  Returns False when not yet implemented so callers fall back to
    an externally-provisioned secret.
    """
    if not relay_url():
        return False
    logger.debug("[relay] self_provision_relay not yet implemented (use an externally-provisioned secret)")
    return False
