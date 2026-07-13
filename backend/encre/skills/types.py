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

"""Skill type definitions.

Defines the enums (:class:`SkillContext`, :class:`SkillSource`), the source
priority ordering, and the :class:`BundledSkillDefinition` dataclass that
describes a single registered skill.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillContext(str, Enum):
    """Where a skill's prompt is injected when activated."""

    INLINE = "inline"
    FORK = "fork"


class SkillSource(str, Enum):
    """Origin of a skill definition (lower number = higher precedence)."""

    MANAGED = "managed"
    USER = "user"
    PROJECT = "project"
    BUNDLED = "bundled"


# Priority ordering for skill sources: managed overrides user, user overrides
# project, project overrides bundled.  Used during registration conflict resolution.
_PRIORITY_ORDER: dict[SkillSource, int] = {
    SkillSource.MANAGED: 0,
    SkillSource.USER: 1,
    SkillSource.PROJECT: 2,
    SkillSource.BUNDLED: 3,
}


@dataclass
class BundledSkillDefinition:
    """A registered skill: its metadata plus a callable that renders its prompt.

    Attributes:
        name: Unique skill identifier (lowercase, hyphen-separated).
        description: Short human-readable summary.
        get_prompt_for_command: Coroutine returning the skill's prompt for the
            given arguments and context.
        aliases: Alternative names that resolve to this skill.
        when_to_use: File-extension hints that trigger auto-activation.
        argument_hint: Usage hint for the argument string.
        allowed_tools: Tool names the skill is permitted to use (``None`` = all).
        model: Optional model override for the skill.
        disable_model_invocation: If true, the skill only emits instructions.
        user_invocable: Whether the skill can be invoked by the user directly.
        context: :class:`SkillContext` (inline or forked sub-agent).
        source: :class:`SkillSource` provenance.
        file_path: Path to the source SKILL.md, if loaded from disk.
        body: Raw prompt body loaded from the skill file.
        hidden: Hide from user-facing skill listings.
        auto_activate: If true, auto-activate when a referenced file matches ``when_to_use`` extensions.
        license: Agent-Skills standard ``license`` field.
        compatibility: Agent-Skills standard ``compatibility`` field.
        metadata: Arbitrary extra metadata key/value pairs.
    """

    name: str
    description: str
    get_prompt_for_command: Callable[[str | None, dict[str, Any]], Awaitable[str]]
    aliases: list[str] = field(default_factory=list)
    when_to_use: str = ""
    argument_hint: str = ""
    allowed_tools: list[str] | None = None
    model: str | None = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: SkillContext = SkillContext.INLINE
    source: SkillSource = SkillSource.BUNDLED
    file_path: str = ""
    body: str = ""
    hidden: bool = False
    auto_activate: bool = False
    # Agent Skills standard fields
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
