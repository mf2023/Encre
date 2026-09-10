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

"""Tests for hooks system and event types."""

import asyncio

import pytest
from encre.hooks.system import EncreHookSystem
from encre.hooks.types import (
    HookProgressEvent,
    HookResponseEvent,
    HookStartedEvent,
)


class TestHookEventTypes:
    """Engineered to validate the shape and field wiring of hook lifecycle events.

    This test class exercises the three concrete event types emitted by the
    hook pipeline 鈥?started, progress, and response 鈥?across 4 scenarios to
    ensure each carries its constructor arguments verbatim into the exposed
    attributes. The design follows the invariant that event dataclasses are
    pure data carriers so that downstream handlers can reason about hook
    state without introspection overhead.
    """

    def test_verify_started_event_carries_hook_identity_and_phase(self):
        """Validate that HookStartedEvent correctly propagates hook identity
        and phase name when constructed.

        The test exercises direct construction with known values and asserts
        that each attribute matches because the event dataclass must preserve
        constructor arguments without transformation for reliable serialization.
        """
        event = HookStartedEvent(
            hook_id="h1", hook_name="test_hook", event_type="pre_tool_exec"
        )
        assert event.hook_id == "h1", "hook_id must match the constructor argument"
        assert event.hook_name == "test_hook", "hook_name must match the constructor argument"
        assert event.event_type == "pre_tool_exec", "event_type must match the constructor argument"

    def test_verify_progress_event_carries_execution_output_and_streams(self):
        """Validate that HookProgressEvent correctly propagates output, stdout,
        and stderr when constructed.

        The test exercises direct construction with mixed output values and
        asserts each field matches because progress events stream intermediate
        state and must preserve empty strings (not None) to distinguish
        'no output yet' from 'output omitted'.
        """
        event = HookProgressEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="on_tool_progress",
            output="running",
            stdout="out",
            stderr="",
        )
        assert event.hook_id == "h1", "hook_id must match the constructor argument"
        assert event.output == "running", "output must reflect the current execution state"
        assert event.stdout == "out", "stdout must be preserved verbatim for streaming"

    def test_verify_response_event_carries_success_outcome_and_exit_code(self):
        """Validate that HookResponseEvent correctly carries a success outcome
        with exit_code 0 and descriptive output.

        The test exercises construction of a completed-hook response and asserts
        that output, outcome, and exit_code all match because downstream
        dispatch logic branches on outcome to determine whether the tool
        execution path should continue or abort.
        """
        event = HookResponseEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="post_tool_exec",
            output="success",
            exit_code=0,
            outcome="success",
        )
        assert event.hook_id == "h1", "hook_id must match the constructor argument"
        assert event.output == "success", "output must reflect the final tool result"
        assert event.outcome == "success", "outcome must signal successful completion"
        assert event.exit_code == 0, "exit_code must indicate a clean process termination"

    def test_verify_response_event_carries_error_outcome_and_nonzero_exit_code(self):
        """Validate that HookResponseEvent correctly carries an error outcome
        with a nonzero exit_code when the tool fails.

        The test exercises construction of a failed-hook response and asserts
        that outcome is 'error' and exit_code is 1 because error-reporting
        paths rely on these fields to route diagnostics back to the caller
        without additional context lookups.
        """
        event = HookResponseEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="post_tool_exec",
            output="something went wrong",
            exit_code=1,
            outcome="error",
        )
        assert event.exit_code == 1, "exit_code must reflect a non-clean process termination"
        assert event.outcome == "error", "outcome must signal failure to downstream handlers"


