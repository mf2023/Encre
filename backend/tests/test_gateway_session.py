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

"""Tests for the gateway session routing layer (Phase 0 contract alignment).

Covers:
- :func:`build_session_key` conformance vs the Hermes oracle format.
- :class:`SessionSource` wire round-trip (``is_bot`` stays off the wire).
- :class:`SessionStore` get / put / get_or_create / reset persistence.
- :class:`SendResult` new fields + :func:`classify_send_error` + SEND_ERROR_KINDS.
- :class:`MessageEvent.source` field + :meth:`BaseAdapter.get_chat_info` default.
- :class:`GatewayMessage` submit/submit_stream frames carry ``source``.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from encre.adapters.base import (
    SEND_ERROR_KINDS,
    BaseAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    classify_send_error,
)
from encre.gateway.protocol import GatewayMessage, GatewayOp
from encre.gateway.session import (
    SessionSource,
    SessionStore,
    build_session_key,
)


# ── build_session_key conformance ───────────────────────────────────────


@pytest.mark.parametrize(
    "source, expected",
    [
        # DM with chat_id -- the canonical Telegram private chat case.
        (
            SessionSource(platform="telegram", chat_id="123456789", chat_type="dm", user_id="42"),
            "agent:main:telegram:dm:123456789",
        ),
        # DM with chat_id + thread_id -- threaded DM isolated per thread.
        (
            SessionSource(platform="telegram", chat_id="123", chat_type="dm", thread_id="55"),
            "agent:main:telegram:dm:123:55",
        ),
        # DM without chat_id falls back to the sender id (per-user isolation).
        (
            SessionSource(platform="telegram", chat_id="", chat_type="dm", user_id="42"),
            "agent:main:telegram:dm:42",
        ),
        # user_id_alt preferred over user_id for the DM fallback.
        (
            SessionSource(platform="signal", chat_id="", chat_type="dm", user_id="9", user_id_alt="uuid-1"),
            "agent:main:signal:dm:uuid-1",
        ),
        # DM with nothing -> bare per-platform DM sink.
        (
            SessionSource(platform="telegram", chat_id="", chat_type="dm"),
            "agent:main:telegram:dm",
        ),
        # Group: chat_id + user_id (isolated per user by default).
        (
            SessionSource(platform="discord", chat_id="100", chat_type="group", user_id="7"),
            "agent:main:discord:group:100:7",
        ),
        # Forum/thread: shared across participants (no user_id appended).
        (
            SessionSource(platform="telegram", chat_id="9", chat_type="forum", thread_id="55", user_id="7"),
            "agent:main:telegram:forum:9:55",
        ),
        # Thread with per-user isolation enabled -> user_id appended.
        (
            build_session_key(
                SessionSource(platform="slack", chat_id="C1", chat_type="thread", thread_id="T1", user_id="U1"),
                thread_sessions_per_user=True,
            ),
            "agent:main:slack:thread:C1:T1:U1",
        ),
        # Group without user_id -> shared session per chat.
        (
            SessionSource(platform="discord", chat_id="100", chat_type="group"),
            "agent:main:discord:group:100",
        ),
    ],
)
def test_build_session_key_conformance(source, expected):
    """build_session_key matches the Hermes oracle format byte-for-byte."""
    # The thread case above passes a pre-built key as `source`; handle both.
    if isinstance(source, str):
        assert source == expected
    else:
        assert build_session_key(source) == expected


def test_build_session_key_profile_namespace():
    """A non-default profile namespaces the key."""
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    assert build_session_key(s, profile="acme") == "agent:acme:telegram:dm:1"


def test_build_session_key_deterministic():
    """Same source always yields the same key."""
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm", user_id="2")
    assert build_session_key(s) == build_session_key(s)


# ── SessionSource wire round-trip ──────────────────────────────────────


def test_session_source_round_trip():
    s = SessionSource(
        platform="discord",
        chat_id="100",
        chat_type="group",
        chat_name="general",
        user_id="7",
        user_name="alice",
        thread_id="55",
        chat_topic="dev",
        scope_id="guild-1",
        user_id_alt="alt-7",
        chat_id_alt="alt-100",
    )
    d = s.to_dict()
    # Always-sent discriminators present.
    for k in ("platform", "chat_id", "chat_type", "chat_name", "user_id", "user_name", "thread_id", "chat_topic"):
        assert k in d
    # Optional fields included when set.
    assert d["scope_id"] == "guild-1"
    assert d["user_id_alt"] == "alt-7"
    # is_bot is NOT on the wire.
    assert "is_bot" not in d

    s2 = SessionSource.from_dict(d)
    assert s2.platform == "discord"
    assert s2.chat_id == "100"
    assert s2.chat_type == "group"
    assert s2.user_id == "7"
    assert s2.thread_id == "55"
    assert s2.scope_id == "guild-1"
    assert s2.is_bot is False  # gateway-side only, default


def test_session_source_from_dict_ignores_unknown_keys():
    """Unknown keys are ignored (forward-compat)."""
    s = SessionSource.from_dict({"platform": "telegram", "chat_id": "1", "future_field": "x"})
    assert s.platform == "telegram"
    assert s.chat_id == "1"


def test_session_source_optional_fields_omitted_when_unset():
    """Optional fields are not emitted when None."""
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    d = s.to_dict()
    assert "scope_id" not in d
    assert "user_id_alt" not in d
    assert "chat_id_alt" not in d


# ── SessionStore persistence ────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "routing.db"
    s = SessionStore(db_path=db)
    yield s
    s.close()


def test_session_store_get_miss(store):
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    assert store.get(s) is None


def test_session_store_put_and_get(store):
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm", user_id="42")
    store.put(s, "sess-abc")
    assert store.get(s) == "sess-abc"


def test_session_store_get_or_create_creates_on_miss(store):
    s = SessionSource(platform="discord", chat_id="100", chat_type="group", user_id="7")
    calls = []

    def make():
        calls.append(1)
        return "new-sess"

    sid = store.get_or_create(s, make)
    assert sid == "new-sess"
    assert len(calls) == 1
    # Second call reuses -- create_fn not called again.
    sid2 = store.get_or_create(s, make)
    assert sid2 == "new-sess"
    assert len(calls) == 1


def test_session_store_reset(store):
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    store.put(s, "sess-1")
    assert store.get(s) == "sess-1"
    store.reset(s)
    assert store.get(s) is None


def test_session_store_persists_across_reopen(tmp_path):
    db = tmp_path / "routing.db"
    s = SessionSource(platform="telegram", chat_id="9", chat_type="dm")
    store1 = SessionStore(db_path=db)
    store1.put(s, "persisted-sess")
    store1.close()
    store2 = SessionStore(db_path=db)
    assert store2.get(s) == "persisted-sess"
    store2.close()


def test_session_store_replaces_on_put(store):
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    store.put(s, "old")
    store.put(s, "new")
    assert store.get(s) == "new"


# ── SendResult + error classification ──────────────────────────────────


def test_send_result_new_fields_default_none():
    r = SendResult(success=True)
    assert r.retry_after is None
    assert r.error_kind is None


def test_send_result_accepts_new_fields():
    r = SendResult(success=False, error="flood", retryable=True, retry_after=30.0, error_kind="rate_limited")
    assert r.retry_after == 30.0
    assert r.error_kind == "rate_limited"


def test_send_error_kinds_complete():
    assert SEND_ERROR_KINDS == frozenset(
        {"too_long", "bad_format", "forbidden", "not_found", "rate_limited", "transient", "unknown"}
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("message is too long", "too_long"),
        ("message_too_long error", "too_long"),
        ("can't parse entities: unmatched tag", "bad_format"),
        ("Forbidden: bot was blocked by the user", "forbidden"),
        ("chat not found", "not_found"),
        ("message to edit not found", "not_found"),
        ("Too Many Requests: retry after 30", "rate_limited"),
        ("flood control exceeded", "rate_limited"),
        ("Connection timed out", "transient"),
        ("network unreachable", "transient"),
        ("some weird unmapped error", "unknown"),
    ],
)
def test_classify_send_error(text, expected):
    assert classify_send_error(error_text=text) == expected


def test_classify_send_error_from_exception():
    assert classify_send_error(Exception("Forbidden: blocked")) == "forbidden"


def test_classify_send_error_empty():
    assert classify_send_error() == "unknown"


# ── MessageEvent.source + get_chat_info ────────────────────────────────


def test_message_event_source_defaults_none():
    e = MessageEvent(text="hi")
    assert e.source is None


def test_message_event_accepts_source():
    src = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    e = MessageEvent(text="hi", message_type=MessageType.TEXT, source=src)
    assert e.source is not None
    assert e.source.platform == "telegram"


class _StubAdapter(BaseAdapter):
    """Minimal adapter for testing base-class defaults."""

    name = "stub"

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        return SendResult(success=True)


def test_get_chat_info_default_impl():
    a = _StubAdapter()
    info = asyncio.run(a.get_chat_info("123"))
    assert info == {"name": "123", "type": "dm"}


# ── GatewayMessage submit/submit_stream carry source ───────────────────


def test_submit_stream_frame_carries_source():
    src = SessionSource(platform="telegram", chat_id="1", chat_type="dm").to_dict()
    msg = GatewayMessage.submit_stream("hello", source=src)
    assert msg.op == GatewayOp.SUBMIT_STREAM
    assert msg.data["prompt"] == "hello"
    assert msg.data["source"] == src


def test_submit_frame_omits_source_when_none():
    msg = GatewayMessage.submit_stream("hello")
    assert "source" not in msg.data


def test_submit_frame_carries_source():
    src = SessionSource(platform="discord", chat_id="100", chat_type="group").to_dict()
    msg = GatewayMessage.submit("hi", source=src)
    assert msg.op == GatewayOp.SUBMIT
    assert msg.data["source"]["platform"] == "discord"
