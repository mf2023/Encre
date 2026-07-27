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

"""Auto-generation of skills from repeated tool-use patterns.

This module turns a flat list of tool names (produced while an agent runs) into
a structured, reusable :term:`skill`. The work happens in two phases:

1. :meth:`SkillGenerator.generate` reduces the tool names to a frequency
   histogram, keeps the most-used entries, and builds a skill definition
   dictionary: a markdown ``body`` plus metadata such as ``name``,
   ``description``, ``when_to_use`` and ``reason``. A caller-supplied
   ``enrich_fn`` may override the generated description/steps with richer
   content; if it raises, the generator falls back to its own defaults.
2. :meth:`SkillGenerator.register` pushes the definition into the agent's
   ``skill_registry`` (in memory) and also writes a YAML-frontmatter markdown
   file under the project's ``skills/auto_generated`` data directory so the
   skill survives restarts.

The skill body is templated: placeholders such as ``{{args}}``,
``{{arguments}}`` and ``{{user_input}}`` are substituted at prompt-resolution
time, and any ``ctx`` keys supplied by the caller are also interpolated.

Note that :meth:`generate` is synchronous and pure (it only reads its inputs),
while :meth:`register` is a coroutine because it touches the async skill
registry and the filesystem.
"""

import contextlib
import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from encre.agent import EncreAgent

logger = logging.getLogger("encre.learning.skill_generator")