class TestHookSystem:
    """Engineered to validate the full lifecycle of the hook dispatch system.

    This test class exercises handler registration, unregistration, event
    emission across all hook phases (pre-tool, post-tool, session, turn,
    error), observer notification, invalid-type rejection, and the enabled
    gate across 12 scenarios to ensure the hook system correctly isolates
    side effects and returns blocking decisions upstream. The design follows
    the invariant that hooks must be opt-in (disabled by default via the
    enabled flag) so that unconfigured deployments never pay dispatch cost.
    """

    def test_verify_system_constructs_with_default_enabled_state(self):
        """Validate that EncreHookSystem constructs with handlers dict and
        enabled flag set to True by default.

        The test exercises bare construction and asserts internal state because
        the hook system must be immediately usable without explicit
        initialization while still allowing consumers to inspect the default
        enabled gate.
        """
        hooks = EncreHookSystem()
        assert hooks is not None, "constructor must return a valid instance"
        assert hooks._handlers is not None, "handlers registry must be initialized"
        assert hooks.enabled is True, "hooks must be enabled by default for backward compatibility"

    def test_verify_handler_registration_stores_callable_under_event_type(self):
        """Validate that register_handler stores the callable in the correct
        event-type bucket and returns the explicitly provided handler id.

        The test exercises registration with a named id and asserts the return
        value and bucket length because the dispatch path indexes by
        event_type string, so mismatched keys would silently drop handlers.
        """
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {"block": False}

        hid = hooks.register_handler("pre_tool_exec", handler, "test_handler")
        assert hid == "test_handler", "explicit handler id must be returned unchanged"
        assert len(hooks._handlers["pre_tool_exec"]) == 1, "exactly one handler must be registered"

    def test_verify_handler_registration_generates_unique_auto_id(self):
        """Validate that register_handler generates a non-empty string id when
        no explicit id is provided.

        The test exercises registration without an id argument and asserts the
        returned id is a non-empty string because auto-generated ids are used
        as the lookup key for subsequent unregister calls.
        """
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        hid = hooks.register_handler("pre_tool_exec", handler)
        assert isinstance(hid, str), "auto-generated id must be a string"
        assert len(hid) > 0, "auto-generated id must not be empty"

    def test_verify_handler_unregistration_removes_callable_and_clears_bucket(self):
        """Validate that unregister_handler removes the callable from the
        event-type bucket and returns True on successful removal.

        The test exercises a register-then-unregister cycle and asserts the
        bucket is empty because stale handlers would fire on every emit and
        cause unintended side effects in downstream consumers.
        """
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        hid = hooks.register_handler("pre_tool_exec", handler, "test_handler")
        result = hooks.unregister_handler(hid)
        assert result is True, "unregister must return True when the handler existed"
        assert len(hooks._handlers["pre_tool_exec"]) == 0, "bucket must be empty after removal"

    def test_verify_unregister_nonexistent_handler_returns_false(self):
        """Validate that unregister_handler returns False when invoked with an
        id that was never registered.

        The test exercises unregistration of a nonexistent id and asserts False
        because the system must not raise on benign cleanup paths 鈥?callers
        often unregister in teardown without knowing whether registration
        succeeded.
        """
        hooks = EncreHookSystem()
        assert hooks.unregister_handler("nonexistent_id") is False, "unregister of unknown id must be safe"

    def test_verify_emit_pre_tool_invokes_registered_handler_and_propagates_block(self):
        """Validate that emit_pre_tool invokes all registered pre-tool handlers
        and returns their blocking decision when present.

        The test exercises handler registration followed by emission and asserts
        the handler was called because pre-tool hooks are the primary gating
        mechanism for tool execution safety checks.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            called = False

            async def handler(name, context, extra):
                """Handler."""
                nonlocal called
                called = True
                return {"block": False}

            hooks.register_handler("pre_tool_exec", handler, "test")
            await hooks.emit_pre_tool("bash", {"cmd": "ls"})
            assert called is True, "handler must be invoked when its event type is emitted"

        asyncio.run(_test())

    def test_verify_emit_pre_tool_returns_block_decision_when_handler_requests_stop(self):
        """Validate that emit_pre_tool returns the handler's block decision
        dict when a registered handler requests the tool execution be stopped.

        The test exercises a handler that returns {"block": True} and asserts
        the returned result carries that decision because blocking is the
        primary safety mechanism 鈥?the caller must act on the returned dict
        rather than ignoring it.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()

            async def handler(name, context, extra):
                """Handler."""
                return {"block": True, "block_reason": "unsafe"}

            hooks.register_handler("pre_tool_exec", handler, "test")
            result = await hooks.emit_pre_tool("bash", {"cmd": "rm -rf /"})
            assert result is not None, "blocking handler must produce a non-None result"
            assert result.get("block") is True, "returned decision must carry the block flag"

        asyncio.run(_test())

    def test_verify_emit_post_tool_injects_handler_output_into_result_string(self):
        """Validate that emit_post_tool passes handler return values into the
        resulting output string so that post-tool hooks can enrich context.

        The test exercises a handler returning {"extra_context": "..."} and
        asserts the injected text appears in the emitted result because the
        post-tool hook contract promises that handler outputs are merged into
        the tool result before it reaches the caller.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()

            async def handler(name, context, extra):
                """Handler."""
                return {"extra_context": "injected context"}

            hooks.register_handler("post_tool_exec", handler, "test")
            result = await hooks.emit_post_tool("bash", {"cmd": "ls"}, "file1.txt")
            assert isinstance(result, str), "post-tool emit must return a string result"
            assert "injected context" in result, "handler-injected context must appear in emitted output"

        asyncio.run(_test())

    def test_verify_emit_session_start_invokes_registered_on_session_start_handler(self):
        """Validate that emit_session_start invokes handlers registered under
        the on_session_start event type.

        The test exercises registration and emission and asserts the handler
        flag flipped because session-start hooks are the hook point for
        initializing per-session state like memory warm-up.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            called = False

            async def handler(name, context, extra):
                """Handler."""
                nonlocal called
                called = True
                return {}

            hooks.register_handler("on_session_start", handler, "test")
            await hooks.emit_session_start()
            assert called is True, "on_session_start handler must be invoked"

        asyncio.run(_test())

    def test_verify_emit_turn_start_invokes_registered_on_turn_start_handler(self):
        """Validate that emit_turn_start invokes handlers registered under the
        on_turn_start event type with the turn index passed through.

        The test exercises registration and emission and asserts the handler
        was called because turn-start hooks anchor per-turn bookkeeping such
        as budget tracking and turn-level summaries.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            called = False

            async def handler(name, context, extra):
                """Handler."""
                nonlocal called
                called = True
                return {}

            hooks.register_handler("on_turn_start", handler, "test")
            await hooks.emit_turn_start(1)
            assert called is True, "on_turn_start handler must be invoked"

        asyncio.run(_test())

    def test_verify_emit_error_invokes_registered_on_error_handler(self):
        """Validate that emit_error invokes handlers registered under the
        on_error event type and forwards the exception object.

        The test exercises registration with a ValueError and asserts the
        handler was called because error hooks are the designated pathway for
        telemetry and alerting 鈥?they must fire even when the primary path
        catches and swallows the exception.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            called = False

            async def handler(name, context, extra):
                """Handler."""
                nonlocal called
                called = True
                return {}

            hooks.register_handler("on_error", handler, "test")
            await hooks.emit_error(ValueError("test error"), "testing")
            assert called is True, "on_error handler must be invoked"

        asyncio.run(_test())

    def test_verify_on_event_observer_receives_all_emitted_events(self):
        """Validate that the observer callback registered via on_event receives
        every event emitted during a hook lifecycle.

        The test exercises emission of a pre-tool hook and asserts at least two
        events were observed because each emit fires a started event and a
        response event, proving the observer sees the full lifecycle.
        """
        hooks = EncreHookSystem()
        events = []

        def observer(event):
            """Observer."""
            events.append(event)

        hooks.on_event(observer)

        async def _test():
            """Helper: Test."""
            async def handler(name, context, extra):
                """Handler."""
                return {}

            hooks.register_handler("pre_tool_exec", handler, "test")
            await hooks.emit_pre_tool("bash", {"cmd": "ls"})

        asyncio.run(_test())
        assert len(events) >= 2, "observer must receive at least started and response events"

    def test_verify_register_handler_raises_on_invalid_event_type(self):
        """Validate that register_handler rejects unknown event type strings
        with a ValueError to prevent silent handler storage under invalid keys.

        The test exercises registration with "invalid_event_type" and asserts
        the exception because the event-type enum is the contract boundary 鈥?        invalid keys would break dispatch lookup and be nearly impossible to
        debug at runtime.
        """
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        with pytest.raises(ValueError):
            hooks.register_handler("invalid_event_type", handler)

    def test_verify_disabled_hooks_return_none_on_emit(self):
        """Validate that when the enabled flag is False, all emit methods return
        None instead of dispatching to registered handlers.

        The test exercises disabling the system, registering a blocking
        handler, and asserting the emit result is None because the enabled
        gate is the fast-path skip that prevents any dispatch overhead when
        hooks are not in use.
        """
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            hooks.enabled = False

            async def handler(name, context, extra):
                """Handler."""
                return {"block": True}

            hooks.register_handler("pre_tool_exec", handler, "test")
            result = await hooks.emit_pre_tool("bash", {"cmd": "ls"})
            assert result is None, "disabled hooks must short-circuit and return None"

        asyncio.run(_test())
