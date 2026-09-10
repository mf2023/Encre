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

import os
import tempfile
from pathlib import Path


def _fake_embedding(texts: list[str]) -> list[list[float]]:
    """Return a deterministic 2-D embedding for each input text.

    The embedding encodes text length as the first dimension and a constant
    1.0 as the second so that slice-level tests can inspect raw float vectors
    without requiring an actual model backend.
    """
    return [[float(len(text)), 1.0] for text in texts]


class TestEncreEmbeddingIndex:
    """Engineered to validate the embedding index slice isolation and incremental scan.

    This test class exercises :class:`EncreEmbeddingIndex` across a two-function
    source file scenario and an incremental-update scenario to ensure that:
    (1) AST-derived symbol slices do not bleed into adjacent functions, and
    (2) incremental rescans update only the slices belonging to changed files.
    These invariants are critical because corrupted slices produce noisy
    vector-store queries and degraded semantic retrieval accuracy.
    """

    def test_verify_symbol_slices_do_not_bleed_into_adjacent_function(self):
        """Validate that each function's embedding slice contains only its own source.

        The test writes two adjacent top-level functions (foo and bar) into a
        temp workspace, runs a full AST scan, and then asserts that foo's slice
        text contains ``def foo():`` but not ``def bar():`` or ``return foo()``.
        This guards against AST slice boundaries leaking across function borders,
        which would corrupt the vector store with mixed-context chunks.
        """
        from encre.capabilities.search.codebase.ast_index import EncreASTIndex
        from encre.capabilities.search.codebase.embedding_index import EncreEmbeddingIndex

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

            # Two top-level defs must yield exactly two slices.
            assert emb.slice_count == 2
            by_symbol = {sl.symbol: sl for sl in emb._slices}
            # Both symbols must be indexed.
            assert set(by_symbol) == {"foo", "bar"}

            foo_text = by_symbol["foo"].text
            bar_text = by_symbol["bar"].text

            # foo's slice must contain its own definition.
            assert "def foo():" in foo_text
            # foo's slice must NOT contain bar's definition (no bleed).
            assert "def bar():" not in foo_text
            # foo's slice must NOT contain bar's call site (no bleed).
            assert "return foo()" not in foo_text

            # bar's slice must contain its own definition.
            assert "def bar():" in bar_text
            # bar's slice must NOT contain foo's definition (no bleed).
            assert "def foo():" not in bar_text

    def test_verify_incremental_scan_updates_only_changed_file_slices(self):
        """Validate that incremental scans touch only modified-file slices.

        The test writes two files (a.py, b.py), records the full-scan snapshot,
        mutates b.py only, runs an incremental AST + embedding scan, and then
        asserts:
        - Both slices still exist in the post-scan state.
        - The untouched a.py slice is byte-identical to the pre-scan snapshot.
        - The mutated b.py slice differs from the pre-scan snapshot.
        This guards against incremental rescans incorrectly rewriting unchanged
        content or failing to update changed content.
        """
        from encre.capabilities.search.codebase.ast_index import EncreASTIndex
        from encre.capabilities.search.codebase.embedding_index import EncreEmbeddingIndex

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
            # Nudge mtime forward: on filesystems with coarse mtime resolution
            # a same-second write can be missed by the incremental scan.
            st = path_b.stat()
            os.utime(path_b, (st.st_atime, st.st_mtime + 10))
            ast_idx.scan_incremental()
            emb.scan_incremental()

            after = {(sl.file, sl.symbol): sl.text for sl in emb._slices}

            # Both files must still be indexed after the incremental scan.
            assert ("a.py", "foo") in after
            assert ("b.py", "bar") in after
            # Unchanged file's slice text must remain byte-identical.
            assert after[("a.py", "foo")] == before[("a.py", "foo")]
            # Mutated file's slice text must reflect the new content.
            assert after[("b.py", "bar")] != before[("b.py", "bar")]
