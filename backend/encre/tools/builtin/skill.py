#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Skill activation tool.

Lets the model activate a domain skill (travel-flights, pdf, data-viz, ...)
by name when the user's request matches the skill's purpose.  The activated
skill's guidance is injected into the next turn's system prompt, the same
channel used by auto-activated document skills.  This closes the loop: the
model sees the skill catalogue (auto-discovered), decides a skill fits, and
activates it itself - without requiring the user to type ``/skill-name``.
"""
import json
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin.find_tool import _resolve_loop


async def _skill_execute(**kwargs: Any) -> str:
    """Activate a domain skill by name.

    The skill's guidance body is cached on the loop so it persists into
    subsequent turns (same mechanism as auto-activated document skills).
    """
    name = (kwargs.get("name") or "").strip()
    if not name:
        return "Error: 'name' is required. Pick a skill name from the catalogue."
    args = kwargs.get("args")
    if isinstance(args, str):
        args = args.strip() or None

    loop = _resolve_loop()
    if loop is None:
        return "Error: skill activation requires a parent loop reference."

    registry = getattr(loop, "skill_registry", None)
    if registry is None:
        return "Error: no skill registry is available on this loop."

    skill = registry.lookup(name)
    if skill is None:
        return (
            f"Error: skill '{name}' not found. "
            "Check the catalogue for the exact name (use a listed /name or alias)."
        )
    # Normalise to the canonical skill name so aliases and exact names share
    # one cache entry.
    canonical = skill.name

    try:
        body = await registry.activate(canonical, args)
    except Exception as exc:
        return f"Error activating skill '{canonical}': {exc}"
    if not body or body.startswith("Error: "):
        return f"Error: skill '{canonical}' could not be activated: {body}"

    # Cache on the loop so the guidance surfaces in the next turn's system
    # prompt via _render_active_doc_skills (the existing injection channel).
    cache = getattr(loop, "_active_doc_skills", None)
    if isinstance(cache, dict):
        cache[canonical] = body

    preview = body.strip().splitlines()[0][:120] if body.strip() else ""
    payload = {
        "activated": canonical,
        "status": "active",
        "guidance_injected": True,
        "preview": preview,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


EncreSkillTool = build_tool(
    name="skill",
    description=(
        "Activate a domain skill by name when the user's request matches a skill's "
        "purpose (e.g. travel-flights for flight search, pdf for PDF processing, "
        "data-viz for charting). The skill's detailed guidance is injected into the "
        "next turn. Consult the Skills catalogue in the system prompt for available "
        "names and their purpose; pick the skill whose purpose matches the request. "
        "Aliases listed in the catalogue also work."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name (e.g. travel-flights, pdf, data-viz) or an alias from the catalogue.",
            },
            "args": {
                "type": "string",
                "description": "Optional argument string forwarded to the skill (e.g. the user's request context).",
            },
        },
        "required": ["name"],
    },
    execute=_skill_execute,
    intents=["general", "coding", "research", "data", "communication"],
    category="meta",
    triggers=["activate skill", "use skill", "skill"],
    always_available=True,
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
