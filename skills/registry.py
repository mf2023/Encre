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

import os
import re
from typing import Any

from yim.skills.types import (
    BundledSkillDefinition,
    SkillContext,
    SkillSource,
    _PRIORITY_ORDER,
)

_EXTENSIONS_HEADER_PATTERN = re.compile(
    r"\.\w+$",
    re.IGNORECASE,
)

_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.MULTILINE | re.DOTALL,
)

_KEY_VALUE_PATTERN = re.compile(r"^\s*(\w[\w\s]*?)\s*:\s*(.*?)\s*$")

_ALIASES_SEPARATOR = re.compile(r",\s*")


class YmiSkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BundledSkillDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, skill: BundledSkillDefinition) -> None:
        existing = self._skills.get(skill.name)
        if existing is not None:
            new_priority = _PRIORITY_ORDER.get(skill.source, 3)
            old_priority = _PRIORITY_ORDER.get(existing.source, 3)
            if new_priority >= old_priority:
                return
        self._skills[skill.name] = skill
        for alias in skill.aliases:
            existing_alias = self._aliases.get(alias)
            if existing_alias is not None:
                existing_skill = self._skills.get(existing_alias)
                if existing_skill is not None:
                    new_priority = _PRIORITY_ORDER.get(skill.source, 3)
                    old_priority = _PRIORITY_ORDER.get(existing_skill.source, 3)
                    if new_priority >= old_priority:
                        continue
            self._aliases[alias] = skill.name

    def lookup(self, name: str) -> BundledSkillDefinition | None:
        skill = self._skills.get(name)
        if skill is not None:
            return skill
        resolved = self._aliases.get(name)
        if resolved is not None:
            return self._skills.get(resolved)
        return None

    async def activate(
        self,
        name: str,
        args: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        skill = self.lookup(name)
        if skill is None:
            return f"Error: skill '{name}' not found."
        ctx = context or {}
        try:
            prompt = await skill.get_prompt_for_command(args, ctx)
            return prompt
        except Exception as e:
            return f"Error activating skill '{name}': {e}"

    async def activate_for_paths(self, file_paths: list[str]) -> list[str]:
        prompts: list[str] = []
        seen: set[str] = set()
        for file_path in file_paths:
            match = _EXTENSIONS_HEADER_PATTERN.search(file_path)
            if match is None:
                continue
            ext = match.group(0).lower()
            for skill in self._skills.values():
                if skill.when_to_use and ext in skill.when_to_use.lower():
                    if skill.name not in seen:
                        seen.add(skill.name)
                        prompts.append(skill.name)
        return prompts

    def load_from_dir(
        self,
        skills_dir: str,
        source: SkillSource = SkillSource.PROJECT,
    ) -> None:
        if not os.path.isdir(skills_dir):
            return
        for root, dirs, files in os.walk(skills_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                if filename.upper() != "SKILL.MD":
                    continue
                filepath = os.path.join(root, filename)
                self._load_skill_md(filepath, source)

    def _load_skill_md(self, filepath: str, source: SkillSource) -> None:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return

        metadata = _parse_frontmatter(content)
        name = metadata.get("name")
        if not name:
            return

        body_start = _find_body_start(content)
        body = content[body_start:].strip()

        description = metadata.get("description", "")
        aliases_raw = metadata.get("aliases", "")
        when_to_use = metadata.get("when_to_use", "")
        argument_hint = metadata.get("argument_hint", "")
        allowed_tools_raw = metadata.get("allowed_tools", "")
        model = metadata.get("model")
        disable_model = _parse_bool(metadata.get("disable_model_invocation", "false"))
        user_invocable = _parse_bool(metadata.get("user_invocable", "true"))
        context_raw = metadata.get("context", "inline")
        context_enum = SkillContext(context_raw) if context_raw in ("inline", "fork") else SkillContext.INLINE

        allowed_tools: list[str] | None = None
        if allowed_tools_raw.strip():
            allowed_tools = [t.strip() for t in _ALIASES_SEPARATOR.split(allowed_tools_raw) if t.strip()]

        async def get_prompt(
            args: str | None = None,
            ctx: dict[str, Any] | None = None,
        ) -> str:
            resolved = body
            if args is not None:
                resolved = resolved.replace("{{args}}", args)
                resolved = resolved.replace("{{arguments}}", args)
                resolved = resolved.replace("{{user_input}}", args)
            if ctx is not None:
                for key, value in ctx.items():
                    resolved = resolved.replace(f"{{{{{key}}}}}", str(value))
            return resolved

        skill = BundledSkillDefinition(
            name=name,
            description=description,
            get_prompt_for_command=get_prompt,
            aliases=[a.strip() for a in _ALIASES_SEPARATOR.split(aliases_raw) if a.strip()],
            when_to_use=when_to_use,
            argument_hint=argument_hint,
            allowed_tools=allowed_tools,
            model=model if model else None,
            disable_model_invocation=disable_model,
            user_invocable=user_invocable,
            context=context_enum,
            source=source,
            file_path=filepath,
        )
        self.register(skill)

    def list_all(self) -> list[BundledSkillDefinition]:
        return list(self._skills.values())


def _parse_frontmatter(content: str) -> dict[str, str]:
    match = _FRONTMATTER_PATTERN.match(content)
    if match is None:
        return {}
    frontmatter_text = match.group(1)
    metadata: dict[str, str] = {}
    for line in frontmatter_text.split("\n"):
        kv_match = _KEY_VALUE_PATTERN.match(line)
        if kv_match:
            key = kv_match.group(1).strip().lower().replace(" ", "_")
            value = kv_match.group(2).strip()
            metadata[key] = value
    return metadata


def _find_body_start(content: str) -> int:
    match = _FRONTMATTER_PATTERN.match(content)
    if match is None:
        return 0
    return match.end()


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")
