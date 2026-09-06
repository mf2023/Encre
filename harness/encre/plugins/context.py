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

"""The ``encre.*`` plugin API context.

Every registration made through a :class:`PluginContext` is a *reversible
side effect*: the method returns an ``undo`` callable, and the registry
records it on a per-plugin LIFO stack so deactivation or uninstall rolls
the plugin back exactly (Task 9.2).

Surfaces (Task 9.3):
- ``tools``      register additional tools
- ``backends``   register model backend classes
- ``loop``       intercept loop phases via the phase bus
- ``events``     subscribe/emit typed plugin events
- ``permissions``register permission policies
- ``commands``   register slash commands
- ``sub_agents`` register sub-agent definitions
- ``templates``  register prompt templates
"""

import logging
from typing import Any, Callable

from encre.logging_config import get_logger

logger = get_logger("encre.plugins")

_UNDO = Callable[[], None]


def _noop_undo() -> None:
    """Undo closure for registrations the host cannot reverse."""


class PluginContext:
    """Per-plugin API surface handed to ``on_activate(context)``.

    The context is deliberately thin: every ``register_*`` forwards to a
    *host capability object* supplied by the embedding application (the
    loop, the tool registry, 鈥?, records the returned undo closure on the
    context's LIFO undo list, and returns the undo to the plugin.  When a
    capability is absent (harness-only embedding), registration becomes a
    no-op that logs at debug level, so plugins degrade gracefully instead
    of crashing lightweight hosts.
    """

    def __init__(
        self,
        plugin_name: str,
        *,
        undo_sink: Callable[[str, _UNDO], None] | None = None,
        tool_registry: Any = None,
        backend_registry: Any = None,
        phase_bus: Any = None,
        event_bus: Any = None,
        permission_registry: Any = None,
        command_registry: Any = None,
        sub_agent_registry: Any = None,
        template_registry: Any = None,
    ) -> None:
        self.plugin_name = plugin_name
        self._undos: list[_UNDO] = []
        self._undo_sink = undo_sink
        _mk = _make_api
        self.tools = _mk(_ToolsApi, tool_registry, plugin_name, self)
        self.backends = _mk(_BackendsApi, backend_registry, plugin_name, self)
        self.loop = _mk(_LoopApi, phase_bus, plugin_name, self)
        self.events = _mk(_EventsApi, event_bus, plugin_name, self)
        self.permissions = _mk(_PermissionsApi, permission_registry, plugin_name, self)
        self.commands = _mk(_CommandsApi, command_registry, plugin_name, self)
        self.sub_agents = _mk(_SubAgentsApi, sub_agent_registry, plugin_name, self)
        self.templates = _mk(_TemplatesApi, template_registry, plugin_name, self)

    def record_undo(self, undo: _UNDO) -> _UNDO:
        """Record *undo* on the plugin's rollback stack and return it.

        With a sink (the live registry), the undo lands on the plugin's
        stack immediately 鈥?so registrations made after ``on_activate``
        returns (async handlers, event callbacks) are still rolled back.
        """
        if undo is _noop_undo:
            return undo
        if self._undo_sink is not None:
            self._undo_sink(self.plugin_name, undo)
        else:
            self._undos.append(undo)
        return undo

    def drain_undos(self) -> list[_UNDO]:
        """Return and clear locally-buffered undos (used when no sink)."""
        undos, self._undos = self._undos, []
        return undos


def build_context(
    plugin_name: str,
    host: dict[str, Any] | None = None,
    undo_sink: Callable[[str, _UNDO], None] | None = None,
) -> PluginContext:
    """Build a :class:`PluginContext` from a host capability mapping.

    ``host`` keys (all optional): ``tools``/``backends``/``loop``/
    ``events``/``permissions``/``commands``/``sub_agents``/``templates``.
    Missing capabilities degrade to no-op registration.  ``undo_sink``
    receives every recorded ``(plugin_name, undo)`` pair.
    """
    host = host or {}
    return PluginContext(
        plugin_name,
        undo_sink=undo_sink,
        tool_registry=host.get("tools"),
        backend_registry=host.get("backends"),
        phase_bus=host.get("loop"),
        event_bus=host.get("events"),
        permission_registry=host.get("permissions"),
        command_registry=host.get("commands"),
        sub_agent_registry=host.get("sub_agents"),
        template_registry=host.get("templates"),
    )


