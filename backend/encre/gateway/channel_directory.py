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

"""Channel directory -- cached map of reachable channels/contacts per platform.

Built on gateway startup, refreshed periodically, and saved to the data dir.
The send_message tool reads this file for action="list" and for resolving
human-friendly channel names to numeric IDs.

Aligns with Hermes ``gateway/channel_directory.py``.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from encre.config import get_data_dir

logger = logging.getLogger("encre.gateway.channel_directory")

DIRECTORY_PATH = Path(get_data_dir()) / "channel_directory.json"


class ChannelDirectory:
    """Cached map of reachable channels/contacts per platform.

    The directory is built by querying each connected adapter for its
    known channels, merged with session-history-derived contacts.
    """

    def __init__(self) -> None:
        self._platforms: Dict[str, List[Dict[str, Any]]] = {}
        self._last_build: float = 0.0

    @property
    def platforms(self) -> Dict[str, List[Dict[str, Any]]]:
        """Per-platform channel entries."""
        return self._platforms

    def build(self, adapters: Dict[str, Any]) -> None:
        """Rebuild the directory from connected adapters.

        Each adapter that implements get_channels() contributes its entries.
        """
        self._platforms.clear()
        for name, adapter in adapters.items():
            get_channels = getattr(adapter, "get_channels", None)
            if callable(get_channels):
                try:
                    channels = get_channels()
                    if channels:
                        self._platforms[name] = channels
                except Exception as e:
                    logger.warning("[channel-dir] %s.get_channels() failed: %s", name, e)
        self._last_build = time.time()
        self._save()

    def lookup(self, platform: str, query: str) -> Optional[Dict[str, Any]]:
        """Look up a channel by name or id on a given platform.

        Returns the matching channel entry, or None.
        """
        entries = self._platforms.get(platform, [])
        query_lower = query.strip().lower().lstrip("#")
        for entry in entries:
            if str(entry.get("id", "")) == query:
                return entry
            if str(entry.get("name", "")).lower() == query_lower:
                return entry
        return None

    def list_platform(self, platform: str) -> List[Dict[str, Any]]:
        """List all channels for a platform."""
        return self._platforms.get(platform, [])

    def list_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all channels across all platforms."""
        return dict(self._platforms)

    def _save(self) -> None:
        """Persist directory to disk."""
        try:
            DIRECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DIRECTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"platforms": self._platforms, "built_at": self._last_build},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning("[channel-dir] save failed: %s", e)

    def load(self) -> bool:
        """Load directory from disk.  Returns True if loaded successfully."""
        if not DIRECTORY_PATH.exists():
            return False
        try:
            with open(DIRECTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._platforms = data.get("platforms", {})
            self._last_build = data.get("built_at", 0.0)
            return True
        except Exception as e:
            logger.warning("[channel-dir] load failed: %s", e)
            return False
