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



from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginSource(Enum):
    BUNDLED = "bundled"       # Ships with encre
    INSTALLED = "installed"   # pip-installed third-party
    PROJECT = "project"       # Project-local plugin
    USER = "user"             # User-local plugin


@dataclass
class PluginManifest:
    """Metadata describing a plugin."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    source: PluginSource = PluginSource.INSTALLED
    dependencies: list[str] = field(default_factory=list)
    min_yim_version: str = "0.1.0"
    max_yim_version: str = ""
    tags: list[str] = field(default_factory=list)

    # What this plugin provides
    provides_tools: list[str] = field(default_factory=list)
    provides_skills: list[str] = field(default_factory=list)
    provides_hooks: list[str] = field(default_factory=list)
    provides_backends: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "source": self.source.value,
            "dependencies": self.dependencies,
            "min_yim_version": self.min_yim_version,
            "max_yim_version": self.max_yim_version,
            "tags": self.tags,
            "provides_tools": self.provides_tools,
            "provides_skills": self.provides_skills,
            "provides_hooks": self.provides_hooks,
            "provides_backends": self.provides_backends,
        }


class EncrePlugin:
    """Protocol for installable plugins.

    A plugin bundles tools, skills, hooks, and backends into a single
    installable package. Plugins are discovered via entry points or
    directory scanning.

    Usage:
        class MyDatabasePlugin(EncrePlugin):
            manifest = PluginManifest(
                name="encre-postgres",
                version="1.0.0",
                description="PostgreSQL tools for encre",
                provides_tools=["database_query", "database_schema"],
            )

            def get_tools(self) -> list[EncreTool]:
                return [DatabaseQueryTool(), DatabaseSchemaTool()]

            def get_skills(self) -> list[BundledSkillDefinition]:
                return [load_skill("database.SKILL.md")]
    """

    manifest: PluginManifest

    def get_tools(self) -> list[Any]:
        """Return tools provided by this plugin."""
        return []

    def get_skills(self) -> list[Any]:
        """Return skills provided by this plugin."""
        return []

    def get_hooks(self) -> list[tuple[str, Any]]:
        """Return (event_type, handler) pairs provided by this plugin."""
        return []

    def get_backends(self) -> dict[str, Any]:
        """Return {name: backend_class} provided by this plugin."""
        return {}

    def on_activate(self) -> None:
        """Called when the plugin is activated."""
        pass

    def on_deactivate(self) -> None:
        """Called when the plugin is deactivated."""
        pass

    def get_config_schema(self) -> dict[str, Any] | None:
        """Return JSON Schema for plugin configuration, or None."""
        return None

    def validate_config(self, _config: dict[str, Any]) -> list[str]:
        """Validate plugin configuration. Returns list of errors (empty = valid)."""
        return []
