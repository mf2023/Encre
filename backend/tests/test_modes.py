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

"""Tests for plan / spec mode switching -- the single-source-of-truth model.

These tests lock down the invariants that previously broke mode switching:

* ``loop.plan_mode_active`` is *derived* from ``config.slash_command_mode``
  so the boolean flag and the mode string can never disagree.
* :meth:`EncreLoop.set_mode` is the only transition entry point and keeps
  ``config``, the ``session.metadata`` mirror, and the derived flag
  consistent.
* Exiting a mode clears the persisted metadata slot -- the old "sticky
  restore" bug where a one-off ``/plan`` kept replaying across every
  later normal message must not recur.
* ``spec`` mode does NOT activate write-tool interception (only ``plan``
  does); switching plan <-> spec flips the flag correctly.
"""

from unittest.mock import MagicMock, patch

import pytest
from encre.config import EncreConfig
from encre.loop import EncreLoop
from encre.session import EncreSession


def _make_loop() -> EncreLoop:
    """Build an EncreLoop with a mocked backend (no real API calls)."""
    config = EncreConfig(
        model="gpt-5.6",
        backend_type="openai",
        permission_mode="default",
        max_turns=10,
        max_tokens=4096,
        log_level="ERROR",
        enable_prompt_caching=False,
    )
    session = EncreSession(config)
    with patch("encre.loop.create_backend") as mock_create_backend:
        mock_backend = MagicMock()
        mock_backend.supports_tool_calling.return_value = True
        mock_backend.supports_prompt_caching.return_value = False
        mock_backend.context_window_size.return_value = 128000
        mock_create_backend.return_value = mock_backend
        return EncreLoop(config=config, session=session)


def _invariant(loop: EncreLoop) -> None:
    """Assert the flag and the mode string never disagree."""
    assert loop.plan_mode_active == (loop.config.slash_command_mode == "plan")


class TestModeSwitchingInvariants:
    """The bool/str sync invariant holds across every transition."""

    def test_default_state_is_normal(self):
        loop = _make_loop()
        assert loop.config.slash_command_mode == ""
        assert loop.plan_mode_active is False
        _invariant(loop)

    def test_set_mode_plan_activates_interception(self):
        loop = _make_loop()
        loop.set_mode("plan")
        assert loop.config.slash_command_mode == "plan"
        assert loop.plan_mode_active is True
        assert loop.session.metadata.get("slash_command_mode") == "plan"
        assert loop.session.metadata.get("plan_mode_active") is True
        _invariant(loop)

    def test_set_mode_spec_does_not_activate_interception(self):
        loop = _make_loop()
        loop.set_mode("spec")
        assert loop.config.slash_command_mode == "spec"
        # spec is a strict mode but does NOT intercept write tools --
        # only plan does.
        assert loop.plan_mode_active is False
        assert loop.session.metadata.get("slash_command_mode") == "spec"
        assert loop.session.metadata.get("plan_mode_active") is False
        _invariant(loop)

    def test_set_mode_clear_pops_persistent_slot(self):
        loop = _make_loop()
        loop.set_mode("plan")
        assert "slash_command_mode" in loop.session.metadata
        loop.set_mode("")
        # The persistent slot must be cleared so nothing can sticky-restore
        # the old mode on a later normal message.
        assert loop.session.metadata.get("slash_command_mode", "") == ""
        assert loop.config.slash_command_mode == ""
        assert loop.plan_mode_active is False
        assert loop.session.metadata.get("plan_mode_active") is False
        _invariant(loop)

    def test_set_mode_normalises_invalid_values(self):
        loop = _make_loop()
        loop.set_mode("plan")
        loop.set_mode("not-a-real-mode")
        assert loop.config.slash_command_mode == ""
        assert loop.plan_mode_active is False
        _invariant(loop)

    def test_enter_exit_plan_mode_wrappers(self):
        loop = _make_loop()
        loop.enter_plan_mode(reason="test")
        assert loop.plan_mode_active is True
        assert loop.config.slash_command_mode == "plan"
        _invariant(loop)
        loop.exit_plan_mode(reason="done")
        assert loop.plan_mode_active is False
        assert loop.config.slash_command_mode == ""
        assert loop.session.metadata.get("slash_command_mode", "") == ""
        _invariant(loop)


