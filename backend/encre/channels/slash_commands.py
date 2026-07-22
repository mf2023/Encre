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

"""Encre slash-command registry.

Slash commands (``/plan``, ``/spec``, project/user ``*.md`` command files, ...)
are modelled as :class:`SlashCommandDef` records and aggregated in
:class:`EncreCommandRegistry`, which merges sources by priority
(builtin < user < project < bundled) and resolves aliases.  This module also
parses terminal-only commands and exposes helpers used by the desktop UI to
render the command palette.
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from encre.prompts.loader import PromptLoader
from encre.skills.registry import parse_yaml_frontmatter


class CommandSource(str, Enum):
    MANAGED = "managed"
    USER = "user"
    PROJECT = "project"
    BUNDLED = "bundled"


_COMMAND_PRIORITY: dict[CommandSource, int] = {
    CommandSource.MANAGED: 0,
    CommandSource.USER: 1,
    CommandSource.PROJECT: 2,
    CommandSource.BUNDLED: 3,
}


@dataclass(frozen=True)
class SlashCommandDef:
    name: str
    title: str
    description: str
    kind: Literal["mode", "action"]
    icon: str = "command"
    # Extended fields -- populated for file-backed commands, empty for
    # the hard-coded BUILTIN set.  Default values keep the dataclass
    # backwards-compatible with all existing call sites.
    argument_hint: str = ""
    prompt_body: str = ""
    source: CommandSource = CommandSource.BUNDLED
    file_path: str = ""
    aliases: tuple[str, ...] = ()
    availability: tuple[str, ...] = ()  # empty = all modes; e.g. ("iwork",)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "kind": self.kind,
            "icon": self.icon,
            "argument_hint": self.argument_hint,
            "source": self.source.value,
            "has_prompt_body": bool(self.prompt_body),
            "prompt": self.prompt_body,
            "file_path": self.file_path,
            "aliases": list(self.aliases),
            "availability": list(self.availability),
        }

    def render_prompt(self, args: str = "") -> str:
        """Return the prompt body with ``{{args}}`` substituted.

        Mirrors the ``{{args}}`` / ``{{arguments}}`` / ``{{user_input}}``
        placeholders supported by :mod:`encre.skills.registry` so command
        authors can use the same conventions for both surfaces.
        """
        body = self.prompt_body
        if not body:
            return body
        token = args or ""
        for placeholder in ("{{args}}", "{{arguments}}", "{{user_input}}"):
            body = body.replace(placeholder, token)
        return body


_prompt_loader = PromptLoader()

BUILTIN_SLASH_COMMANDS: tuple[SlashCommandDef, ...] = (
    SlashCommandDef(
        "plan", "Plan Mode",
        "Plan first, then run once you are ready",
        "mode", "list-checks",
    ),
    SlashCommandDef(
        "spec", "Spec Mode",
        "Write a spec before implementation",
        "mode", "list-checks",
    ),
    SlashCommandDef(
        "new-session", "New Session",
        "Start a fresh conversation",
        "action", "plus-circle",
    ),
    SlashCommandDef(
        "clear-session", "Clear Session",
        "Clear the current session",
        "action", "rotate-ccw",
    ),
    SlashCommandDef(
        "init", "Init Project",
        "Analyze project and generate workspace configuration",
        "action", "wand-sparkles",
        availability=("iwork",),
        prompt_body=_prompt_loader.load("init", category=""),
    ),
)


TERMINAL_SLASH_COMMANDS: tuple[SlashCommandDef, ...] = (
    SlashCommandDef("exit", "Exit", "Exit the terminal", "action"),
    SlashCommandDef("quit", "Quit", "Quit the terminal", "action"),
    SlashCommandDef("new", "New Session", "Start a fresh session", "action"),
    SlashCommandDef("clear", "Clear Session", "Clear the current session", "action"),
)


# Project-level command directories scanned under the active workspace.
# Kept in lock-step with the equivalent skill candidates in
# :mod:`encre.agent` so users can drop commands into either layout.
_PROJECT_COMMAND_CANDIDATE_DIRS: tuple[str, ...] = (
    ".encre/commands",
    ".claude/commands",
)

# User-level (global) command directories, relative to the home directory.
# These are scanned once per agent (not reloaded on workspace switch) so a
# user's personal commands (e.g. ``~/.claude/commands/commit.md``) are always
# available regardless of the active workspace.
_USER_COMMAND_CANDIDATE_DIRS: tuple[str, ...] = (
    ".claude/commands",
    ".encre/commands",
)


class EncreCommandRegistry:
    """File-backed slash-command registry with priority-based merging.

    Higher-priority sources override same-named commands from lower
    sources.  Builtin entries (``CommandSource.BUNDLED``) are seeded
    automatically so they remain available even when no project or
    user commands are present.
    """

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommandDef] = {}
        self._aliases: dict[str, str] = {}
        for cmd in BUILTIN_SLASH_COMMANDS:
            self.register(cmd)

    def register(self, command: SlashCommandDef) -> None:
        existing = self._commands.get(command.name)
        if existing is not None:
            new_priority = _COMMAND_PRIORITY.get(command.source, 3)
            old_priority = _COMMAND_PRIORITY.get(existing.source, 3)
            if new_priority >= old_priority:
                return
        self._commands[command.name] = command
        for alias in command.aliases:
            if not alias or alias == command.name:
                continue
            existing_alias = self._aliases.get(alias)
            if existing_alias is not None:
                existing_cmd = self._commands.get(existing_alias)
                if existing_cmd is not None:
                    new_priority = _COMMAND_PRIORITY.get(command.source, 3)
                    old_priority = _COMMAND_PRIORITY.get(existing_cmd.source, 3)
                    if new_priority >= old_priority:
                        continue
            self._aliases[alias] = command.name

    def lookup(self, name: str) -> SlashCommandDef | None:
        cmd = self._commands.get(name)
        if cmd is not None:
            return cmd
        resolved = self._aliases.get(name)
        if resolved is not None:
            return self._commands.get(resolved)
        return None

    def list_all(self) -> list[SlashCommandDef]:
        return list(self._commands.values())

    def clear_non_builtin(self) -> None:
        """Drop every command that is not part of the bundled set.

        Used before reloading project/user commands so stale entries do
        not linger after a directory disappears.
        """
        self._commands = {
            name: cmd
            for name, cmd in self._commands.items()
            if cmd.source == CommandSource.BUNDLED
        }
        self._aliases = {
            alias: target
            for alias, target in self._aliases.items()
            if target in self._commands
        }

    def clear_source(self, source: CommandSource) -> None:
        """Drop every command originating from *source*.

        Unlike :meth:`clear_non_builtin` this preserves other non-builtin
        sources -- e.g. clearing ``PROJECT`` on a workspace switch must not
        wipe user-level (``USER``) commands loaded from the home directory
        and ``settings.json``.
        """
        self._commands = {
            name: cmd
            for name, cmd in self._commands.items()
            if cmd.source != source
        }
        self._aliases = {
            alias: target
            for alias, target in self._aliases.items()
            if target in self._commands
        }

    def load_from_dir(self, commands_dir: str, source: CommandSource) -> int:
        """Load ``*.md`` command files from *commands_dir*.

        Returns the number of commands successfully registered.
        Files without a YAML frontmatter ``name:`` are skipped
        silently -- matching the tolerant behaviour of the skills
        registry.
        """
        if not os.path.isdir(commands_dir):
            return 0
        loaded = 0
        for entry in sorted(os.listdir(commands_dir)):
            full = os.path.join(commands_dir, entry)
            if not os.path.isfile(full):
                continue
            if not entry.lower().endswith(".md"):
                continue
            try:
                with open(full, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            cmd = _command_from_markdown(content, source, full)
            if cmd is None:
                continue
            self.register(cmd)
            loaded += 1
        return loaded


def _command_from_markdown(
    content: str, source: CommandSource, file_path: str
) -> SlashCommandDef | None:
    metadata, body = parse_yaml_frontmatter(content)
    raw_name = str(metadata.get("name", "")).strip()
    if not raw_name:
        return None
    name = raw_name.lower().replace("_", "-")
    title = str(metadata.get("title", name)).strip() or name
    description = str(metadata.get("description", "")).strip()
    kind_raw = str(metadata.get("kind", "action")).strip().lower()
    # There are no user-defined modes -- only the two built-ins (plan/spec)
    # are modes.  File-based commands are always actions (commands), even if
    # a frontmatter ``kind: mode`` is present, so they never get mistaken for
    # modes (no tool interception, no spec gate, no set_mode).
    kind: Literal["mode", "action"] = "action"
    _ = kind_raw  # kept for clarity; intentionally ignored
    icon = str(metadata.get("icon", "command")).strip() or "command"
    argument_hint = str(metadata.get("argument_hint", "")).strip()
    aliases_raw = metadata.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases = [a.strip().lower() for a in re.split(r"[,\s]+", aliases_raw) if a.strip()]
    elif isinstance(aliases_raw, list):
        aliases = [str(a).strip().lower() for a in aliases_raw if a]
    else:
        aliases = []
    return SlashCommandDef(
        name=name,
        title=title,
        description=description,
        kind=kind,
        icon=icon,
        argument_hint=argument_hint,
        prompt_body=body.strip(),
        source=source,
        file_path=file_path,
        aliases=tuple(aliases),
    )


def load_project_commands(
    workspace_path: str, registry: EncreCommandRegistry | None = None
) -> EncreCommandRegistry:
    """Load project-level commands for *workspace_path*.

    When *registry* is provided it is reused (and its **project** entries
    cleared first -- user-level entries are preserved).  Otherwise a fresh
    registry is created.  Existing builtin and user entries are preserved in
    either case.
    """
    reg = registry if registry is not None else EncreCommandRegistry()
    reg.clear_source(CommandSource.PROJECT)
    if not workspace_path:
        return reg
    for rel in _PROJECT_COMMAND_CANDIDATE_DIRS:
        full = os.path.join(workspace_path, rel)
        if os.path.isdir(full):
            reg.load_from_dir(full, CommandSource.PROJECT)
    return reg


def _command_from_settings_dict(d: dict, source: CommandSource,
                                file_path: str) -> SlashCommandDef | None:
    """Build a :class:`SlashCommandDef` from a settings.json command dict."""
    raw_name = str(d.get("name", "")).strip()
    if not raw_name:
        return None
    name = raw_name.lower().replace("_", "-")
    title = str(d.get("title", name)).strip() or name
    description = str(d.get("description", "")).strip()
    icon = str(d.get("icon", "command")).strip() or "command"
    argument_hint = str(d.get("argument_hint", "")).strip()
    prompt_body = str(d.get("prompt", "") or d.get("prompt_body", "")).strip()
    aliases_raw = d.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases = [a.strip().lower() for a in re.split(r"[,\s]+", aliases_raw) if a.strip()]
    elif isinstance(aliases_raw, list):
        aliases = [str(a).strip().lower() for a in aliases_raw if a]
    else:
        aliases = []
    # No user-defined modes -- settings commands are always actions.
    return SlashCommandDef(
        name=name,
        title=title,
        description=description,
        kind="action",
        icon=icon,
        argument_hint=argument_hint,
        prompt_body=prompt_body,
        source=source,
        file_path=file_path,
        aliases=tuple(aliases),
    )


def load_user_commands(
    registry: EncreCommandRegistry | None = None,
) -> EncreCommandRegistry:
    """Load user-level (global) commands into *registry*.

    Two sources, both tagged :attr:`CommandSource.USER`:

    * Home-directory ``*.md`` command files (``~/.claude/commands``,
      ``~/.encre/commands``) -- previously a dead code path
      (``CommandSource.USER`` had no loader).
    * ``custom_slash_commands`` stored in ``settings.json`` (frontend-managed
      JSON commands).

    User commands override project and bundled commands of the same name
    (``USER`` has higher priority than ``PROJECT``/``BUNDLED``).  This is
    called once per agent and is NOT re-run on workspace switch, so a user's
    personal commands persist across workspaces.  Existing ``USER`` entries
    are cleared first so a reload stays fresh.
    """
    reg = registry if registry is not None else EncreCommandRegistry()
    reg.clear_source(CommandSource.USER)
    home = os.path.expanduser("~")
    for rel in _USER_COMMAND_CANDIDATE_DIRS:
        full = os.path.join(home, rel)
        if os.path.isdir(full):
            reg.load_from_dir(full, CommandSource.USER)
    # Ingest settings.json custom_slash_commands so the backend registry is
    # the single source of truth surfaced via get_slash_command_defs.
    try:
        from encre.settings_manager import load_custom_slash_commands
        for entry in load_custom_slash_commands():
            if not isinstance(entry, dict):
                continue
            cmd = _command_from_settings_dict(entry, CommandSource.USER, "")
            if cmd is not None:
                reg.register(cmd)
    except Exception:
        pass
    return reg


def get_slash_command_defs(
    registry: EncreCommandRegistry | None = None,
) -> list[dict]:
    """Return all slash commands as plain dicts for the frontend.

    When *registry* is supplied, its commands are merged in front of
    the builtins so that project / user commands take priority.
    """
    if registry is None:
        return [cmd.to_dict() for cmd in BUILTIN_SLASH_COMMANDS]
    return [cmd.to_dict() for cmd in registry.list_all()]


def parse_terminal_slash_command(prompt: str) -> SlashCommandDef | None:
    """Parse a terminal prompt and return the matching slash command, if any."""
    text = prompt.strip()
    if not text.startswith("/"):
        return None
    name = text[1:].strip().lower()
    for cmd in TERMINAL_SLASH_COMMANDS:
        if cmd.name == name:
            return cmd
    return None
