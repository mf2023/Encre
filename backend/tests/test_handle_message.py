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

"""Tests for BaseAdapter.handle_message inbound routing (Phase 1).

Covers the canonical inbound entry: source normalization, the two-level
guard (queue while active, bypass for /stop etc.), dispatch to a registered
message handler or the legacy process_with_stream, and pending-message
drainage on completion.
"""

import asyncio

import pytest

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource, build_session_key


class _StubAdapter(BaseAdapter):
    """Minimal adapter: only implements the abstract send()."""

    name = "stub"

    def __init__(self):
        super().__init__()
        self.sent: list[tuple[str, str]] = []

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id="m1")


def _dm_event(text="hi", chat_id="123", user_id="42", platform="stub"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        chat_id=chat_id,
        user_id=user_id,
        source=SessionSource(platform=platform, chat_id=chat_id, chat_type="dm", user_id=user_id),
    )


# ── source normalization ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_synthesizes_source_when_missing():
    """An event without `source` gets a synthesized one (platform=adapter.name)."""
    a = _StubAdapter()
    seen = []

    async def handler(event):
        seen.append(event)

    a.set_message_handler(handler)
    # No source on the event.
    event = MessageEvent(text="hi", chat_id="123", user_id="42")
    await a.handle_message(event)
    assert len(seen) == 1
    # Synthesized source uses the adapter name as platform.
    assert seen[0].source is not None
    assert seen[0].source.platform == "stub"
    assert seen[0].source.chat_id == "123"
    assert seen[0].source.user_id == "42"


# ── dispatch ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_dispatches_to_handler():
    """When a handler is set, handle_message awaits it with the event."""
    a = _StubAdapter()
    seen = []

    async def handler(event):
        seen.append(event)

    a.set_message_handler(handler)
    event = _dm_event("hello")
    await a.handle_message(event)
    assert seen == [event]


@pytest.mark.asyncio
async def test_handle_message_no_handler_falls_back_to_process_with_stream():
    """Without a handler, handle_message delegates to process_with_stream
    and forwards the source so the server routes per-conversation."""
    a = _StubAdapter()
    calls = []

    async def fake_pws(content, chat_id, session_id=None, *, source=None):
        calls.append((content, chat_id, source))

    # Monkeypatch the legacy path so no WebSocket is touched.
    a.process_with_stream = fake_pws  # type: ignore[assignment]
    event = _dm_event("hello", chat_id="9", user_id="u1")
    await a.handle_message(event)
    assert len(calls) == 1
    content, chat_id, source = calls[0]
    assert content == "hello"
    assert chat_id == "9"
    assert source is not None
    assert source.platform == "stub"
    assert source.chat_id == "9"


# ── two-level guard ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_queues_concurrent_message():
    """A second message arriving while the session is active is queued, not
    dispatched concurrently.  After the first completes, the queued one runs."""
    a = _StubAdapter()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def handler(event):
        order.append(f"start:{event.text}")
        first_started.set()
        if event.text == "first":
            await release_first.wait()
        order.append(f"end:{event.text}")

    a.set_message_handler(handler)

    t1 = asyncio.create_task(a.handle_message(_dm_event("first", chat_id="1")))
    await first_started.wait()

    # Second message on the same session_key should queue (same chat_id "1").
    t2 = asyncio.create_task(a.handle_message(_dm_event("second", chat_id="1")))
    await asyncio.sleep(0)  # let t2 run to the guard (queues, returns)
    await t2

    # The second handler has NOT run yet -- it's queued.
    assert order == ["start:first"]

    release_first.set()
    await t1
    # Drain runs the queued message.
    for _ in range(10):
        await asyncio.sleep(0)
        if "end:second" in order:
            break
    assert "start:second" in order
    assert "end:second" in order


@pytest.mark.asyncio
async def test_handle_message_different_chats_share_adapter_context():
    """Messages from different chats are serialized in one adapter context."""
    a = _StubAdapter()
    release = asyncio.Event()
    started: list[str] = []

    async def handler(event):
        started.append(event.text)
        if event.text == "a":
            await release.wait()

    a.set_message_handler(handler)

    ta = asyncio.create_task(a.handle_message(_dm_event("a", chat_id="1")))
    await asyncio.sleep(0)
    # Chat IDs only control delivery.  The adapter has one Agent context, so
    # the second message waits until the first turn has completed.
    tb = asyncio.create_task(a.handle_message(_dm_event("b", chat_id="2")))
    await asyncio.sleep(0)
    assert "a" in started
    assert "b" not in started
    release.set()
    await ta
    await tb
    assert "b" in started


@pytest.mark.asyncio
async def test_handle_message_bypass_command_not_queued():
    """/stop (a bypass command) is NOT queued even while a session is active."""
    a = _StubAdapter()
    release = asyncio.Event()
    first_started = asyncio.Event()
    seen: list[str] = []

    async def handler(event):
        seen.append(event.text)
        if event.text == "running":
            first_started.set()
            await release.wait()

    a.set_message_handler(handler)

    t1 = asyncio.create_task(a.handle_message(_dm_event("running", chat_id="1")))
    await first_started.wait()

    # /stop arrives while session "1" is active -- bypass, not queued.
    stop_event = MessageEvent(
        text="/stop",
        chat_id="1",
        source=SessionSource(platform="stub", chat_id="1", chat_type="dm"),
    )
    t2 = asyncio.create_task(a.handle_message(stop_event))
    await asyncio.sleep(0)
    assert "/stop" in seen

    release.set()
    await t1
    await t2


# ── drain on completion ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_drains_pending_after_completion():
    """Queued messages are re-dispatched after the active session completes."""
    a = _StubAdapter()
    first_started = asyncio.Event()
    release = asyncio.Event()
    handled: list[str] = []

    async def handler(event):
        handled.append(event.text)
        if event.text == "first":
            first_started.set()
            await release.wait()

    a.set_message_handler(handler)

    t1 = asyncio.create_task(a.handle_message(_dm_event("first", chat_id="c")))
    await first_started.wait()
    # Queue two messages while active.
    t_q1 = asyncio.create_task(a.handle_message(_dm_event("q1", chat_id="c")))
    t_q2 = asyncio.create_task(a.handle_message(_dm_event("q2", chat_id="c")))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await t_q1
    await t_q2
    assert handled == ["first"]

    release.set()
    await t1
    # Both queued messages get drained (in order).
    for _ in range(20):
        await asyncio.sleep(0)
        if len(handled) >= 3:
            break
    assert handled == ["first", "q1", "q2"]
