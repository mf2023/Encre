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

"""Layered system-prompt builder.

Assembles the agent's system prompt from reusable *blocks*.  Each block has a
``priority`` (lower numbers are emitted earlier) and an optional ``condition``
list of intents that gate its inclusion.  :class:`EncrePromptBuilder` collects
core blocks, mode-specific blocks, slash-command blocks and a specialty block,
filters them by the active intents, sorts by priority, and concatenates them.

A ``__PROMPT_CACHE_BOUNDARY__`` marker is appended so callers can split the
static (cacheable) prefix from the dynamic (session-specific) suffix.
"""

from dataclasses import dataclass
from typing import Any

from encre.prompts.loader import PromptLoader
from encre.utils.types import PermissionMode

_loader = PromptLoader()

# ── Block definitions ──────────────────────────────────────────────


@dataclass
class PromptBlock:
    """A single reusable fragment of the system prompt.

    Attributes:
        priority: Emission order; lower values come first.
        name: Unique block identifier (later blocks may override earlier ones).
        content: Rendered prompt text.
        condition: Intents that must be present for inclusion; ``None`` means
            always include.
    """

    priority: int
    name: str
    content: str
    condition: list[str] | None = None  # intents that trigger this block; None = always

    def with_context(self, ctx: dict[str, str]) -> PromptBlock:
        """Return a copy with ``{{key}}`` placeholders replaced by *ctx* values."""
        content = self.content
        for key, val in ctx.items():
            content = content.replace(f"{{{{{key}}}}}", val)
        return PromptBlock(
            priority=self.priority, name=self.name, content=content,
            condition=self.condition,
        )


# ── Core presets ────────────────────────────────────────────────────


def _identity_block() -> PromptBlock:
    """Core identity/behaviour block, always included (highest priority 0)."""
    return PromptBlock(priority=0, name="identity", condition=None, content=_loader.load("identity"))


def _tool_usage_block(_tools: list[dict[str, Any]] | None = None) -> PromptBlock:
    """Tool-usage guidance block (the model's instructions for using tools)."""
    return PromptBlock(
        priority=5, name="tool_usage",
        condition=None,
        content=_loader.load("tool_usage"),
    )


def _permission_block(mode: PermissionMode) -> PromptBlock:
    """Permission/autonomy block describing how freely the agent may act."""
    if mode == "bypass":
        guidance = "You have full autonomy to execute any tool without asking for permission. Use this responsibly."
    elif mode == "dont_ask":
        guidance = "Execute tasks directly without asking for confirmation. Only pause if an operation appears destructive and irreversible."
    elif mode == "accept_edits":
        guidance = "You may read, write, and edit files freely. Shell commands and web requests may require confirmation."
    elif mode == "plan":
        guidance = "First create a clear plan. Present it to the user for approval before executing any changes."
    elif mode == "spec":
        guidance = "First produce a complete specification. Present it to the user for review and approval before writing any code or making changes."
    elif mode == "auto":
        guidance = "Most operations are auto-approved. Dangerous operations (rm -rf, chmod 777, etc.) require confirmation."
    else:
        guidance = "Ask for permission before executing tools that modify files, run shell commands, or access the network."

    return PromptBlock(
        priority=20, name="permission", condition=None,
        content=_loader.load_with_context("permission", mode=mode, guidance=guidance),
    )


def _language_block(lang_pref: str, app_lang: str) -> PromptBlock | None:
    """Language block forcing the response language (``zh``/``en``), or None."""
    resolved = lang_pref if lang_pref != "auto" else app_lang
    if resolved == "zh":
        instruction = "IMPORTANT: You must always respond in Chinese (中文) throughout the entire conversation. Even if the user writes in another language, you must reply in Chinese. Do not switch to other languages under any circumstances."
    elif resolved == "en":
        instruction = "IMPORTANT: You must always respond in English throughout the entire conversation. Even if the user writes in another language, you must reply in English. Do not switch to other languages under any circumstances."
    else:
        return None
    return PromptBlock(priority=25, name="language", condition=None, content=instruction)


def _output_format_block() -> PromptBlock:
    """Output-formatting block (inverted pyramid, diff format, no emojis)."""
    return PromptBlock(priority=30, name="output_format", condition=["general", "coding", "data"], content=_loader.load("output_format"))


def _safety_block() -> PromptBlock:
    """Safety/security block (secrets, data protection, risk framework)."""
    return PromptBlock(priority=5, name="safety", condition=None, content=_loader.load("safety"))


def _task_management_block() -> PromptBlock:
    """Task-management block (todo lists) for coding/data sessions."""
    return PromptBlock(priority=15, name="task_management", condition=["coding", "data"], content=_loader.load("task_management"))


def _specialty_coding_block() -> PromptBlock:
    """Specialty block for coding-domain guidance."""
    return PromptBlock(priority=100, name="specialty", condition=["coding"], content=_loader.load("specialty_coding"))


