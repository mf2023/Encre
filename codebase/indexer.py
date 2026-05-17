#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

"""
Multi-language code indexer with BM25 search and dependency analysis.

This module implements :class:`YmiCodeIndex`, a workspace-level code
indexing engine that supports:

- **Full scan**: Walks the entire workspace, parsing every recognised source
  file into a :class:`ModuleInfo` record with imports, exports, and language.
- **Incremental scan**: Re-parses only files whose modification timestamps
  have changed since the last scan, preserving the existing index for
  unchanged files and removing deleted files.
- **Live file watcher**: Integrates with the ``watchfiles`` library to
  detect filesystem changes in real time and trigger incremental re-indexing.
- **Multi-language parsing**: Uses language-appropriate techniques for each
  supported language:
  - Python: ``ast`` module for structural import/export extraction
  - JavaScript/TypeScript: regex-based import and export matching
  - Rust: regex-based ``use`` statement and ``pub fn/struct/enum/trait`` extraction
  - Go: regex-based import block and exported function/type extraction
  - Others: generic fallback for include/import/require patterns
- **Dependency graph**: Resolves import statements to module paths, building
  both forward and reverse dependency graphs for impact analysis.
- **BM25 full-text search**: Okapi BM25 ranking with code-specific tokenisation
  and a +2.0 name-match bonus for module paths matching query tokens.
- **Context builder**: Generates a formatted string containing source code,
  imports, dependents, and exports for a given file — useful for LLM context.

Supported file extensions:
    Python (``.py``, ``.pyi``, ``.pyx``),
    JavaScript/TypeScript (``.js``, ``.jsx``, ``.ts``, ``.tsx``, ``.mjs``, ``.cjs``),
    Rust (``.rs``),
    Go (``.go``),
    Others (``.java``, ``.rb``, ``.php``, ``.c``, ``.cpp``, ``.h``, ``.hpp``,
    ``.cc``, ``.cxx``, ``.swift``, ``.kt``, ``.scala``).

Design notes:
    The index is entirely in-memory and rebuilt on each ``scan()`` call.
    For large workspaces (>10,000 files), consider using the incremental
    scan mode or the file watcher to avoid repeated full re-indexing.
"""

import ast
import asyncio
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ModuleInfo:
    """Metadata for a single source code module in the index.

    Stores everything extracted during parsing: the file path relative to
    the workspace root, the module name, lists of imports and exports,
    the programming language, and line count.  The ``imported_by`` field is
    populated during the dependency graph build phase.

    Attributes:
        path: File path relative to the workspace root (Unix-style separators).
        name: Module name (typically the relative path or file stem).
        imports: List of module names or paths that this module imports.
        imported_by: List of module paths that import this module (populated
            during :meth:`YmiCodeIndex._build_dependencies`).
        exports: List of public symbols exported by this module (functions,
            classes, constants, types, etc.).
        language: Programming language identifier (e.g., ``"python"``,
            ``"rust"``, ``"typescript"``).
        loc: Lines of code (total line count in the source file).
    """

    path: str
    name: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    language: str = ""
    loc: int = 0


