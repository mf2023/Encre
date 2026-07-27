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

"""Tests for gateway authorization (Phase 2a).

Covers:
- :class:`PairingStore` code mint / redeem / expiry / persistence.
- :class:`AuthorizationChecker` 5-layer precedence (platform allow-all >
  allowlist > pairing > global allow-all > deny), with settings + env sources.
- ``/pair`` slash command in :meth:`BaseAdapter.handle_message`.
- Reject notice sent on denial; authorized message dispatched.
"""

import asyncio
import os
import time

import pytest

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.authz import (
    AuthorizationChecker,
    LAYER_ALLOWLIST,
    LAYER_DEFAULT_ALLOW,
    LAYER_DENY,
    LAYER_GLOBAL_ALLOW_ALL,
    LAYER_PAIRING,
    LAYER_PLATFORM_ALLOW_ALL,
)
from encre.gateway.pairing import PairingStore


# ── PairingStore ────────────────────────────────────────────────────────


@pytest.fixture
def pairing(tmp_path):
    store = PairingStore(path=tmp_path / "pairing.json")
    yield store
    store.close()


def test_pairing_mint_and_redeem(pairing):
    code = pairing.create_code(ttl=600)
    assert len(code) == 6
    assert pairing.redeem(code, "telegram", "42") is True
    assert pairing.is_paired("telegram", "42") is True


def test_pairing_redeem_unknown_code(pairing):
    assert pairing.redeem("NOPE", "telegram", "42") is False
    assert pairing.is_paired("telegram", "42") is False


def test_pairing_redeem_twice_fails(pairing):
    code = pairing.create_code()
    assert pairing.redeem(code, "telegram", "42") is True
    # Second redeem of the same code is rejected.
    assert pairing.redeem(code, "telegram", "99") is False
    assert pairing.is_paired("telegram", "99") is False


def test_pairing_expired_code(pairing):
    code = pairing.create_code(ttl=-1)  # already expired
    assert pairing.redeem(code, "telegram", "42") is False
    assert pairing.is_paired("telegram", "42") is False


def test_pairing_unpair(pairing):
    code = pairing.create_code()
    pairing.redeem(code, "telegram", "42")
    assert pairing.is_paired("telegram", "42") is True
    assert pairing.unpair("telegram", "42") is True
    assert pairing.is_paired("telegram", "42") is False
    assert pairing.unpair("telegram", "42") is False  # already gone


def test_pairing_persists_across_reopen(tmp_path):
    p = tmp_path / "pairing.json"
    s1 = PairingStore(path=p)
    code = s1.create_code()
    s1.redeem(code, "telegram", "42")
    s1.close()
    s2 = PairingStore(path=p)
    assert s2.is_paired("telegram", "42") is True
    s2.close()


def test_pairing_is_per_platform_user(pairing):
    code = pairing.create_code()
    pairing.redeem(code, "telegram", "42")
    # Same user_id on a different platform is NOT paired.
    assert pairing.is_paired("discord", "42") is False


# ── AuthorizationChecker 5-layer precedence ────────────────────────────


def _checker(settings=None, pairing=None, monkeypatch_env=None):
    cfg = settings or {}

    def config_fn():
        return cfg

    return AuthorizationChecker(pairing=pairing, config_fn=config_fn)


def _src(platform="telegram", user_id="42", user_id_alt=None):
    return SessionSource(platform=platform, chat_id="1", chat_type="dm", user_id=user_id, user_id_alt=user_id_alt)


def test_authz_default_allow():
    """With no authorization configured, the default is to allow all (legacy)."""
    c = _checker()
    r = c.is_authorized(_src(), "telegram")
    assert r.authorized
    assert r.layer == LAYER_DEFAULT_ALLOW


