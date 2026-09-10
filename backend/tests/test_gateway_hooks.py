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

"""Tests for the gateway lifecycle hook registry (Phase 3).

This is distinct from ``test_hooks.py`` (which covers the tool-execution hook
system in ``encre.hooks.*``).  These tests cover the gateway lifecycle hooks
in ``encre.gateway.hooks``:

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


# 鈹€鈹€ register / emit / emit_collect 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_verify_emit_fires_registered_handler():
    """Validate that emit invokes every handler registered for the event.

    The test registers an async handler that records the event type and
    context tuple, emits AGENT_START, and asserts the observed sequence
    matches exactly because emit is the primary delivery mechanism for
    lifecycle notifications.
    """
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append((et, ctx))

    reg.register(AGENT_START, h)
    await reg.emit(AGENT_START, {"session_id": "s1"})
    assert seen == [(AGENT_START, {"session_id": "s1"})]


@pytest.mark.asyncio
async def test_verify_emit_invokes_sync_handler():
    """Validate that emit wraps sync handlers transparently.

    The test registers a synchronous handler and emits SESSION_START, then
    asserts the handler received the event because the registry must accept
    both sync and async callables without requiring the caller to decorate.
    """
    reg = get_hook_registry()
    seen = []

    def h(et, ctx):  # sync
        seen.append(et)

    reg.register(SESSION_START, h)
    await reg.emit(SESSION_START, {})
    assert seen == [SESSION_START]


@pytest.mark.asyncio
async def test_verify_emit_collect_returns_non_none_results():
    """Validate that emit_collect gathers non-None returns from handlers.

    The test registers a handler that returns a decision dict, emits a
    command-scoped event, and asserts the returned list contains exactly
    that dict because emit_collect is the contract used by decision hooks
    to produce deny/allow/rewrite outcomes.
    """
    reg = get_hook_registry()

    async def h(et, ctx):
        return {"decision": "deny"}

    reg.register("command:secret", h)
    results = await reg.emit_collect("command:secret", {})
    assert results == [{"decision": "deny"}]


@pytest.mark.asyncio
async def test_verify_emit_collect_skips_none_returns():
    """Validate that emit_collect filters out None returns from handlers.

    The test registers one handler returning None and another returning a
    decision dict, emits AGENT_END, and asserts only the non-None result
    is collected because handlers that opt out of decision-making must not
    inject spurious entries into the results list.
    """
    reg = get_hook_registry()

    async def h1(et, ctx):
        return None

    async def h2(et, ctx):
        return {"ok": True}

    reg.register(AGENT_END, h1)
    reg.register(AGENT_END, h2)
    results = await reg.emit_collect(AGENT_END, {})
    assert results == [{"ok": True}]


# 鈹€鈹€ wildcard resolution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_verify_wildcard_base_star_matches_subcommands():
    """Validate that command:* matches any sub-command event.

    The test registers a handler on the wildcard pattern and emits two
    distinct command events, then asserts both were observed because the
    wildcard must expand to every event whose prefix matches base.
    """
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append(et)

    reg.register("command:*", h)
    await reg.emit("command:new", {})
    await reg.emit("command:stop", {})
    assert seen == ["command:new", "command:stop"]


@pytest.mark.asyncio
async def test_verify_bare_base_does_not_match_sub_events():
    """Validate that a bare base event name does not match sub-events.

    The test registers on the exact string 'agent' and emits AGENT_START,
    then asserts the handler was not called because the registry mirrors
    Hermes-style semantics where bare bases require exact matches only.
    """
    reg = get_hook_registry()
    seen = []

    async def h(et, ctx):
        seen.append(et)

    reg.register("agent", h)  # bare base, no wildcard
    await reg.emit(AGENT_START, {})
    assert seen == []  # not matched


@pytest.mark.asyncio
async def test_verify_exact_and_wildcard_both_fire():
    """Validate that exact and wildcard handlers both fire for the same event.

    The test registers one exact handler and one wildcard handler for the
    same base namespace, emits AGENT_START, and asserts both observed both
    invocations because exact and wildcard registrations are additive, not
    mutually exclusive.
    """
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


# 鈹€鈹€ exception isolation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_verify_failing_handler_does_not_abort_others_on_emit():
    """Validate that one handler's exception does not prevent other handlers from running.

    The test registers a handler that raises RuntimeError alongside a healthy
    handler on AGENT_STEP, emits the event, and asserts the healthy handler
    still observed the event because per-handler exception isolation is
    essential to prevent a single broken hook from killing the pipeline.
    """
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
async def test_verify_failing_handler_does_not_abort_others_on_emit_collect():
    """Validate that one collector handler's exception does not poison the result list.

    The test registers a handler that raises RuntimeError alongside a healthy
    collector on AGENT_END, emits the event via emit_collect, and asserts
    the healthy result is returned unchanged because exception isolation must
    hold for the decision-collector path as well.
    """
    reg = get_hook_registry()

    async def bad(et, ctx):
        raise RuntimeError("boom")

    async def good(et, ctx):
        return {"ok": True}

    reg.register(AGENT_END, bad)
    reg.register(AGENT_END, good)
    results = await reg.emit_collect(AGENT_END, {})
    assert results == [{"ok": True}]


# 鈹€鈹€ filesystem discovery 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_verify_discover_and_load_hook(tmp_path):
    """Validate that discover_and_load loads a well-formed hook directory.

    The test creates a hook directory containing a valid HOOK.yaml manifest
    and a handler.py module, calls discover_and_load, and asserts the hook
    name is returned because the filesystem resolver must pick up conforming
    directories so users can extend the gateway via the hooks folder.
    """
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


def test_verify_discover_skips_missing_manifest(tmp_path):
    """Validate that discover_and_load skips directories without HOOK.yaml.

    The test creates a directory containing only handler.py and asserts
    discover_and_load returns an empty list because the manifest is the
    authoritative registration document and its absence means the directory
    is not a valid hook.
    """
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "bad"
    hook_dir.mkdir(parents=True)
    (hook_dir / "handler.py").write_text("def handle(*a, **k): pass\n", encoding="utf-8")
    # No HOOK.yaml.
    reg = reset_hook_registry(hooks_dir=hooks_root)
    loaded = reg.discover_and_load()
    assert loaded == []


def test_verify_discover_skips_malformed_handler(tmp_path):
    """Validate that discover_and_load skips directories with invalid Python.

    The test creates a hook directory with a valid manifest but a handler.py
    containing invalid Python and asserts it is skipped because module-load
    failures must not crash the registry discovery phase.
    """
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "broken"
    hook_dir.mkdir(parents=True)
    (hook_dir / "HOOK.yaml").write_text("name: broken\n", encoding="utf-8")
    (hook_dir / "handler.py").write_text("this is not valid python !!!\n", encoding="utf-8")
    reg = reset_hook_registry(hooks_dir=hooks_root)
    loaded = reg.discover_and_load()
    assert loaded == []


def test_verify_discover_nonexistent_dir_returns_empty():
    """Validate that discover_and_load is safe when the hooks dir is absent.

    The test points at a path that does not exist and asserts an empty list
    is returned because discovery must be idempotent and tolerant of missing
    directories during development or when the hooks folder is optional.
    """
    reg = reset_hook_registry(hooks_dir="/tmp/encre_definitely_missing")
    assert reg.discover_and_load() == []


# 鈹€鈹€ command:* decision hooks via handle_message 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


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
async def test_verify_command_hook_deny_aborts_dispatch():
    """Validate that a deny decision stops further message dispatch.

    The test registers a handler that returns decision='deny', sends a
    /secret command through the adapter, and asserts the inner handler was
    not called while a deny notice was sent back to the chat because
    deny is the strongest rejection signal in the command-decision contract.
    """
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
async def test_verify_command_hook_handled_aborts_dispatch():
    """Validate that a handled decision stops further message dispatch.

    The test registers a handler that returns decision='handled', sends a
    /wave command, and asserts the inner handler was never reached because
    handled signals that the hook itself consumed the request.
    """
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
async def test_verify_command_hook_rewrite_changes_dispatched_text():
    """Validate that a rewrite decision substitutes the prompt before dispatch.

    The test registers a handler that returns decision='rewrite' with a new
    text value, sends a /hi command, and asserts the inner handler received
    the rewritten text rather than the original command because rewrite is
    the mechanism by which hooks transform user input before the agent sees it.
    """
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
async def test_verify_command_hook_wildcard_fires_for_any_command():
    """Validate that command:* fires for every command regardless of name.

    The test registers the COMMAND_WILDCARD handler, sends a synthetic
    /anything command, and asserts the handler observed the command name
    because the wildcard is the primary observability hook for command
    telemetry and rate-limiting decisions.
    """
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
async def test_verify_command_hook_allow_proceeds_to_dispatch():
    """Validate that an allow decision lets the normal handler run.

    The test registers a handler that returns decision='allow', sends a
    /go command, and asserts the inner handler received the original text
    because allow is the passthrough signal that defers to the default
    message pipeline.
    """
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
async def test_verify_non_command_message_skips_command_hooks():
    """Validate that plain messages do not trigger command hooks.

    The test registers the COMMAND_WILDCARD handler and sends a non-command
    message (no leading slash), then asserts the handler was never invoked
    because command hooks must only fire when the message is syntactically
    a command to avoid noisy false positives on normal chat.
    """
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


# 鈹€鈹€ gateway:startup smoke (GatewayRunner) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@pytest.mark.asyncio
async def test_verify_gateway_startup_emits_after_discovery(tmp_path):
    """Validate that GatewayRunner.start emits gateway:startup after hook discovery.

    The test constructs a minimal GatewayRunner instance with a real hook
    directory so discover_and_load registers a handler before start runs,
    then asserts the hook module recorded the startup event because the
    gateway lifecycle contract requires a startup notification to be emitted
    once the adapter graph is assembled.
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