class YmiCodeIndex:
    """In-memory searchable index of source code files in a workspace.

    The index builds a structured representation of every source file in
    the workspace, enabling fast full-text search (BM25), dependency
    queries, and context extraction for downstream use (e.g., LLM prompts).

    The class maintains:
    - A dictionary of :class:`ModuleInfo` records keyed by relative path.
    - Forward and reverse dependency graphs for import chain analysis.
    - A BM25-weighted inverted index for relevance-ranked code search.
    - File modification timestamps for incremental re-indexing.
    - An optional ``asyncio.Task`` for live file watching via ``watchfiles``.

    Args:
        workspace: Absolute or relative path to the workspace root directory
            to index.
    """

    # ── Language extension sets ──────────────────────────────────────

    _PY_EXTS: set[str] = {".py", ".pyi", ".pyx"}
    """Python file extensions parsed via the ``ast`` module."""

    _JS_EXTS: set[str] = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    """JavaScript/TypeScript file extensions parsed via regex."""

    _RS_EXTS: set[str] = {".rs"}
    """Rust file extensions parsed via regex."""

    _GO_EXTS: set[str] = {".go"}
    """Go file extensions parsed via regex."""

    _KNOWN_EXTS: set[str] = {
        ".py", ".pyi", ".pyx",
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".rs", ".go",
        ".java", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cc", ".cxx",
        ".swift", ".kt", ".scala",
    }
    """Complete set of recognised source file extensions for indexing."""

    def __init__(self, workspace: str) -> None:
        """Initialise a new code index for the given workspace.

        Args:
            workspace: Path to the workspace root directory.  The index
                will recursively discover and parse all source files under
                this directory.
        """
        self.workspace: str = workspace
        self._modules: dict[str, ModuleInfo] = {}
        self._depgraph: dict[str, set[str]] = {}
        self._reverse_depgraph: dict[str, set[str]] = {}
        self._inverted_index: dict[str, dict[str, float]] = {}
        self._doc_freq: dict[str, int] = {}
        self._total_docs: int = 0
        self._indexed: bool = False
        self._file_mtimes: dict[str, float] = {}
        self._watcher_task: Optional[asyncio.Task] = None

    # ── Scanning ─────────────────────────────────────────────────────

    def scan(self) -> None:
        """Perform a full scan of the workspace, rebuilding the entire index.

        Walks the entire workspace directory tree, skipping common build
        artifact and cache directories (``node_modules``, ``__pycache__``,
        ``target``, ``build``, ``.git``, etc.) and dot-directories.  Each
        recognised source file is parsed into a :class:`ModuleInfo` record,
        then dependency graphs and the BM25 inverted index are rebuilt.

        This is a blocking, CPU-bound operation.  For large workspaces,
        consider calling this in a thread pool executor.
        """
        ws = Path(self.workspace).resolve()
        if not ws.exists():
            self._indexed = True
            return
        self._modules.clear()
        self._depgraph.clear()
        self._reverse_depgraph.clear()
        self._file_mtimes.clear()
        for root, dirs, files in os.walk(str(ws)):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", "target", "build", "dist",
                ".git", "venv", ".venv", "env", ".tox", ".eggs",
                ".mypy_cache", ".pytest_cache", ".ruff_cache",
            )]
            for fname in files:
                fpath = Path(root) / fname
                suffix = fpath.suffix.lower()
                if suffix not in self._KNOWN_EXTS:
                    continue
                rel = str(fpath.relative_to(ws)).replace("\\", "/")
                try:
                    mtime = fpath.stat().st_mtime
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                self._file_mtimes[rel] = mtime
                mod = self._parse_file(rel, content, suffix)
                self._modules[rel] = mod
        self._build_dependencies()
        self._build_inverted_index()
        self._indexed = True

    def scan_incremental(self) -> None:
        """Incrementally update the index: re-parse changed/new files, remove deleted files.

        Compares the current filesystem state against the cached modification
        timestamps (``_file_mtimes``).  Only files whose mtime has increased
        (or are newly encountered) are re-parsed.  Files that no longer exist
        on disk are removed from the index, including cleanup of their
        dependency graph entries and ``imported_by`` references.

        If the index has never been built (``_indexed`` is False), falls back
        to a full :meth:`scan`.  Dependency graphs and the inverted index are
        only rebuilt if changes were actually detected.
        """
        ws = Path(self.workspace).resolve()
        if not ws.exists():
            self._indexed = True
            return
        if not self._indexed:
            self.scan()
            return

        current_files: set[str] = set()
        changed_files: set[str] = set()

        for root, dirs, files in os.walk(str(ws)):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", "target", "build", "dist",
                ".git", "venv", ".venv", "env", ".tox", ".eggs",
                ".mypy_cache", ".pytest_cache", ".ruff_cache",
            )]
            for fname in files:
                fpath = Path(root) / fname
                suffix = fpath.suffix.lower()
                if suffix not in self._KNOWN_EXTS:
                    continue
                rel = str(fpath.relative_to(ws)).replace("\\", "/")
                current_files.add(rel)
                try:
                    mtime = fpath.stat().st_mtime
                except Exception:
                    continue
                if rel not in self._file_mtimes or self._file_mtimes[rel] < mtime:
                    changed_files.add(rel)
                    self._file_mtimes[rel] = mtime
                else:
                    self._file_mtimes[rel] = mtime

        # Remove deleted files from the index, including dependency references.
        deleted_files = set(self._modules.keys()) - current_files
        for rel in deleted_files:
            self._modules.pop(rel, None)
            self._inverted_index.pop(rel, None)
            self._file_mtimes.pop(rel, None)
            self._depgraph.pop(rel, None)
            self._reverse_depgraph.pop(rel, None)
            for mod in self._modules.values():
                if rel in mod.imported_by:
                    mod.imported_by.remove(rel)

        # Re-parse changed and new files.
        for rel in changed_files:
            fpath = ws / rel
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            self._inverted_index.pop(rel, None)
            mod = self._parse_file(rel, content, suffix=fpath.suffix.lower())
            self._modules[rel] = mod

        # Rebuild only if there were actual changes.
        if changed_files or deleted_files:
            self._build_dependencies()
            self._build_inverted_index()

    # ── File watcher ─────────────────────────────────────────────────

    async def watch(self) -> Optional[asyncio.Task]:
        """Start watching the workspace for file changes using ``watchfiles``.

        Launches an ``asyncio.Task`` that monitors the workspace directory
        for filesystem events.  On each batch of changes, it filters out
        non-code files and changes under ignored directories, then calls
        :meth:`scan_incremental` to update the index.

        Returns:
            The ``asyncio.Task`` handle for cancellation, or ``None`` if
            ``watchfiles`` is not installed.
        """
        try:
            import watchfiles
        except ImportError:
            return None

        if self._watcher_task is not None and not self._watcher_task.done():
            return self._watcher_task

        ws = Path(self.workspace).resolve()
        if not ws.exists():
            return None

        _WATCH_IGNORE_DIRS = (
            ".git", "node_modules", "__pycache__", "target", "build", "dist",
            "venv", ".venv", "env", ".tox", ".eggs", ".mypy_cache",
            ".pytest_cache", ".ruff_cache",
        )

        async def _watcher_loop() -> None:
            try:
                async for changes in watchfiles.awatch(str(ws)):
                    relevant_changes = False
                    for change_type, changed_path in changes:
                        rel_path = str(Path(changed_path).relative_to(ws))
                        parts = rel_path.replace("\\", "/").split("/")
                        if any(p in _WATCH_IGNORE_DIRS for p in parts):
                            continue
                        if Path(changed_path).suffix.lower() in self._KNOWN_EXTS:
                            relevant_changes = True
                            break
                    if relevant_changes:
                        self.scan_incremental()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        self._watcher_task = asyncio.create_task(_watcher_loop())
        return self._watcher_task

    def stop_watch(self) -> None:
        """Stop the file watcher task if one is running.

        Cancels the running ``asyncio.Task`` and sets the watcher reference
        to ``None``.  Safe to call even if no watcher is active.
        """
        if self._watcher_task is not None and not self._watcher_task.done():
            self._watcher_task.cancel()
            self._watcher_task = None

    # ── File parsing ─────────────────────────────────────────────────

    def _parse_file(self, rel_path: str, content: str, suffix: str) -> ModuleInfo:
        """Route file parsing to the appropriate language-specific parser.

        Dispatches based on file extension to one of the specialised parsers:
        :meth:`_parse_python`, :meth:`_parse_javascript`, :meth:`_parse_rust`,
        :meth:`_parse_go`, or :meth:`_parse_generic`.

        Args:
            rel_path: File path relative to the workspace root.
            content: UTF-8 decoded file contents.
            suffix: Lowercased file extension (e.g., ``".py"``, ``".rs"``).

        Returns:
            A :class:`ModuleInfo` instance with parsed metadata.
        """
        if suffix in self._PY_EXTS:
            return self._parse_python(rel_path, content)
        elif suffix in self._JS_EXTS:
            return self._parse_javascript(rel_path, content, suffix)
        elif suffix in self._RS_EXTS:
            return self._parse_rust(rel_path, content)
        elif suffix in self._GO_EXTS:
            return self._parse_go(rel_path, content)
        else:
            return self._parse_generic(rel_path, content, suffix)

    def _parse_python(self, rel_path: str, content: str) -> ModuleInfo:
        """Parse a Python source file using the ``ast`` module.

        Extracts:
        - Imports: ``import X`` and ``from X import Y`` statements
        - Exports: top-level functions, async functions, classes (non-underscore),
          and module-level uppercase constants (``UPPER_CASE = ...``)

        Args:
            rel_path: Relative file path.
            content: File content as string.

        Returns:
            A :class:`ModuleInfo` with language set to ``"python"``.
        """
        info = ModuleInfo(path=rel_path, name=rel_path, language="python", loc=len(content.splitlines()))
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return info
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    info.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    info.imports.append(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name and not node.name.startswith("_"):
                    info.exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if node.name and not node.name.startswith("_"):
                    info.exports.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id and not target.id.startswith("_") and target.id.isupper():
                        info.exports.append(target.id)
        return info

    def _parse_javascript(self, rel_path: str, content: str, suffix: str) -> ModuleInfo:
        """Parse a JavaScript/TypeScript source file using regex.

        Extracts:
        - Imports: ``import ... from "module"``, ``import "module"``,
          ``require("module")`` — only for non-relative module names
        - Exports: ``export function/class/const/let/var/interface/type/enum Name``
          and ``export { name1, name2 }`` (handles ``as`` aliases)

        Args:
            rel_path: Relative file path.
            content: File content as string.
            suffix: File extension (``".js"``, ``".ts"``, ``".tsx"``, etc.).

        Returns:
            A :class:`ModuleInfo` with language set to ``"typescript"`` or
            ``"javascript"``.
        """
        lang = "typescript" if suffix in (".ts", ".tsx") else "javascript"
        info = ModuleInfo(path=rel_path, name=rel_path, language=lang, loc=len(content.splitlines()))
        import_re = re.compile(
            r'''(?:import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s*,?\s*)*from\s+['"]([^'"]+)['"])|'''
            r'''(?:import\s+['"]([^'"]+)['"])|'''
            r'''(?:require\s*\(\s*['"]([^'"]+)['"]\s*\))'''
        )
        for m in import_re.finditer(content):
            mod_name = m.group(1) or m.group(2) or m.group(3)
            if mod_name and not mod_name.startswith("."):
                info.imports.append(mod_name)
        export_re = re.compile(
            r'''(?:export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+))|'''
            r'''(?:export\s*\{\s*([^}]*)\s*\})'''
        )
        for m in export_re.finditer(content):
            name = m.group(1)
            if name:
                info.exports.append(name)
            elif m.group(2):
                for part in m.group(2).split(","):
                    part = part.strip()
                    if part:
                        info.exports.append(part.split(" as ")[-1].strip())
        return info

    def _parse_rust(self, rel_path: str, content: str) -> ModuleInfo:
        """Parse a Rust source file using regex.

        Extracts:
        - Imports: ``use crate::module;``, ``use std::collections::HashMap;``
        - Exports: ``pub fn``, ``pub async fn``, ``pub struct``,
          ``pub enum``, ``pub trait``

        Args:
            rel_path: Relative file path.
            content: File content as string.

        Returns:
            A :class:`ModuleInfo` with language set to ``"rust"``.
        """
        info = ModuleInfo(path=rel_path, name=rel_path, language="rust", loc=len(content.splitlines()))
        use_re = re.compile(r'use\s+((?:\w+::)*\w+)\s*;')
        for m in use_re.finditer(content):
            info.imports.append(m.group(1))
        pub_re = re.compile(r'pub\s+(?:async\s+)?fn\s+(\w+)')
        pub_struct_re = re.compile(r'pub\s+struct\s+(\w+)')
        pub_enum_re = re.compile(r'pub\s+enum\s+(\w+)')
        pub_trait_re = re.compile(r'pub\s+trait\s+(\w+)')
        for m in pub_re.finditer(content):
            info.exports.append(m.group(1))
        for m in pub_struct_re.finditer(content):
            info.exports.append(m.group(1))
        for m in pub_enum_re.finditer(content):
            info.exports.append(m.group(1))
        for m in pub_trait_re.finditer(content):
            info.exports.append(m.group(1))
        return info

    def _parse_go(self, rel_path: str, content: str) -> ModuleInfo:
        """Parse a Go source file using regex.

        Extracts:
        - Imports: both multi-line ``import ( "pkg1" "pkg2" )`` blocks and
          single-line ``import "pkg"`` statements
        - Exports: exported functions (uppercase first letter) and
          struct type definitions

        Args:
            rel_path: Relative file path.
            content: File content as string.

        Returns:
            A :class:`ModuleInfo` with language set to ``"go"``.
        """
        info = ModuleInfo(path=rel_path, name=rel_path, language="go", loc=len(content.splitlines()))
        import_block_re = re.compile(r'import\s*\(\s*((?:[^)]*?\"[^\"]+\"[^)]*?)*)\s*\)', re.DOTALL)
        for block in import_block_re.finditer(content):
            for line in block.group(1).split("\n"):
                m = re.search(r'"([^"]+)"', line)
                if m:
                    info.imports.append(m.group(1))
        single_import_re = re.compile(r'import\s+"([^"]+)"')
        for m in single_import_re.finditer(content):
            info.imports.append(m.group(1))
        func_re = re.compile(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)')
        for m in func_re.finditer(content):
            name = m.group(1)
            if name and name[0].isupper():
                info.exports.append(name)
        type_re = re.compile(r'type\s+(\w+)\s+struct')
        for m in type_re.finditer(content):
            info.exports.append(m.group(1))
        return info

    def _parse_generic(self, rel_path: str, content: str, suffix: str) -> ModuleInfo:
        """Parse a source file in an unsupported language using a generic regex fallback.

        Attempts to extract import-like statements using a broad pattern
        matching ``import``, ``from ... import``, ``#include``, and
        ``require()`` constructs.  This provides best-effort import tracking
        for languages without a dedicated parser.

        Args:
            rel_path: Relative file path.
            content: File content as string.
            suffix: File extension used as the language identifier.

        Returns:
            A :class:`ModuleInfo` with language set to the file extension
            (without the dot).
        """
        info = ModuleInfo(path=rel_path, name=rel_path, language=suffix.lstrip("."), loc=len(content.splitlines()))
        import_re = re.compile(
            r'''(?:import\s+[\w.]+)|'''
            r'''(?:from\s+\S+\s+import\s+\S+)|'''
            r'''(?:#include\s+[<\"][^>\"]+[>\"])|'''
            r'''(?:require\s*\(\s*['"][^'"]+['"]\s*\))'''
        )
        for m in import_re.finditer(content):
            info.imports.append(m.group(0).strip())
        return info

    # ── Dependency graph ─────────────────────────────────────────────

    def _build_dependencies(self) -> None:
        """Build forward and reverse dependency graphs from module import data.

        Resolves each module's import list to actual module paths in the
        index by matching the import root package name against known module
        basenames.  Populates:
        - ``_depgraph[mod_path]``: set of module paths that *mod_path* imports
        - ``_reverse_depgraph[mod_path]``: set of module paths that import *mod_path*
        - ``ModuleInfo.imported_by`` on each module: list of importing module paths

        Resolution is heuristic: given an import ``foo.bar.baz``, only the
        root ``foo`` is used for matching — this works for flat project
        structures where module basenames are unique.
        """
        self._depgraph.clear()
        self._reverse_depgraph.clear()
        modules_by_name: dict[str, ModuleInfo] = {}
        for mod in self._modules.values():
            base = os.path.splitext(os.path.basename(mod.path))[0]
            modules_by_name[base] = mod
        for mod in self._modules.values():
            deps: set[str] = set()
            for imp in mod.imports:
                parts = imp.split(".")
                candidate = parts[0]
                if candidate in modules_by_name:
                    resolved = modules_by_name[candidate].path
                    deps.add(resolved)
            self._depgraph[mod.path] = deps
        for mod_path, deps in self._depgraph.items():
            for dep in deps:
                if dep not in self._reverse_depgraph:
                    self._reverse_depgraph[dep] = set()
                self._reverse_depgraph[dep].add(mod_path)
        for mod_path, mod in self._modules.items():
            for dep_path in self._depgraph.get(mod_path, set()):
                dep_mod = self._modules.get(dep_path)
                if dep_mod:
                    dep_mod.imported_by.append(mod_path)

    # ── Inverted index ───────────────────────────────────────────────

    def _build_inverted_index(self) -> None:
        """Build a BM25-weighted inverted index over all indexed source files.

        For each module, the file content is lowercased and tokenised.
        Term frequency (TF) is computed as raw count normalised by the
        maximum TF in that document (to favour informative tokens over
        high-frequency noise).  Document frequency (DF) is tracked for each
        token for the IDF component of BM25 scoring.

        The index maps:
            ``_inverted_index[mod_path][token]`` → normalised TF score
            ``_doc_freq[token]`` → number of documents containing the token
        """
        self._inverted_index.clear()
        self._doc_freq.clear()
        for mod in self._modules.values():
            try:
                full_path = os.path.join(self.workspace, mod.path)
                text = Path(full_path).read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            tokens = self._tokenize(text)
            tf: dict[str, float] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0.0) + 1.0
            max_tf = max(tf.values()) if tf else 1.0
            for token, count in tf.items():
                tf[token] = count / max_tf
            self._inverted_index[mod.path] = tf
            for token in tf:
                self._doc_freq[token] = self._doc_freq.get(token, 0) + 1
        self._total_docs = len(self._modules)

    def _tokenize(self, text: str) -> list[str]:
        """Tokenise source code text into searchable terms.

        Extracts alphanumeric identifiers matching ``[a-zA-Z_]\\w*``, then
        filters out single-character tokens and a curated list of common
        English stop words that are unlikely to be meaningful search terms
        in a code context.

        Args:
            text: Lowercased source code text.

        Returns:
            A list of token strings ready for indexing or querying.
        """
        tokens = re.findall(r'[a-zA-Z_]\w*', text)
        return [t for t in tokens if len(t) > 1 and t not in (
            "the", "this", "that", "with", "from", "have", "been", "were",
            "they", "their", "will", "would", "could", "should", "about",
            "which", "when", "where", "what", "into", "over", "after",
            "before", "between", "under", "above", "there", "here",
            "also", "than", "then", "just", "only", "very", "much",
            "such", "each", "every", "both", "some", "these", "those",
            "because", "while", "during", "through", "other", "being",
        )]

    # ── Public query API ─────────────────────────────────────────────

    def build_dependency_graph(self) -> dict[str, set[str]]:
        """Return the forward dependency graph.

        Each entry maps a module path to the set of module paths it imports.
        Triggers a full scan if the index has not been built yet.

        Returns:
            A dictionary of ``{module_path: {dependency_path, ...}}``.
        """
        if not self._indexed:
            self.scan()
        return dict(self._depgraph)

    def get_importers(self, file_path: str) -> list[str]:
        """Return all modules that import the given file.

        Uses the reverse dependency graph to find dependents.  Triggers a
        full scan if the index has not been built yet.

        Args:
            file_path: Relative file path to query (workspace-relative).

        Returns:
            A list of module paths that import the given file.
        """
        if not self._indexed:
            self.scan()
        return list(self._reverse_depgraph.get(file_path, set()))

    def find_relevant(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """Search the codebase using BM25 ranking and return top results.

        Okapi BM25 is a bag-of-words ranking function that scores documents
        by the frequency of query terms in each document, adjusted for
        document length and term rarity across the corpus.  A +2.0 bonus is
        applied when a query token appears in the module's path, boosting
        files whose name directly matches the search term.

        BM25 parameters (saturated term frequency with full IDF):
            - k1 = 1.5 (term frequency saturation)
            - b = 0.75 (length normalisation strength)

        Args:
            query: Free-text search query (e.g., ``"database connection pool"``).
            limit: Maximum number of results to return.  Defaults to 10.

        Returns:
            A list of ``(module_path, score)`` tuples sorted by descending
            relevance score.  Empty list if the query produces no tokens.
        """
        if not self._indexed:
            self.scan()
        query_tokens = self._tokenize(query.lower())
        if not query_tokens:
            return []
        scores: dict[str, float] = {}
        k1: float = 1.5
        b: float = 0.75
        avgdl: float = sum(len(self._inverted_index.get(p, {})) for p in self._modules) / max(self._total_docs, 1)
        for mod_path, tf in self._inverted_index.items():
            score: float = 0.0
            dl = len(tf)
            for token in query_tokens:
                if token not in tf:
                    continue
                df = self._doc_freq.get(token, 1)
                idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1.0)
                tf_val = tf[token]
                numerator = tf_val * (k1 + 1.0)
                denominator = tf_val + k1 * (1.0 - b + b * dl / max(avgdl, 1.0))
                score += idf * numerator / max(denominator, 0.001)
            mod_name_lower = mod_path.lower()
            for qt in query_tokens:
                if qt in mod_name_lower:
                    score += 2.0
            if score > 0:
                scores[mod_path] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    def build_context(self, file_path: str) -> str:
        """Build a formatted context string for a given file.

        The context includes the file header (path, language, LOC), the
        full source code, and up to 30 entries each of imports, importers,
        and exports.  This is designed to produce a compact prompt context
        for LLM consumption.

        Args:
            file_path: Relative file path to build context for.

        Returns:
            A formatted string ready for inclusion in LLM prompts, or an
            empty string if the file is not in the index.
        """
        if not self._indexed:
            self.scan()
        mod = self._modules.get(file_path)
        if mod is None:
            return ""
        parts: list[str] = []
        parts.append(f"[{file_path}] ({mod.language}, {mod.loc} loc)")
        try:
            full_path = os.path.join(self.workspace, file_path)
            parts.append(Path(full_path).read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
        if mod.imports:
            parts.append("Imports: " + ", ".join(mod.imports[:30]))
        if mod.imported_by:
            parts.append("Imported by: " + ", ".join(mod.imported_by[:30]))
        if mod.exports:
            parts.append("Exports: " + ", ".join(mod.exports[:30]))
        return "\n\n".join(parts)

    def get_module_info(self, file_path: str) -> ModuleInfo | None:
        """Retrieve the :class:`ModuleInfo` for a given file path.

        Triggers a full scan if the index has not been built yet.

        Args:
            file_path:<think> Relative file path to look up.

        Returns:
            The :class:`ModuleInfo` record, or ``None`` if the file is not
            in the index.
        """
        if not self._indexed:
            self.scan()
        return self._modules.get(file_path)

    def list_all_modules(self) -> list[ModuleInfo]:
        """Return all indexed modules.

        Triggers a full scan if the index has not been built yet.

        Returns:
            A list of all :class:`ModuleInfo` records in the index.
        """
        if not self._indexed:
            self.scan()
        return list(self._modules.values())

    def search_by_name(self, name: str) -> list[ModuleInfo]:
        """Search modules by file path or export name substring match.

        Performs a case-insensitive substring search against module paths,
        module names, and export names.  Useful for quick lookup when you
        know part of a symbol or file name.

        Args:
            name: Substring to search for (e.g., ``"database"``, ``"connect"``).

        Returns:
            A list of :class:`ModuleInfo` records whose path, name, or
            exports contain the search string.
        """
        if not self._indexed:
            self.scan()
        results: list[ModuleInfo] = []
        name_lower = name.lower()
        for mod in self._modules.values():
            if name_lower in mod.path.lower() or name_lower in mod.name.lower():
                results.append(mod)
            else:
                for exp in mod.exports:
                    if name_lower in exp.lower():
                        results.append(mod)
                        break
        return results