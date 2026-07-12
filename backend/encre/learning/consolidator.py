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

"""Periodic memory consolidation for the learning subsystem.

:class:`MemoryConsolidator` wraps the agent's ``memory_system`` and, on a
fixed interval, triggers its ``consolidate()`` coroutine so short-term
memories are merged into long-term storage without blocking the agent loop.
"""

import asyncio
import contextlib
import logging

from encre.agent import EncreAgent

logger = logging.getLogger("encre.learning.consolidator")


class MemoryConsolidator:
    """Runs memory consolidation on a background timer."""
    def __init__(self, agent: EncreAgent, interval: int = 3600) -> None:
        """Wire up the agent and the consolidation interval (seconds)."""
        self._agent = agent
        self._interval = interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch the background consolidation loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Memory consolidator started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        """Stop the loop and await its cancellation."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Memory consolidator stopped")

    async def _loop(self) -> None:
        """Sleep for the interval, then consolidate, while running."""
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            await self._consolidate()

    async def consolidate_now(self) -> None:
        """Force a single consolidation pass immediately."""
        await self._consolidate()

    async def _consolidate(self) -> None:
        """Call the agent's memory_system.consolidate() if available."""
        memory_system = getattr(self._agent, "memory_system", None)
        if memory_system is None:
            return

        try:
            if hasattr(memory_system, "consolidate") and callable(memory_system.consolidate):
                result = await memory_system.consolidate()
                logger.info("Memory consolidation completed: %s", result)
        except Exception as e:
            logger.warning("Memory consolidation failed: %s", e)
