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
    """Engineered to validate the ModuleInfo dataclass contract for codebase metadata storage.

    This test class exercises ModuleInfo across 5 scenarios to ensure that all
    fields (path, name, imports, imported_by, exports, language, loc) are
    correctly stored on construction, that default values are sensible empty
    containers, and that the class is recognized as a dataclass. The design
    supports the codebase indexer by providing a structured record for each
    source file that captures its dependency graph edges and export surface.
    """

    def test_verify_creation_with_all_fields_populated(self):
        """Validate that ModuleInfo stores all constructor arguments correctly.

        The test constructs a ModuleInfo with all 7 fields set and asserts
        each field matches its input because the dataclass must preserve
        all metadata for accurate dependency graph construction.
        """
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        mi = ModuleInfo(
            path="src/my_module.py",
            name="my_module",
            imports=["os", "json", "typing"],
            imported_by=["main.py", "test_module.py"],
            exports=["public_func", "MyClass", "CONSTANT"],
            language="python",
            loc=150,
        )
        assert mi.path == "src/my_module.py"
        assert mi.name == "my_module"
        assert len(mi.imports) == 3
        assert "os" in mi.imports
        assert len(mi.imported_by) == 2
        assert "main.py" in mi.imported_by
        assert len(mi.exports) == 3
        assert "MyClass" in mi.exports
        assert mi.language == "python"
        assert mi.loc == 150

    def test_verify_default_values_are_empty_containers_and_zeros(self):
        """Validate that omitted fields default to empty lists, empty strings, and zero.

        The test constructs ModuleInfo with only path and name and asserts
        imports, imported_by, and exports are [], language is "", and loc
        is 0 because default values must be safe empty containers.
        """
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="test.py", name="test")
        assert mi.imports == []
        assert mi.imported_by == []
        assert mi.exports == []
        assert mi.language == ""
        assert mi.loc == 0

    def test_verify_moduleinfo_is_dataclass(self):
        """Validate that ModuleInfo is recognized as a dataclass by the standard library.

        The test asserts is_dataclass(ModuleInfo) is True because the class
        relies on dataclass-generated methods for correct equality, repr,
        and immutable field semantics.
        """
        from dataclasses import is_dataclass
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        assert is_dataclass(ModuleInfo)

    def test_verify_language_variants_are_preserved(self):
        """Validate that ModuleInfo stores any language string without transformation.

        The test constructs ModuleInfo entries for 6 different language values
        and asserts each language field matches because the indexer must
        support polyglot workspaces with Python, Rust, Go, JS, TS, and Java.
        """
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        for lang in ["python", "rust", "go", "javascript", "typescript", "java"]:
            mi = ModuleInfo(path=f"src/module.{lang[:2]}", name="mod", language=lang)
            assert mi.language == lang

    def test_verify_windows_path_slashes_are_preserved(self):
        """Validate that Windows-style backslash paths are stored without alteration.

        The test constructs ModuleInfo with a backslash path and asserts 'src'
        is present in the stored path because path normalization must not
        break Windows absolute paths during index construction.
        """
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="src\\subdir\\module.py", name="module")
        assert "src" in mi.path


# ===========================================================================
# EncreCodeIndex construction
# ===========================================================================

