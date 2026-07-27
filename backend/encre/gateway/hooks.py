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

"""Gateway hook registry: lifecycle event callbacks.

A lightweight event-driven callback registry that discovers user-installed
hooks from the filesystem and dispatches lifecycle events to them.

A hook is a directory under ``~/.dunimd/encre/hooks/<name>/`` containing:

- ``HOOK.yaml`` -- manifest (currently just metadata; the directory name is the
  hook id).
- ``handler.py`` -- a module defining ``handle(event_type: str, context: dict)``.
  The handler may be sync or async; non-None return values are collected by
  :meth:`HookRegistry.emit_collect` for decision-type hooks.

Hook events:

- ``gateway:startup`` -- gateway process starts.
- ``session:start`` -- new conversation session begins.
- ``session:end`` -- session completes or times out.
- ``session:reset`` -- user resets the session (``/new``).
- ``agent:start`` -- agent begins processing a message.
- ``agent:step`` -- agent completes one tool-calling iteration.
- ``agent:end`` -- agent finishes and returns a response.
- ``command:<canonical>`` / ``command:*`` -- a slash command is about to run
  (decision-type: handlers may return ``{"decision": ...}`` to allow/deny/
  handle/rewrite it).

Design notes:

- No ``Hook`` class, no ``HookContext`` class -- the context is a plain ``dict``.
- Handlers resolve by exact event type first, then a wildcard ``base:*`` (a bare
  base like ``"agent"`` does NOT match ``"agent:start"`` -- the ``:*`` suffix is
  required).
- Per-handler try/except: a misbehaving hook is logged and skipped, never aborts
  the pipeline.
"""

import asyncio
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

from encre.config import get_data_dir

logger = logging.getLogger("encre.gateway.hooks")

# The directory user-installed hooks live in.
HOOKS_DIR = Path(get_data_dir()) / "hooks"

# ── Named event-type constants ────────────────────────────────────────

GATEWAY_STARTUP = "gateway:startup"
SESSION_START = "session:start"
SESSION_END = "session:end"
SESSION_RESET = "session:reset"
AGENT_START = "agent:start"
AGENT_STEP = "agent:step"
AGENT_END = "agent:end"
# command:<canonical> for a specific command; COMMAND_WILDCARD matches all.
COMMAND_WILDCARD = "command:*"


def _command_event(canonical: str) -> str:
    """Build the specific command event type for a canonical command name."""
    return f"command:{canonical}"


