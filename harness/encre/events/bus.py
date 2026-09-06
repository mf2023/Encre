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

"""Phase bus: typed lifecycle hooks for agent-loop phases.

The loop is decomposed into named phases (``prompt``, ``pre_model``,
``model``, ``recovery``, ``tools``, ``compact``, ``turn_end``).  The
:class:`PhaseBus` lets collaborators observe -- and in well-defined cases
influence -- a phase without the loop importing them directly.

The canonical example is ``pre_model_request``: the historical
``hook_system.emit_pre_model_request`` semantic (a listener may return a
``modified_input`` dict that rewrites the backend messages) is preserved by
registering the hook as a bus handler; the loop now emits through the bus
and takes the last non-``None`` handler result, so exactly one invocation
with identical semantics is guaranteed.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from encre.logging_config import get_logger

logger = get_logger(__name__)

PhaseHandler = Callable[..., Awaitable[Any]]

# Well-known phase names (open set; collaborators may register more).
PHASE_PRE_MODEL_REQUEST = "pre_model_request"
PHASE_TURN_START = "turn_start"
PHASE_TURN_END = "turn_end"
PHASE_SESSION_START = "session_start"
PHASE_SESSION_END = "session_end"


class PhaseBus:
    """Registry of async handlers keyed by phase name.

    Handlers are invoked in registration order.  A handler that raises is
    logged and skipped -- a misbehaving observer can never take down the
    loop.  :meth:`emit` returns the last non-``None`` handler result so a
    single "influential" handler (e.g. ``pre_model_request`` input
    rewriting) keeps its historical semantics.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[PhaseHandler]] = {}

    def on(self, phase: str, handler: PhaseHandler) -> None:
        """Register ``handler`` for ``phase``.

        Args:
            phase: The phase name (see the ``PHASE_*`` constants).
            handler: An async callable receiving the phase payload as
                keyword arguments.
        """
        self._handlers.setdefault(phase, []).append(handler)

    def off(self, phase: str, handler: PhaseHandler) -> None:
        """Remove a previously registered handler (no-op when absent)."""
        handlers = self._handlers.get(phase)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            pass
        if not handlers:
            self._handlers.pop(phase, None)

    def has_listeners(self, phase: str) -> bool:
        """Whether any handler is registered for ``phase``."""
        return bool(self._handlers.get(phase))

    async def emit(self, phase: str, /, **payload: Any) -> Any:
        """Dispatch ``payload`` to every handler registered for ``phase``.

        Args:
            phase: The phase name.
            **payload: Keyword payload forwarded to every handler.

        Returns:
            The last non-``None`` handler result, or ``None`` when no
            handler produced a value.  This mirrors the historical
            single-hook semantics of ``pre_model_request``.
        """
        result: Any = None
        for handler in list(self._handlers.get(phase, ())):
            try:
                handler_result = await handler(**payload)
            except Exception:
                logger.warning(
                    "[phase_bus] handler failed phase=%s handler=%s",
                    phase, getattr(handler, "__qualname__", handler),
                    exc_info=True,
                )
                continue
            if handler_result is not None:
                result = handler_result
        return result
