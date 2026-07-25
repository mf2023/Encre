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

"""Platform Adapter Registry.

Allows platform adapters (built-in and plugin) to self-register so the gateway
can discover and instantiate them without hardcoded if/elif chains.

Built-in adapters register at module import time (bottom of their file).
Plugin adapters register via plugin discovery.  The registry supports deferred
(lazy) loading to avoid importing heavy SDKs at startup.

Aligns with Hermes ``gateway/platform_registry.py``.

Usage (adapter module):

    from encre.gateway.platform_registry import platform_registry, PlatformEntry
    from encre.gateway.config import Platform

    platform_registry.register(PlatformEntry(
        name="telegram",
        label="Telegram",
        platform=Platform.TELEGRAM,
        adapter_factory=lambda cfg: TelegramAdapter(cfg),
        check_fn=check_telegram_requirements,
        required_env=["TELEGRAM_BOT_TOKEN"],
    ))

Usage (gateway runner):

    adapter = platform_registry.create_adapter("telegram", platform_config)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platform_registry")


@dataclass
class PlatformEntry:
    """Metadata and factory for a single platform adapter.

    Attributes:
        name: Identifier used in config (e.g. "telegram", "discord").
        label: Human-readable label (e.g. "Telegram", "Discord").
        platform: The Platform enum value.
        adapter_factory: Callable that receives a PlatformConfig and returns
            an adapter instance.
        check_fn: Returns True when the platform's dependencies are available.
        validate_config: Given a PlatformConfig, is it properly configured?
        required_env: Env vars this platform needs (for setup display).
        install_hint: Hint shown when check_fn returns False.
        source: "builtin" or "plugin".
        plugin_name: Name of the plugin that registered this entry.
        max_message_length: Platform's per-message size cap.
        platform_hint: System prompt hint for this platform.
        emoji: Display emoji for CLI/UI.
        allowed_users_env: Env var name for allowed user ids.
        allow_all_env: Env var name for allow-all flag.
    """

    name: str
    label: str
    platform: Platform
    adapter_factory: Callable[[PlatformConfig], Any]
    check_fn: Callable[[], bool]
    validate_config: Optional[Callable[[PlatformConfig], bool]] = None
    required_env: list[str] = field(default_factory=list)
    install_hint: str = ""
    source: str = "builtin"
    plugin_name: str = ""
    max_message_length: int = 0
    platform_hint: str = ""
    emoji: str = "🔌"
    allowed_users_env: str = ""
    allow_all_env: str = ""


class PlatformRegistry:
    """Central registry of platform adapters.

    Thread-safe for reads (dict lookups are atomic under GIL).
    Writes happen at startup during sequential discovery.
    """

    def __init__(self) -> None:
        self._entries: dict[str, PlatformEntry] = {}
        # Deferred loaders: name -> zero-arg callable that imports the adapter
        # module (which calls register() to populate _entries).
        self._deferred: dict[str, Callable[[], None]] = {}

    # -- Deferred loading --

    def register_deferred(self, name: str, loader: Callable[[], None]) -> None:
        """Register a lazy loader for a platform not yet imported.

        The loader runs at most once, the first time the platform is looked up.
        A concrete registration takes precedence over a deferred one.
        """
        if name in self._entries:
            return
        self._deferred[name] = loader

    def _resolve(self, name: str) -> None:
        """Run the deferred loader for a name if one is pending."""
        loader = self._deferred.pop(name, None)
        if loader is None:
            return
        try:
            loader()
        except Exception as e:
            logger.warning(
                "Deferred load of platform '%s' failed: %s", name, e, exc_info=True
            )

    def _resolve_all(self) -> None:
        """Run every pending deferred loader."""
        if not self._deferred:
            return
        for name in list(self._deferred):
            self._resolve(name)

    # -- Registration --

    def register(self, entry: PlatformEntry) -> None:
        """Register a platform adapter entry.

        If an entry with the same name exists, it is replaced (last writer wins).
        """
        self._deferred.pop(entry.name, None)
        if entry.name in self._entries:
            prev = self._entries[entry.name]
            logger.info(
                "Platform '%s' re-registered (was %s, now %s)",
                entry.name, prev.source, entry.source,
            )
        self._entries[entry.name] = entry
        logger.debug("Registered platform adapter: %s (%s)", entry.name, entry.source)

    def unregister(self, name: str) -> bool:
        """Remove a platform entry.  Returns True if it existed."""
        self._deferred.pop(name, None)
        return self._entries.pop(name, None) is not None

    # -- Lookup --

    def get(self, name: str) -> Optional[PlatformEntry]:
        """Look up a platform entry by name."""
        if name not in self._entries:
            self._resolve(name)
        return self._entries.get(name)

    def all_entries(self) -> list[PlatformEntry]:
        """Return all registered platform entries."""
        self._resolve_all()
        return list(self._entries.values())

    def plugin_entries(self) -> list[PlatformEntry]:
        """Return only plugin-registered entries."""
        self._resolve_all()
        return [e for e in self._entries.values() if e.source == "plugin"]

    def is_registered(self, name: str) -> bool:
        """Check if a platform is registered (including deferred)."""
        return name in self._entries or name in self._deferred

    # -- Factory --

    def create_adapter(self, name: str, config: PlatformConfig) -> Optional[Any]:
        """Create an adapter instance for the given platform name.

        Returns None if:
        - No entry registered for the name
        - check_fn() returns False (missing deps)
        - validate_config() returns False (misconfigured)
        - The factory raises an exception
        """
        if name not in self._entries:
            self._resolve(name)
        entry = self._entries.get(name)
        if entry is None:
            return None

        if not entry.check_fn():
            hint = f" ({entry.install_hint})" if entry.install_hint else ""
            logger.warning("Platform '%s' requirements not met%s", entry.label, hint)
            return None

        if entry.validate_config is not None:
            try:
                if not entry.validate_config(config):
                    logger.warning("Platform '%s' config validation failed", entry.label)
                    return None
            except Exception as e:
                logger.warning("Platform '%s' config validation error: %s", entry.label, e)
                return None

        try:
            adapter = entry.adapter_factory(config)
            return adapter
        except Exception as e:
            logger.error(
                "Failed to create adapter for platform '%s': %s",
                entry.label, e, exc_info=True,
            )
            return None


# Module-level singleton
platform_registry = PlatformRegistry()