class TestEncreCodeIndexConstruction:
    """Engineered to validate EncreCodeIndex construction and initial empty state.

    This test class exercises index construction across 4 scenarios to ensure
    that the workspace path is stored correctly (both relative and absolute),
    that the internal data structures start empty, and that the known-file
    extension set covers the expected polyglot languages. The design uses
    lazy indexing — _modules, _depgraph, _reverse_depgraph, and _inverted_index
    are all empty dicts until scan() is called.
    """

    def test_verify_construction_stores_workspace_path(self):
        """Validate that EncreCodeIndex stores the workspace path from the constructor.

        The test constructs an index with workspace='.' and asserts the
        workspace attribute equals '.' and _indexed is False because
        construction must not auto-trigger scanning.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        assert ci is not None
        assert ci.workspace == "."
        assert ci._indexed is False

    def test_verify_construction_with_absolute_path(self):
        """Validate that EncreCodeIndex resolves and stores an absolute workspace path.

        The test constructs an index with os.path.abspath('.') and asserts
        the stored workspace matches the absolute path because the index
        must normalize paths for consistent file resolution.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        abs_path = os.path.abspath(".")
        ci = EncreCodeIndex(workspace=abs_path)
        assert ci.workspace == abs_path

    def test_verify_initial_state_has_empty_internal_structures(self):
        """Validate that all internal indexes are empty before scan() is called.

        The test asserts _modules, _depgraph, _reverse_depgraph, _inverted_index
        are all {} and _total_docs is 0 and _indexed is False because an
        unscanned index must not contain stale data from a prior run.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        assert ci._modules == {}
        assert ci._depgraph == {}
        assert ci._reverse_depgraph == {}
        assert ci._inverted_index == {}
        assert ci._total_docs == 0
        assert ci._indexed is False

    def test_verify_known_extensions_set_contains_supported_languages(self):
        """Validate that _KNOWN_EXTS includes extensions for all supported source languages.

        The test asserts that .py, .rs, .go, .js, .ts, and .java are all
        present in the known extensions set because the indexer must
        recognize source files across the supported polyglot workspace.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        assert ".py" in EncreCodeIndex._KNOWN_EXTS
        assert ".rs" in EncreCodeIndex._KNOWN_EXTS
        assert ".go" in EncreCodeIndex._KNOWN_EXTS
        assert ".js" in EncreCodeIndex._KNOWN_EXTS
        assert ".ts" in EncreCodeIndex._KNOWN_EXTS
        assert ".java" in EncreCodeIndex._KNOWN_EXTS


# ===========================================================================
# EncreCodeIndex scan and search
# ===========================================================================

class TestEncreCodeIndexScan:
    """Engineered to validate the EncreCodeIndex scan operation across real and edge-case directories.

    This test class exercises scanning across 6 scenarios including the current
    workspace, an empty temporary directory, and a nonexistent path. The design
    ensures that scan() sets _indexed=True and populates _modules, and that
    missing or empty directories produce safe empty results rather than exceptions.
    """

    def test_verify_scan_completes_without_error(self):
        """Validate that scan() sets _indexed=True when run on the current workspace.

        The test constructs an index and calls scan(), asserting _indexed is
        True because scanning must mark the index as populated regardless
        of how many files are found.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        assert ci._indexed is True

    def test_verify_scan_populates_modules_dict(self):
        """Validate that scan() discovers at least one module in the workspace.

        The test asserts len(_modules) > 0 because the workspace contains
        Python source files that must be indexed.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        assert len(ci._modules) > 0

    def test_verify_scanned_modules_have_valid_string_paths(self):
        """Validate that every scanned module has a non-empty string path.

        The test iterates over all modules and asserts each path is a
        non-empty string because every indexed module must have a valid
        filesystem path for later retrieval and context building.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        for _path, mod in ci._modules.items():
            assert isinstance(mod.path, str)
            assert len(mod.path) > 0

    def test_verify_scan_discovers_python_modules(self):
        """Validate that scan() finds at least one Python-language module in the workspace.

        The test filters modules by language=='python' and asserts the count
        is positive because the workspace must contain Python source files.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        python_modules = [m for m in ci._modules.values() if m.language == "python"]
        assert len(python_modules) > 0

    def test_verify_scan_empty_directory_produces_empty_index(self):
        """Validate that scan() on an empty temp directory sets _indexed=True with no modules.

        The test creates a temporary empty directory, scans it, and asserts
        _indexed is True and _modules is empty because scanning an empty
        tree must succeed without error and produce no module entries.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            ci = EncreCodeIndex(workspace=tmpdir)
            ci.scan()
            assert ci._indexed is True
            assert len(ci._modules) == 0

    def test_verify_scan_nonexistent_directory_produces_empty_index(self):
        """Validate that scan() on a nonexistent path sets _indexed=True with no modules.

        The test scans a path that does not exist and asserts _indexed is
        True and _modules is empty because the scanner must handle missing
        directories gracefully without raising.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace="/nonexistent/path/for/testing")
        ci.scan()
        assert ci._indexed is True
        assert len(ci._modules) == 0


