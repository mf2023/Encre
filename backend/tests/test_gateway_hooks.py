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

"""Tests for the gateway lifecycle hook registry (Phase 3).

This is distinct from ``test_hooks.py`` (which covers the tool-execution hook
system in ``encre.hooks.*``).  These tests cover the gateway lifecycle hooks
in ``encre.gateway.hooks`` (aligns with Hermes ``gateway/hooks.py``):

- :class:`HookRegistry` programmatic register / emit / emit_collect.
- Wildcard ``base:*`` resolution (bare base does NOT match).
- Sync + async handlers; per-handler exception isolation.
- Filesystem discovery via :meth:`discover_and_load` (HOOK.yaml + handler.py).
- ``command:<canonical>`` + ``command:*`` decision hooks in handle_message
  (deny / handled / rewrite / allow).
- ``gateway:startup`` emit from AdapterManager.start_gateway (smoke).
"""

import asyncio
import textwrap

import pytest

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.hooks import (
    AGENT_END,
    AGENT_START,
    AGENT_STEP,
    COMMAND_WILDCARD,
    GATEWAY_STARTUP,
    SESSION_START,
    get_hook_registry,
    reset_hook_registry,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Each test gets a fresh registry so handlers don't leak across tests."""
    reset_hook_registry(hooks_dir="/tmp/encre_no_hooks_dir")
    yield
    reset_hook_registry(hooks_dir="/tmp/encre_no_hooks_dir")


# ── register / emit / emit_collect ─────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_fires_registered_handler():
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append((et, ctx))

    reg.register(AGENT_START, h)
    await reg.emit(AGENT_START, {"session_id": "s1"})
    assert seen == [(AGENT_START, {"session_id": "s1"})]


@pytest.mark.asyncio
async def test_emit_supports_sync_handler():
    reg = get_hook_registry()
    seen = []

    def h(et, ctx):  # sync
        seen.append(et)

    reg.register(SESSION_START, h)
    await reg.emit(SESSION_START, {})
    assert seen == [SESSION_START]


@pytest.mark.asyncio
async def test_emit_collect_returns_non_none():
    reg = get_hook_registry()

    async def h(et, ctx):
        return {"decision": "deny"}

    reg.register("command:secret", h)
    results = await reg.emit_collect("command:secret", {})
    assert results == [{"decision": "deny"}]


@pytest.mark.asyncio
async def test_emit_collect_skips_none_returns():
    reg = get_hook_registry()

    async def h1(et, ctx):
        return None

    async def h2(et, ctx):
        return {"ok": True}

    reg.register(AGENT_END, h1)
    reg.register(AGENT_END, h2)
    results = await reg.emit_collect(AGENT_END, {})
    assert results == [{"ok": True}]


# ── wildcard resolution ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wildcard_base_star_matches():
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append(et)

    reg.register("command:*", h)
    await reg.emit("command:new", {})
    await reg.emit("command:stop", {})
    assert seen == ["command:new", "command:stop"]


@pytest.mark.asyncio
async def test_bare_base_does_not_match():
    """A bare base (no :*) does NOT match base:sub events (mirrors Hermes)."""
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append(et)

    reg.register("agent", h)  # bare base, no wildcard
    await reg.emit(AGENT_START, {})
    assert seen == []  # not matched


@pytest.mark.asyncio
async def test_exact_and_wildcard_both_fire():
    reg = get_hook_registry()
    seen = []

    async def exact(et, ctx):
        seen.append(f"exact:{et}")

    async def wild(et, ctx):
        seen.append(f"wild:{et}")

    reg.register(AGENT_START, exact)
    reg.register("agent:*", wild)
    await reg.emit(AGENT_START, {})
    assert seen == ["exact:agent:start", "wild:agent:start"]


# ── exception isolation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failing_handler_does_not_abort_others():
    reg = get_hook_registry()
    seen = []

    async def bad(et, ctx):
        raise RuntimeError("boom")

    async def good(et, ctx):
        seen.append(et)

    reg.register(AGENT_STEP, bad)
    reg.register(AGENT_STEP, good)
    await reg.emit(AGENT_STEP, {})
    assert seen == [AGENT_STEP]  # good still ran


@pytest.mark.asyncio
async def test_failing_collector_does_not_abort_others():
    reg = get_hook_registry()

    async def bad(et, ctx):
        raise RuntimeError("boom")

    async def good(et, ctx):
        return {"ok": True}

    reg.register(AGENT_END, bad)
    reg.register(AGENT_END, good)
    results = await reg.emit_collect(AGENT_END, {})
    assert results == [{"ok": True}]


# ── filesystem discovery ──────────────────────────────────────────────


def test_discover_and_load_hook(tmp_path):
    """A hook directory with HOOK.yaml + handler.py is discovered and loaded."""
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "myhook"
    hook_dir.mkdir(parents=True)
    (hook_dir / "HOOK.yaml").write_text("name: myhook\n", encoding="utf-8")
    (hook_dir / "handler.py").write_text(textwrap.dedent("""
        EVENTS = ["agent:start"]
        async def handle(event_type, context):
            pass
    """), encoding="utf-8")

    reg = reset_hook_registry(hooks_dir=hooks_root)
    loaded = reg.discover_and_load()
    assert loaded == ["myhook"]


def test_discover_skips_missing_manifest(tmp_path):
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "bad"
    hook_dir.mkdir(parents=True)
    (hook_dir / "handler.py").write_text("def handle(*a, **k): pass\n", encoding="utf-8")
    # No HOOK.yaml.
    reg = reset_hook_registry(hooks_dir=hooks_root)
    loaded = reg.discover_and_load()
    assert loaded == []


def test_discover_skips_malformed_handler(tmp_path):
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "broken"
    hook_dir.mkdir(parents=True)
    (hook_dir / "HOOK.yaml").write_text("name: broken\n", encoding="utf-8")
    (hook_dir / "handler.py").write_text("this is not valid python !!!\n", encoding="utf-8")
    reg = reset_hook_registry(hooks_dir=hooks_root)
    loaded = reg.discover_and_load()
    assert loaded == []


def test_discover_nonexistent_dir_returns_empty():
    reg = reset_hook_registry(hooks_dir="/tmp/encre_definitely_missing")
    assert reg.discover_and_load() == []


# ── command:* decision hooks via handle_message ───────────────────────


class _CmdAdapter(BasePlatformAdapter):
    name = "telegram"

    def __init__(self):
        # Bypass BasePlatformAdapter.__init__ for testing
        self._message_handler = None
        self._authz = None
        self._pairing = None
        self._running = True
        self._fatal_error_code = None
        self._fatal_error_message = None
        self._active_sessions = {}
        self._pending_messages = {}
        self._background_tasks = set()
        self.sent: list[tuple[str, str]] = []

    async def connect(self, *, is_reconnect=False) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id="m1")

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}


