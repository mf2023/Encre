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

"""Learning engine that crystallises repeated tool patterns into skills.

This module implements the proactive half of the learning subsystem.
:class:`LearningEngine` watches the tool calls an agent makes during a run and,
once it believes a pattern is repeated often enough, asks
:class:`~encre.learning.skill_generator.SkillGenerator` to turn that pattern
into an auto-generated skill and register it with the skill store.

How it works
------------
* The engine is fed the names of the tools used in a run via
  :meth:`LearningEngine.analyze_run`. It does not track the call sequence
  itself in detail; it only counts how many tools were involved.
* When the number of distinct tool names in a single run reaches
  :attr:`TOOL_CALL_THRESHOLD`, the engine spawns a background asyncio task that
  performs the (potentially slow) skill generation and registration off the
  critical path.
* All in-flight crystallisation tasks are tracked so that :meth:`stop` can
  cancel them and wait for them to finish tearing down.

Caveats
-------
The engine deliberately ignores partial failures: if a generated skill cannot
be registered, the error is logged by the generator and the engine simply
forgets the task. This keeps the learning side-effects from ever blocking or
crashing the main agent loop.
"""

import asyncio
import logging

from encre.agent import EncreAgent

logger = logging.getLogger("encre.learning")


class LearningEngine:
    """Spawns skill-crystallisation tasks from frequent tool use.

    The engine is a thin orchestrator: it decides *when* a run is worth
    learning from, and delegates the actual skill creation to
    :class:`~encre.learning.skill_generator.SkillGenerator`. It owns an agent
    reference (used only to construct the generator) and a small bookkeeping
    structure that tracks the background tasks it has launched.

    Attributes
    ----------
    TOOL_CALL_THRESHOLD:
        Minimum number of distinct tool names a run must use before the engine
        considers the pattern worth crystallising into a skill. Set to 5.
    _agent:
        The agent whose skills will be generated and registered.
    _running:
        Lifecycle flag; the engine only acts on runs while this is ``True``.
    _tasks:
        Live list of :class:`asyncio.Task` objects spawned for crystallisation.
        Entries remove themselves when their task completes.
    """

    # Below this many distinct tools a run is treated as too small to learn from.
    TOOL_CALL_THRESHOLD = 5

    def __init__(self, agent: EncreAgent) -> None:
        """Initialise the engine with its owning agent.

        Args:
            agent: The agent used to build skill generators. The reference is
                stored and later handed to :class:`SkillGenerator`; it is not
                otherwise used here.

        Returns:
            None.
        """
        self._agent = agent
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Mark the engine as running and ready to analyse runs.

        Returns:
            None.
        """
        self._running = True
        logger.info("Learning engine started")

    async def stop(self) -> None:
        """Shut the engine down, cancelling all in-flight crystallisation.

        Cancels every tracked task, waits for them to finish (exceptions are
        collected and ignored so a failing skill generation cannot block
        shutdown), then clears the task list. Idempotent after the first call
        because ``_running`` is ``False`` and the task list is empty.

        Returns:
            None.
        """
        self._running = False
        for task in self._tasks:
            task.cancel()
        # Gather with return_exceptions so a cancelled/failed task does not
        # propagate an exception out of shutdown.
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Learning engine stopped")

    async def analyze_run(self, tool_names: list[str], prompt: str) -> None:
        """Consider a finished run and perhaps queue a crystallisation task.

        The engine ignores runs while stopped or while the run did not involve
        enough distinct tools. When the run clears the threshold, a background
        task is created for :meth:`_crystallize` and appended to the tracked
        task list; a done-callback later prunes it once finished.

        Args:
            tool_names: Names of the tools used during the run. Used only to
                measure how "rich" the run was against
                :attr:`TOOL_CALL_THRESHOLD`.
            prompt: The original user prompt for the run, passed through to the
                generator so the generated skill can capture intent.

        Returns:
            None.
        """
        if not self._running:
            return
        if len(tool_names) < self.TOOL_CALL_THRESHOLD:
            return
        # Offload the (potentially slow) generation/registration to the event
        # loop so the caller's analysis path is never blocked.
        task = asyncio.create_task(self._crystallize(tool_names, prompt))
        self._tasks.append(task)
        # When the task finishes, drop it from the list if still present.
        task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)

    async def _crystallize(self, tool_names: list[str], prompt: str) -> None:
        """Generate and register a skill from the observed tool pattern.

        Builds a :class:`SkillGenerator` for the owning agent, asks it to
        synthesise a skill definition from the tool names and prompt, and if a
        definition comes back, registers it. A ``None`` result from the
        generator means nothing worth saving was found, so we silently stop.

        Args:
            tool_names: Tool names that formed the pattern to learn.
            prompt: The originating prompt, preserved as skill context.

        Returns:
            None.

        Raises:
            Any exception raised by ``SkillGenerator.register`` is allowed to
            propagate to the task wrapper; the engine does not catch it here,
            so callers awaiting the task (or the done-callback pruner) should
            treat failures as non-fatal.
        """
        # Imported lazily to avoid a circular import at module load time.
        from encre.learning.skill_generator import SkillGenerator

        generator = SkillGenerator(self._agent)
        skill_def = generator.generate(tool_names, prompt)
        if skill_def is None:
            return
        await generator.register(skill_def)