def _make_api(cls: type, host: Any, plugin_name: str, ctx: PluginContext) -> Any:
    """Instantiate an API object wired to the context's undo recorder."""
    api = cls(host, plugin_name)
    api._ctx = ctx
    return api


class _ApiBase:
    """Shared no-host guard for context APIs."""

    _label = "api"

    def __init__(self, host: Any, plugin_name: str) -> None:
        self._host = host
        self._plugin = plugin_name

    def _absent(self) -> _UNDO:
        logger.debug("Plugin '%s': %s host not available in this embedding",
                     self._plugin, self._label)
        return _noop_undo


class _ToolsApi(_ApiBase):
    """``encre.tools`` 鈥?register tools into the live tool registry."""

    _label = "tools"

    def register(self, tool: Any) -> _UNDO:
        """Register *tool*; returns its undo closure."""
        if self._host is None:
            return self._absent()
        try:
            return self._ctx.record_undo(self._host.plugin_register_tool(tool, source=self._plugin))
        except TypeError:
            return self._ctx.record_undo(self._host.register_tool(tool))


class _BackendsApi(_ApiBase):
    """``encre.backends`` 鈥?register model backend classes."""

    _label = "backends"

    def register(self, name: str, backend_class: type) -> _UNDO:
        """Register backend class under *name*; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.plugin_register_backend(name, backend_class))


class _LoopApi(_ApiBase):
    """``encre.loop`` 鈥?intercept loop phases via the phase bus."""

    _label = "loop"

    def intercept(self, phase: str, handler: Callable[..., Any]) -> _UNDO:
        """Subscribe *handler* to *phase* on the phase bus; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.subscribe(phase, handler, source=self._plugin))


class _EventsApi(_ApiBase):
    """``encre.events`` 鈥?typed plugin event pub/sub."""

    _label = "events"

    def subscribe(self, event_type: str, handler: Callable[..., Any]) -> _UNDO:
        """Subscribe to *event_type*; returns the unsubscribe closure."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.subscribe(event_type, handler, source=self._plugin))

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit a plugin event (best effort; never raises into the plugin)."""
        if self._host is None:
            return
        try:
            self._host.emit(event_type, payload or {}, source=self._plugin)
        except Exception:
            logger.debug("Plugin '%s' emit %s failed", self._plugin, event_type,
                         exc_info=True)


class _PermissionsApi(_ApiBase):
    """``encre.permissions`` 鈥?register permission policies."""

    _label = "permissions"

    def register(self, policy: Any) -> _UNDO:
        """Register *policy*; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.plugin_register_policy(policy, source=self._plugin))


class _CommandsApi(_ApiBase):
    """``encre.commands`` 鈥?register slash commands."""

    _label = "commands"

    def register(self, command: dict[str, Any]) -> _UNDO:
        """Register a slash-command definition; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.plugin_register_command(command, source=self._plugin))


class _SubAgentsApi(_ApiBase):
    """``encre.sub_agents`` 鈥?register sub-agent definitions."""

    _label = "sub_agents"

    def register(self, definition: dict[str, Any]) -> _UNDO:
        """Register a sub-agent definition; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.plugin_register_sub_agent(definition, source=self._plugin))


class _TemplatesApi(_ApiBase):
    """``encre.templates`` 鈥?register prompt templates."""

    _label = "templates"

    def register(self, name: str, template: str) -> _UNDO:
        """Register prompt template under *name*; returns undo."""
        if self._host is None:
            return self._absent()
        return self._ctx.record_undo(self._host.plugin_register_template(name, template, source=self._plugin))
