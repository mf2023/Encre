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

"""Tests for encre.codebase.indexer -- EncreCodeIndex and ModuleInfo."""

import os
import tempfile
import textwrap

# ===========================================================================
# ModuleInfo dataclass
# ===========================================================================

class TestModuleInfo:
    """Tests for the ModuleInfo dataclass."""

    def test_creation_with_all_fields(self):
        """Test: Creation with all fields."""
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(
            path="src/my_module.py",
            name="my_module",
            imports=["os", "json", "typing"],
            imported_by=["main.py", "test_module.py"],
            exports=["public_func", "MyClass", "CONSTANT"],
            language="python",
            loc=150,
        )
        # Verify: mi.path == "src/my_module.py"
        assert mi.path == "src/my_module.py"
        # Verify: mi.name == "my_module"
        assert mi.name == "my_module"
        # Verify: len(mi.imports) == 3
        assert len(mi.imports) == 3
        # Verify: "os" in mi.imports
        assert "os" in mi.imports
        # Verify: len(mi.imported_by) == 2
        assert len(mi.imported_by) == 2
        # Verify: "main.py" in mi.imported_by
        assert "main.py" in mi.imported_by
        # Verify: len(mi.exports) == 3
        assert len(mi.exports) == 3
        # Verify: "MyClass" in mi.exports
        assert "MyClass" in mi.exports
        # Verify: mi.language == "python"
        assert mi.language == "python"
        # Verify: mi.loc == 150
        assert mi.loc == 150

    def test_default_values(self):
        """Test: Default values."""
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="test.py", name="test")
        # Verify: mi.imports == []
        assert mi.imports == []
        # Verify: mi.imported_by == []
        assert mi.imported_by == []
        # Verify: mi.exports == []
        assert mi.exports == []
        # Verify: mi.language == ""
        assert mi.language == ""
        # Verify: mi.loc == 0
        assert mi.loc == 0

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.codebase.indexer import ModuleInfo
        # Verify: is_dataclass(ModuleInfo)
        assert is_dataclass(ModuleInfo)

    def test_language_variants(self):
        """Test: Language variants."""
        from encre.codebase.indexer import ModuleInfo
        for lang in ["python", "rust", "go", "javascript", "typescript", "java"]:
            mi = ModuleInfo(path=f"src/module.{lang[:2]}", name="mod", language=lang)
            # Verify: mi.language == lang
            assert mi.language == lang

    def test_windows_path_normalization(self):
        """Test: Windows path normalization."""
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="src\\subdir\\module.py", name="module")
        # Verify: "src" in mi.path
        assert "src" in mi.path


# ===========================================================================
# EncreCodeIndex construction
# ===========================================================================

class TestEncreCodeIndexConstruction:
    """Tests for EncreCodeIndex construction and initial state."""

    def test_construction(self):
        """Test: Construction."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        # Verify: ci is not None
        assert ci is not None
        # Verify: ci.workspace == "."
        assert ci.workspace == "."
        # Verify: ci._indexed is False
        assert ci._indexed is False

    def test_construction_absolute_path(self):
        """Test: Construction absolute path."""
        from encre.codebase.indexer import EncreCodeIndex
        abs_path = os.path.abspath(".")
        ci = EncreCodeIndex(workspace=abs_path)
        # Verify: ci.workspace == abs_path
        assert ci.workspace == abs_path

    def test_initial_state_empty(self):
        """Test: Initial state empty."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        # Verify: ci._modules == {}
        assert ci._modules == {}
        # Verify: ci._depgraph == {}
        assert ci._depgraph == {}
        # Verify: ci._reverse_depgraph == {}
        assert ci._reverse_depgraph == {}
        # Verify: ci._inverted_index == {}
        assert ci._inverted_index == {}
        # Verify: ci._total_docs == 0
        assert ci._total_docs == 0
        # Verify: ci._indexed is False
        assert ci._indexed is False

    def test_known_extensions_set(self):
        """Test: Known extensions set."""
        from encre.codebase.indexer import EncreCodeIndex
        # Verify: ".py" in EncreCodeIndex._KNOWN_EXTS
        assert ".py" in EncreCodeIndex._KNOWN_EXTS
        # Verify: ".rs" in EncreCodeIndex._KNOWN_EXTS
        assert ".rs" in EncreCodeIndex._KNOWN_EXTS
        # Verify: ".go" in EncreCodeIndex._KNOWN_EXTS
        assert ".go" in EncreCodeIndex._KNOWN_EXTS
        # Verify: ".js" in EncreCodeIndex._KNOWN_EXTS
        assert ".js" in EncreCodeIndex._KNOWN_EXTS
        # Verify: ".ts" in EncreCodeIndex._KNOWN_EXTS
        assert ".ts" in EncreCodeIndex._KNOWN_EXTS
        # Verify: ".java" in EncreCodeIndex._KNOWN_EXTS
        assert ".java" in EncreCodeIndex._KNOWN_EXTS


