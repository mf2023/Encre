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

"""Tests for gateway outbound delivery (Phase 2b).

Covers:
- :class:`DeliveryTarget.parse` for explicit and bare-adapter forms.
- :class:`DeliveryRouter.deliver` explicit-target / adapter-id / origin paths.
- Truncation: under-cap passes through; over-cap saves audit + appends note
  for non-chunking adapters; chunking adapters receive the full payload.
- Per-target failure isolation (one bad target does not abort the rest).
"""

import asyncio

import pytest

from encre.adapters.base import BaseAdapter, SendResult
from encre.gateway.delivery import (
    MAX_PLATFORM_OUTPUT,
    DeliveryRouter,
    DeliveryTarget,
)


class _Adapter(BaseAdapter):
    """In-memory adapter recording every send."""

    name = "telegram"

    def __init__(self, *, push_chat_id=None, splits=False, max_len=0):
        # Bypass BaseAdapter.__init__ (no gateway client needed for these tests).
        self.name = "telegram"
        self.max_message_length = max_len
        self.splits_long_messages = splits
        self._last_push_chat_id = push_chat_id
        self.sent: list[tuple[str, str]] = []

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id="m1")


class _FailingAdapter(_Adapter):
    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        raise RuntimeError("boom")


class _Manager:
    """Minimal adapter manager stub holding _instances."""

    def __init__(self, instances):
        self._instances = instances


# ── DeliveryTarget.parse ───────────────────────────────────────────────


def test_parse_explicit_target():
    t = DeliveryTarget.parse("telegram:123456")
    assert t.platform == "telegram"
    assert t.chat_id == "123456"


def test_parse_bare_adapter():
    t = DeliveryTarget.parse("telegram")
    assert t.platform == "telegram"
    assert t.chat_id is None


def test_parse_strips_whitespace():
    t = DeliveryTarget.parse("  telegram : 123  ")
    assert t.platform == "telegram"
    assert t.chat_id == "123"


def test_parse_empty_chat_falls_back_to_none():
    t = DeliveryTarget.parse("telegram:")
    assert t.platform == "telegram"
    assert t.chat_id is None


# ── deliver ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_explicit_target():
    a = _Adapter()
    router = DeliveryRouter(_Manager({"telegram": a}), audit_dir="/tmp/encre_test_audit")
    results = await router.deliver("hello", ["telegram:123"])
    assert len(results) == 1
    assert results[0].success
    assert a.sent == [("123", "hello")]


@pytest.mark.asyncio
async def test_deliver_bare_adapter_uses_default_push():
    a = _Adapter(push_chat_id="auto-chat")
    router = DeliveryRouter(_Manager({"telegram": a}))
    results = await router.deliver("hello", ["telegram"])
    assert results[0].success
    assert a.sent == [("auto-chat", "hello")]


@pytest.mark.asyncio
async def test_deliver_origin_fallback():
    a = _Adapter()
    router = DeliveryRouter(_Manager({"telegram": a}))
    results = await router.deliver("hello", None, origin=("telegram", "999"))
    assert results[0].success
    assert a.sent == [("999", "hello")]


@pytest.mark.asyncio
async def test_deliver_no_targets_no_origin_returns_empty():
    a = _Adapter()
    router = DeliveryRouter(_Manager({"telegram": a}))
    results = await router.deliver("hello", None, origin=None)
    assert results == []
    assert a.sent == []


@pytest.mark.asyncio
async def test_deliver_missing_adapter_reports_error():
    router = DeliveryRouter(_Manager({}))
    results = await router.deliver("hello", ["telegram:123"])
    assert results[0].success is False
    assert "not running" in results[0].error


@pytest.mark.asyncio
async def test_deliver_bare_adapter_no_push_target_reports_error():
    a = _Adapter(push_chat_id=None)
    router = DeliveryRouter(_Manager({"telegram": a}))
    results = await router.deliver("hello", ["telegram"])
    assert results[0].success is False
    assert "chat_id" in results[0].error


# ── truncation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_under_cap_passes_through():
    a = _Adapter()
    router = DeliveryRouter(_Manager({"telegram": a}), max_output=100)
    content = "x" * 50
    results = await router.deliver(content, ["telegram:1"])
    assert results[0].truncated is False
    assert results[0].saved_path is None
    assert a.sent[0][1] == content


@pytest.mark.asyncio
async def test_deliver_over_cap_truncates_and_saves(tmp_path):
    a = _Adapter()  # splits_long_messages = False
    router = DeliveryRouter(_Manager({"telegram": a}), max_output=100, audit_dir=tmp_path)
    content = "y" * 500
    results = await router.deliver(content, ["telegram:1"])
    assert results[0].truncated is True
    assert results[0].saved_path is not None
    sent_content = a.sent[0][1]
    assert "[truncated" in sent_content
    # The payload was shortened (full 500 chars wouldn't fit); the note carries
    # the absolute audit path, so the exact length depends on the path -- we
    # only assert it's meaningfully shorter than the original.
    assert len(sent_content) < len(content)
    # Full output was saved to disk.
    from pathlib import Path
    saved = Path(results[0].saved_path).read_text(encoding="utf-8")
    assert saved == content


@pytest.mark.asyncio
async def test_deliver_chunking_adapter_gets_full_payload(tmp_path):
    """An adapter advertising splits_long_messages receives the full content."""
    a = _Adapter(splits=True)
    router = DeliveryRouter(_Manager({"telegram": a}), max_output=100, audit_dir=tmp_path)
    content = "z" * 500
    results = await router.deliver(content, ["telegram:1"])
    assert results[0].truncated is False
    assert results[0].saved_path is None
    assert a.sent[0][1] == content  # full payload, no truncation


# ── failure isolation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_one_bad_target_does_not_abort_others():
    good = _Adapter()
    bad = _FailingAdapter()
    router = DeliveryRouter(_Manager({"telegram": good, "discord": bad}))
    results = await router.deliver("hello", ["telegram:1", "discord:2"])
    assert len(results) == 2
    assert results[0].success is True   # telegram ok
    assert results[1].success is False   # discord failed
    assert good.sent == [("1", "hello")]
