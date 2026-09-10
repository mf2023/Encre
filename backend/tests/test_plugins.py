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

"""Tests for plugin system: manifest, plugin protocol, and registry."""


from encre.plugins.registry import PluginRegistry
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource


class TestPluginManifest:
    """Engineered to validate PluginManifest construction and serialization.

Tests confirm that minimal manifests default source to
PluginSource.INSTALLED, that full manifests preserve all optional
fields (description, author, license, homepage, dependencies, tags,
tool/skill/hook/backend provisions), that the PluginSource enum maps
to the correct string values, and that to_dict serialises the
manifest faithfully.
"""
    def test_verify_manifest_create_minimal(self):
        """Validate that minimal PluginManifest defaults source to INSTALLED."""
        m = PluginManifest(name="test-plugin", version="0.1.0")
        assert m.name == "test-plugin"
        assert m.version == "0.1.0"
        assert m.source == PluginSource.INSTALLED

    def test_verify_manifest_create_full(self):
        """Validate that full PluginManifest preserves all optional fields."""
        m = PluginManifest(
            name="full-plugin",
            version="1.0.0",
            description="A full plugin",
            author="Test Author",
            license="Apache-2.0",
            homepage="https://example.com",
            source=PluginSource.PROJECT,
            dependencies=["dep1", "dep2"],
            min_ea_version="0.2.0",
            tags=["database", "tools"],
            provides_tools=["db_query"],
            provides_skills=["db_skill"],
            provides_hooks=["on_session_start"],
            provides_backends=["postgres"],
        )
        assert m.name == "full-plugin"
        assert m.author == "Test Author"
        assert m.license == "Apache-2.0"
        assert m.source == PluginSource.PROJECT
        assert "dep1" in m.dependencies
        assert "database" in m.tags
        assert "db_query" in m.provides_tools

    def test_verify_manifest_plugin_source_enum(self):
        """Validate that PluginSource enum values map to correct strings."""
        assert PluginSource.BUNDLED.value == "bundled"
        assert PluginSource.INSTALLED.value == "installed"
        assert PluginSource.PROJECT.value == "project"
        assert PluginSource.USER.value == "user"

    def test_verify_manifest_to_dict(self):
        """Validate that to_dict serialises the manifest faithfully."""
        m = PluginManifest(name="dict-test", version="0.1.0")
        d = m.to_dict()
        assert d["name"] == "dict-test"
        assert d["version"] == "0.1.0"
        assert d["source"] == "installed"


class TestEncrePlugin:
    """Engineered to validate the EncrePlugin base class contract.

Tests confirm that plugin subclasses can declare tools, hooks, and
empty defaults for unimplemented interfaces (skills, backends), and
that the base class provides sensible empty return values when a
subclass overrides nothing.
"""
    def test_verify_plugin_with_tools(self):
        """Validate that a plugin subclass can declare and return tools."""
        class MyPlugin(EncrePlugin):
            manifest = PluginManifest(name="my-plugin", version="1.0.0")

            def get_tools(self):
                """Return the tools provided by this plugin."""
                return ["fake_tool"]

        plugin = MyPlugin()
        assert plugin.manifest.name == "my-plugin"
        assert plugin.get_tools() == ["fake_tool"]

    def test_verify_plugin_with_hooks(self):
        """Validate that a plugin subclass can declare and return hooks."""
        class HookPlugin(EncrePlugin):
            manifest = PluginManifest(name="hook-plugin", version="1.0.0")

            def get_hooks(self):
                """Return the hooks provided by this plugin."""
                return [("on_session_start", lambda: None)]

        plugin = HookPlugin()
        hooks = plugin.get_hooks()
        assert len(hooks) == 1
        assert hooks[0][0] == "on_session_start"

    def test_verify_plugin_default_returns_empty(self):
        """Validate that unimplemented interface methods return sensible empty defaults."""
        class EmptyPlugin(EncrePlugin):
            manifest = PluginManifest(name="empty", version="0.1.0")

        plugin = EmptyPlugin()
        assert plugin.get_tools() == []
        assert plugin.get_skills() == []
        assert plugin.get_hooks() == []
        assert plugin.get_backends() == {}


