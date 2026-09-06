#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 漏 2025-2026 Wenze Wei. All Rights Reserved.
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
    """Engineered to validate the _sanitize_tool_groups pause/resume fix.

    This test class exercises the sanitize function across 9 message-list
    shapes that a cancelled turn can produce: complete groups, incomplete
    groups with orphaned results, leading orphans, empty IDs, double
    incomplete groups, idempotency, and input immutability. The design
    ensures no malformed message sequence reaches the LLM backend, which
    would otherwise return a 400 validation error.
    """
    def test_verify_complete_group_unchanged(self):
        """Validate that a complete assistant-tool-group passes through unchanged.

        The test exercises _sanitize_tool_groups with an assistant declaring
        tool calls A and B followed by both tool results, and asserts the
        roles and tool_call_ids are preserved in order because a complete
        group requires no correction.
        """
        msgs = [_assistant(["A", "B"]), _tool("A"), _tool("B")]
        out = _sanitize_tool_groups(msgs)
        self.assertEqual([m["role"] for m in out], ["assistant", "tool", "tool"])
        self.assertEqual(out[1]["tool_call_id"], "A")
        self.assertEqual(out[2]["tool_call_id"], "B")

    def test_verify_incomplete_group_gets_tombstone_not_dropped(self):
        """Validate that an incomplete group gets a tombstone for the missing result.

        The test exercises sanitize with an assistant declaring A and B but
        only A's result present, and asserts the group is kept (not dropped)
        and B receives a tombstone containing 'not persisted' because the
        incomplete result must be preserved so the LLM sees the cancelled
        tool call rather than a missing message.
        """
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

    def test_verify_orphan_tool_result_dropped(self):
        """Validate that an orphan tool result with no matching assistant declaration is dropped.

        The test exercises sanitize with a user message, a tool result for
        "GHOST" (no assistant declared it), and another user message, and
        asserts all tool roles are removed because orphan results have no
        corresponding assistant tool_call and would break the message schema.
        """
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

    def test_verify_orphan_after_complete_group_dropped(self):
        """Validate that an orphan tool result following a complete group is dropped.

        The test exercises sanitize with a complete A,B group followed by a
        stray C result from a prior turn and asserts the output contains only
        the A,B group because the orphan C has no matching assistant declaration
        in the current message sequence.
        """
        # Complete A,B group followed by a stray C result from a prior turn.
        msgs = [_assistant(["A", "B"]), _tool("A"), _tool("B"), _tool("C")]
        out = _sanitize_tool_groups(msgs)
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["assistant", "tool", "tool"])
        ids = [m.get("tool_call_id") for m in out if m["role"] == "tool"]
        self.assertEqual(ids, ["A", "B"])

    def test_verify_leading_orphan_tools_dropped(self):
        """Validate that leading orphan tool results preceding any assistant are dropped.

        The test exercises sanitize with two orphan tool results (X, Y) followed
        by an assistant declaring A and its result, and asserts only the valid
        assistant-tool pair survives because leading orphans have no context.
        """
        msgs = [_tool("X"), _tool("Y"), _assistant(["A"]), _tool("A")]
        out = _sanitize_tool_groups(msgs)
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["assistant", "tool"])

    def test_verify_assistant_with_no_id_tool_calls_dropped(self):
        """Validate that an assistant with empty-ID tool calls and its orphan result are dropped entirely.

        The test exercises sanitize with an assistant whose tool_call has id=""
        followed by a tool result for "whatever", and asserts the output is an
        empty list because empty IDs are invalid and the associated tool result
        cannot be matched to any declaration.
        """
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "", "type": "function", "function": {"name": "x", "arguments": "{}"}}
            ]},
            _tool("whatever"),
        ]
        out = _sanitize_tool_groups(msgs)
        self.assertEqual(out, [])

    def test_verify_two_groups_both_incomplete(self):
        """Validate that two incomplete groups each receive tombstones for their missing results.

        The test exercises sanitize with two assistant declarations (A,B and C,D)
        each followed by only the first tool result, and asserts all four IDs
        appear in the output with B and D receiving tombstone content because
        each incomplete group must be closed independently.
        """
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

    def test_verify_idempotent(self):
        """Validate that running sanitize twice on the same input produces identical output.

        The test exercises sanitize on an incomplete group once, then runs it
        again on the already-sanitized output, and asserts equality because
        the second pass must be a no-op on an already-correct message list.
        """
        msgs = [_assistant(["A", "B"]), _tool("A")]
        once = _sanitize_tool_groups(msgs)
        twice = _sanitize_tool_groups(once)
        self.assertEqual(once, twice)

    def test_verify_does_not_mutate_input(self):
        """Validate that sanitize does not mutate the input message list in place.

        The test exercises sanitize on a valid complete group after capturing
        a shallow copy of the input and asserts the original list is unchanged
        because the function must produce a new list rather than mutating
        the caller's data.
        """
        msgs = [_assistant(["A"]), _tool("A")]
        original = [dict(m) for m in msgs]
        _sanitize_tool_groups(msgs)
        self.assertEqual(msgs, original)


if __name__ == "__main__":
    unittest.main()