class SkillGenerator:
    """Builds and registers skills from a detected tool pattern.

    The generator is stateless apart from its two constructor collaborators: the
    owning ``agent`` (reached lazily to obtain the skill registry at registration
    time) and an optional ``enrich_fn`` callback that may inject richer metadata
    than the built-in heuristics produce.

    Typical usage::

        gen = SkillGenerator(agent, enrich_fn=my_enricher)
        skill_def = gen.generate(tool_names, prompt)
        if skill_def is not None:
            await gen.register(skill_def)

    Attributes
    ----------
    _agent:
        The agent whose ``skill_registry`` the generated skill is registered
        against. Never used during :meth:`generate`.
    _enrich_fn:
        Optional ``(tool_names, prompt) -> dict`` callback. May return any of
        ``description``, ``when_to_use``, ``steps`` and ``reason``; returned
        values override the generator's own defaults. If it raises, the failure
        is swallowed and defaults are used instead.
    """

    def __init__(
        self,
        agent: EncreAgent,
        *,
        enrich_fn: Callable[[list[str], str], dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the generator with its agent and optional enricher.

        Args:
            agent: The agent that owns the skill registry used by
                :meth:`register`. Stored for later, lazy access.
            enrich_fn: Optional callback invoked during :meth:`generate` to
                provide higher-quality metadata. It receives the tool names and
                prompt and must return a dict; any missing keys fall back to the
                generator's heuristics.

        Returns:
            None.
        """
        self._agent = agent
        self._enrich_fn = enrich_fn

    def generate(self, tool_names: list[str], prompt: str) -> dict[str, Any] | None:
        """Produce a skill-definition dict from a tool-frequency pattern.

        Counts how often each tool name appears, keeps the five most frequent,
        derives a stable skill name from a hash of the prompt, and assembles a
        markdown body. If an ``enrich_fn`` was supplied it is consulted first
        for ``description`` / ``when_to_use`` / ``steps`` / ``reason``; anything
        it does not provide is filled by the built-in ``_build_*`` helpers.

        Args:
            tool_names: All tool names used in the run (duplicates allowed and
                counted). An empty list yields ``None``.
            prompt: The run's prompt; hashed to namespace the generated skill
                name and used to draft the description.

        Returns:
            A skill-definition dictionary with keys ``name``, ``description``,
            ``aliases``, ``source``, ``when_to_use``, ``body``, ``generated_at``,
            ``tool_names`` and ``reason``. Returns ``None`` when no tools were
            observed.

        Raises:
            Does not raise; the ``enrich_fn`` call is wrapped so any exception
            from it is suppressed and defaults used instead.
        """
        # Tally how many times each tool was used in the run.
        tool_counts: dict[str, int] = {}
        for name in tool_names:
            tool_counts[name] = tool_counts.get(name, 0) + 1

        # Keep the five most frequently used tools; ties broken by name order.
        top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
        if not top_tools:
            return None

        # Hash the prompt to make the skill name stable across identical runs
        # while keeping it short and filesystem-safe.
        name_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
        skill_name = f"auto-{top_tools[0][0]}-{name_hash}"

        # Ask the optional enricher for better metadata; ignore any failure.
        enrichment: dict[str, Any] = {}
        if self._enrich_fn:
            with contextlib.suppress(Exception):
                enrichment = self._enrich_fn(tool_names, prompt)

        # Prefer enriched values, falling back to generated heuristics.
        description = enrichment.get("description") or self._build_description(prompt, top_tools)
        when_to_use = enrichment.get("when_to_use") or self._build_when_to_use(top_tools)
        steps = enrichment.get("steps") or self._build_steps(top_tools)
        generated_reason = enrichment.get("reason", "Repeated tool-use pattern detected")

        # Assemble the markdown body section by section.
        body_parts = [
            f"# {skill_name}",
            "",
            description,
            "",
            "## When to Use",
            "",
            when_to_use or "Tasks matching the detected tool pattern",
            "",
            "## Tools",
            "",
        ]
        for tool_name, count in top_tools:
            body_parts.append(f"- `{tool_name}` (used {count} times)")
        body_parts.extend(["", "## Steps", ""])
        for step in steps:
            body_parts.append(f"- {step}")

        body = "\n".join(body_parts)

        return {
            "name": skill_name,
            "description": description,
            "aliases": [skill_name],
            "source": "auto_generated",
            "when_to_use": when_to_use,
            "body": body,
            # Epoch timestamp marks when this skill was synthesised.
            "generated_at": time.time(),
            "tool_names": tool_names,
            "reason": generated_reason,
        }

    def _build_description(self, prompt: str, top_tools: list[tuple[str, int]]) -> str:
        """Construct a human-readable skill description from the prompt.

        Args:
            prompt: The run prompt; only the first 80 characters are used as a
                preview and newlines are flattened for single-line display.
            top_tools: The most-frequent ``(name, count)`` pairs; the first three
                names are named in the description.

        Returns:
            A sentence describing the auto-generated skill and its prompt. The
            returned string is user-facing help text, not a code comment.
        """
        tools_str = ", ".join(f"{name}" for name, _ in top_tools[:3])
        prompt_preview = prompt[:80].replace("\n", " ")
        return f"Automatically generated skill for task involving {tools_str}. Prompt: {prompt_preview}"

    def _build_when_to_use(self, top_tools: list[tuple[str, int]]) -> str:
        """Construct a 'when to use' hint from the top tools.

        Maps the leading tool names to a short applicability hint. Known tool
        families (shell, file reading/search, web) get a canned description;
        anything else falls back to a generic per-tool phrase.

        Args:
            top_tools: The most-frequent ``(name, count)`` pairs; only the first
                three are consulted.

        Returns:
            A comma-joined string of applicability hints, or an empty string if
            no tools were supplied.
        """
        patterns = []
        # Inspect at most the first three tools for the applicability hint.
        for name, _ in top_tools[:3]:
            if name in ("bash", "run_command", "execute"):
                patterns.append("*.py, *.sh, *.toml, *.json")
            elif name in ("file_read", "read_file", "grep", "glob"):
                patterns.append("source files, logs, configuration")
            elif name in ("web_search", "web_fetch", "web"):
                patterns.append("web research, documentation lookup")
            else:
                patterns.append(f"tasks requiring `{name}`")
        return ", ".join(patterns)

    def _build_steps(self, top_tools: list[tuple[str, int]]) -> list[str]:
        """Construct the ordered step list for the skill body.

        Produces one human-readable step per tool, in frequency order. Each step
        names the tool and how many times it was seen, with a phrasing tailored
        to common tool families.

        Args:
            top_tools: The most-frequent ``(name, count)`` pairs to describe.

        Returns:
            A list of step strings suitable for the ``## Steps`` section.
        """
        steps: list[str] = []
        for name, count in top_tools:
            if name in ("bash", "run_command", "execute"):
                steps.append(f"Execute command using `{name}` ({count} times)")
            elif name in ("file_read", "read_file"):
                steps.append(f"Read file contents using `{name}` ({count} times)")
            elif name in ("grep",):
                steps.append(f"Search codebase using `{name}` ({count} times)")
            elif name in ("glob",):
                steps.append(f"Find files using `{name}` ({count} times)")
            elif name in ("web_search", "web_fetch"):
                steps.append(f"Research using `{name}` ({count} times)")
            else:
                steps.append(f"Execute `{name}` ({count} times)")
        return steps

    async def register(self, skill_def: dict[str, Any]) -> None:
        """Register the skill in-memory and write its markdown to disk.

        Looks up the agent's ``skill_registry`` and, if present, builds a
        :class:`~encre.skills.types.BundledSkillDefinition` whose prompt resolver
        substitutes ``{{args}}`` / ``{{arguments}}`` / ``{{user_input}}`` and any
        caller ``ctx`` keys into the stored body. The same definition is then
        rendered to a YAML-frontmatter markdown file under the auto-generated
        skills directory and written with UTF-8 encoding.

        Args:
            skill_def: The dictionary returned by :meth:`generate`. Must contain
                at least ``name``, ``description``, ``body`` and ``tool_names``.

        Returns:
            None.

        Raises:
            Propagates any exception from the skill registry or the filesystem
            write (for example a permission error). A missing ``skill_registry``
            is the one tolerated failure: it causes a silent early return.
        """
        # The registry is optional; if the agent has none, skip registration.
        skill_registry = getattr(self._agent, "skill_registry", None)
        if skill_registry is None:
            return

        # Imported lazily to keep module import light and avoid cycles.
        from encre.skills.types import BundledSkillDefinition, SkillContext, SkillSource

        body = skill_def["body"]
        name = skill_def["name"]
        aliases = list(skill_def.get("aliases") or [])
        when_to_use = skill_def.get("when_to_use", "")

        # The prompt resolver fills in runtime placeholders so the same
        # definition can adapt to the actual invocation arguments and context.
        async def get_prompt(
            args: str | None = None,
            ctx: dict[str, Any] | None = None,
        ) -> str:
            resolved = body
            if args is not None:
                # Support several conventional argument placeholder spellings.
                resolved = resolved.replace("{{args}}", args)
                resolved = resolved.replace("{{arguments}}", args)
                resolved = resolved.replace("{{user_input}}", args)
            if ctx is not None:
                # Substitute any {{key}} entries supplied by the caller context.
                for key, value in ctx.items():
                    resolved = resolved.replace(f"{{{{{key}}}}}", str(value))
            return resolved

        bundled = BundledSkillDefinition(
            name=name,
            description=skill_def["description"],
            get_prompt_for_command=get_prompt,
            aliases=aliases,
            when_to_use=when_to_use,
            context=SkillContext.INLINE,
            source=SkillSource.BUNDLED,
            body=body,
        )
        skill_registry.register(bundled)

        skills_dir = self._get_auto_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skills_dir / f"{skill_def['name']}.md"
        skill_content = self._format_skill_md(skill_def)
        skill_path.write_text(skill_content, encoding="utf-8")
        logger.info(
            "Generated skill: %s (%d tool calls, reason: %s)",
            skill_def["name"],
            len(skill_def["tool_names"]),
            skill_def.get("reason", "pattern detected"),
        )

    def _get_auto_skills_dir(self) -> Path:
        """Return the on-disk directory for auto-generated skills.

        The path is resolved lazily so that configuration is loaded only when a
        skill is actually written. It is the project's data directory joined
        with ``skills/auto_generated``.

        Returns:
            A :class:`pathlib.Path` to the auto-generated skills directory.
        """
        from encre.config import get_data_dir
        return get_data_dir() / "skills" / "auto_generated"

    def _format_skill_md(self, skill_def: dict[str, Any]) -> str:
        """Render the skill definition as a YAML-frontmatter markdown file.

        The output opens with a ``---`` delimited YAML block carrying ``name``,
        ``description``, ``source``, optional ``aliases`` and optional
        ``when_to_use``, followed by a blank line and the markdown ``body``.

        Args:
            skill_def: The definition dictionary returned by :meth:`generate`.

        Returns:
            The complete markdown document as a single string.
        """
        lines = ["---"]
        lines.append(f"name: {skill_def['name']}")
        lines.append(f"description: {skill_def['description']}")
        lines.append(f"source: {skill_def['source']}")
        if skill_def.get("aliases"):
            lines.append(f"aliases: {', '.join(skill_def['aliases'])}")
        if skill_def.get("when_to_use"):
            lines.append(f"when_to_use: {skill_def['when_to_use']}")
        lines.append("---")
        lines.append("")
        lines.append(skill_def["body"])
        return "\n".join(lines)