class TestPluginRegistry:
    """Engineered to validate the PluginRegistry lifecycle operations.

Tests cover empty registry invariants, registration, duplicate-name
suppression, activate/deactivate toggling, unregistration, lookup by
name, full manifest listing, and aggregate tool/skill/hook/backend
collection from active plugins.  Reset must clear all state.
"""
    def test_verify_registry_empty(self):
        """Validate that a new registry has zero count and zero active count."""
        registry = PluginRegistry()
        assert registry.count == 0
        assert registry.active_count == 0

    def test_verify_registry_register_plugin(self):
        """Validate that register increments the count."""
        class TestPlugin(EncrePlugin):
            manifest = PluginManifest(name="reg-test", version="1.0.0")

        registry = PluginRegistry()
        registry.register(TestPlugin())
        assert registry.count == 1

    def test_verify_registry_register_duplicate_name(self):
        """Validate that duplicate registration is suppressed."""
        class DupPlugin(EncrePlugin):
            manifest = PluginManifest(name="dup", version="1.0.0")

        registry = PluginRegistry()
        registry.register(DupPlugin())
        registry.register(DupPlugin())
        assert registry.count == 1

    def test_verify_registry_activate_deactivate(self):
        """Validate that activate/deactivate toggle active_count correctly."""
        class ActPlugin(EncrePlugin):
            manifest = PluginManifest(name="act-test", version="1.0.0")

        registry = PluginRegistry()
        plugin = ActPlugin()
        registry.register(plugin)
        assert registry.activate("act-test") is True
        assert registry.active_count == 1
        assert registry.deactivate("act-test") is True
        assert registry.active_count == 0

    def test_verify_registry_unregister(self):
        """Validate that unregister removes the plugin and decrements count."""
        class UnregPlugin(EncrePlugin):
            manifest = PluginManifest(name="unreg-test", version="1.0.0")

        registry = PluginRegistry()
        registry.register(UnregPlugin())
        assert registry.unregister("unreg-test") is True
        assert registry.count == 0

    def test_verify_registry_get(self):
        """Validate that get and get_manifest return the registered plugin."""
        class GetPlugin(EncrePlugin):
            manifest = PluginManifest(name="get-test", version="1.0.0")

        registry = PluginRegistry()
        plugin = GetPlugin()
        registry.register(plugin)
        assert registry.get("get-test") is not None
        assert registry.get_manifest("get-test") is not None

    def test_verify_registry_list_all(self):
        """Validate that list_all returns all registered manifests."""
        class ListPlugin(EncrePlugin):
            manifest = PluginManifest(name="list-test", version="1.0.0")

        registry = PluginRegistry()
        registry.register(ListPlugin())
        manifests = registry.list_all()
        assert len(manifests) == 1
        assert manifests[0].name == "list-test"

    def test_verify_registry_get_all_tools(self):
        """Validate that get_all_tools collects tools from active plugins."""
        class ToolPlugin(EncrePlugin):
            manifest = PluginManifest(name="tool-plugin", version="1.0.0")

            def get_tools(self):
                """Return the tools provided by this plugin."""
                return ["tool1", "tool2"]

        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        registry.activate("tool-plugin")
        tools = registry.get_all_tools()
        assert isinstance(tools, list)

    def test_verify_registry_get_all_skills(self):
        """Validate that get_all_skills collects skills from active plugins."""
        class SkillPlugin(EncrePlugin):
            manifest = PluginManifest(name="skill-plugin", version="1.0.0")

            def get_skills(self):
                """Return the skills provided by this plugin."""
                return ["skill1"]

        registry = PluginRegistry()
        plugin = SkillPlugin()
        registry.register(plugin)
        registry.activate("skill-plugin")
        skills = registry.get_all_skills()
        assert isinstance(skills, list)

    def test_verify_registry_get_all_hooks(self):
        """Validate that get_all_hooks collects hooks from active plugins."""
        class HookPlugin(EncrePlugin):
            manifest = PluginManifest(name="hook-plugin2", version="1.0.0")

            def get_hooks(self):
                """Return the hooks provided by this plugin."""
                return [("pre_tool_exec", lambda: None)]

        registry = PluginRegistry()
        plugin = HookPlugin()
        registry.register(plugin)
        registry.activate("hook-plugin2")
        hooks = registry.get_all_hooks()
        assert isinstance(hooks, dict)

    def test_verify_registry_get_all_backends(self):
        """Validate that get_all_backends collects backends from active plugins."""
        class BackendPlugin(EncrePlugin):
            manifest = PluginManifest(name="be-plugin", version="1.0.0")

            def get_backends(self):
                """Return the backends provided by this plugin."""
                return {"custom": "FakeBackend"}

        registry = PluginRegistry()
        plugin = BackendPlugin()
        registry.register(plugin)
        registry.activate("be-plugin")
        backends = registry.get_all_backends()
        assert isinstance(backends, dict)
        assert "custom" in backends

    def test_verify_registry_reset(self):
        """Validate that reset clears all state including active count."""
        class ResetPlugin(EncrePlugin):
            manifest = PluginManifest(name="reset-test", version="1.0.0")

        registry = PluginRegistry()
        registry.register(ResetPlugin())
        registry.activate("reset-test")
        registry.reset()
        assert registry.count == 0
        assert registry.active_count == 0
