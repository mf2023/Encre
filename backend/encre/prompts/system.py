#!/usr/bin/env python3

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

from dataclasses import dataclass
from typing import Any

from encre.prompts.loader import PromptLoader
from encre.utils.types import PermissionMode

_loader = PromptLoader()

# ── Block definitions ──────────────────────────────────────────────


@dataclass
class PromptBlock:
    priority: int
    name: str
    content: str
    condition: list[str] | None = None  # intents that trigger this block; None = always

    def with_context(self, ctx: dict[str, str]) -> PromptBlock:
        content = self.content
        for key, val in ctx.items():
            content = content.replace(f"{{{{{key}}}}}", val)
        return PromptBlock(
            priority=self.priority, name=self.name, content=content,
            condition=self.condition,
        )


# ── Core presets ────────────────────────────────────────────────────


def _identity_block() -> PromptBlock:
    return PromptBlock(priority=0, name="identity", condition=None, content=_loader.load("identity"))  # noqa: E501


def _tool_usage_block(_tools: list[dict[str, Any]] | None = None) -> PromptBlock:
    return PromptBlock(
        priority=5, name="tool_usage",
        condition=None,
        content=_loader.load("tool_usage"),
    )


def _permission_block(mode: PermissionMode) -> PromptBlock:
    if mode == "bypass":
        guidance = "You have full autonomy to execute any tool without asking for permission. Use this responsibly."  # noqa: E501
    elif mode == "dont_ask":
        guidance = "Execute tasks directly without asking for confirmation. Only pause if an operation appears destructive and irreversible."  # noqa: E501
    elif mode == "accept_edits":
        guidance = "You may read, write, and edit files freely. Shell commands and web requests may require confirmation."  # noqa: E501
    elif mode == "plan":
        guidance = "First create a clear plan. Present it to the user for approval before executing any changes."  # noqa: E501
    elif mode == "spec":
        guidance = "First produce a complete specification. Present it to the user for review and approval before writing any code or making changes."  # noqa: E501
    elif mode == "auto":
        guidance = "Most operations are auto-approved. Dangerous operations (rm -rf, chmod 777, etc.) require confirmation."  # noqa: E501
    else:
        guidance = "Ask for permission before executing tools that modify files, run shell commands, or access the network."  # noqa: E501

    return PromptBlock(
        priority=20, name="permission", condition=None,
        content=_loader.load_with_context("permission", mode=mode, guidance=guidance),
    )


def _language_block(lang_pref: str, app_lang: str) -> PromptBlock | None:
    resolved = lang_pref if lang_pref != "auto" else app_lang
    if resolved == "zh":
        instruction = "IMPORTANT: You must always respond in Chinese (中文) throughout the entire conversation. Even if the user writes in another language, you must reply in Chinese. Do not switch to other languages under any circumstances."  # noqa: E501
    elif resolved == "en":
        instruction = "IMPORTANT: You must always respond in English throughout the entire conversation. Even if the user writes in another language, you must reply in English. Do not switch to other languages under any circumstances."  # noqa: E501
    else:
        return None
    return PromptBlock(priority=25, name="language", condition=None, content=instruction)


def _output_format_block() -> PromptBlock:
    return PromptBlock(priority=30, name="output_format", condition=["general", "coding", "data"], content=_loader.load("output_format"))  # noqa: E501


def _safety_block() -> PromptBlock:
    return PromptBlock(priority=5, name="safety", condition=None, content=_loader.load("safety"))


def _task_management_block() -> PromptBlock:
    return PromptBlock(priority=15, name="task_management", condition=["coding", "data"], content=_loader.load("task_management"))  # noqa: E501


def _specialty_coding_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["coding"], content=_loader.load("specialty_coding"))  # noqa: E501


def _specialty_research_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["research"], content=_loader.load("specialty_research"))  # noqa: E501


def _specialty_data_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["data"], content=_loader.load("specialty_data"))  # noqa: E501


def _specialty_general_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=None, content=_loader.load("specialty_general"))  # noqa: E501


def _iwork_block(workspace_root: str, workspace_name: str, project_summary: str = "") -> PromptBlock:  # noqa: E501
    ctx = dict(workspace_name=workspace_name, workspace_root=workspace_root)
    content = _loader.load_with_context("workspace_mode", **ctx)
    if project_summary:
        snapshot = f"\n\n### Project Snapshot\n{project_summary}"
        content = content.replace("{{project_snapshot}}", snapshot)
    else:
        content = content.replace("{{project_snapshot}}", "")
    return PromptBlock(priority=2, name="iwork", condition=None, content=content)


