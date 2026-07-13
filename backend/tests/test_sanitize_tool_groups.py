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

from __future__ import annotations

"""Tests for ``_sanitize_tool_groups`` -- the pause/resume tool-closure fix.

Each test reproduces a message-list shape that a cancelled turn can leave
behind, and asserts sanitize closes it so no 400 reaches the backend.
"""

import unittest

from encre.compact.engine import _sanitize_tool_groups


def _assistant(tool_call_ids: list[str], text: str = "") -> dict:
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {"id": tid, "type": "function", "function": {"name": "x", "arguments": "{}"}}
            for tid in tool_call_ids
        ],
    }


def _tool(tid: str, content: str = "ok") -> dict:
    return {"role": "tool", "tool_call_id": tid, "content": content}


class SanitizeToolGroupsTest(unittest.TestCase):
    def test_complete_group_unchanged(self):
        msgs = [_assistant(["A", "B"]), _tool("A"), _tool("B")]
        out = _sanitize_tool_groups(msgs)
        self.assertEqual([m["role"] for m in out], ["assistant", "tool", "tool"])
        self.assertEqual(out[1]["tool_call_id"], "A")
        self.assertEqual(out[2]["tool_call_id"], "B")

    def test_incomplete_group_gets_tombstone_not_dropped(self):
        # Cancel mid-turn: assistant declared A and B, only A's result landed.
        msgs = [_assistant(["A", "B"]), _tool("A")]
        out = _sanitize_tool_groups(msgs)
        # Group is KEPT (not dropped) and B gets a tombstone so the good A
        # result survives.
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["assistant", "tool", "tool"])
        self.assertEqual(out[1]["tool_call_id"], "A")
        self.assertEqual(out[1]["content"], "ok")
        self.assertEqual(out[2]["tool_call_id"], "B")
        self.assertIn("not persisted", out[2]["content"])

    def test_orphan_tool_result_dropped(self):
        # A tool result whose id no assistant declared -- the streaming-cancel
        # case where the assistant message was never persisted but a result was.
        msgs = [
            {"role": "user", "content": "hi"},
            _tool("GHOST"),  # no assistant declared GHOST
            {"role": "user", "content": "again"},
        ]
        out = _sanitize_tool_groups(msgs)
        roles = [m["role"] for m in out]
        self.assertNotIn("tool", roles)
        self.assertEqual(roles, ["user", "user"])

    def test_orphan_after_complete_group_dropped(self):
        # Complete A,B group followed by a stray C result from a prior turn.
        msgs = [_assistant(["A", "B"]), _tool("A"), _tool("B"), _tool("C")]
        out = _sanitize_tool_groups(msgs)
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["assistant", "tool", "tool"])
        ids = [m.get("tool_call_id") for m in out if m["role"] == "tool"]
        self.assertEqual(ids, ["A", "B"])

    def test_leading_orphan_tools_dropped(self):
        msgs = [_tool("X"), _tool("Y"), _assistant(["A"]), _tool("A")]
        out = _sanitize_tool_groups(msgs)
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["assistant", "tool"])

    def test_assistant_with_no_id_tool_calls_dropped(self):
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "", "type": "function", "function": {"name": "x", "arguments": "{}"}}
            ]},
            _tool("whatever"),
        ]
        out = _sanitize_tool_groups(msgs)
        self.assertEqual(out, [])

    def test_two_groups_both_incomplete(self):
        msgs = [
            _assistant(["A", "B"]), _tool("A"),  # B missing
            _assistant(["C", "D"]), _tool("C"),  # D missing
        ]
        out = _sanitize_tool_groups(msgs)
        # Both groups kept, each with a tombstone for the missing id.
        ids = [m.get("tool_call_id") for m in out if m["role"] == "tool"]
        self.assertEqual(ids, ["A", "B", "C", "D"])
        tombstoned = [m for m in out if m["role"] == "tool" and "not persisted" in m["content"]]
        self.assertEqual(len(tombstoned), 2)
        tomb_ids = {m["tool_call_id"] for m in tombstoned}
        self.assertEqual(tomb_ids, {"B", "D"})

    def test_idempotent(self):
        msgs = [_assistant(["A", "B"]), _tool("A")]
        once = _sanitize_tool_groups(msgs)
        twice = _sanitize_tool_groups(once)
        self.assertEqual(once, twice)

    def test_does_not_mutate_input(self):
        msgs = [_assistant(["A"]), _tool("A")]
        original = [dict(m) for m in msgs]
        _sanitize_tool_groups(msgs)
        self.assertEqual(msgs, original)


if __name__ == "__main__":
    unittest.main()
