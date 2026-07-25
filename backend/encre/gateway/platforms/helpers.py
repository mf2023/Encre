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

"""Shared helpers for platform adapters.

Utility classes and functions used across multiple adapters:
- MessageDeduplicator: Prevent processing the same message twice
- ThreadParticipationTracker: Track bot participation in threads
- Media caching helpers
- Text formatting utilities
"""

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("encre.gateway.platforms.helpers")


# -- Message deduplication -----------------------------------------------------


class MessageDeduplicator:
    """Prevents processing the same message twice (within a time window).

    Uses a bounded LRU cache of message fingerprints.  Each fingerprint is
    derived from (chat_id, message_id) or a content hash when no id is available.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 300.0) -> None:
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def is_duplicate(self, chat_id: str, message_id: str | None, text: str = "") -> bool:
        """Return True if this message was already seen recently."""
        key = self._make_key(chat_id, message_id, text)
        now = time.time()
        self._evict_expired(now)

        if key in self._cache:
            return True

        self._cache[key] = now
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return False

    def _make_key(self, chat_id: str, message_id: str | None, text: str) -> str:
        if message_id:
            return f"{chat_id}:{message_id}"
        content = f"{chat_id}:{text[:200]}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self._ttl
        while self._cache:
            key, ts = next(iter(self._cache.items()))
            if ts > cutoff:
                break
            self._cache.popitem(last=False)


# -- Thread participation tracking ---------------------------------------------


class ThreadParticipationTracker:
    """Track whether the bot has participated in a thread/topic.

    Used to decide whether to respond to messages in a thread where the bot
    was not explicitly mentioned.
    """

    def __init__(self, max_threads: int = 500) -> None:
        self._threads: OrderedDict[str, float] = OrderedDict()
        self._max_threads = max_threads

    def mark_participated(self, thread_key: str) -> None:
        """Mark that the bot has participated in a thread."""
        self._threads[thread_key] = time.time()
        self._threads.move_to_end(thread_key)
        while len(self._threads) > self._max_threads:
            self._threads.popitem(last=False)

    def has_participated(self, thread_key: str) -> bool:
        """Check if the bot has participated in a thread."""
        return thread_key in self._threads


# -- Text formatting utilities -------------------------------------------------


def convert_table_to_bullets(text: str) -> str:
    """Convert markdown tables to bullet-point lists.

    Useful for platforms that don't render tables (Telegram, WhatsApp, etc.).
    """
    lines = text.split("\n")
    result: list[str] = []
    headers: list[str] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Skip separator lines (e.g. |---|---|)
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue
            if not in_table:
                headers = cells
                in_table = True
            else:
                # Data row: format as bullet with key:value pairs
                parts = []
                for i, cell in enumerate(cells):
                    if i < len(headers) and headers[i]:
                        parts.append(f"{headers[i]}: {cell}")
                    else:
                        parts.append(cell)
                result.append(f"• {' | '.join(parts)}")
        else:
            if in_table:
                in_table = False
                headers = []
            result.append(line)

    return "\n".join(result)


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def utf16_len(text: str) -> int:
    """Count UTF-16 code units (Telegram's length unit)."""
    return len(text.encode("utf-16-le")) // 2


# -- Media cache helpers -------------------------------------------------------


def cache_media_from_bytes(
    data: bytes,
    extension: str,
    prefix: str = "media",
) -> str:
    """Save media bytes to a temp file and return the path.

    Used by adapters that download media from platform APIs before passing
    to the agent (e.g., Telegram photos, Discord attachments).
    """
    import tempfile
    import os

    if not extension.startswith("."):
        extension = f".{extension}"
    fd, path = tempfile.mkstemp(prefix=f"encre_{prefix}_", suffix=extension)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def cache_media_from_url(url: str, extension: str = ".bin") -> str | None:
    """Download media from a URL and cache it locally.

    Returns the local file path, or None on failure.
    """
    import urllib.request
    import tempfile
    import os

    if not extension.startswith("."):
        extension = f".{extension}"
    try:
        fd, path = tempfile.mkstemp(prefix="encre_media_", suffix=extension)
        os.close(fd)
        urllib.request.urlretrieve(url, path)
        return path
    except Exception as e:
        logger.warning("Failed to cache media from %s: %s", url, e)
        return None
