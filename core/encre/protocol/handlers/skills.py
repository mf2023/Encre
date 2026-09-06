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

"""Skills domain handlers: enable / install / uninstall / update.

Owns the user-skill lifecycle plus the encrypted skills index and the zip
package helpers.  Extracted verbatim from ``encre.transport.ws``
(architecture refactor Stage 3 / Task 5.2); behaviour is unchanged, only
the layout moved.  Outer-loop ``continue`` statements of the original
dispatch chain became ``return`` inside the extracted methods.
"""

import base64
import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from typing import Any

from encre.server.protocol import (
    ClientInstallSkill,
    ClientUninstallSkill,
    ClientUpdateSkill,
    ClientUpdateSkills,
)

logger = logging.getLogger("encre.transport.ws")


def _find_skill_root(extracted_dir: str) -> str | None:
    """Find the directory containing SKILL.md in an extracted zip tree.

    Returns the path to the directory that directly contains SKILL.md.
    """
    for root, dirs, files in os.walk(extracted_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.upper() == "SKILL.MD":
                return root
    return None


def _copy_skill_tree(src_dir: str, dest_dir: str) -> None:
    """Copy all files from src_dir into dest_dir, overwriting dest."""
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


class SkillsHandlers:
    """Skill lifecycle handlers and index management."""

    @staticmethod
    async def _build_skills_list(info: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            registry = info.agent.skill_registry
            for name, skill in registry._skills.items():
                if getattr(skill, "hidden", False):
                    continue
                if skill.source in ("bundled", "managed"):
                    continue
                entry: dict[str, Any] = {
                    "name": name,
                    "description": skill.description,
                    "aliases": skill.aliases,
                    "source": skill.source,
                    "argument_hint": skill.argument_hint,
                    "allowed_tools": skill.allowed_tools,
                    "when_to_use": skill.when_to_use,
                    "context": str(skill.context) if hasattr(skill, "context") else "inline",
                    "model": skill.model,
                    "disable_model_invocation": skill.disable_model_invocation,
                    "user_invocable": skill.user_invocable,
                    "license": getattr(skill, "license", ""),
                    "compatibility": getattr(skill, "compatibility", ""),
                    "metadata": getattr(skill, "metadata", {}),
                }
                if skill.body:
                    entry["body"] = skill.body
                else:
                    try:
                        entry["body"] = await skill.get_prompt_for_command(None, {})
                    except Exception:
                        entry["body"] = ""
                results.append(entry)
        except Exception as e:
            logger.error(f"_build_skills_list failed: {e}")
        return results

    # 鈹€鈹€ Skills index management 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @staticmethod
    def _skills_index_path(skills_dir: Any) -> str:
        return os.path.join(str(skills_dir), "index.json")

    @staticmethod
    def _load_skills_index(skills_dir: Any) -> dict[str, Any]:
        idx_path = SkillsHandlers._skills_index_path(skills_dir)
        if not os.path.isfile(idx_path):
            return {"skills": {}}
        try:
            from encre.crypto import decrypt
            with open(idx_path, encoding="utf-8") as f:
                raw = decrypt(f.read())
            return json.loads(raw)
        except Exception:
            return {"skills": {}}

    @staticmethod
    def _save_skills_index(skills_dir: Any, index: dict[str, Any]) -> None:
        from encre.crypto import encrypt
        idx_path = SkillsHandlers._skills_index_path(skills_dir)
        raw = json.dumps(index, ensure_ascii=False, indent=2)
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(encrypt(raw))

    @staticmethod
    def _add_skill_to_index(skills_dir: Any, name: str, source_type: str = "md") -> None:
        index = SkillsHandlers._load_skills_index(skills_dir)
        index["skills"][name] = {
            "name": name,
            "installed_at": int(time.time()),
            "type": source_type,
        }
        SkillsHandlers._save_skills_index(skills_dir, index)

    @staticmethod
    def _remove_skill_from_index(skills_dir: Any, name: str) -> None:
        index = SkillsHandlers._load_skills_index(skills_dir)
        index["skills"].pop(name, None)
        SkillsHandlers._save_skills_index(skills_dir, index)

    # 鈹€鈹€ Zip helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @staticmethod
    def _looks_like_base64_zip(content: str) -> bool:
        """Heuristic: base64 zip payloads are single-line, no markdown frontmatter."""
        stripped = content.strip()
        if not stripped:
            return False
        if "\n" in stripped:
            return False
        if stripped.startswith("---"):
            return False
        # Must be valid base64-ish (no unicode, only base64 chars)
        if not re.match(r"^[A-Za-z0-9+/=]+$", stripped):
            return False
        try:
            decoded = base64.b64decode(stripped)
            # Check for zip magic bytes
            return decoded[:4] == b"PK\x03\x04"
        except Exception:
            return False

    @staticmethod
    def _install_skill_from_zip_data(content: str, skill_dir: Any) -> None:
        """Extract base64-encoded zip directly into skill_dir."""
        decoded = base64.b64decode(content.strip())
        tmpdir = tempfile.mkdtemp(prefix="yim_skill_")
        try:
            with zipfile.ZipFile(zipfile.BytesIO(decoded), "r") as zf:
                zf.extractall(tmpdir)

            src = _find_skill_root(tmpdir)
            if src is None:
                raise ValueError("No SKILL.md found in zip package")
            _copy_skill_tree(src, str(skill_dir))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _install_skill_from_zip_file(zip_path: str, skill_dir: Any) -> None:
        """Extract zip from disk directly into skill_dir."""
        tmpdir = tempfile.mkdtemp(prefix="yim_skill_")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)

            src = _find_skill_root(tmpdir)
            if src is None:
                raise ValueError("No SKILL.md found in zip package")
            _copy_skill_tree(src, str(skill_dir))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # 鈹€鈹€ Client message handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _h_update_skills(self, ws: Any, msg: ClientUpdateSkills) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        info.agent.config.enabled_skills = list(msg.enabled_skills)
        self._persist_config(info)
        available = await self._build_skills_list(info)
        await self._send(ws, "skills_updated",
                enabled_skills=msg.enabled_skills, available_skills=available)

    async def _h_install_skill(self, ws: Any, msg: ClientInstallSkill) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        from encre.config import get_data_dir
        from encre.skills.types import SkillSource
        skills_dir = get_data_dir() / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        try:
            content = msg.content
            file_path = msg.file_path
            # Always install into a subdirectory named after the skill
            skill_dir = skills_dir / msg.name
            if skill_dir.exists():
                shutil.rmtree(str(skill_dir), ignore_errors=True)
            skill_dir.mkdir(parents=True, exist_ok=True)

            if file_path and file_path.lower().endswith(".zip") and os.path.isfile(file_path):
                self._install_skill_from_zip_file(file_path, skill_dir)
                self._add_skill_to_index(skills_dir, msg.name, "zip")
            elif self._looks_like_base64_zip(content):
                self._install_skill_from_zip_data(content, skill_dir)
                self._add_skill_to_index(skills_dir, msg.name, "zip")
            else:
                skill_md = skill_dir / "SKILL.md"
                skill_md.write_text(content, encoding="utf-8")
                self._add_skill_to_index(skills_dir, msg.name, "md")

            info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
            available = await self._build_skills_list(info)
            await self._send(ws, "skill_installed", name=msg.name, available_skills=available)
        except Exception as e:
            logger.error(f"Skill install failed: {e}")
            await self._send(ws, "skill_install_error", name=msg.name, message=str(e))

    async def _h_uninstall_skill(self, ws: Any, msg: ClientUninstallSkill) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        from encre.config import get_data_dir
        from encre.skills.types import SkillSource
        skills_dir = get_data_dir() / "skills"
        try:
            skill_name = msg.name
            # Find the actual skill directory -- the dir name may differ
            # from the frontmatter name (e.g. zip file "github-1.0.0.zip"
            # creates a dir named "github-1.0.0" but SKILL.md has "name: github").
            found_dir = None
            if (skills_dir / skill_name).exists():
                found_dir = skills_dir / skill_name
            else:
                for entry in os.listdir(str(skills_dir)):
                    entry_path = skills_dir / entry
                    if entry_path.is_dir():
                        skill_md = entry_path / "SKILL.md"
                        if skill_md.exists():
                            try:
                                text = skill_md.read_text(encoding="utf-8")
                                import re as _re
                                m = _re.search(r"^name\s*:\s*(.+)$", text, _re.MULTILINE)
                                if m and m.group(1).strip() == skill_name:
                                    found_dir = entry_path
                                    break
                            except Exception:
                                pass
            if found_dir:
                shutil.rmtree(str(found_dir), ignore_errors=True)
                logger.info("[uninstall_skill] removed directory %s", found_dir)
            # Remove from index -- find the correct key
            index = SkillsHandlers._load_skills_index(skills_dir)
            index_key = skill_name
            if index_key not in index.get("skills", {}):
                for k in list(index.get("skills", {})):
                    if k.startswith(skill_name):
                        index_key = k
                        break
            index["skills"].pop(index_key, None)
            SkillsHandlers._save_skills_index(skills_dir, index)
            # Clear from registry and reload
            info.agent.skill_registry._skills.pop(skill_name, None)
            info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
            available = await self._build_skills_list(info)
            await self._send(ws, "skill_uninstalled", name=skill_name, available_skills=available)
        except Exception as e:
            logger.error(f"Skill uninstall failed: {e}")
            await self._send(ws, "error", message=f"Failed to uninstall skill: {e}")

    async def _h_update_skill(self, ws: Any, msg: ClientUpdateSkill) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        from encre.config import get_data_dir
        from encre.skills.types import SkillSource
        skills_dir = get_data_dir() / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        try:
            skill_dir = skills_dir / msg.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(msg.content, encoding="utf-8")
            info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
            available = await self._build_skills_list(info)
            await self._send(ws, "skill_installed", name=msg.name, available_skills=available)
        except Exception as e:
            await self._send(ws, "skill_install_error", name=msg.name, message=str(e))
