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

"""``encre-plugin.json`` declarative manifest support.

VSCode-style plugins ship a JSON manifest describing their static
contributions (skills, slash commands, templates) and their activation
events.  Two tracks are supported:

- **Declarative track**: a directory with only ``encre-plugin.json`` 鈥?  static contributions (skill files, command definitions, templates)
  become visible at startup without executing any plugin code.
- **Hybrid track**: ``encre-plugin.json`` + ``plugin.py`` 鈥?the manifest
  drives metadata, permissions, engines, and lazy activation; the Python
  module provides the imperative :class:`EncrePlugin` implementation.

Both tracks share the same registry, so hand-built ``EncrePlugin``
subclasses keep working unchanged (9.1 dual track).
"""

import json
from pathlib import Path
from typing import Any

from encre.logging_config import get_logger
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource

logger = get_logger("encre.plugins")

MANIFEST_FILENAME = "encre-plugin.json"

_SUPPORTED_ENGINES = {"python", "typescript", "rust"}


def load_manifest(path: Path) -> PluginManifest | None:
    """Parse an ``encre-plugin.json`` file into a :class:`PluginManifest`.

    Returns ``None`` when the file is missing or invalid.  Unknown keys
    are ignored; required fields are ``name`` and ``version``.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("Invalid manifest %s: %s", path, e)
        return None
    if not isinstance(raw, dict):
        logger.warning("Manifest %s must be a JSON object", path)
        return None
    name = raw.get("name")
    version = raw.get("version")
    if not name or not version:
        logger.warning("Manifest %s missing 'name' or 'version'", path)
        return None

    contributes = raw.get("contributes") or {}
    provides_skills = [
        s.get("name", Path(str(s.get("path", ""))).stem) if isinstance(s, dict)
        else Path(str(s)).stem
        for s in contributes.get("skills", [])
    ]
    provides_tools = [
        t.get("name", "?") if isinstance(t, dict) else str(t)
        for t in contributes.get("tools", [])
    ]
    provides_backends = list((contributes.get("backends") or {}).keys())

    manifest = PluginManifest(
        name=str(name),
        version=str(version),
        description=str(raw.get("description", "")),
        author=str(raw.get("author", "")),
        license=str(raw.get("license", "MIT")),
        homepage=str(raw.get("homepage", "")),
        source=PluginSource.PROJECT,
        dependencies=list(raw.get("dependencies", [])),
        min_yim_version=str(raw.get("engines", {}).get("encre", "0.1.0")),
        tags=list(raw.get("tags", [])),
        provides_tools=provides_tools,
        provides_skills=provides_skills,
        provides_backends=provides_backends,
        activation_events=list(raw.get("activationEvents", [])),
        permissions=list(raw.get("permissions", [])),
        engines={k: str(v) for k, v in (raw.get("engines") or {}).items()
                 if k in _SUPPORTED_ENGINES},
        contributes=contributes,
    )
    return manifest


class DeclarativePlugin(EncrePlugin):
    """A plugin defined purely by ``encre-plugin.json`` (no Python code).

    Static contributions are served straight from the manifest:
    - ``contributes.skills``: list of ``{name, path}`` relative SKILL.md paths
    - ``contributes.commands``: list of slash-command definitions
    - ``contributes.templates``: list of template definitions

    No side effects occur at load time; the instance is inert until the
    host activates it, and its code (if any) is only imported when an
    activation event fires (lazy activation, 9.4).
    """

    def __init__(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        self.manifest = manifest
        self._dir = plugin_dir

    def get_skills(self) -> list[Any]:
        """Load skill files declared in ``contributes.skills``."""
        from encre.skills.types import BundledSkillDefinition

        skills: list[Any] = []
        for entry in self.manifest.contributes.get("skills", []):
            try:
                if isinstance(entry, dict):
                    name = entry.get("name", "")
                    rel = entry.get("path", "")
                else:
                    name, rel = "", str(entry)
                skill_path = self._dir / rel
                if not rel or not skill_path.is_file():
                    skill_path = self._dir / "SKILL.md"
                if skill_path.is_file():
                    skills.append(BundledSkillDefinition(
                        name=name or skill_path.parent.name,
                        content=skill_path.read_text(encoding="utf-8-sig"),
                        source=f"plugin:{self.manifest.name}",
                    ))
            except Exception as e:
                logger.warning("Plugin '%s' skill load failed: %s", self.manifest.name, e)
        return skills

    def get_commands(self) -> list[dict[str, Any]]:
        """Return slash-command definitions from ``contributes.commands``."""
        return list(self.manifest.contributes.get("commands", []))

    def get_templates(self) -> list[dict[str, Any]]:
        """Return template definitions from ``contributes.templates``."""
        return list(self.manifest.contributes.get("templates", []))