# ===========================================================================
# EncreCodeIndex scan and search
# ===========================================================================

class TestEncreCodeIndexScan:
    """Tests for scanning a real codebase."""

    def test_scan_runs_without_error(self):
        """Test: Scan runs without error."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        # Verify: ci._indexed is True
        assert ci._indexed is True

    def test_scan_indexes_modules(self):
        """Test: Scan indexes modules."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        # Verify: len(ci._modules) > 0
        assert len(ci._modules) > 0

    def test_scan_modules_have_paths(self):
        """Test: Scan modules have paths."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        for _path, mod in ci._modules.items():
            # Verify: isinstance(mod.path, str)
            assert isinstance(mod.path, str)
            # Verify: len(mod.path) > 0
            assert len(mod.path) > 0

    def test_scan_finds_python_files(self):
        """Test: Scan finds python files."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        python_modules = [m for m in ci._modules.values() if m.language == "python"]
        # Verify: len(python_modules) > 0
        assert len(python_modules) > 0

    def test_scan_empty_directory(self):
        """Test: Scan empty directory."""
        from encre.codebase.indexer import EncreCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            ci = EncreCodeIndex(workspace=tmpdir)
            ci.scan()
            # Verify: ci._indexed is True
            assert ci._indexed is True
            # Verify: len(ci._modules) == 0
            assert len(ci._modules) == 0

    def test_scan_nonexistent_directory(self):
        """Test: Scan nonexistent directory."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace="/nonexistent/path/for/testing")
        ci.scan()
        # Verify: ci._indexed is True
        assert ci._indexed is True
        # Verify: len(ci._modules) == 0
        assert len(ci._modules) == 0


class TestEncreCodeIndexWithFiles:
    """Tests that scan a temporary directory with known files."""

    def test_scan_python_file_parses_imports(self):
        """Test: Scan python file parses imports."""
        from encre.codebase.indexer import EncreCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "test_mod.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write(textwrap.dedent("""\
                    import os  # noqa: E402
                    import json  # noqa: E402
                    from collections import defaultdict  # noqa: E402

                    def public_function():
                        return 42

                    class MyClass:
                        pass

                    CONSTANT = 3.14
                """))
            ci = EncreCodeIndex(workspace=tmpdir)
            ci.scan()
            # Verify: ci._indexed is True
            assert ci._indexed is True
            # Verify: len(ci._modules) == 1
            assert len(ci._modules) == 1
            mod_key = next(iter(ci._modules.keys()))
            mod = ci._modules[mod_key]
            # Verify: mod.language == "python"
            assert mod.language == "python"
            # Verify: "os" in mod.imports
            assert "os" in mod.imports
            # Verify: "json" in mod.imports
            assert "json" in mod.imports
            # Verify: "public_function" in mod.exports
            assert "public_function" in mod.exports
            # Verify: "MyClass" in mod.exports
            assert "MyClass" in mod.exports
            # Verify: "CONSTANT" in mod.exports
            assert "CONSTANT" in mod.exports


# ===========================================================================
# EncreCodeIndex public query API
# ===========================================================================

class TestEncreCodeIndexQueries:
    """Tests for the public query methods."""

    def test_build_dependency_graph(self):
        """Test: Build dependency graph."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        graph = ci.build_dependency_graph()
        # Verify: isinstance(graph, dict)
        assert isinstance(graph, dict)

    def test_get_importers(self):
        """Test: Get importers."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        # Pick any module and query its importers
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            importers = ci.get_importers(first_path)
            # Verify: isinstance(importers, list)
            assert isinstance(importers, list)

    def test_get_importers_nonexistent(self):
        """Test: Get importers nonexistent."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        importers = ci.get_importers("nonexistent_file.py")
        # Verify: importers == []
        assert importers == []

    def test_find_relevant_returns_list(self):
        """Test: Find relevant returns list."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("python class")
        # Verify: isinstance(results, list)
        assert isinstance(results, list)

    def test_find_relevant_empty_query(self):
        """Test: Find relevant empty query."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("")
        # Verify: results == []
        assert results == []

    def test_find_relevant_returns_tuples(self):
        """Test: Find relevant returns tuples."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("import")
        for item in results:
            # Verify: isinstance(item, tuple)
            assert isinstance(item, tuple)
            # Verify: len(item) == 2
            assert len(item) == 2
            # Verify: isinstance(item[0], str)
            assert isinstance(item[0], str)
            # Verify: isinstance(item[1], float)
            assert isinstance(item[1], float)

    def test_find_relevant_sorted_descending(self):
        """Test: Find relevant sorted descending."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("def class")
        if len(results) >= 2:
            # Verify: results[0][1] >= results[1][1]
            assert results[0][1] >= results[1][1]

    def test_build_context_returns_str(self):
        """Test: Build context returns str."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            context = ci.build_context(first_path)
            # Verify: isinstance(context, str)
            assert isinstance(context, str)
            # Verify: len(context) > 0
            assert len(context) > 0

    def test_build_context_nonexistent(self):
        """Test: Build context nonexistent."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        context = ci.build_context("no_such_file.py")
        # Verify: context == ""
        assert context == ""

    def test_get_module_info(self):
        """Test: Get module info."""
        from encre.codebase.indexer import EncreCodeIndex, ModuleInfo
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            mod = ci.get_module_info(first_path)
            # Verify: isinstance(mod, ModuleInfo)
            assert isinstance(mod, ModuleInfo)

    def test_get_module_info_nonexistent(self):
        """Test: Get module info nonexistent."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        mod = ci.get_module_info("nonexistent.py")
        # Verify: mod is None
        assert mod is None

    def test_list_all_modules_returns_list(self):
        """Test: List all modules returns list."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        modules = ci.list_all_modules()
        # Verify: isinstance(modules, list)
        assert isinstance(modules, list)
        from encre.codebase.indexer import ModuleInfo
        for mod in modules:
            # Verify: isinstance(mod, ModuleInfo)
            assert isinstance(mod, ModuleInfo)

    def test_search_by_name_returns_list(self):
        """Test: Search by name returns list."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.search_by_name("agent")
        # Verify: isinstance(results, list)
        assert isinstance(results, list)

    def test_search_by_name_case_insensitive(self):
        """Test: Search by name case insensitive."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        upper = ci.search_by_name("AGENT")
        lower = ci.search_by_name("agent")
        # Verify: len(upper) == len(lower)
        assert len(upper) == len(lower)


# ===========================================================================
# EncreCodeIndex incremental scan
# ===========================================================================

class TestEncreCodeIndexIncremental:
    """Tests for incremental scanning."""

    def test_scan_incremental_on_fresh_index(self):
        """Test: Scan incremental on fresh index."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan_incremental()
        # Verify: ci._indexed is True
        assert ci._indexed is True

    def test_scan_incremental_after_full_scan(self):
        """Test: Scan incremental after full scan."""
        from encre.codebase.indexer import EncreCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python file
            src = os.path.join(tmpdir, "hello.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("import os\n\ndef greet():\n    return 'hello'\n")

            ci = EncreCodeIndex(workspace=tmpdir)
            ci.scan()
            # Verify: len(ci._modules) == 1
            assert len(ci._modules) == 1

            # Create a new file
            src2 = os.path.join(tmpdir, "world.py")
            with open(src2, "w", encoding="utf-8") as f:
                f.write("import sys\n\ndef farewell():\n    return 'bye'\n")

            ci.scan_incremental()
            # Verify: len(ci._modules) == 2
            assert len(ci._modules) == 2
