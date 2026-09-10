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

"""Tests for the gateway session routing layer.

Covers:
- :func:`build_session_key` conformance.
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

from encre.gateway.platforms.base import (
    SEND_ERROR_KINDS,
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    classify_send_error,
)
from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp
from encre.gateway.session import (
    SessionSource,
    SessionStore,
    build_session_key,
)


# 鈹€鈹€ build_session_key conformance 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


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
def test_verify_build_session_key_conformance(source, expected):
    """Validate that build_session_key produces the expected canonical key format.

    The test asserts byte-for-byte equality against the precomputed expected
    string for a range of platform/chat_type/thread configurations because
    the session key is the primary index into SessionStore and any mismatch
    causes cross-session message leakage or lost messages.
    """
    # The thread case above passes a pre-built key as `source`; handle both.
    if isinstance(source, str):
        assert source == expected
    else:
        assert build_session_key(source) == expected


def test_verify_build_session_key_profile_namespace():
    """Validate that a non-default profile namespaces the session key.

    The test asserts the key includes 'acme' when profile='acme' is supplied
    because multi-tenant deployments must keep sessions isolated by profile
    even when platform and chat identifiers collide.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    assert build_session_key(s, profile="acme") == "agent:acme:telegram:dm:1"


def test_verify_build_session_key_deterministic():
    """Validate that identical sources always yield the same key.

    The test asserts build_session_key(s) == build_session_key(s) because
    determinism is required for cache hits and for storing/retrieving the
    same logical session across different runtime invocations.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm", user_id="2")
    assert build_session_key(s) == build_session_key(s)


# 鈹€鈹€ SessionSource wire round-trip 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_verify_session_source_round_trip():
    """Validate that SessionSource round-trips through to_dict/from_dict faithfully.

    The test constructs a fully populated SessionSource, serializes it, asserts
    the discriminators (platform, chat_id, chat_type, etc.) are present, asserts
    optional fields are included when set, and asserts is_bot is absent from
    the wire payload because is_bot is a gateway-local flag that must not leak
    into persisted or cross-process payloads.
    """
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


def test_verify_session_source_from_dict_ignores_unknown_keys():
    """Validate that from_dict tolerates future/unknown fields gracefully.

    The test passes a dict containing a synthetic future_field and asserts
    the resulting SessionSource ignores it rather than raising because
    forward compatibility requires the parser to skip unrecognized keys.
    """
    s = SessionSource.from_dict({"platform": "telegram", "chat_id": "1", "future_field": "x"})
    assert s.platform == "telegram"
    assert s.chat_id == "1"


def test_verify_session_source_optional_fields_omitted_when_unset():
    """Validate that optional fields are excluded from the dict when None.

    The test constructs a minimal SessionSource and asserts scope_id,
    user_id_alt, and chat_id_alt are absent from the serialized output
    because omitting unset optionals keeps the wire payload compact and
    avoids ambiguity between None and missing keys.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    d = s.to_dict()
    assert "scope_id" not in d
    assert "user_id_alt" not in d
    assert "chat_id_alt" not in d


# 鈹€鈹€ SessionStore persistence 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "routing.db"
    s = SessionStore(db_path=db)
    yield s
    s.close()


def test_verify_session_store_get_miss(store):
    """Validate that get returns None for an unregistered source.

    The test asserts None because a miss must not return a bogus key or
    raise; the caller branches on None to decide whether to create a new
    session.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    assert store.get(s) is None


def test_verify_session_store_put_and_get(store):
    """Validate that put followed by get returns the stored session ID.

    The test writes a mapping and reads it back, asserting equality because
    the store's core contract is lossless K-V persistence for the lifetime
    of the open connection.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm", user_id="42")
    store.put(s, "sess-abc")
    assert store.get(s) == "sess-abc"


def test_verify_session_store_get_or_create_creates_on_miss(store):
    """Validate that get_or_create invokes make exactly once on a miss.

    The test asserts the returned session ID equals the value from make
    and that make was called only once, then calls get_or_create again
    and asserts no additional call occurred because cached hits must
    bypass factory invocation.
    """
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


