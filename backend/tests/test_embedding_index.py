#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
from pathlib import Path


def _fake_embedding(texts: list[str]) -> list[list[float]]:
    return [[float(len(text)), 1.0] for text in texts]


class TestEncreEmbeddingIndex:
    def test_symbol_slices_do_not_bleed_into_adjacent_function(self):
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

            assert emb.slice_count == 2
            by_symbol = {sl.symbol: sl for sl in emb._slices}
            assert set(by_symbol) == {"foo", "bar"}

            foo_text = by_symbol["foo"].text
            bar_text = by_symbol["bar"].text

            assert "def foo():" in foo_text
            assert "def bar():" not in foo_text
            assert "return foo()" not in foo_text

            assert "def bar():" in bar_text
            assert "def foo():" not in bar_text

    def test_incremental_scan_updates_only_changed_file_slices(self):
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

            assert ("a.py", "foo") in after
            assert ("b.py", "bar") in after
            assert after[("a.py", "foo")] == before[("a.py", "foo")]
            assert after[("b.py", "bar")] != before[("b.py", "bar")]