def _specialty_research_block() -> PromptBlock:
    """Specialty block for research-domain guidance."""
    return PromptBlock(priority=100, name="specialty", condition=["research"], content=_loader.load("specialty_research"))


def _specialty_data_block() -> PromptBlock:
    """Specialty block for data-analysis-domain guidance."""
    return PromptBlock(priority=100, name="specialty", condition=["data"], content=_loader.load("specialty_data"))


def _specialty_general_block() -> PromptBlock:
    """Fallback specialty block used when no specific intent is detected."""
    return PromptBlock(priority=100, name="specialty", condition=None, content=_loader.load("specialty_general"))


def _iwork_block(workspace_root: str, workspace_name: str, project_summary: str = "") -> PromptBlock:
    """Workspace (iWork) mode block describing the project and its files."""
    ctx = dict(workspace_name=workspace_name, workspace_root=workspace_root)
    content = _loader.load_with_context("workspace_mode", **ctx)
    if project_summary:
        snapshot = f"\n\n### Project Snapshot\n{project_summary}"
        content = content.replace("{{project_snapshot}}", snapshot)
    else:
        content = content.replace("{{project_snapshot}}", "")
    return PromptBlock(priority=2, name="iwork", condition=None, content=content)


def _plan_mode_block() -> PromptBlock:
    """Plan-mode block: instruct the model to plan, not execute."""
    content = _loader.load("plan_mode", category="modes")
    return PromptBlock(priority=195, name="plan_mode", condition=None, content=content)


def _spec_mode_block() -> PromptBlock:
    """Spec-mode block: instruct the model to specify, not implement."""
    content = _loader.load("spec_mode", category="modes")
    return PromptBlock(priority=195, name="spec_mode", condition=None, content=content)


def _command_instructions_block(name: str, body: str) -> PromptBlock:
    """Active-command block: sticky one-shot-style prompt injection.

    A slash *command* (built-in action or user-defined ``*.md`` command) is
    NOT a mode.  Its prompt body is injected every turn while active, but it
    must never be confused with plan/spec: there is no tool interception and
    no spec gate.  The block is framed explicitly so the model treats it as
    supplementary instructions rather than a mode declaration.
    """
    name = (name or "").strip()
    body = (body or "").strip()
    if not name:
        return PromptBlock(priority=190, name="command_instructions",
                           condition=None, content="")
    parts = [
        f"## Active Command: /{name}",
        "",
        "These are **command instructions**, active for this session until "
        "the user clears them. This is **NOT a mode** - the operating mode "
        "(normal / plan / spec) is unchanged and its rules still apply. "
        "Treat the text below as additional instructions to follow alongside "
        "the active mode; do not declare yourself to be in a new mode.",
        "",
        body,
    ]
    return PromptBlock(priority=190, name="command_instructions",
                       condition=None, content="\n".join(parts))


def _slash_commands_block(
    slash_command_mode: str, slash_commands: list[dict[str, Any]] | None,
    active_command_name: str = "",
) -> PromptBlock:
    """Inform the model about available slash commands and the active mode."""
    commands = slash_commands or []
    lines: list[str] = ["## Slash Commands"]
    if slash_command_mode:
        lines.append(
            f"The current session is in **/{slash_command_mode}** mode. "
            "Follow the mode instructions above for this turn. "
            "This is authoritative -- when asked which mode you are in, "
            f"answer **{slash_command_mode} mode**."
        )
    else:
        # Normal mode is an explicit, declared state -- not "no mode".
        # Without this, the model can misread the internal "Work Phase"
        # (discover/execute/...) hint as the current mode and answer
        # e.g. "discover mode" when asked.
        lines.append(
            "The current session is in **normal mode** (no plan/spec mode "
            "is active). When asked which mode you are in, answer "
            "**normal mode**. The 'Work Phase' hint elsewhere is an "
            "internal scheduling cue, not a mode."
        )
    if active_command_name:
        # A command may be active alongside (or instead of) a mode.  State
        # it explicitly so the model does not mistake the command's injected
        # instructions for a mode declaration.
        lines.append(
            f"A slash **command** ``/{active_command_name}`` is active. A "
            "command is NOT a mode - it only injects extra instructions for "
            "this turn. The session mode above is unchanged by the command."
        )
    if commands:
        modes = [c for c in commands if c.get("kind") == "mode"]
        actions = [c for c in commands if c.get("kind", "action") != "mode"]
        if modes:
            lines.append("Available modes:")
            for cmd in modes:
                name = cmd.get("name", "")
                title = cmd.get("title", name)
                description = cmd.get("description", "")
                lines.append(f"- /{name}: {title}{f' -- {description}' if description else ''}")
        if actions:
            lines.append("Available commands:")
            for cmd in actions:
                name = cmd.get("name", "")
                title = cmd.get("title", name)
                description = cmd.get("description", "")
                lines.append(f"- /{name}: {title}{f' -- {description}' if description else ''}")
    else:
        lines.append("No slash commands are available.")
    content = "\n".join(lines)
    return PromptBlock(priority=48, name="slash_commands", condition=None, content=content)


