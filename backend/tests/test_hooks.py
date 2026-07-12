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
    """Test suite for HookEventTypes."""
    def test_started_event(self):
        """Test: Started event."""
        event = HookStartedEvent(
            hook_id="h1", hook_name="test_hook", event_type="pre_tool_exec"
        )
        # Verify: event.hook_id == "h1"
        assert event.hook_id == "h1"
        # Verify: event.hook_name == "test_hook"
        assert event.hook_name == "test_hook"
        # Verify: event.event_type == "pre_tool_exec"
        assert event.event_type == "pre_tool_exec"

    def test_progress_event(self):
        """Test: Progress event."""
        event = HookProgressEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="on_tool_progress",
            output="running",
            stdout="out",
            stderr="",
        )
        # Verify: event.hook_id == "h1"
        assert event.hook_id == "h1"
        # Verify: event.output == "running"
        assert event.output == "running"
        # Verify: event.stdout == "out"
        assert event.stdout == "out"

    def test_response_event(self):
        """Test: Response event."""
        event = HookResponseEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="post_tool_exec",
            output="success",
            exit_code=0,
            outcome="success",
        )
        # Verify: event.hook_id == "h1"
        assert event.hook_id == "h1"
        # Verify: event.output == "success"
        assert event.output == "success"
        # Verify: event.outcome == "success"
        assert event.outcome == "success"
        # Verify: event.exit_code == 0
        assert event.exit_code == 0

    def test_response_event_error(self):
        """Test: Response event error."""
        event = HookResponseEvent(
            hook_id="h1",
            hook_name="test_hook",
            event_type="post_tool_exec",
            output="something went wrong",
            exit_code=1,
            outcome="error",
        )
        # Verify: event.exit_code == 1
        assert event.exit_code == 1
        # Verify: event.outcome == "error"
        assert event.outcome == "error"


class TestHookSystem:
    """Test suite for HookSystem."""
    def test_create(self):
        """Test: Create."""
        hooks = EncreHookSystem()
        # Verify: hooks is not None
        assert hooks is not None
        # Verify: hooks._handlers is not None
        assert hooks._handlers is not None
        # Verify: hooks.enabled is True
        assert hooks.enabled is True

    def test_register_handler(self):
        """Test: Register handler."""
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {"block": False}

        hid = hooks.register_handler("pre_tool_exec", handler, "test_handler")
        # Verify: hid == "test_handler"
        assert hid == "test_handler"
        # Verify: len(hooks._handlers["pre_tool_exec"]) == 1
        assert len(hooks._handlers["pre_tool_exec"]) == 1

    def test_register_handler_auto_id(self):
        """Test: Register handler auto id."""
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        hid = hooks.register_handler("pre_tool_exec", handler)
        # Verify: isinstance(hid, str)
        assert isinstance(hid, str)
        # Verify: len(hid) > 0
        assert len(hid) > 0

    def test_unregister_handler(self):
        """Test: Unregister handler."""
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        hid = hooks.register_handler("pre_tool_exec", handler, "test_handler")
        result = hooks.unregister_handler(hid)
        # Verify: result is True
        assert result is True
        # Verify: len(hooks._handlers["pre_tool_exec"]) == 0
        assert len(hooks._handlers["pre_tool_exec"]) == 0

    def test_unregister_nonexistent(self):
        """Test: Unregister nonexistent."""
        hooks = EncreHookSystem()
        # Verify: hooks.unregister_handler("nonexistent_id") is False
        assert hooks.unregister_handler("nonexistent_id") is False

    def test_emit_pre_tool(self):
        """Test: Emit pre tool."""
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
            # Verify: called is True
            assert called is True

        asyncio.run(_test())

    def test_emit_pre_tool_block(self):
        """Test: Emit pre tool block."""
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()

            async def handler(name, context, extra):
                """Handler."""
                return {"block": True, "block_reason": "unsafe"}

            hooks.register_handler("pre_tool_exec", handler, "test")
            result = await hooks.emit_pre_tool("bash", {"cmd": "rm -rf /"})
            # Verify: result is not None
            assert result is not None
            # Verify: result.get("block") is True
            assert result.get("block") is True

        asyncio.run(_test())

    def test_emit_post_tool(self):
        """Test: Emit post tool."""
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()

            async def handler(name, context, extra):
                """Handler."""
                return {"extra_context": "injected context"}

            hooks.register_handler("post_tool_exec", handler, "test")
            result = await hooks.emit_post_tool("bash", {"cmd": "ls"}, "file1.txt")
            # Verify: isinstance(result, str)
            assert isinstance(result, str)
            # Verify: "injected context" in result
            assert "injected context" in result

        asyncio.run(_test())

    def test_emit_session_start(self):
        """Test: Emit session start."""
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
            # Verify: called is True
            assert called is True

        asyncio.run(_test())

    def test_emit_turn_start(self):
        """Test: Emit turn start."""
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
            # Verify: called is True
            assert called is True

        asyncio.run(_test())

    def test_emit_error(self):
        """Test: Emit error."""
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
            # Verify: called is True
            assert called is True

        asyncio.run(_test())

    def test_on_event_observer(self):
        """Test: On event observer."""
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
            # Should have received at least started + response events
            assert len(events) >= 2

        asyncio.run(_test())

    def test_register_invalid_event_type(self):
        """Test: Register invalid event type."""
        hooks = EncreHookSystem()

        async def handler(name, context, extra):
            """Handler."""
            return {}

        with pytest.raises(ValueError):
            hooks.register_handler("invalid_event_type", handler)

    def test_disabled_hooks(self):
        """Test: Disabled hooks."""
        async def _test():
            """Helper: Test."""
            hooks = EncreHookSystem()
            hooks.enabled = False

            async def handler(name, context, extra):
                """Handler."""
                return {"block": True}

            hooks.register_handler("pre_tool_exec", handler, "test")
            result = await hooks.emit_pre_tool("bash", {"cmd": "ls"})
            # Verify: result is None
            assert result is None

        asyncio.run(_test())
