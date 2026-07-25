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

import asyncio
import json
import os
import re
import time
from typing import Any

from encre.codebase.document_manager import EncreDocumentManager
from encre.codebase.indexer import EncreCodeIndex
from encre.config import EncreConfig
from encre.git.repo import EncreGitRepo


class ContextBuilder:
    """Builds all context / prompt blocks injected into the system message.

    Owns all ``_*_prompt_cache`` variables and related state
    (``_document_manager``, ``_code_index``, etc.) so EncreLoop no longer
    carries them directly.
    """

    def __init__(self, config: EncreConfig, session: Any, *,
                 cache_fresh: Any,
                 memory_system: Any = None,
                 soul_system: Any = None,
                 profile_system: Any = None,
                 git: Any = None,
                 rules_loader: Any = None) -> None:
        self._config = config
        self._session = session
        self._cache_fresh = cache_fresh

        self.memory_system = memory_system
        self.soul_system = soul_system
        self.profile_system = profile_system
        self._git = git
        self._rules_loader = rules_loader

        self._document_manager: EncreDocumentManager | None = None
        self._document_manager_data_dir: str | None = None
        self._code_index: EncreCodeIndex | None = None

        # Prompt caches
        self._workspace_info_cache: tuple[str, float, tuple[str, str, str]] | None = None
        self._memory_prompt_cache: tuple[str, float, str] | None = None
        self._soul_prompt_cache: tuple[str, float, str] | None = None
        self._document_prompt_cache: tuple[str, float, str] | None = None
        self._codebase_context_cache: tuple[tuple[str, int, int], float, str] | None = None
        self._profile_prompt_cache: tuple[str, str, float, str] | None = None
        self._rules_prompt_cache: tuple[tuple[str, bool, bool], float, str] | None = None

    # ── Directory tree (static helper) ──────────────────────────────

    def build_directory_tree(self, ws_path: str, max_depth: int = 4, max_entries: int = 200) -> str:
        skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv",
                     "target", "build", "dist", ".tox", ".eggs",
                     ".mypy_cache", ".pytest_cache", ".ruff_cache",
                     ".svn", ".hg", ".idea", ".vscode"}
        skip_ext = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe"}
        lines: list[str] = []
        total_files = 0
        try:
            for root, dirs, files in os.walk(ws_path):
                dirs[:] = [d for d in dirs
                           if not d.startswith(".") and d not in skip_dirs]
                rel = os.path.relpath(root, ws_path)
                if rel == ".":
                    rel = ""
                depth = rel.count(os.sep) + 1 if rel else 0
                if depth > max_depth:
                    continue
                indent = "  " * depth
                if depth == 0:
                    lines.append("\U0001f4c1 workspace/")
                else:
                    basename = os.path.basename(root)
                    lines.append(f"{indent}\U0001f4c1 {basename}/")
                for fname in sorted(files):
                    if fname.startswith("."):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in skip_ext:
                        continue
                    if len(lines) >= max_entries:
                        break
                    lines.append(f"{indent}  \U0001f4c4 {fname}")
                    total_files += 1
                if len(lines) >= max_entries:
                    lines.append(f"  ... (truncated at {max_entries} entries)")
                    break
        except (OSError, PermissionError):
            pass
        if not lines:
            return ""
        header = (
            f"## Workspace Structure\n"
            f"{total_files} files shown (tree depth \u2264{max_depth}). "
            f"Index is still building \u2014 full file contents coming soon.\n"
            f"```\n" + "\n".join(lines) + "\n```"
        )
        return header

    # ── Workspace info ───────────────────────────────────────────────

    def workspace_info(self) -> tuple[str, str, str]:
        """Return (workspace_root, workspace_name, project_summary) for the prompt builder.

        Returns ("", "", "") when not running inside a workspace.

        Cache key includes the git branch so that switching branches
        automatically refreshes the workspace context.
        """
        ws_path = getattr(self._config, "workspace", "") or ""
        if not ws_path or not os.path.isdir(ws_path):
            self._workspace_info_cache = None
            return "", "", ""
        cache_key = ws_path
        try:
            repo = self._git
            if repo is not None:
                branch = repo.get_branch() if hasattr(repo, "get_branch") else ""
                if branch:
                    cache_key = f"{ws_path}@{branch}"
        except Exception:
            pass
        if (
            self._workspace_info_cache is not None
            and self._workspace_info_cache[0] == cache_key
            and self._cache_fresh(self._workspace_info_cache[1])
        ):
            return self._workspace_info_cache[2]

        ws_name = os.path.basename(ws_path)

        yim_dir = os.path.join(ws_path, ".encre")
        ws_config_path = os.path.join(yim_dir, "config.json")
        ws_config: dict[str, Any] = {}
        if os.path.isfile(ws_config_path):
            try:
                with open(ws_config_path, encoding="utf-8") as f:
                    ws_config = json.load(f)
            except Exception:
                pass

        summary_lines: list[str] = []

        custom_prompt = ws_config.get("system_prompt", "")
        if custom_prompt:
            summary_lines.append("Project-specific instructions:")
            summary_lines.append(custom_prompt)
            summary_lines.append("")

        try:
            visible: list[tuple[str, bool]] = []
            with os.scandir(ws_path) as entries:
                for entry in entries:
                    name = entry.name
                    if name.startswith(".") and name != ".encre":
                        continue
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    visible.append((name, is_dir))
            visible.sort(key=lambda item: (not item[1], item[0]))
            if visible:
                summary_lines.append("Top-level entries:")
                for name, is_dir in visible[:40]:
                    prefix = "/" if is_dir else " "
                    summary_lines.append(f"  {prefix}{name}")
                if len(visible) > 40:
                    summary_lines.append(f"  ... and {len(visible) - 40} more entries")
        except Exception:
            pass

        try:
            git_repo = EncreGitRepo(ws_path)
            if git_repo.is_in_repo():
                state = git_repo.get_state()
                summary_lines.append("")
                summary_lines.append("Git status:")
                summary_lines.append(f"  branch: {state.branch}")
                summary_lines.append(f"  clean: {'yes' if state.is_clean else 'no'}")
                if state.changed_files:
                    summary_lines.append(f"  changed: {', '.join(state.changed_files[:20])}")
                if state.untracked_files:
                    summary_lines.append(f"  untracked: {', '.join(state.untracked_files[:10])}")
                if state.recent_commits:
                    summary_lines.append("  recent commits:")
                    for commit in state.recent_commits[:5]:
                        summary_lines.append(f"    {commit}")
        except Exception:
            pass

        result = (ws_path, ws_name, "\n".join(summary_lines))
        self._workspace_info_cache = (cache_key, time.time(), result)
        return result

    # ── Codebase index ───────────────────────────────────────────────

    def inject_code_index(self, idx: Any) -> None:
        """Inject a fully-built code index from the background IndexManager."""
        self._code_index = idx
        self._codebase_context_cache = None
        ws_path = getattr(idx, "workspace", "")
        if ws_path and self._session.messages:
            new_ctx = self._build_codebase_context_sync(ws_path, idx)
            if new_ctx:
                for m in self._session.messages:
                    if m.get("role") == "system":
                        old = m.get("content", "")
                        if "## Codebase Index" in old:
                            pass
                        elif "## Workspace Structure" in old or \
                             "Codebase index is still being built" in old:
                            m["content"] = old + "\n\n" + new_ctx
                            self._session.mark_messages_dirty()
                        break

    def _build_codebase_context_sync(self, _ws_path: str, idx: Any) -> str:
        try:
            modules = idx.list_all_modules()
            total = len(modules)
            if total == 0:
                return ""
            by_lang: dict[str, int] = {}
            for mod in modules:
                lang = getattr(mod, "language", None) or "other"
                by_lang[lang] = by_lang.get(lang, 0) + 1
            lang_items = sorted(by_lang.items(), key=lambda x: (-x[1], x[0]))
            lines = ["## Codebase Index",
                     f"Indexed {total} source files in the workspace.",
                     "Use `codebase_search` to find relevant code, or "
                     "`codebase_context` to view a specific file's details."]
            if lang_items:
                lines.append("Language breakdown: " +
                             ", ".join(f"{lang}: {count}" for lang, count in lang_items))
            return "\n".join(lines)
        except Exception:
            return ""

    async def build_codebase_context(self) -> str:
        """Build codebase context from the workspace index when available."""
        ws_path = getattr(self._config, "workspace", "") or ""
        if not ws_path or not os.path.isdir(ws_path):
            return ""

        loop = asyncio.get_running_loop()

        if self._code_index is None or getattr(self._code_index, "workspace", "") != ws_path:
            _t0 = time.time()
            try:
                idx = await loop.run_in_executor(None, EncreCodeIndex, ws_path)
                self._code_index = idx
                if not idx._indexed:
                    return self.build_directory_tree(ws_path)
            except Exception:
                return self.build_directory_tree(ws_path)
        elif not self._code_index._indexed:
            return self.build_directory_tree(ws_path)

        if self._code_index is None:
            return ""

        modules = self._code_index.list_all_modules()
        total = len(modules)
        if total == 0:
            return ""

        by_lang: dict[str, int] = {}
        for mod in modules:
            lang = mod.language or "other"
            by_lang[lang] = by_lang.get(lang, 0) + 1
        lang_summary_items = tuple(sorted(by_lang.items(), key=lambda x: (-x[1], x[0])))
        cache_key = (ws_path, total, int(self._code_index._indexed), lang_summary_items)
        if (
            self._codebase_context_cache is not None
            and self._codebase_context_cache[0] == cache_key
            and self._cache_fresh(self._codebase_context_cache[1])
        ):
            return self._codebase_context_cache[2]

        lines: list[str] = []
        lines.append("## Codebase Index")
        lines.append(f"Indexed {total} source files in the workspace.")
        lines.append("Use `codebase_search` to find relevant code, or `codebase_context` to view a specific file's details.")

        if lang_summary_items:
            lang_summary = ", ".join(f"{lang}: {count}" for lang, count in lang_summary_items)
            lines.append(f"Language breakdown: {lang_summary}")

        result = "\n".join(lines)
        self._codebase_context_cache = (cache_key, time.time(), result)
        return result

    # ── Document context ─────────────────────────────────────────────

    def build_document_context(self) -> str:
        from encre.config import get_data_dir

        try:
            data_dir = str(get_data_dir())
            index_path = os.path.join(data_dir, "documents", "index.json")
            try:
                st = os.stat(index_path)
                cache_key = f"{data_dir}:{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                cache_key = data_dir
            if (
                self._document_prompt_cache is not None
                and self._document_prompt_cache[0] == cache_key
                and self._cache_fresh(self._document_prompt_cache[1])
            ):
                return self._document_prompt_cache[2]

            if self._document_manager is None or self._document_manager_data_dir != data_dir:
                self._document_manager = EncreDocumentManager(data_dir)
                self._document_manager_data_dir = data_dir
            else:
                self._document_manager._load()
            prompt = self._document_manager.build_context()
            self._document_prompt_cache = (cache_key, time.time(), prompt)
            return prompt
        except Exception:
            return ""

    # ── Memory prompt ────────────────────────────────────────────────

    def build_memory_prompt(self) -> str:
        if self.memory_system is None:
            return ""

        memory_dir = self.memory_system.get_memory_path()
        cache_key = memory_dir
        if (
            self._memory_prompt_cache is not None
            and self._memory_prompt_cache[0] == cache_key
            and self._cache_fresh(self._memory_prompt_cache[1])
        ):
            return self._memory_prompt_cache[2]

        prompt = self.memory_system.build_prompt()
        self._memory_prompt_cache = (cache_key, time.time(), prompt)
        return prompt

    # ── Soul prompt ──────────────────────────────────────────────────

    def build_soul_prompt(self) -> str:
        if self.soul_system is None:
            return ""

        soul_dir = self.soul_system.get_soul_dir()
        cache_key = soul_dir
        if (
            self._soul_prompt_cache is not None
            and self._soul_prompt_cache[0] == cache_key
            and self._cache_fresh(self._soul_prompt_cache[1])
        ):
            return self._soul_prompt_cache[2]

        prompt = self.soul_system.build_prompt()
        self._soul_prompt_cache = (cache_key, time.time(), prompt)
        return prompt

    # ── Profile prompt ───────────────────────────────────────────────

    def refresh_profile_in_system(self) -> None:
        if self.profile_system is None:
            return
        if not self._session.messages or self._session.messages[0].get("role") != "system":
            return
        try:
            query = ""
            for m in reversed(self._session.messages):
                if m.get("role") == "user":
                    query = m.get("content", "")
                    break
            fresh = self.profile_system.build_relevant_prompt(query=query, threshold=0.0)
            if not fresh:
                return
            content = self._session.messages[0].get("content", "")
            content = re.sub(
                r"\n+## User Profile.*?(?=\n+## |\Z)",
                "",
                content,
                count=1,
                flags=re.DOTALL,
            )
            content = content.rstrip() + "\n\n" + fresh
            self._session.messages[0]["content"] = content
            self._session.mark_messages_dirty()
        except Exception:
            pass

    def build_profile_prompt(self, query: str) -> str:
        if self.profile_system is None:
            return ""
        cache_key = (getattr(self.profile_system, "_profile_path", ""), query)
        if (
            self._profile_prompt_cache is not None
            and self._profile_prompt_cache[0] == cache_key[0]
            and self._profile_prompt_cache[1] == cache_key[1]
            and self._cache_fresh(self._profile_prompt_cache[2])
        ):
            return self._profile_prompt_cache[3]
        prompt = self.profile_system.build_relevant_prompt(query=query, threshold=0.0)
        self._profile_prompt_cache = (cache_key[0], cache_key[1], time.time(), prompt)
        return prompt

    # ── Rules prompt ─────────────────────────────────────────────────

    def build_rules_prompt(self) -> str:
        ws_root = getattr(self._config, "workspace", "") or ""
        cache_key = (
            ws_root,
            bool(self._config.enable_project_rules),
            bool(self._config.enable_global_rules),
        )
        if (
            self._rules_prompt_cache is not None
            and self._rules_prompt_cache[0] == cache_key
            and self._cache_fresh(self._rules_prompt_cache[1])
        ):
            return self._rules_prompt_cache[2]
        prompt = self._rules_loader.build_rules_prompt(
            ws_root,
            enable_project=self._config.enable_project_rules,
            enable_global=self._config.enable_global_rules,
        )
        self._rules_prompt_cache = (cache_key, time.time(), prompt)
        return prompt
