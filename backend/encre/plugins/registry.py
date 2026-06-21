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



import importlib
import importlib.metadata
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from encre.logging_config import get_logger
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource

logger = get_logger("encre.plugins")

_ENTRY_POINT_GROUP = "encre.plugins"


class PluginRegistry:
    """Discovers, loads, and manages lifecycle of encre plugins.

    Discovery order (later overrides earlier):
    1. Bundled plugins (encre/plugins/bundled/)
    2. pip-installed plugins (entry point: encre.plugins)
    3. Project-local plugins (./.encre/plugins/)
    4. User-local plugins (~/.dunimd/encre/plugins/)
    """

    def __init__(self) -> None:
        self._plugins: dict[str, EncrePlugin] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._activated: set[str] = set()
        self._failed: dict[str, str] = {}

    @property
    def count(self) -> int:
        return len(self._plugins)

    @property
    def active_count(self) -> int:
        return len(self._activated)

    def register(self, plugin: EncrePlugin) -> None:
        """Register a plugin instance directly."""
        name = plugin.manifest.name
        existing = self._plugins.get(name)
        if existing is not None:
            existing_source_priority = _source_priority(existing.manifest.source)
            new_source_priority = _source_priority(plugin.manifest.source)
            if new_source_priority >= existing_source_priority:
                return  # Existing has higher or equal priority
        self._plugins[name] = plugin
        self._manifests[name] = plugin.manifest

    def unregister(self, name: str) -> bool:
        if name in self._activated:
            self.deactivate(name)
        removed = self._plugins.pop(name, None) is not None
        self._manifests.pop(name, None)
        self._failed.pop(name, None)
        return removed

    def get(self, name: str) -> EncrePlugin | None:
        return self._plugins.get(name)

    def get_manifest(self, name: str) -> PluginManifest | None:
        return self._manifests.get(name)

    def list_all(self) -> list[PluginManifest]:
        return list(self._manifests.values())

    def list_activated(self) -> list[str]:
        return sorted(self._activated)

    def list_failed(self) -> dict[str, str]:
        return dict(self._failed)

    # ── Discovery ────────────────────────────────────────────────

    def discover_all(self) -> int:
        """Run all discovery mechanisms. Returns count of newly found plugins."""
        before = len(self._plugins)
        self._discover_entry_points()
        self._discover_directory("./.encre/plugins/", PluginSource.PROJECT)
        self._discover_directory("~/.dunimd/encre/plugins/", PluginSource.USER)
        return len(self._plugins) - before

    def _discover_entry_points(self) -> None:
        """Discover plugins registered via pip entry points."""
        try:
            entry_points = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
        except TypeError:
            # Python < 3.12
            try:
                entry_points = importlib.metadata.entry_points().get(_ENTRY_POINT_GROUP, [])
            except Exception:
                return
        except Exception:
            return

        for ep in entry_points:
            try:
                plugin_factory = ep.load()
                plugin = plugin_factory()
                if not isinstance(plugin, EncrePlugin):
                    logger.warning(f"Entry point '{ep.name}' did not return a EncrePlugin instance")
                    continue
                plugin.manifest.source = PluginSource.INSTALLED
                self.register(plugin)
                logger.info(f"Discovered plugin '{plugin.manifest.name}' via entry point '{ep.name}'")  # noqa: E501
            except Exception as e:
                logger.warning(f"Failed to load plugin from entry point '{ep.name}': {e}")
                self._failed[ep.name] = str(e)

    def _discover_directory(self, dir_path: str, source: PluginSource) -> None:
        path = Path(dir_path).expanduser().resolve()
        if not path.is_dir():
            return

        for entry in sorted(path.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                self._load_plugin_from_dir(entry, source)
            elif entry.suffix == ".py" and entry.stem != "__init__":
                self._load_plugin_from_file(entry, source)

    def _load_plugin_from_dir(self, path: Path, source: PluginSource) -> None:
        init_file = path / "__init__.py"
        plugin_file = path / "plugin.py"
        if plugin_file.exists():
            self._load_module_from_file(str(plugin_file), path.stem, source)
        elif init_file.exists():
            self._load_plugin_package(str(path), source)

    def _load_plugin_from_file(self, path: Path, source: PluginSource) -> None:
        self._load_module_from_file(str(path), path.stem, source)

    def _load_plugin_package(self, package_path: str, source: PluginSource) -> None:
        try:
            spec = importlib.util.spec_from_file_location(
                f"yim_plugin_{Path(package_path).stem}",
                os.path.join(package_path, "__init__.py"),
            )
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            self._extract_plugin(module, Path(package_path).stem, source)
        except Exception as e:
            logger.warning(f"Failed to load plugin package '{package_path}': {e}")
            self._failed[Path(package_path).stem] = str(e)

    def _load_module_from_file(self, filepath: str, name: str, source: PluginSource) -> None:
        try:
            spec = importlib.util.spec_from_file_location(f"yim_plugin_{name}", filepath)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            self._extract_plugin(module, name, source)
        except Exception as e:
            logger.warning(f"Failed to load plugin '{name}' from '{filepath}': {e}")
            self._failed[name] = str(e)

    def _extract_plugin(self, module: Any, name: str, source: PluginSource) -> None:
        # Look for a class that extends EncrePlugin
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, EncrePlugin) and attr is not EncrePlugin:
                plugin = attr()
                plugin.manifest.source = source
                self.register(plugin)
                logger.info(f"Loaded plugin '{plugin.manifest.name}' from {source.value}/{name}")
                return
        # Look for a plugin instance
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, EncrePlugin):
                attr.manifest.source = source
                self.register(attr)
                return
        # Look for a create_plugin() factory
        if hasattr(module, "create_plugin"):
            try:
                plugin = module.create_plugin()
                if isinstance(plugin, EncrePlugin):
                    plugin.manifest.source = source
                    self.register(plugin)
                    return
            except Exception:
                pass

    # ── Lifecycle ────────────────────────────────────────────────

    def activate(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        if name in self._activated:
            return True
        try:
            plugin.on_activate()
            self._activated.add(name)
            return True
        except Exception as e:
            logger.error(f"Failed to activate plugin '{name}': {e}")
            self._failed[name] = str(e)
            return False

    def deactivate(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        if name not in self._activated:
            return True
        try:
            plugin.on_deactivate()
            self._activated.discard(name)
            return True
        except Exception as e:
            logger.error(f"Error deactivating plugin '{name}': {e}")
            return False

    def activate_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name in self._plugins:
            results[name] = self.activate(name)
        return results

    def deactivate_all(self) -> None:
        for name in list(self._activated):
            self.deactivate(name)

    # ── Tool/Skill/Hook aggregation ──────────────────────────────

    def get_all_tools(self) -> list[Any]:
        tools: list[Any] = []
        seen: set[str] = set()
        for name in self._activated:
            plugin = self._plugins[name]
            for tool in plugin.get_tools():
                tool_name = getattr(tool, "name", "")
                if tool_name and tool_name not in seen:
                    seen.add(tool_name)
                    tools.append(tool)
        return tools

    def get_all_skills(self) -> list[Any]:
        skills: list[Any] = []
        seen: set[str] = set()
        for name in self._activated:
            plugin = self._plugins[name]
            for skill in plugin.get_skills():
                skill_name = getattr(skill, "name", "")
                if skill_name and skill_name not in seen:
                    seen.add(skill_name)
                    skills.append(skill)
        return skills

    def get_all_hooks(self) -> dict[str, list[Any]]:
        hooks: dict[str, list[Any]] = {}
        for name in self._activated:
            plugin = self._plugins[name]
            for event_type, handler in plugin.get_hooks():
                hooks.setdefault(event_type, []).append(handler)
        return hooks

    def get_all_backends(self) -> dict[str, type[Any]]:
        backends: dict[str, type[Any]] = {}
        for name in self._activated:
            plugin = self._plugins[name]
            backends.update(plugin.get_backends())
        return backends

    def reset(self) -> None:
        self.deactivate_all()
        self._plugins.clear()
        self._manifests.clear()
        self._activated.clear()
        self._failed.clear()


def _source_priority(source: PluginSource) -> int:
    _ORDER = {
        PluginSource.BUNDLED: 0,
        PluginSource.INSTALLED: 1,
        PluginSource.PROJECT: 2,
        PluginSource.USER: 3,
    }
    return _ORDER.get(source, 1)