class TestModeSwitchScenarios:
    """The user-reported flow: enter -> exit -> re-enter must not get stuck."""

    def test_plan_exit_spec_exit_normal(self):
        """Reproduce the reported bug: enter plan, exit, then enter another mode.

        Before the fix, exiting plan left the persisted metadata in place and
        the per-message path restored it, so the session got stuck in plan.
        Now every transition is clean and the final state is normal.
        """
        loop = _make_loop()
        # enter plan
        loop.set_mode("plan")
        assert loop.plan_mode_active is True
        _invariant(loop)
        # exit to normal
        loop.set_mode("")
        assert loop.plan_mode_active is False
        assert loop.session.metadata.get("slash_command_mode", "") == ""
        _invariant(loop)
        # enter spec -- must still work after the plan cycle
        loop.set_mode("spec")
        assert loop.config.slash_command_mode == "spec"
        assert loop.plan_mode_active is False
        _invariant(loop)
        # exit to normal again
        loop.set_mode("")
        assert loop.config.slash_command_mode == ""
        assert loop.plan_mode_active is False
        assert loop.session.metadata.get("slash_command_mode", "") == ""
        _invariant(loop)

    def test_plan_to_spec_direct_switch(self):
        """Switching plan -> spec -> plan flips the interception flag each time."""
        loop = _make_loop()
        loop.set_mode("plan")
        assert loop.plan_mode_active is True
        _invariant(loop)
        # plan -> spec: interception turns off
        loop.set_mode("spec")
        assert loop.plan_mode_active is False
        assert loop.config.slash_command_mode == "spec"
        _invariant(loop)
        # spec -> plan: interception turns back on
        loop.set_mode("plan")
        assert loop.plan_mode_active is True
        assert loop.config.slash_command_mode == "plan"
        _invariant(loop)

    def test_no_sticky_restore_after_exit(self):
        """After exiting plan, the metadata slot is gone -- nothing replays it.

        This is the regression guard for the sticky bug: the old per-message
        path did ``config = metadata["slash_command_mode"]`` whenever a run
        message arrived without an explicit mode, which resurrected plan mode
        on every subsequent normal turn.  With the slot cleared on exit,
        reading the persisted mode returns empty.
        """
        loop = _make_loop()
        loop.set_mode("plan")
        assert loop.session.metadata.get("slash_command_mode") == "plan"
        loop.set_mode("")
        # Simulate a later normal run arriving with no explicit mode: the
        # persisted mode it would have restored from is now empty.
        persisted = loop.session.metadata.get("slash_command_mode", "") or ""
        assert persisted == ""
        assert loop.plan_mode_active is False

    def test_repeated_enter_plan_is_idempotent(self):
        loop = _make_loop()
        loop.set_mode("plan")
        loop.set_mode("plan")
        loop.set_mode("plan")
        assert loop.config.slash_command_mode == "plan"
        assert loop.plan_mode_active is True
        _invariant(loop)

    def test_exit_when_not_in_plan_is_safe(self):
        loop = _make_loop()
        # Exiting from normal must not raise and must leave state clean.
        loop.exit_plan_mode(reason="no-op")
        assert loop.config.slash_command_mode == ""
        assert loop.plan_mode_active is False
        _invariant(loop)


