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

"""Test module: unit tests covering the Encre embedding index functionality."""

import tempfile
from pathlib import Path


def _fake_embedding(texts: list[str]) -> list[list[float]]:
    """Helper: Fake embedding."""
    return [[float(len(text)), 1.0] for text in texts]


class TestEncreEmbeddingIndex:
    """Test suite for EncreEmbeddingIndex."""
    def test_symbol_slices_do_not_bleed_into_adjacent_function(self):
        """Test: Symbol slices do not bleed into adjacent function."""
        from encre.codebase.ast_index import EncreASTIndex
        from encre.codebase.embedding_index import EncreEmbeddingIndex

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "a.py").write_text(
                "def foo():\n"
                "    return 1\n"
                "\n"
                "def bar():\n"
                "    return foo()\n",
                encoding="utf-8",
            )

            ast_idx = EncreASTIndex(str(ws))
            ast_idx.scan()
            emb = EncreEmbeddingIndex(str(ws), ast_index=ast_idx, embedding_fn=_fake_embedding)
            emb.scan()

            # Verify: emb.slice_count == 2
            assert emb.slice_count == 2
            by_symbol = {sl.symbol: sl for sl in emb._slices}
            # Verify: set(by_symbol) == {"foo", "bar"}
            assert set(by_symbol) == {"foo", "bar"}

            foo_text = by_symbol["foo"].text
            bar_text = by_symbol["bar"].text

            # Verify: "def foo():" in foo_text
            assert "def foo():" in foo_text
            # Verify: "def bar():" not in foo_text
            assert "def bar():" not in foo_text
            # Verify: "return foo()" not in foo_text
            assert "return foo()" not in foo_text

            # Verify: "def bar():" in bar_text
            assert "def bar():" in bar_text
            # Verify: "def foo():" not in bar_text
            assert "def foo():" not in bar_text

    def test_incremental_scan_updates_only_changed_file_slices(self):
        """Test: Incremental scan updates only changed file slices."""
        from encre.codebase.ast_index import EncreASTIndex
        from encre.codebase.embedding_index import EncreEmbeddingIndex

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            path_a = ws / "a.py"
            path_b = ws / "b.py"
            path_a.write_text("def foo():\n    return 1\n", encoding="utf-8")
            path_b.write_text("def bar():\n    return 2\n", encoding="utf-8")

            ast_idx = EncreASTIndex(str(ws))
            ast_idx.scan()
            emb = EncreEmbeddingIndex(str(ws), ast_index=ast_idx, embedding_fn=_fake_embedding)
            emb.scan()

            before = {(sl.file, sl.symbol): sl.text for sl in emb._slices}

            path_b.write_text("def bar():\n    return 22\n", encoding="utf-8")
            ast_idx.scan_incremental()
            emb.scan_incremental()

            after = {(sl.file, sl.symbol): sl.text for sl in emb._slices}

            # Verify: ("a.py", "foo") in after
            assert ("a.py", "foo") in after
            # Verify: ("b.py", "bar") in after
            assert ("b.py", "bar") in after
            # Verify: after[("a.py", "foo")] == before[("a.py", "foo")]
            assert after[("a.py", "foo")] == before[("a.py", "foo")]
            # Verify: after[("b.py", "bar")] != before[("b.py", "bar")]
            assert after[("b.py", "bar")] != before[("b.py", "bar")]