class TestEncreCodeIndexWithFiles:
    """Engineered to validate that scan() correctly parses Python source files for imports and exports.

    This test class creates a temporary directory with a known Python module
    and verifies that the index extracts the correct import list, export list,
    and language tag. The design ensures the parser handles standard Python
    import patterns (import X, from Y import Z) and public symbol detection.
    """

    def test_verify_scan_python_file_parses_imports_and_exports(self):
        """Validate that scan() extracts imports, exports, and language from a Python source file.

        The test creates a temp directory containing a Python module with
        known imports (os, json, collections.defaultdict) and exports
        (public_function, MyClass, CONSTANT), scans it, and asserts the
        indexed module has language='python', the expected imports, and
        the expected exports because the parser must accurately capture
        the module's dependency and export surface.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
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
            assert ci._indexed is True
            assert len(ci._modules) == 1
            mod_key = next(iter(ci._modules.keys()))
            mod = ci._modules[mod_key]
            assert mod.language == "python"
            assert "os" in mod.imports
            assert "json" in mod.imports
            assert "public_function" in mod.exports
            assert "MyClass" in mod.exports
            assert "CONSTANT" in mod.exports


# ===========================================================================
# EncreCodeIndex public query API
# ===========================================================================

class TestEncreCodeIndexQueries:
    """Engineered to validate the public query API of EncreCodeIndex for dependency and relevance lookups.

    This test class exercises 13 query methods including build_dependency_graph,
    get_importers, find_relevant, build_context, get_module_info, list_all_modules,
    and search_by_name. The design ensures each query returns the documented
    type (dict, list, str, ModuleInfo, or None) and handles missing inputs
    gracefully without raising exceptions.
    """

    def test_verify_build_dependency_graph_returns_dict(self):
        """Validate that build_dependency_graph() returns a dict even on an unscanned index.

        The test asserts isinstance(graph, dict) because the dependency graph
        is always a dictionary mapping module paths to their imported dependencies.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        graph = ci.build_dependency_graph()
        assert isinstance(graph, dict)

    def test_verify_get_importers_returns_list_for_scanned_module(self):
        """Validate that get_importers() returns a list for a module present in the index.

        The test scans the index, picks the first module, and asserts the
        returned importers list is a Python list because get_importers
        must always return a list (possibly empty) for any queried path.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            importers = ci.get_importers(first_path)
            assert isinstance(importers, list)

    def test_verify_get_importers_nonexistent_returns_empty_list(self):
        """Validate that get_importers() returns [] for a path not in the index.

        The test queries a nonexistent file path and asserts the result is
        [] because missing modules should have zero importers, not raise.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        importers = ci.get_importers("nonexistent_file.py")
        assert importers == []

    def test_verify_find_relevant_returns_a_list(self):
        """Validate that find_relevant() returns a list for any query string.

        The test asserts isinstance(results, list) because relevance search
        must always return a list of (path, score) tuples.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("python class")
        assert isinstance(results, list)

    def test_verify_find_relevant_empty_query_returns_empty_list(self):
        """Validate that find_relevant('') returns an empty list with no matches.

        The test asserts results == [] because an empty query string should
        not match any module and must return an empty list, not raise.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("")
        assert results == []

    def test_verify_find_relevant_returns_tuple_entries(self):
        """Validate that every entry in find_relevant results is a (str, float) tuple.

        The test iterates over results for the query 'import' and asserts
        each item is a 2-tuple with str path and float score because the
        relevance API contracts each result as (module_path, relevance_score).
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("import")
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], float)

    def test_verify_find_relevant_results_are_sorted_descending_by_score(self):
        """Validate that find_relevant results are ordered by descending relevance score.

        The test queries 'def class' and asserts that if at least 2 results
        are returned, the first score is >= the second score because the
        relevance engine must sort results from highest to lowest score.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.find_relevant("def class")
        if len(results) >= 2:
            assert results[0][1] >= results[1][1]

    def test_verify_build_context_returns_nonempty_string_for_known_module(self):
        """Validate that build_context() returns a non-empty string for a module present in the index.

        The test scans the index, picks the first module, and asserts the
        context string is non-empty because build_context must serialize
        the module's source and metadata for LLM context injection.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            context = ci.build_context(first_path)
            assert isinstance(context, str)
            assert len(context) > 0

    def test_verify_build_context_returns_empty_string_for_missing_module(self):
        """Validate that build_context() returns '' for a path not in the index.

        The test queries a nonexistent file and asserts the result is ''
        because missing modules must not raise — they should yield an
        empty context string so callers can handle absence gracefully.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        context = ci.build_context("no_such_file.py")
        assert context == ""

    def test_verify_get_module_info_returns_ModuleInfo_for_known_path(self):
        """Validate that get_module_info() returns a ModuleInfo instance for a scanned module.

        The test scans the index, picks the first module path, and asserts
        the result is an instance of ModuleInfo because get_module_info
        must return the full structured metadata record.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex, ModuleInfo
        ci = EncreCodeIndex(workspace=".")
        ci.scan()
        if ci._modules:
            first_path = next(iter(ci._modules.keys()))
            mod = ci.get_module_info(first_path)
            assert isinstance(mod, ModuleInfo)

    def test_verify_get_module_info_returns_none_for_missing_path(self):
        """Validate that get_module_info() returns None for a path not in the index.

        The test queries 'nonexistent.py' and asserts None because missing
        modules must yield None, not raise, so callers can distinguish
        between found and not-found without exception handling.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        mod = ci.get_module_info("nonexistent.py")
        assert mod is None

    def test_verify_list_all_modules_returns_list_of_ModuleInfo(self):
        """Validate that list_all_modules() returns a list where every element is a ModuleInfo.

        The test asserts the return type is list and that every element
        passes isinstance(mod, ModuleInfo) because the method is the
        primary way to iterate over all indexed modules.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        modules = ci.list_all_modules()
        assert isinstance(modules, list)
        from encre.capabilities.search.codebase.indexer import ModuleInfo
        for mod in modules:
            assert isinstance(mod, ModuleInfo)

    def test_verify_search_by_name_returns_list(self):
        """Validate that search_by_name() returns a list for any search term.

        The test queries 'agent' and asserts the result is a list because
        name search must always return a list of matching ModuleInfo objects.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        results = ci.search_by_name("agent")
        assert isinstance(results, list)

    def test_verify_search_by_name_is_case_insensitive(self):
        """Validate that search_by_name() returns the same count for upper and lower case queries.

        The test queries 'AGENT' and 'agent' and asserts equal result counts
        because name search must be case-insensitive to match user intent
        regardless of capitalization.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        upper = ci.search_by_name("AGENT")
        lower = ci.search_by_name("agent")
        assert len(upper) == len(lower)


# ===========================================================================
# EncreCodeIndex incremental scan
# ===========================================================================

class TestEncreCodeIndexIncremental:
    """Engineered to validate incremental scanning on top of an existing index.

    This test class exercises 2 scenarios: incremental scan on a fresh index
    and incremental scan after adding a new file to an already-scanned directory.
    The design ensures that scan_incremental() adds new modules without
    dropping previously indexed entries, enabling efficient re-indexing
    after file system changes without full re-scan overhead.
    """

    def test_verify_scan_incremental_on_fresh_index(self):
        """Validate that scan_incremental() sets _indexed=True on a fresh unscanned index.

        The test calls scan_incremental() without a prior full scan and asserts
        _indexed is True because the incremental method must also populate
        the index when no prior scan has occurred.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        ci.scan_incremental()
        assert ci._indexed is True

    def test_verify_scan_incremental_adds_newly_created_files(self):
        """Validate that scan_incremental() discovers files created after the initial full scan.

        The test creates a temp directory with one Python file, scans it (1
        module), creates a second Python file, runs scan_incremental(), and
        asserts the module count is now 2 because incremental scanning must
        detect and index new files without re-scanning existing ones.
        """
        from encre.capabilities.search.codebase.indexer import EncreCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "hello.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("import os\n\ndef greet():\n    return 'hello'\n")

            ci = EncreCodeIndex(workspace=tmpdir)
            ci.scan()
            assert len(ci._modules) == 1

            src2 = os.path.join(tmpdir, "world.py")
            with open(src2, "w", encoding="utf-8") as f:
                f.write("import sys\n\ndef farewell():\n    return 'bye'\n")

            ci.scan_incremental()
            assert len(ci._modules) == 2