class TestPlanModeWaiterWake:
    """Leaving plan mode wakes a waiter parked on a pending proposal."""

    def test_set_mode_clear_wakes_pending_plan_event(self):
        import asyncio
        loop = _make_loop()
        loop.set_mode("plan")
        # Plant a waiter as if a PlanProposal is pending.
        loop._plan_event = asyncio.Event()
        loop.set_mode("")
        # Transitioning out of plan must set the event so the waiter unblocks.
        assert loop._plan_event.is_set() is True

    def test_enter_plan_does_not_spuriously_wake(self):
        import asyncio
        loop = _make_loop()
        loop._plan_event = asyncio.Event()
        loop.set_mode("plan")
        # Entering plan should not trip a waiter (there is none pending).
        assert loop._plan_event.is_set() is False


class TestStagePromptNotAMode:
    """The internal work-phase hint must not read as a user 'mode'.

    Regression guard for the confusion where the model answered 'discover
    mode' (the task_stage) instead of the real slash-command mode.  The
    stage prompt is still injected (it helps steer behaviour) but its
    wording is now explicitly framed as an internal work phase, never a
    mode, and tells the model to consult the mode block instead.
    """

    def test_stage_prompt_does_not_say_mode(self):
        loop = _make_loop()
        loop.session.metadata["task_stage"] = "discover"
        prompt = loop._build_stage_prompt()
        # The old wording "Current stage: discover" was read as a mode
        # declaration.  The new wording uses "Work Phase" and "work phase"
        # and explicitly disclaims being a mode.
        assert "Work Phase" in prompt
        assert "work phase" in prompt
        assert "not a mode" in prompt.lower() or "not a user mode" in prompt.lower()
        # The misleading bare "Current stage:" phrase must be gone.
        assert "Current stage:" not in prompt


class TestSpecDataRouting:
    """A ``__spec_data__:`` SystemMessage must become a spec_update, not a bubble.

    Regression guard for the leak where the raw spec JSON rendered as a
    visible 'System message' strip at the top of the conversation.  The
    ws.py SystemMessage handler intercepts the ``__spec_data__:`` prefix
    and re-routes it as a ``spec_update`` event so the frontend renders the
    spec card instead of a leaked JSON strip.
    """

    def _make_handler(self):
        """Build a bare EncreWSHandler with a capturing _send."""
        from encre.server.ws import EncreWSHandler
        handler = EncreWSHandler.__new__(EncreWSHandler)
        sent: list[tuple[str, dict]] = []

        async def _send(ws, msg_type, **kwargs):
            sent.append((msg_type, kwargs))
        handler._send = _send  # type: ignore[assignment]
        return handler, sent

    def test_spec_data_rerouted_as_spec_update(self):
        import asyncio
        import json
        from encre.utils.types import SystemMessage

        handler, sent = self._make_handler()
        spec_payload = {"title": "Demo", "sections": [], "status": "review"}
        event = SystemMessage(
            content="__spec_data__:" + json.dumps(spec_payload),
            kind="spec",
        )
        info = MagicMock()
        info.session_id = "s1"

        asyncio.run(handler._dispatch_event(ws=object(), _info=info, event=event))

        # The spec data must be re-routed as spec_update with the parsed spec.
        assert sent and sent[0][0] == "spec_update"
        assert sent[0][1]["spec"] == spec_payload
        assert sent[0][1]["status"] == "review"
        assert sent[0][1]["session_id"] == "s1"
        # And it must NOT also leak as a system_message bubble.
        assert not any(t == "system_message" for t, _ in sent)

    def test_plain_system_message_still_bubbles(self):
        import asyncio
        from encre.utils.types import create_system_message

        handler, sent = self._make_handler()
        event = create_system_message(
            "Specification generated. Review it.", kind="spec",
        )
        info = MagicMock()
        info.session_id = "s1"

        asyncio.run(handler._dispatch_event(ws=object(), _info=info, event=event))

        # A friendly (non __spec_data__) notice still renders as a bubble.
        assert sent and sent[0][0] == "system_message"
        assert sent[0][1]["content"] == "Specification generated. Review it."
        assert sent[0][1]["kind"] == "spec"