def _cmd_event(text, chat_id="1", user_id="u1"):
    return MessageEvent(
        text=text,
        source=SessionSource(platform="telegram", chat_id=chat_id, chat_type="dm", user_id=user_id),
    )


@pytest.mark.asyncio
async def test_command_hook_deny_aborts():
    reg = get_hook_registry()

    async def deny(et, ctx):
        return {"decision": "deny", "message": "forbidden"}

    reg.register("command:secret", deny)
    a = _CmdAdapter()
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event)

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("/secret"))
    assert dispatched == []
    assert a.sent  # deny notice sent
    assert "forbidden" in a.sent[0][1]


@pytest.mark.asyncio
async def test_command_hook_handled_aborts():
    reg = get_hook_registry()

    async def handled(et, ctx):
        return {"decision": "handled"}

    reg.register("command:wave", handled)
    a = _CmdAdapter()
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event)

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("/wave"))
    assert dispatched == []  # never reached


@pytest.mark.asyncio
async def test_command_hook_rewrite_changes_text():
    reg = get_hook_registry()

    async def rewrite(et, ctx):
        return {"decision": "rewrite", "text": "hello rewritten"}

    reg.register("command:hi", rewrite)
    a = _CmdAdapter()
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event.text)

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("/hi"))
    # The rewritten text (no longer a command) was dispatched.
    assert dispatched == ["hello rewritten"]


@pytest.mark.asyncio
async def test_command_hook_wildcard_fires():
    reg = get_hook_registry()
    seen = []

    async def wild(et, ctx):
        seen.append(ctx.get("command"))
        return None  # allow

    reg.register(COMMAND_WILDCARD, wild)
    a = _CmdAdapter()

    async def handler(adapter, event):
        pass

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("/anything"))
    assert seen == ["anything"]


@pytest.mark.asyncio
async def test_command_hook_allow_proceeds():
    reg = get_hook_registry()

    async def allow(et, ctx):
        return {"decision": "allow"}

    reg.register("command:go", allow)
    a = _CmdAdapter()
    dispatched = []

    async def handler(adapter, event):
        dispatched.append(event.text)

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("/go"))
    assert dispatched == ["/go"]


@pytest.mark.asyncio
async def test_non_command_message_skips_command_hooks():
    """A plain (non-/) message does not trigger command hooks."""
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append(et)

    reg.register(COMMAND_WILDCARD, h)
    a = _CmdAdapter()

    async def handler(adapter, event):
        pass

    a.set_message_handler(handler)
    await a.handle_message(_cmd_event("just chatting"))
    assert seen == []


# ── gateway:startup smoke (GatewayRunner) ────────────────────────────


@pytest.mark.asyncio
async def test_gateway_startup_emits(tmp_path):
    """GatewayRunner.start fires gateway:startup after discovery.

    Uses a real hook file so discover_and_load registers the handler before
    the emit (start clears the registry on discovery, so a handler
    must come from the filesystem to survive to the emit).
    """
    from encre.gateway.run import GatewayRunner

    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "startup_hook"
    hook_dir.mkdir(parents=True)
    (hook_dir / "HOOK.yaml").write_text("name: startup_hook\n", encoding="utf-8")
    (hook_dir / "handler.py").write_text(textwrap.dedent("""
        EVENTS = ["gateway:startup"]
        SEEN = []
        async def handle(event_type, context):
            SEEN.append(event_type)
    """), encoding="utf-8")

    reset_hook_registry(hooks_dir=hooks_root)
    reg = get_hook_registry()

    # Build a runner with stubbed attributes to avoid real startup.
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._running = False
    runner._instances = {}
    runner._hooks = reg
    runner._gateway_config = None
    runner._channel_dir = type('_Dir', (), {'load': lambda self: None})()
    runner._session_store = None
    runner._ws_bridge = None
    await runner.start()

    # The hook module recorded the startup event.
    import sys
    mod = sys.modules.get("encre_hooks.startup_hook")
    assert mod is not None
    assert "gateway:startup" in mod.SEEN