def _plan_mode_block() -> PromptBlock:
    content = _loader.load("planner", category="skills")
    content = content.replace(
        "## Planner Sub-Agent -- Task Breakdown Specialist",
        "## Planning Mode -- Present a Plan, Do Not Execute",
    )
    content = content.replace(
        "You are a planning sub-agent. Your job is to break down a goal into "
        "concrete, actionable tasks.",
        "You are in **planning mode**. Your job is to ANALYZE and PLAN -- NEVER "
        "to execute. Present a clear, structured plan to the user for approval "
        "before any changes are made. Break the goal into concrete, actionable "
        "steps with dependencies and effort estimates.",
    )
    return PromptBlock(priority=50, name="plan_mode", condition=None, content=content)


def _spec_mode_block() -> PromptBlock:
    content = _loader.load("spec_writer", category="skills")
    content = content.replace(
        "## Spec Writer Sub-Agent -- Requirements & Specification Specialist\n\n"
        "You are a specification sub-agent. Your job is to transform ambiguous "
        "requirements into precise, complete, and actionable specifications.",
        "## Specification Mode -- Specify Requirements, Do Not Implement\n\n"
        "You are in **specification mode**. Your job is to produce a complete, "
        "precise specification -- NOT to write code. Transform the requirements "
        "into a detailed, actionable specification that covers all states (happy "
        "path, edge cases, errors). Present the spec for user review before any "
        "implementation begins.",
    )
    return PromptBlock(priority=50, name="spec_mode", condition=None, content=content)


def _slash_commands_block(
    slash_command_mode: str, slash_commands: list[dict[str, Any]] | None
) -> PromptBlock:
    """Inform the model about available slash commands and the active mode."""
    commands = slash_commands or []
    lines: list[str] = ["## Slash Commands"]
    if slash_command_mode:
        lines.append(
            f"The current session is in **/{slash_command_mode}** mode. "
            "Follow the mode instructions above for this turn."
        )
    if commands:
        lines.append("Available slash commands:")
        for cmd in commands:
            name = cmd.get("name", "")
            title = cmd.get("title", name)
            description = cmd.get("description", "")
            lines.append(f"- /{name}: {title}{f' -- {description}' if description else ''}")
    else:
        lines.append("No slash commands are available.")
    content = "\n".join(lines)
    return PromptBlock(priority=48, name="slash_commands", condition=None, content=content)


def _normal_mode_block(session_id: str = "") -> PromptBlock:
    from encre.tools.builtin._sandbox import get_session_files_dir
    files_root = str(get_session_files_dir(session_id))
    content = _loader.load_with_context("general_mode", files_root=files_root)
    return PromptBlock(priority=2, name="mode", condition=None, content=content)


def _environment_block() -> PromptBlock:
    import platform as _platform
    import sys as _sys

    os_name = _platform.system() or _sys.platform
    if os_name == "Windows":
        details = f"Windows {_platform.version()} ({_platform.machine()})"
        shell_hint = (
            "You are on **Windows**.  The shell is `cmd.exe` — use **Windows commands**:\n"
            "  • `dir` instead of `ls`        • `type` instead of `cat`\n"
            "  • `find` / `findstr` instead of `grep` / `find`\n"
            "  • `copy` instead of `cp`       • `move` / `ren` instead of `mv`\n"
            "  • `del` instead of `rm`         • `mkdir` / `rmdir` instead of `mkdir` / `rm -rf`\n"
            "  • `echo` works the same way     • `cd` works the same way\n"
            "File paths use **backslashes** (`\\\\`).  PowerShell commands also work.\n"
            "**Do NOT** output Linux/bash commands like `ls`, `cat`, `grep`, `rm -rf`, `cp`, `mv`."
        )
    elif os_name == "Darwin":
        details = f"macOS {_platform.mac_ver()[0]} ({_platform.machine()})"
        shell_hint = (
            "You are on **macOS**.  The shell is `bash`/`zsh` — use Unix commands.\n"
            "File paths use forward slashes (`/`)."
        )
    elif os_name == "Linux":
        details = f"Linux ({_platform.machine()})"
        shell_hint = (
            "You are on **Linux**.  The shell is `bash` — use standard Unix commands.\n"
            "File paths use forward slashes (`/`)."
        )
    else:
        details = os_name
        shell_hint = ""

    content = (
        f"## Operating System\n"
        f"**{os_name}** -- {details}\n"
        f"{shell_hint}"
    ).strip()
    return PromptBlock(priority=8, name="environment", condition=None, content=content)


