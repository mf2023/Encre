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

import os
import re
from dataclasses import dataclass, field
from typing import Any

from encre.memdir.age import memory_age_days, memory_age_text, memory_freshness_text
from encre.memdir.entrypoint import load_entrypoint_raw, write_entrypoint
from encre.memdir.manifest import format_memory_manifest
from encre.memdir.semantic import MemoryConsolidator, SemanticMemorySearch, WorkingMemory
from encre.prompts.loader import PromptLoader

FRONTMATTER_MAX_LINES = 30
MAX_MEMORY_FILES = 200
ENTRYPOINT_NAME = "MEMORY.md"
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000


@dataclass
class MemoryHeader:
    """Metadata extracted from a memory file's front matter and mtime."""
    filename: str
    file_path: str
    mtime_ms: float
    description: str | None = None
    memory_type: str | None = None
    tags: list[str] = field(default_factory=list)
    age_text: str = ""


@dataclass
class EntrypointResult:
    """Holds the loaded MEMORY.md entrypoint plus size/truncation metadata."""
    content: str
    line_count: int
    byte_count: int
    was_line_truncated: bool
    was_byte_truncated: bool


_loader = PromptLoader()


class EncreMemorySystem:
    """Façade orchestrating all memory-directory operations for an agent.

    Wraps the entrypoint loader, manifest formatter, :class:`SemanticMemorySearch`,
    :class:`WorkingMemory`, and :class:`MemoryConsolidator`. Callers typically
    construct it with the agent's ``auto_memory_path`` and then use
    :meth:`build_prompt` / :meth:`build_prompt_with_context` to inject memory
    into a model prompt.
    """
    MAX_ENTRYPOINT_LINES = MAX_ENTRYPOINT_LINES
    MAX_ENTRYPOINT_BYTES = MAX_ENTRYPOINT_BYTES
    FRONTMATTER_MAX_LINES = FRONTMATTER_MAX_LINES
    ENTRYPOINT_NAME = ENTRYPOINT_NAME

    def __init__(self, auto_memory_path: str):
        self.auto_memory_path = auto_memory_path
        self._ensure_dir()
        self._semantic = SemanticMemorySearch(auto_memory_path)
        self._consolidator = MemoryConsolidator(auto_memory_path)
        self._working: WorkingMemory = WorkingMemory()

    def _ensure_dir(self) -> None:
        """Create the memory directory if it does not already exist."""
        os.makedirs(self.auto_memory_path, exist_ok=True)

    def scan(self) -> list[MemoryHeader]:
        """Enumerate memory files and extract their headers.

        Walks the memory directory, skips the entrypoint, dotfiles, internal
        underscore-prefixed files, and non-markdown files, then parses each
        remaining file's front matter for description/type/tags and computes
        a human-readable age. Results are sorted newest-first and capped at
        ``MAX_MEMORY_FILES``.

        Returns:
            List of :class:`MemoryHeader` objects (empty on OS errors).
        """
        memories: list[MemoryHeader] = []
        try:
            with os.scandir(self.auto_memory_path) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.name == ENTRYPOINT_NAME:
                        continue
                    # Hide dotfiles and underscore-prefixed internal files
                    # (e.g. _profile.md) from the user-facing memory list.
                    # They are still loaded by the system; just not shown.
                    if entry.name.startswith(".") or entry.name.startswith("_"):
                        continue
                    if not entry.name.endswith(".md"):
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    # st_mtime_ns is nanoseconds; convert to milliseconds
                    mtime_ms = stat.st_mtime_ns / 1_000_000.0
                    header = MemoryHeader(
                        filename=entry.name,
                        file_path=entry.path,
                        mtime_ms=mtime_ms,
                    )
                    try:
                        with open(entry.path, encoding="utf-8") as f:
                            raw_head = "".join(
                                f.readline() for _ in range(FRONTMATTER_MAX_LINES + 5)
                            )
                        # Decrypt if needed
                        if raw_head.strip() and not raw_head.strip().startswith("---") and not raw_head.strip().startswith("#"):
                            try:
                                from encre.crypto import decrypt
                                head = decrypt(raw_head.strip())
                            except Exception:
                                head = raw_head
                        else:
                            head = raw_head
                    except (OSError, UnicodeDecodeError):
                        memories.append(header)
                        continue
                    fm = self._parse_frontmatter(head)
                    if fm:
                        header.description = fm.get("description")
                        header.memory_type = fm.get("type")
                        header.tags = fm.get("tags", [])
                    header.age_text = memory_age_text(header.mtime_ms)
                    memories.append(header)
        except OSError:
            return []

        memories.sort(key=lambda m: m.mtime_ms, reverse=True)
        if len(memories) > MAX_MEMORY_FILES:
            memories = memories[:MAX_MEMORY_FILES]
        return memories

    def _parse_frontmatter(self, content: str) -> dict[str, Any] | None:
        """Extract a YAML front-matter block delimited by ``---`` lines.

        Args:
            content: Raw (possibly decrypted) file content.

        Returns:
            Parsed mapping, or ``None`` when no front matter is present.
        """
        pattern = r"^---\s*\n(.*?)\n---"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return None
        # Pull the text between the opening and closing '---' delimiters
        yaml_block = match.group(1)
        return self._parse_simple_yaml(yaml_block)

    def _parse_simple_yaml(self, yaml_block: str) -> dict[str, Any]:
        """Parse a minimal subset of YAML used in memory front matter.

        Supports ``key: value`` scalars and ``key:\\n  - item`` lists; it is
        intentionally not a full YAML parser to avoid extra dependencies.

        Args:
            yaml_block: Text between the ``---`` delimiters.

        Returns:
            Mapping of front-matter keys to string or list values.
        """
        result: dict[str, Any] = {}
        current_key: str | None = None
        current_list: list[str] = []

        for line in yaml_block.split("\n"):
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue

            list_match = re.match(r"^\s+-\s+(.+)$", stripped)
            if list_match and current_key:
                current_list.append(list_match.group(1).strip().strip("\"'"))
                continue

            if current_key is not None and current_list:
                result[current_key] = current_list
                current_list = []
                current_key = None

            kv_match = re.match(r"^(\w[\w_-]*)\s*:\s*(.*)$", stripped)
            if kv_match:
                key = kv_match.group(1)
                value = kv_match.group(2).strip()
                if not value:
                    current_key = key
                    current_list = []
                else:
                    val = value.strip("\"'")
                    result[key] = val

        if current_key is not None and current_list:
            result[current_key] = current_list

        return result

    def format_manifest(self, memories: list[MemoryHeader] | None = None) -> str:
        """Render the Markdown manifest, scanning if no list is supplied."""
        if memories is None:
            memories = self.scan()
        return format_memory_manifest(memories)

    def load_entrypoint(self) -> EntrypointResult:
        """Load and size-limit the MEMORY.md entrypoint for prompts."""
        raw = load_entrypoint_raw(self.auto_memory_path)
        return EntrypointResult(
            content=raw["content"],
            line_count=raw["line_count"],
            byte_count=raw["byte_count"],
            was_line_truncated=raw["was_line_truncated"],
            was_byte_truncated=raw["was_byte_truncated"],
        )

    def build_prompt(self) -> str:
        """Assemble the full memory prompt shown to the model.

        Combines the base memory-system template, the MEMORY.md entrypoint,
        the Markdown manifest of available memories, and usage hints into a
        single string ready to be injected into a system prompt.

        Returns:
            The assembled memory prompt text.
        """
        entrypoint = self.load_entrypoint()
        memories = self.scan()

        # Load the base memory-system template shared across all agents
        base = _loader.load("memory_system", category="memdir")

        parts = [base, ""]

        if entrypoint.content:
            parts.append("=== MEMORY.md Entrypoint ===")
            parts.append(entrypoint.content)
            if entrypoint.was_line_truncated or entrypoint.was_byte_truncated:
                parts.append("")
                parts.append(
                    "[Note: MEMORY.md was truncated due to size limits. "
                    "The full file is available at the memory directory path.]"
                )
        else:
            parts.append("=== MEMORY.md Entrypoint ===")
            parts.append(
                "(No entrypoint content yet. "
                "Create MEMORY.md to establish core project memory.)"
            )

        parts.append("")

        if memories:
            manifest = self.format_manifest(memories)
            parts.append(manifest)
        else:
            parts.append("# Memory Manifest")
            parts.append("")
            parts.append("(No memory files found.)")

        parts.append("")
        parts.append(
            "To read a memory, view the relevant .md file. "
            "To create a memory, write a new .md file."
        )

        return "\n".join(parts)

    def write_entrypoint(self, content: str) -> None:
        """Encrypt and persist the MEMORY.md entrypoint, with plaintext fallback."""
        from encre.crypto import encrypt
        file_path = os.path.join(self.auto_memory_path, ENTRYPOINT_NAME)
        os.makedirs(self.auto_memory_path, exist_ok=True)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                # Encrypt before persisting so memory stays confidential at rest
                f.write(encrypt(content))
        except Exception:
            write_entrypoint(self.auto_memory_path, content)

    def _get_file_age(self, mtime_ms: float) -> str:
        """Return the human-readable age string for a timestamp."""
        return memory_age_text(mtime_ms)

    def _get_freshness_text(self, mtime_ms: float) -> str:
        """Return the staleness reminder snippet for a timestamp."""
        return memory_freshness_text(mtime_ms)

    def get_memory_path(self) -> str:
        """Return the underlying memory directory path."""
        return self.auto_memory_path

    # ---- semantic search -------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list:
        """Semantic search over memory files. Returns SearchResult list."""
        return self._semantic.search(query, top_k=top_k)

    def search_relevant(self, query: str, top_k: int = 5) -> list:
        """Semantic search with higher relevance threshold."""
        return self._semantic.search_relevant(query, top_k=top_k)

    def refresh_index(self) -> None:
        """Force re-index of all memory files."""
        self._semantic._rebuild_from_disk()

    # ---- working memory --------------------------------------------------

    @property
    def working(self) -> WorkingMemory:
        return self._working

    def reset_working(self) -> None:
        self._working = WorkingMemory()

    def inject_working_memory_prompt(self) -> str:
        summary = self._working.summarize()
        if summary.startswith("(empty"):
            return ""
        return f"Working memory:\n{summary}"

    # ---- consolidation ---------------------------------------------------

    def consolidate(self) -> list:
        """Run duplicate/conflict/staleness checks and return actions."""
        files: dict[str, str] = {}
        age_days: dict[str, int] = {}
        for m in self.scan():
            try:
                with open(m.file_path, encoding="utf-8") as f:
                    files[m.filename] = f.read()
            except (OSError, UnicodeDecodeError):
                pass
            age_days[m.filename] = memory_age_days(m.mtime_ms)
        return self._consolidator.consolidate(files, age_days)

    # ---- build prompt with semantic context -------------------------------

    def build_prompt_with_context(self, query: str = "", top_k: int = 5) -> str:
        """Like build_prompt() but prepends semantically-relevant memories."""
        parts: list[str] = []
        if query:
            results = self.search(query, top_k=top_k)
            if results:
                parts.append("## Semantically Relevant Memories")
                parts.append("")
                for r in results:
                    parts.append(f"### {r.file_name} (score: {r.score:.2f})")
                    parts.append(r.snippet)
                    parts.append("")
        parts.append(self.build_prompt())
        return "\n".join(parts)