def test_authz_platform_allow_all_settings():
    c = _checker(settings={"adapter_telegram_allow_all": "true"})
    r = c.is_authorized(_src(user_id="anyone"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PLATFORM_ALLOW_ALL


def test_authz_platform_allow_all_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL_USERS", "1")
    c = _checker()
    r = c.is_authorized(_src(user_id="anyone"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PLATFORM_ALLOW_ALL


def test_authz_allowlist_settings():
    c = _checker(settings={"adapter_telegram_allowed_users": "42,99"})
    assert c.is_authorized(_src(user_id="42"), "telegram").authorized is True
    assert c.is_authorized(_src(user_id="99"), "telegram").authorized is True
    r = c.is_authorized(_src(user_id="77"), "telegram")
    assert r.authorized is False
    assert r.layer == LAYER_DENY


def test_authz_allowlist_user_id_alt():
    c = _checker(settings={"adapter_signal_allowed_users": "uuid-1"})
    r = c.is_authorized(_src(platform="signal", user_id="9", user_id_alt="uuid-1"), "signal")
    assert r.authorized
    assert r.layer == LAYER_ALLOWLIST


def test_authz_allowlist_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "42")
    c = _checker()
    assert c.is_authorized(_src(user_id="42"), "telegram").authorized is True
    assert c.is_authorized(_src(user_id="77"), "telegram").authorized is False


def test_authz_pairing_layer(pairing):
    pairing.redeem(pairing.create_code(), "telegram", "42")
    c = _checker(pairing=pairing)
    r = c.is_authorized(_src(user_id="42"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PAIRING


def test_authz_global_allow_all():
    c = _checker(settings={"gateway_allow_all_users": "true"})
    r = c.is_authorized(_src(user_id="anyone"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_GLOBAL_ALLOW_ALL


def test_authz_global_allow_all_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_ALLOW_ALL_USERS", "yes")
    c = _checker()
    r = c.is_authorized(_src(user_id="anyone"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_GLOBAL_ALLOW_ALL


def test_authz_precedence_platform_over_allowlist():
    """Platform allow-all beats allowlist (a user not in the list is still allowed)."""
    c = _checker(settings={
        "adapter_telegram_allow_all": "true",
        "adapter_telegram_allowed_users": "99",
    })
    r = c.is_authorized(_src(user_id="77"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PLATFORM_ALLOW_ALL


def test_authz_precedence_allowlist_over_pairing(pairing):
    """Allowlist beats pairing (paired user not in list is denied... no: paired
    is a separate layer below allowlist; allowlist match wins)."""
    pairing.redeem(pairing.create_code(), "telegram", "42")
    c = _checker(settings={"adapter_telegram_allowed_users": "99"}, pairing=pairing)
    # 42 is paired but NOT in allowlist -> pairing layer applies (authorized).
    r = c.is_authorized(_src(user_id="42"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PAIRING
    # 99 is in allowlist -> allowlist wins.
    r2 = c.is_authorized(_src(user_id="99"), "telegram")
    assert r2.authorized
    assert r2.layer == LAYER_ALLOWLIST


def test_authz_precedence_pairing_over_global(pairing):
    """Paired user hits the pairing layer, not global."""
    pairing.redeem(pairing.create_code(), "telegram", "42")
    c = _checker(settings={"gateway_allow_all_users": "true"}, pairing=pairing)
    r = c.is_authorized(_src(user_id="42"), "telegram")
    assert r.authorized
    assert r.layer == LAYER_PAIRING


def test_authz_no_user_id_denies():
    """A message with no user_id can only pass via allow-all."""
    c = _checker(settings={"adapter_telegram_allowed_users": "42"})
    r = c.is_authorized(SessionSource(platform="telegram", chat_id="1", chat_type="dm"), "telegram")
    assert not r.authorized
    assert r.layer == LAYER_DENY


# ── handle_message integration: /pair + reject ─────────────────────────


class _AuthzAdapter(BasePlatformAdapter):
    name = "telegram"

    def __init__(self):
        super().__init__()
        self.sent: list[tuple[str, str]] = []

    async def connect(self, *, is_reconnect=False) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id="m1")


def _event(text, chat_id="1", user_id="42"):
    return MessageEvent(
        text=text,
        source=SessionSource(platform="telegram", chat_id=chat_id, chat_type="dm", user_id=user_id),
    )


@pytest.mark.asyncio
async def test_handle_message_rejects_unauthorized(tmp_path):
    a = _AuthzAdapter()
    pairing = PairingStore(path=tmp_path / "p.json")
    a.set_pairing(pairing)
    # Configure an allowlist that excludes "intruder" so auth check is active.
    a.set_authz(AuthorizationChecker(pairing=pairing, config_fn=lambda: {"adapter_telegram_allowed_users": "legit-user"}))
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event)

    a.set_message_handler(handler)
    await a.handle_message(_event("hi", user_id="intruder"))
    assert dispatched == []  # never reached the handler
    assert a.sent  # a reject notice was sent
    assert "not authorized" in a.sent[0][1].lower() or "⛔" in a.sent[0][1]
    pairing.close()


@pytest.mark.asyncio
async def test_handle_message_pair_redeem_flow(tmp_path):
    a = _AuthzAdapter()
    pairing = PairingStore(path=tmp_path / "p.json")
    a.set_pairing(pairing)
    a.set_authz(AuthorizationChecker(pairing=pairing, config_fn=lambda: {}))

    # 1. Intruder tries /pair with an unknown code -> rejected, not paired.
    await a.handle_message(_event("/pair WRONG", user_id="intruder"))
    assert pairing.is_paired("telegram", "intruder") is False
    assert any("Invalid" in c or "❌" in c for _, c in a.sent)

    a.sent.clear()
    # 2. Mint a code (no authz check on mint when no authorized user... but
    #    authz is on and the minter is unauthorized -> must be denied mint).
    #    To mint, disable authz temporarily via global allow-all.
    a2 = _AuthzAdapter()
    a2.set_pairing(pairing)
    a2.set_authz(AuthorizationChecker(pairing=pairing, config_fn=lambda: {"gateway_allow_all_users": "true"}))
    await a2.handle_message(_event("/pair", user_id="admin"))
    # The mint notice contains the code.
    mint_msg = [c for _, c in a2.sent if "Pairing code:" in c]
    assert mint_msg, f"expected mint notice, got {a2.sent}"
    code = mint_msg[0].split("Pairing code:")[1].split("\n")[0].strip()
    assert len(code) == 6

    a2.sent.clear()
    # 3. New user redeems the code -> paired + authorized.
    await a2.handle_message(_event(f"/pair {code}", user_id="newuser"))
    assert pairing.is_paired("telegram", "newuser") is True
    assert any("Paired" in c or "✅" in c for _, c in a2.sent)

    a2.sent.clear()
    # 4. Now the paired newuser can send a normal message -> dispatched.
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event)

    a2.set_message_handler(handler)
    await a2.handle_message(_event("hello", user_id="newuser"))
    assert len(dispatched) == 1
    pairing.close()


@pytest.mark.asyncio
async def test_handle_message_no_authz_allows_everything():
    """Without an authz checker, handle_message dispatches everything (legacy)."""
    a = _AuthzAdapter()
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event)

    a.set_message_handler(handler)
    await a.handle_message(_event("hi", user_id="anyone"))
    assert len(dispatched) == 1
    assert a.sent == []  # no reject notice