def _current_datetime_block() -> PromptBlock:
    """Inject current date and time so the model has temporal awareness.
    The model's training data has a knowledge cutoff; this block explicitly
    overrides it with the real current date."""
    from datetime import datetime as _dt
    now = _dt.now()
    year = now.year
    content = (
        f"## Current Date & Time\n"
        f"Today is: **{now.strftime('%A, %B %d, %Y')}**\n"
        f"Current time: **{now.strftime('%H:%M:%S')}**\n"
        f"\n"
        f"**IMPORTANT: The current year is {year}.** Your training data may have\n"
        f"an earlier cutoff date, but the actual current date is {year}.\n"
        f"Use this information when the task involves time-sensitive topics,\n"
        f"news, events, scheduling, or any scenario where recency matters."
    ).strip()
    return PromptBlock(priority=9, name="current_datetime", condition=None, content=content)


# ── Builder ─────────────────────────────────────────────────────────


class EncrePromptBuilder:
    """Layered system prompt builder with priority-based block assembly."""

    def __init__(self) -> None:
        self._blocks: dict[str, PromptBlock] = {}

    def add_block(self, block: PromptBlock) -> None:
        self._blocks[block.name] = block

    def remove_block(self, name: str) -> None:
        self._blocks.pop(name, None)

    def add_custom_instructions(self, text: str) -> None:
        self.add_block(PromptBlock(priority=200, name="custom", content=text))

    def build(
        self,
        mode: PermissionMode = "default",
        tools: list[dict[str, Any]] | None = None,
        specialty: str = "general",
        custom_instructions: str = "",
        intents: list[str] | None = None,
        workspace_root: str = "",
        workspace_name: str = "",
        project_summary: str = "",
        language_preference: str = "auto",
        app_language: str = "zh",
        session_id: str = "",
        slash_command_mode: str = "",
        slash_commands: list[dict[str, Any]] | None = None,
    ) -> str:
        intents = intents or ["general"]

        # Collect blocks
        blocks: dict[str, PromptBlock] = dict(self._blocks)

        # Mode header -- iWork takes priority over normal
        if workspace_root:
            mode_block = _iwork_block(workspace_root, workspace_name or workspace_root, project_summary)  # noqa: E501
        else:
            mode_block = _normal_mode_block(session_id)
        blocks[mode_block.name] = mode_block

        # Always-add core blocks (if not overridden)
        defaults = [
            _identity_block(),
            _safety_block(),
            _current_datetime_block(),
            _environment_block(),
            _tool_usage_block(tools),
            _task_management_block(),
            _permission_block(mode),
            _language_block(language_preference, app_language),
            _output_format_block(),
        ]
        for block in defaults:
            if block is not None and block.name not in blocks:
                blocks[block.name] = block

        # Slash command mode blocks -- inject detailed instructions when active.
        # The slash command mode is independent of the permission mode.
        if slash_command_mode == "plan" and "plan_mode" not in blocks:
            blocks["plan_mode"] = _plan_mode_block()
        elif slash_command_mode == "spec" and "spec_mode" not in blocks:
            blocks["spec_mode"] = _spec_mode_block()

        # Inform the model about available slash commands and the active mode.
        if "slash_commands" not in blocks:
            blocks["slash_commands"] = _slash_commands_block(slash_command_mode, slash_commands)

        # Specialty block (if not overridden)
        if "specialty" not in blocks:
            specialty_map: dict[str, PromptBlock] = {}
            if "coding" in intents:
                specialty_map["coding"] = _specialty_coding_block()
            if "research" in intents:
                specialty_map["research"] = _specialty_research_block()
            if "data" in intents:
                specialty_map["data"] = _specialty_data_block()
            # specific specialty takes priority, fall back to general
            if specialty in specialty_map:
                blocks["specialty"] = specialty_map[specialty]
            elif specialty_map:
                blocks["specialty"] = next(iter(specialty_map.values()))
            else:
                blocks["specialty"] = _specialty_general_block()

        # Custom instructions
        if custom_instructions:
            blocks["custom"] = PromptBlock(
                priority=200, name="custom", condition=None, content=custom_instructions,
            )

        # Filter by condition, then sort by priority, then assemble
        filtered: list[PromptBlock] = []
        for block in blocks.values():
            if block.condition is None or any(i in block.condition for i in intents):
                filtered.append(block)

        sorted_blocks = sorted(filtered, key=lambda b: b.priority)
        parts: list[str] = []
        for block in sorted_blocks:
            content = block.content.strip()
            if content:
                parts.append(content)

        prompt = "\n\n".join(parts)

        # Prompt caching boundary: everything above is static/cacheable,
        # everything below is dynamic/session-specific.
        prompt += "\n\n__PROMPT_CACHE_BOUNDARY__\n"

        return prompt

    def build_with_context(
        self,
        ctx: dict[str, str],
        mode: PermissionMode = "default",
        tools: list[dict[str, Any]] | None = None,
        specialty: str = "general",
    ) -> str:
        """Build with template variable substitution ({{key}} replaced by ctx values)."""
        prompt = self.build(mode=mode, tools=tools, specialty=specialty)
        for key, val in ctx.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", val)
        return prompt
