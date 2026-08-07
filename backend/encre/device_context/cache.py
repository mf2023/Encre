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

"""Device context cache — persists collected provider data to disk.

The cache avoids re-probing hardware at every agent startup.  A TTL
(default 24h) controls how often the cache is refreshed.
"""

import json
import os
import time
from typing import Any


class DeviceContextCache:
    def __init__(self, cache_path: str, ttl: int = 86400) -> None:
        self._path = cache_path
        self._ttl = ttl

    def load(self) -> dict[str, dict[str, Any] | None] | None:
        if not os.path.isfile(self._path):
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("_timestamp", 0)
            if time.time() - ts > self._ttl:
                return None
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception:
            return None

    def save(self, data: dict[str, dict[str, Any] | None]) -> None:
        try:
            payload = dict(data)
            payload["_timestamp"] = time.time()
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            if os.path.isfile(self._path):
                os.remove(self._path)
        except Exception:
            pass