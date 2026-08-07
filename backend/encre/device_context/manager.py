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

"""DeviceContextManager — orchestrates provider collection, caching, and
catalog building for the L1 device context block.

Usage::

    mgr = DeviceContextManager(config)
    catalog = await mgr.build_catalog()
    # → inject catalog into system prompt
    detail = await mgr.get_detail("hardware_info")
    # → return full data for a device_* tool
"""

from typing import Any

import asyncio

from encre.config import EncreConfig
from encre.device_context.cache import DeviceContextCache
from encre.device_context.catalog import build_catalog
from encre.device_context.providers.platform_ import PlatformInfoProvider
from encre.device_context.providers.hardware import HardwareInfoProvider
from encre.device_context.providers.gpu import GPUInfoProvider
from encre.device_context.providers.display import DisplayInfoProvider
from encre.device_context.providers.network import NetworkInfoProvider
from encre.device_context.providers.location import LocationInfoProvider
from encre.device_context.providers.sensors import SensorInfoProvider
from encre.device_context.providers.battery import BatteryInfoProvider


_DEFAULT_PROVIDERS = [
    PlatformInfoProvider(),
    HardwareInfoProvider(),
    GPUInfoProvider(),
    DisplayInfoProvider(),
    NetworkInfoProvider(),
    LocationInfoProvider(),
    SensorInfoProvider(),
    BatteryInfoProvider(),
]


class DeviceContextManager:
    def __init__(self, config: EncreConfig) -> None:
        self._config = config
        self._enabled = getattr(config, "device_context_enabled", True)
        ttl = getattr(config, "device_context_cache_ttl", 86400)
        whitelist: list[str] = getattr(config, "device_context_providers", []) or []

        self._providers = _DEFAULT_PROVIDERS
        if whitelist:
            self._providers = [p for p in self._providers if p.name in whitelist]

        from encre.config import get_data_dir
        cache_dir = get_data_dir() / "device_context"
        self._cache = DeviceContextCache(str(cache_dir / "cache.json"), ttl=ttl)

        self._cached_data: dict[str, dict[str, Any] | None] | None = None
        self._catalog: str = ""

    async def build_catalog(self) -> str:
        if not self._enabled:
            return ""
        if self._catalog:
            return self._catalog

        data = self._cache.load()
        if data is None:
            data = await self._collect_all()
            self._cache.save(data)

        self._cached_data = data
        self._catalog = build_catalog(data)
        return self._catalog

    def get_detail(self, provider_name: str) -> dict[str, Any] | None:
        if self._cached_data is None:
            return None
        return self._cached_data.get(provider_name)

    def get_catalog(self) -> str:
        return self._catalog

    def get_all_data(self) -> dict[str, dict[str, Any] | None]:
        return dict(self._cached_data) if self._cached_data else {}

    async def _collect_all(self) -> dict[str, dict[str, Any] | None]:
        results: dict[str, dict[str, Any] | None] = {}

        async def _run(p: Any) -> None:
            try:
                data = await p.collect_async()
                results[p.name] = data
            except Exception:
                results[p.name] = None

        tasks = [_run(p) for p in self._providers]
        await asyncio.gather(*tasks)
        return results

    def refresh(self) -> None:
        self._cache.clear()
        self._cached_data = None
        self._catalog = ""