def _skills_block(skill_summary: str = "") -> PromptBlock | None:
    """Dynamic skill catalogue: what skills are available and when to use them.

    Replaces the hard-coded skill lists previously baked into mode/specialty
    prompt blocks.  ``skill_summary`` is pre-rendered by the caller (the loop,
    from the live skill registry) so this module stays free of a registry
    dependency.  Returns ``None`` when no summary is provided.
    """
    if not skill_summary or not skill_summary.strip():
        return None
    content = "## Skills (auto-discovered)\n\n" + skill_summary.strip()
    return PromptBlock(priority=47, name="skills", condition=None, content=content)


def _normal_mode_block(session_id: str = "") -> PromptBlock:
    """Normal (non-workspace) mode block with the session files directory."""
    from encre.tools.builtin._sandbox import get_session_files_dir
    files_root = str(get_session_files_dir(session_id))
    content = _loader.load_with_context("general_mode", files_root=files_root)
    return PromptBlock(priority=2, name="mode", condition=None, content=content)


def _environment_block(workspace_root: str = "") -> PromptBlock:
    """Environment block: OS, shell hints, cwd, and git-repo detection."""
    import os as _os
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

    # CC-style <env> facts: working directory + whether it is a git repo.
    cwd = workspace_root or _os.getcwd()
    is_git = _os.path.isdir(_os.path.join(cwd, ".git"))
    env_facts = (
        f"Working directory: {cwd}\n"
        f"Is directory a git repo: {'Yes' if is_git else 'No'}\n"
    )

    content = (
        f"## Environment\n"
        f"{env_facts}"
        f"\n"
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
        """Register or override a block by its ``name``."""
        self._blocks[block.name] = block

    def remove_block(self, name: str) -> None:
        """Remove a previously registered block (no-op if absent)."""
        self._blocks.pop(name, None)

    def add_custom_instructions(self, text: str) -> None:
        """Add user-provided custom instructions at the highest priority."""
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
        skill_summary: str = "",
        active_command: dict[str, Any] | None = None,
    ) -> str:
        """Assemble the full system prompt from the active blocks.

        Collects core, mode, slash-command, skill-catalogue and specialty
        blocks, filters them by the active intents, sorts by priority,
        concatenates, and appends the prompt-cache boundary marker.
        """
        intents = intents or ["general"]

        # Collect blocks
        blocks: dict[str, PromptBlock] = dict(self._blocks)

        # Mode header -- iWork takes priority over normal
        if workspace_root:
            mode_block = _iwork_block(workspace_root, workspace_name or workspace_root, project_summary)
        else:
            mode_block = _normal_mode_block(session_id)
        blocks[mode_block.name] = mode_block

        # Always-add core blocks (if not overridden)
        defaults = [
            _identity_block(),
            _safety_block(),
            _current_datetime_block(),
            _environment_block(workspace_root),
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
            blocks["slash_commands"] = _slash_commands_block(
                slash_command_mode, slash_commands,
                active_command_name=(active_command or {}).get("name", ""),
            )

        # Active slash *command* (not a mode): sticky prompt injection,
        # re-applied every turn while active.  Explicitly framed so the
        # model never mistakes it for a mode declaration.
        if active_command and active_command.get("name"):
            if "command_instructions" not in blocks:
                blocks["command_instructions"] = _command_instructions_block(
                    active_command.get("name", ""),
                    active_command.get("prompt", ""),
                )

        # Dynamic skill catalogue (replaces hard-coded skill lists in mode prompts).
        if "skills" not in blocks:
            skills_block = _skills_block(skill_summary)
            if skills_block is not None:
                blocks["skills"] = skills_block

        # Specialty block (if not overridden)
        if "specialty" not in blocks:
            specialty_map: dict[str, PromptBlock] = {}
            # A specialty can be triggered either by an active intent (derived
            # from the tool surface) or by an explicit ``specialty`` argument
            # (e.g. EncreCodingPrompt forces "coding").  Union both sources so
            # either path produces the right block.
            active = set(intents)
            if specialty:
                active.add(specialty)
            if "coding" in active:
                specialty_map["coding"] = _specialty_coding_block()
            if "research" in active:
                specialty_map["research"] = _specialty_research_block()
            if "data" in active:
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

        # Filter by condition, then sort by priority, then assemble.
        # A block is kept when its condition is empty, or when any active intent
        # OR the explicit ``specialty`` argument matches the condition.  This
        # lets e.g. EncreCodingPrompt (which forces specialty="coding" with no
        # coding intent) still surface the coding specialty block.
        filter_keys = set(intents)
        if specialty:
            filter_keys.add(specialty)
        filtered: list[PromptBlock] = []
        for block in blocks.values():
            if block.condition is None or any(i in block.condition for i in filter_keys):
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
