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

import re
from typing import Any


class SkillManager:
    """Skill activation, collection, and rendering for EncreLoop.

    Manages the lifecycle of tool skills (auto-activated usage guidance),
    document skills (domain guidance scoped by file extension), and the
    dynamic skill catalogue presented to the model.  Composed into
    :class:`EncreLoop` via delegation.
    """

    _SKILL_PATTERN = re.compile(r"^/(\S+)(?:\s+(.*))?", re.DOTALL)

    def __init__(self, skill_registry: Any | None) -> None:
        self._skill_registry = skill_registry
        self._active_tool_skills: dict[str, str] = {}
        self._active_doc_skills: dict[str, str] = {}

    @property
    def active_tool_skills(self) -> dict[str, str]:
        return self._active_tool_skills

    @property
    def active_doc_skills(self) -> dict[str, str]:
        return self._active_doc_skills

    async def activate_skills(self, prompt: str) -> tuple[str, str]:
        if not self._skill_registry:
            return "", prompt
        parts: list[str] = []
        remaining = prompt
        while True:
            m = self._SKILL_PATTERN.match(remaining)
            if not m:
                break
            skill_name = m.group(1)
            args = (m.group(2) or "").strip() or None
            skill = self._skill_registry.lookup(skill_name)
            if skill is None:
                break
            skill_prompt = await self._skill_registry.activate(skill_name, args)
            if not skill_prompt.startswith("Error: "):
                parts.append(skill_prompt)
            end = m.end()
            remaining = remaining[end:].strip()
        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n", remaining
        return "", prompt

    async def collect_tool_skill(self, tool_name: str) -> None:
        if not self._skill_registry or not tool_name:
            return
        if tool_name in self._active_tool_skills:
            return
        skill_name = f"tool-{tool_name.replace('_', '-')}"
        skill = self._skill_registry.lookup(skill_name)
        if skill is None:
            return
        try:
            body = await self._skill_registry.activate(skill_name)
        except Exception:
            return
        if not body or body.startswith("Error: "):
            return
        self._active_tool_skills[tool_name] = body

    async def collect_doc_skills(self, args: dict) -> None:
        if not self._skill_registry or not args:
            return
        paths = [str(v) for v in args.values() if isinstance(v, str)]
        if not paths:
            return
        try:
            names = await self._skill_registry.activate_for_paths(paths)
        except Exception:
            return
        for skill_name in names:
            if skill_name in self._active_doc_skills:
                continue
            try:
                body = await self._skill_registry.activate(
                    skill_name, "(referenced this session)"
                )
            except Exception:
                continue
            if not body or body.startswith("Error: "):
                continue
            self._active_doc_skills[skill_name] = body

    def render_active_tool_skills(self) -> str:
        if not self._active_tool_skills:
            return ""
        parts = [
            "## Tool Skills (auto-activated)",
            "",
            "Detailed usage guidance for tools already used this session:",
            "",
        ]
        for tool_name, body in self._active_tool_skills.items():
            parts.append(f"### tool-{tool_name.replace('_', '-')}")
            parts.append("")
            parts.append(body.strip())
            parts.append("")
        return "\n".join(parts).rstrip()

    def render_active_doc_skills(self) -> str:
        if not self._active_doc_skills:
            return ""
        parts = [
            "## Document Skills (auto-activated)",
            "",
            "Domain guidance for file types referenced this session:",
            "",
        ]
        for skill_name, body in self._active_doc_skills.items():
            parts.append(f"### {skill_name}")
            parts.append("")
            parts.append(body.strip())
            parts.append("")
        return "\n".join(parts).rstrip()

    def render_skill_catalogue(self) -> str:
        if not self._skill_registry:
            return ""
        skills = [
            s for s in self._skill_registry.list_all()
            if s.user_invocable and not s.name.startswith("tool-")
        ]
        if not skills:
            return ""
        groups: dict[str, list[str]] = {}
        for s in sorted(skills, key=lambda x: x.name):
            prefix = s.name.split("-", 1)[0] if "-" in s.name else "general"
            groups.setdefault(prefix, []).append(
                f"- `/{s.name}`: {s.description.strip()}"
            )
        parts = [
            "Invoke a skill by typing `/skill-name <args>` (aliases also work), "
            "or call the `skill` tool with `name` (and optional `args`) to "
            "activate it yourself when the request matches a skill's purpose.",
            "Use a skill when the request matches its purpose.",
            "",
        ]
        for group_name in sorted(groups):
            parts.append(f"**{group_name}**")
            parts.extend(groups[group_name])
            parts.append("")
        return "\n".join(parts).rstrip()