def test_verify_session_store_reset_clears_entry(store):
    """Validate that reset removes a previously stored mapping.

    The test writes a session, confirms retrieval, calls reset, and asserts
    the subsequent get returns None because reset is the only mechanism
    for expiring a session binding without closing the store.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    store.put(s, "sess-1")
    assert store.get(s) == "sess-1"
    store.reset(s)
    assert store.get(s) is None


def test_verify_session_store_persists_across_reopen(tmp_path):
    """Validate that stored mappings survive store close/reopen.

    The test writes a mapping in one SessionStore instance, closes it,
    opens a second instance pointing at the same database, and asserts
    the value is still retrievable because persistence across restarts
    is required for gateway resilience.
    """
    db = tmp_path / "routing.db"
    s = SessionSource(platform="telegram", chat_id="9", chat_type="dm")
    store1 = SessionStore(db_path=db)
    store1.put(s, "persisted-sess")
    store1.close()
    store2 = SessionStore(db_path=db)
    assert store2.get(s) == "persisted-sess"
    store2.close()


def test_verify_session_store_replaces_on_put(store):
    """Validate that a second put for the same source overwrites the previous value.

    The test asserts the final get returns 'new' after two sequential puts
    because the store implements an upsert contract, not an append-only log.
    """
    s = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    store.put(s, "old")
    store.put(s, "new")
    assert store.get(s) == "new"


# 鈹€鈹€ SendResult + error classification 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_verify_send_result_new_fields_default_none():
    """Validate that SendResult's optional fields default to None.

    The test constructs a minimal successful result and asserts retry_after
    and error_kind are None because callers must not receive stale error
    metadata on a clean success path.
    """
    r = SendResult(success=True)
    assert r.retry_after is None
    assert r.error_kind is None


def test_verify_send_result_accepts_new_fields():
    """Validate that SendResult stores retry_after and error_kind when provided.

    The test constructs a failed result carrying rate-limit metadata and
    asserts both fields survive because the adapter needs these values to
    schedule retries with the correct back-off window.
    """
    r = SendResult(success=False, error="flood", retryable=True, retry_after=30.0, error_kind="rate_limited")
    assert r.retry_after == 30.0
    assert r.error_kind == "rate_limited"


def test_verify_send_error_kinds_complete():
    """Validate that SEND_ERROR_KINDS enumerates the documented error taxonomy.

    The test asserts the frozenset matches the seven canonical kinds because
    classify_send_error branches on these strings and any drift would cause
    unmapped errors to fall through to 'unknown' silently.
    """
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
def test_verify_classify_send_error_maps_text_to_kind(text, expected):
    """Validate that classify_send_error maps error text to the expected kind.

    The test asserts exact kind equality for a spectrum of real-world error
    messages because the classification function is the single point of
    truth for retry-vs-fail decisions in the send path.
    """
    assert classify_send_error(error_text=text) == expected


def test_verify_classify_send_error_from_exception():
    """Validate that classify_send_error accepts an Exception instance.

    The test passes an Exception object whose message contains 'Forbidden'
    and asserts the result is 'forbidden' because adapters commonly surface
    wrapped exceptions rather than plain strings.
    """
    assert classify_send_error(Exception("Forbidden: blocked")) == "forbidden"


def test_verify_classify_send_error_empty_defaults_to_unknown():
    """Validate that classify_send_error returns 'unknown' for empty input.

    The test asserts the fallback kind is 'unknown' because any caller that
    receives an empty error must still produce a deterministic classification
    rather than crashing or returning None.
    """
    assert classify_send_error() == "unknown"


# 鈹€鈹€ MessageEvent.source + get_chat_info 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_verify_message_event_source_defaults_none():
    """Validate that MessageEvent.source is None when not supplied.

    The test constructs a minimal event and asserts source is None because
    source is an optional enrichment field and downstream code must handle
    its absence gracefully.
    """
    e = MessageEvent(text="hi")
    assert e.source is None


def test_verify_message_event_accepts_source():
    """Validate that MessageEvent stores the provided SessionSource.

    The test constructs an event with an explicit source and asserts the
    source object survives and its platform field is accessible because
    the gateway routes on source.platform to select adapter behavior.
    """
    src = SessionSource(platform="telegram", chat_id="1", chat_type="dm")
    e = MessageEvent(text="hi", message_type=MessageType.TEXT, source=src)
    assert e.source is not None
    assert e.source.platform == "telegram"


class _StubAdapter(BasePlatformAdapter):
    """Minimal adapter for testing base-class defaults."""

    name = "stub"

    async def connect(self, *, is_reconnect=False) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        return SendResult(success=True)


def test_verify_get_chat_info_default_impl():
    """Validate that the base get_chat_info implementation returns sensible defaults.

    The test constructs a stub adapter and calls get_chat_info, asserting
    the returned dict contains 'name' and 'type' keys with reasonable
    defaults because the base class must provide a fallback for platforms
    that do not override chat-info resolution.
    """
    from encre.gateway.config import Platform, PlatformConfig
    a = _StubAdapter(config=PlatformConfig(enabled=True), platform=Platform.TELEGRAM)
    info = asyncio.run(a.get_chat_info("123"))
    assert info == {"name": "123", "type": "dm"}


# 鈹€鈹€ GatewayMessage submit/submit_stream carry source 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_verify_submit_stream_frame_carries_source():
    """Validate that GatewayMessage.submit_stream includes the source dict.

    The test asserts the frame op is SUBMIT_STREAM, the prompt text is
    preserved, and the source dict is attached because the server side
    uses source to resolve or create the target session before running
    the agent.
    """
    src = SessionSource(platform="telegram", chat_id="1", chat_type="dm").to_dict()
    msg = GatewayMessage.submit_stream("hello", source=src)
    assert msg.op == GatewayOp.SUBMIT_STREAM
    assert msg.data["prompt"] == "hello"
    assert msg.data["source"] == src


def test_verify_submit_stream_frame_omits_source_when_none():
    """Validate that submit_stream omits the source key when no source is supplied.

    The test asserts 'source' is absent from data because legacy clients
    that do not carry a SessionSource must still be able to submit streams
    without triggering a missing-key validation error on the server.
    """
    msg = GatewayMessage.submit_stream("hello")
    assert "source" not in msg.data


def test_verify_submit_frame_carries_source():
    """Validate that GatewayMessage.submit includes the source dict.

    The test asserts the frame op is SUBMIT and the source platform field
    is preserved because submit (non-streaming) must carry the same
    routing metadata as submit_stream to ensure consistent session lookup.
    """
    src = SessionSource(platform="discord", chat_id="100", chat_type="group").to_dict()
    msg = GatewayMessage.submit("hi", source=src)
    assert msg.op == GatewayOp.SUBMIT
    assert msg.data["source"]["platform"] == "discord"
