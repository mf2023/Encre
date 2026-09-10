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

"""Profile domain handlers: memory / rules / hooks / documents.

Owns the settings-panel data planes (memory entries, global + project
rules, project hooks, indexed documents) and their unified snapshot
builders shared with ``_push_all_data``.  Extracted verbatim from
``encre.transport.ws`` (architecture refactor Stage 3 / Task 5.2);
behaviour is unchanged, only the layout moved.  Outer-loop ``continue``
statements of the original dispatch chain became ``return`` inside the
extracted methods.
"""

import asyncio
import contextlib
import logging
import os
from typing import Any

from encre.server.protocol import (
    ClientAddDocument,
    ClientDeleteGlobalRule,
    ClientGetGlobalRuleContent,
    ClientGetMemoryDetail,
    ClientGetMemoryList,
    ClientGetProfile,
    ClientListDocuments,
    ClientListGlobalRules,
    ClientListProjectHooks,
    ClientListProjectRules,
    ClientRemoveDocument,
    ClientSaveGlobalRule,
)

logger = logging.getLogger("encre.transport.ws")


class ProfileHandlers:
    """Memory / rules / hooks / documents handlers and snapshot builders."""

    @staticmethod
    def _parse_memory_frontmatter(content: str) -> dict[str, Any] | None:
        import re
        pattern = r"^---\s*\n(.*?)\n---"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return None
        yaml_block = match.group(1)
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

    def _build_global_rules_list(self) -> list[dict[str, Any]]:
        """All global rules (used by global_rules_list responses/snapshots)."""
        from encre.config import get_data_dir
        rules_dir = get_data_dir() / "rules"
        rules_list: list[dict[str, Any]] = []
        if rules_dir.is_dir():
            for fpath in sorted(rules_dir.glob("*.md"), key=lambda p:
                p.stat().st_mtime, reverse=True):
                try:
                    rules_list.append({
                        "name": fpath.stem,
                        "path": str(fpath.relative_to(rules_dir)),
                        "size": fpath.stat().st_size,
                        "modified": fpath.stat().st_mtime,
                    })
                except Exception:
                    continue
        return rules_list

    def _build_memory_list(self) -> list[dict[str, Any]]:
        """All memory entries (used by memory_list responses/snapshots)."""
        from encre.config import get_data_dir
        from encre.crypto import decrypt as _decrypt
        mem_dir = get_data_dir() / "memory"
        entries: list[dict[str, Any]] = []
        if mem_dir.is_dir():
            for fpath in sorted(mem_dir.glob("*.md"), key=lambda p:
                p.stat().st_mtime, reverse=True):
                # Hide the internal profile file (_profile.md) from the
                # settings UI; it is still loaded by the system.
                if fpath.name == "_profile.md":
                    continue
                try:
                    raw = fpath.read_text("utf-8")
                    content = raw
                    if raw.strip() and not raw.strip().startswith("---") and not raw.strip().startswith("#"):
                        with contextlib.suppress(Exception):
                            content = _decrypt(raw)
                    meta = self._parse_memory_frontmatter(raw) if "---" in raw else None
                    if not meta:
                        meta = self._parse_memory_frontmatter(content) if "---" in content else None
                    entry: dict[str, Any] = {
                        "name": fpath.stem,
                        "path": str(fpath.relative_to(mem_dir)),
                        "size": fpath.stat().st_size,
                        "modified": fpath.stat().st_mtime,
                        "preview": content[:200].replace("\n", " ").strip(),
                    }
                    if meta:
                        entry["title"] = meta.get("title", "")
                        entry["tags"] = list(meta.get("tags", [])) if isinstance(meta.get("tags"), list | tuple) else []
                        entry["type"] = str(meta.get("type", ""))
                    entries.append(entry)
                except Exception:
                    continue
        return entries

    def _build_documents_list(self) -> list[dict[str, Any]]:
        """All indexed documents (used by documents_list responses/snapshots)."""
        from encre.capabilities.search.codebase.document_manager import EncreDocumentManager
        from encre.config import get_data_dir
        mgr = EncreDocumentManager(str(get_data_dir()))
        return mgr.list_all()

    def _build_usage_stats(self) -> dict[str, Any]:
        """Aggregated usage stats with display-name resolution."""
        try:
            from encre.telemetry import EncreTelemetry
            stats = EncreTelemetry.get_all_sessions_usage()
            model_names: dict[str, str] = {}
            current_model_ids: set[str] = set()
            if self._default_config:
                for mc in self._default_config.models:
                    mid = (mc.model_id or "").strip()
                    if mid and mc.name:
                        model_names[mid] = mc.name
            if stats.get("sessions"):
                for s in stats["sessions"]:
                    raw = (s.get("model", "") or "").strip()
                    if not raw or raw == "unknown":
                        s["model"] = "(unknown model)"
                        s["model_status"] = "unknown"
                    elif raw in model_names:
                        s["model"] = model_names[raw]
                        s["model_status"] = "active"
                    else:
                        # Model is no longer in the user's config: keep the
                        # raw id so the historical record is preserved.
                        s["model"] = raw
                        s["model_status"] = "deleted"
            if stats.get("model_breakdown"):
                mb: dict[str, dict[str, Any]] = {}
                for raw, data in stats["model_breakdown"].items():
                    if not raw or raw == "unknown":
                        display = "(unknown model)"
                    elif raw in model_names:
                        display = model_names[raw]
                    else:
                        display = raw
                    if display in mb:
                        for k in ("input_tokens", "output_tokens", "total_tokens", "turns"):
                            mb[display][k] = mb[display].get(k, 0) + data.get(k, 0)
                    else:
                        mb[display] = dict(data)
                stats["model_breakdown"] = mb
            return stats
        except Exception:
            return {
                "total_sessions": 0, "total_tokens": 0,
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_tool_calls": 0,
                "tool_call_breakdown": {},
                "model_breakdown": {},
                "sessions": [],
            }

    def _build_project_rules_list(self) -> list[dict[str, Any]]:
        """Project-level rules for the current workspace context."""
        ws_path = (self._workspace_path or self._default_config.workspace) if self._default_config else ""
        rules_list: list[dict[str, Any]] = []
        if ws_path and os.path.isdir(ws_path):
            for rel_path, priority, name in [
                (".encre/rules.md", 100, "encre"),
                (".cursorrules", 90, "cursor"),
                (".windsurfrules", 85, "windsurf"),
                (".clinerules", 80, "cline"),
                ("CLAUDE.md", 75, "claude"),
                (".github/copilot-instructions.md", 60, "copilot"),
            ]:
                full_path = os.path.join(ws_path, rel_path)
                if os.path.isfile(full_path):
                    try:
                        st = os.stat(full_path)
                        rules_list.append({
                            "name": name,
                            "path": rel_path,
                            "priority": priority,
                            "modified": st.st_mtime,
                        })
                    except Exception:
                        continue
            # Codex instructions: AGENTS.md chain, .codex/config.toml
            # developer_instructions, and model_instructions_file.
            try:
                from encre.codex_compat import build_codex_context
                ctx = build_codex_context(ws_path)
                seen_codex: set[str] = set()
                for path, _ in ctx.instructions:
                    if path in seen_codex:
                        continue
                    seen_codex.add(path)
                    rel = path
                    if rel.startswith(ws_path + os.sep):
                        rel = rel[len(ws_path) + len(os.sep):]
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        mtime = 0.0
                    rules_list.append({
                        "name": "codex",
                        "path": rel,
                        "priority": 65,
                        "modified": mtime,
                    })
            except Exception:
                pass
            rules_list.sort(key=lambda r: -r["priority"])
        return rules_list

    def _build_project_hooks_list(self) -> list[dict[str, Any]]:
        """Project hooks for the current agent context."""
        from encre.hooks import EncreHookSystem
        info = self._info
        hook_system: EncreHookSystem | None = (
            getattr(getattr(info, "agent", None), "hook_system", None)
        )
        hooks_list: list[dict[str, Any]] = []
        if hook_system is not None:
            for h in hook_system.list_handlers():
                hooks_list.append({
                    "handler_id": h.get("handler_id", ""),
                    "event_type": h.get("event_type", ""),
                    "source_path": h.get("source_path", ""),
                    "matcher": h.get("matcher", ""),
                    "command": h.get("command", ""),
                    "hook_type": h.get("hook_type", "command"),
                    "timeout_ms": int(h.get("timeout_ms", 0) or 0),
                })
        return hooks_list

    # 鈹€鈹€ Client message handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _h_get_memory_list(self, ws: Any, msg: ClientGetMemoryList) -> None:
        await self._send(ws, "memory_list", entries=self._build_memory_list())

    async def _h_get_memory_detail(self, ws: Any, msg: ClientGetMemoryDetail) -> None:
        from encre.config import get_data_dir
        mem_dir = get_data_dir() / "memory"
        file_path = mem_dir / msg.path
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(mem_dir.resolve())) or not file_path.is_file():
            await self._send(ws, "memory_detail", path=msg.path, content="", error="File not found or access denied")
        else:
            try:
                raw = file_path.read_text("utf-8")
                content = raw
                from encre.crypto import decrypt
                if not raw.startswith("---"):
                    with contextlib.suppress(Exception):
                        content = decrypt(raw)
            except Exception:
                content = ""
            await self._send(ws, "memory_detail", path=msg.path, content=content)

    async def _h_list_global_rules(self, ws: Any, msg: ClientListGlobalRules) -> None:
        await self._send(ws, "global_rules_list", rules=self._build_global_rules_list())

    async def _h_list_project_rules(self, ws: Any, msg: ClientListProjectRules) -> None:
        await self._send(ws, "project_rules_list", rules=self._build_project_rules_list())

    async def _h_list_project_hooks(self, ws: Any, msg: ClientListProjectHooks) -> None:
        await self._send(ws, "project_hooks_list", hooks=self._build_project_hooks_list())

    async def _h_save_global_rule(self, ws: Any, msg: ClientSaveGlobalRule) -> None:
        from encre.config import get_data_dir
        from encre.crypto import encrypt
        rules_dir = get_data_dir() / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_path = rules_dir / f"{msg.name}.md"
        try:
            # Global rules are encrypted at rest, like soul/ and memory/.
            rule_path.write_text(encrypt(msg.content), encoding="utf-8")
            await self._send(ws, "global_rule_saved", name=msg.name)
            # Push the full list from the unified builder (single
            # source of truth) so the frontend stays in sync.
            await self._send(ws, "global_rules_list", rules=self._build_global_rules_list())
        except Exception as e:
            await self._send(ws, "error", message=f"Failed to save global rule: {e}")

    async def _h_delete_global_rule(self, ws: Any, msg: ClientDeleteGlobalRule) -> None:
        from encre.config import get_data_dir
        rules_dir = get_data_dir() / "rules"
        rule_path = rules_dir / f"{msg.name}.md"
        try:
            if rule_path.is_file():
                rule_path.unlink()
            await self._send(ws, "global_rule_deleted", name=msg.name)
        except Exception as e:
            await self._send(ws, "error", message=f"Failed to delete global rule: {e}")

    async def _h_get_global_rule_content(self, ws: Any, msg: ClientGetGlobalRuleContent) -> None:
        from encre.config import get_data_dir
        rules_dir = get_data_dir() / "rules"
        rule_path = (rules_dir / f"{msg.name}.md").resolve()
        if not str(rule_path).startswith(str(rules_dir.resolve())) or not rule_path.is_file():
            await self._send(ws, "global_rule_content", name=msg.name, content="", error="File not found")
        else:
            try:
                # Single reader shared with the prompt loader, so at-rest
                # decryption stays in one place.
                from encre.rules.loader import read_global_rule_text
                content = read_global_rule_text(str(rule_path))
                await self._send(ws, "global_rule_content", name=msg.name, content=content)
            except Exception as e:
                await self._send(ws, "global_rule_content", name=msg.name, content="", error=str(e))

    async def _h_get_profile(self, ws: Any, msg: ClientGetProfile) -> None:
        from encre.config import get_data_dir
        from encre.profile.system import EncreProfileSystem
        mem_dir = str(get_data_dir() / "memory")
        ps = EncreProfileSystem(mem_dir)
        ps.load()
        data = ps.get_data()
        await self._send(ws, "profile_data", profile=data)

    async def _h_add_document(self, ws: Any, msg: ClientAddDocument) -> None:
        from encre.capabilities.search.codebase.document_manager import EncreDocumentManager

        from encre.config import get_data_dir
        try:
            mgr = EncreDocumentManager(str(get_data_dir()))
            if msg.file_path:
                doc = mgr.add_from_local(msg.name, msg.file_path)
                await self._send(ws, "document_added", document=doc.to_dict())
                await self._send(ws, "documents_list", documents=self._build_documents_list())
            elif msg.url:
                doc = mgr.add_pending_url(msg.name, msg.url)
                await self._send(ws, "document_added", document=doc.to_dict())
                await self._send(ws, "documents_list", documents=self._build_documents_list())
                _t = asyncio.ensure_future(self._crawl_and_update(ws, mgr, doc, msg.url))
                self._tasks.add(_t)
            else:
                await self._send(ws, "document_error", message="Either file_path or url is required")
        except Exception as e:
            await self._send(ws, "document_error", message=str(e))

    async def _h_remove_document(self, ws: Any, msg: ClientRemoveDocument) -> None:
        from encre.capabilities.search.codebase.document_manager import EncreDocumentManager

        from encre.config import get_data_dir
        try:
            mgr = EncreDocumentManager(str(get_data_dir()))
            removed = mgr.remove(msg.id)
            if removed:
                await self._send(ws, "document_removed", id=msg.id)
                await self._send(ws, "documents_list", documents=self._build_documents_list())
            else:
                await self._send(ws, "document_error", message="Document not found")
        except Exception as e:
            await self._send(ws, "document_error", message=str(e))

    async def _h_list_documents(self, ws: Any, msg: ClientListDocuments) -> None:
        try:
            await self._send(ws, "documents_list", documents=self._build_documents_list())
        except Exception as e:
            await self._send(ws, "document_error", message=str(e))

    async def _crawl_and_update(self, ws: Any, mgr: Any, doc: Any, url: str) -> None:
        from encre.capabilities.search.codebase.document_manager import crawl_url_to_text
        try:
            loop = asyncio.get_event_loop()
            full_text = await loop.run_in_executor(None, crawl_url_to_text, doc.name, url)
            updated = mgr.finish_url_crawl(doc.id, full_text)
            if updated:
                await self._send(ws, "document_updated", document=updated.to_dict())
                await self._send(ws, "documents_list", documents=self._build_documents_list())
        except Exception as e:
            mgr._documents.pop(doc.id, None)
            mgr._save()
            await self._send(ws, "document_error", message=f"Crawl failed: {e}")