class HookRegistry:
    """Filesystem-discovered lifecycle hook registry.

    Single shared instance accessible via :func:`get_hook_registry`.  The
    registry is populated by :meth:`discover_and_load` (called once at gateway
    startup) and dispatched to via :meth:`emit` (fire-and-forget) and
    :meth:`emit_collect` (decision-type, collects non-None return values).
    """

    def __init__(self, hooks_dir: str | Path | None = None) -> None:
        if hooks_dir is None:
            hooks_dir = HOOKS_DIR
        self._hooks_dir = Path(hooks_dir)
        # event_type -> list of callables.
        self._handlers: dict[str, list[Callable[..., Any]]] = {}
        self._loaded_hooks: list[str] = []

    @property
    def loaded_hooks(self) -> list[str]:
        """Names of the hooks successfully loaded from disk."""
        return list(self._loaded_hooks)

    # ── registration ──────────────────────────────────────────────────

    def register(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Register ``handler`` for ``event_type`` programmatically.

        Used by built-in hooks (none shipped by default) and tests.  User hooks
        register themselves via :meth:`discover_and_load`.
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def unregister(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Remove a previously-registered handler (no-op if absent)."""
        handlers = self._handlers.get(event_type)
        if handlers:
            self._handlers[event_type] = [h for h in handlers if h is not handler]

    # ── discovery ──────────────────────────────────────────────────────

    def discover_and_load(self) -> list[str]:
        """Discover and load hooks from ``self._hooks_dir``.

        Each subdirectory is expected to contain a ``HOOK.yaml`` manifest and a
        ``handler.py`` module.  The handler module is registered in
        ``sys.modules`` (as ``encre_hooks.<name>``) before execution so that
        Pydantic / typing forward-refs resolve.

        Missing or malformed hooks are logged and skipped -- they never abort
        discovery.  Returns the list of successfully-loaded hook names.
        """
        self._handlers.clear()
        self._loaded_hooks.clear()
        if not self._hooks_dir.exists():
            logger.info("[hooks] hooks dir %s does not exist -- no user hooks", self._hooks_dir)
            return []
        loaded: list[str] = []
        for entry in sorted(self._hooks_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
                continue
            name = entry.name
            handler_path = entry / "handler.py"
            manifest_path = entry / "HOOK.yaml"
            if not handler_path.exists():
                logger.warning("[hooks] %s: missing handler.py -- skipping", name)
                continue
            if not manifest_path.exists():
                logger.warning("[hooks] %s: missing HOOK.yaml -- skipping", name)
                continue
            try:
                # Read manifest (currently metadata-only; validates it parses).
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f) or {}
                if not isinstance(manifest, dict):
                    raise ValueError("HOOK.yaml must be a mapping")
                # Load handler.py as a module.
                module_name = f"encre_hooks.{name}"
                spec = importlib.util.spec_from_file_location(module_name, handler_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("could not create module spec")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                handle_fn = getattr(module, "handle", None)
                if handle_fn is None or not callable(handle_fn):
                    logger.warning("[hooks] %s: handler.py has no callable handle() -- skipping", name)
                    continue
                # The handler registers itself via register() calls inside the
                # module, OR we register it as a wildcard for every event.
                # Encre follows the same convention: the handler module's
                # register() (if defined) wires events.  If the module exposes
                # ``EVENTS`` (a list of event types), register handle() for each.
                events = getattr(module, "EVENTS", None)
                if events:
                    for ev in events:
                        self.register(ev, handle_fn)
                loaded.append(name)
                logger.info("[hooks] loaded hook '%s' (manifest=%s)", name, manifest.get("name", name))
            except Exception as e:
                logger.warning("[hooks] failed to load hook '%s': %s %s", name, type(e).__name__, e)
        self._loaded_hooks = loaded
        return loaded

    # ── resolution ────────────────────────────────────────────────────

    def _resolve_handlers(self, event_type: str) -> list[Callable[..., Any]]:
        """Resolve handlers for an event: exact match first, then ``base:*``.

        A bare base (e.g. ``"agent"``) does NOT match ``"agent:start"`` -- the
        ``:*`` wildcard suffix is required.
        """
        handlers: list[Callable[..., Any]] = []
        exact = self._handlers.get(event_type)
        if exact:
            handlers.extend(exact)
        # Wildcard: "command:*" matches any "command:<x>"; a generic "<base>:*"
        # wildcard matches any "<base>:<x>".
        if ":" in event_type:
            base = event_type.split(":", 1)[0]
            wildcard = f"{base}:*"
            if wildcard != event_type:
                wild = self._handlers.get(wildcard)
                if wild:
                    handlers.extend(wild)
        return handlers

    # ── dispatch ──────────────────────────────────────────────────────

    async def emit(self, event_type: str, context: dict[str, Any] | None = None) -> None:
        """Fire ``event_type`` -- return values are discarded.

        Each handler runs in its own try/except so a failing hook never aborts
        the pipeline.  Sync handlers are awaited via the event loop; async
        handlers are awaited directly.
        """
        context = context or {}
        for handler in self._resolve_handlers(event_type):
            try:
                result = handler(event_type, context)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.warning("[hooks] handler for %s raised: %s %s", event_type, type(e).__name__, e)

    async def emit_collect(self, event_type: str, context: dict[str, Any] | None = None) -> list[Any]:
        """Fire ``event_type`` and collect non-None return values.

        Used for decision-type hooks (e.g. ``command:*``): handlers return
        ``{"decision": "allow" | "deny" | "handled" | "rewrite", ...}`` and the
        caller decides based on the collected list (first decisive value wins).
        """
        context = context or {}
        results: list[Any] = []
        for handler in self._resolve_handlers(event_type):
            try:
                result = handler(event_type, context)
                if inspect.isawaitable(result):
                    result = await result
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.warning("[hooks] collector for %s raised: %s %s", event_type, type(e).__name__, e)
        return results


# ── Module-level singleton ──────────────────────────────────────────────

_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    """Return the shared :class:`HookRegistry` singleton.

    Lazily created on first call.  Callers (AdapterManager, EventRouter,
    BaseAdapter) use this to emit lifecycle events without holding their own
    reference.
    """
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry


def reset_hook_registry(hooks_dir: str | Path | None = None) -> HookRegistry:
    """Reset the singleton (for tests / reconfiguration).

    Creates a fresh registry pointing at ``hooks_dir`` (defaults to the
    standard user hooks dir).  Does NOT discover -- call ``discover_and_load``
    afterwards.
    """
    global _registry
    _registry = HookRegistry(hooks_dir=hooks_dir)
    return _registry
