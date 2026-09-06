#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 漏 2025-2026 Wenze Wei. All Rights Reserved.
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

"""Per-turn phase mixins of the agent loop.

Each mixin extracts one section of the former monolithic ``_run_impl``:

* :mod:`.prompt` -- system prompt build + session message preparation;
* :mod:`.compact` -- pre-model and post-tool context compaction;
* :mod:`.model` -- backend request preparation and streaming;
* :mod:`.recovery` -- post-stream recovery decisions and turn tail;
* :mod:`.tools` -- tool call preparation, gating and secondary tools;
* :mod:`.execute` -- safe/parallel and unsafe/sequential tool execution.

Phases share state via :class:`~encre.loop.turn_ctx.TurnContext` and signal
control flow with ``t.do_continue`` / ``t.do_break`` /
:class:`~encre.loop.turn_ctx.TurnExit`.
"""

from encre.loop.phases.compact import PhaseCompactMixin
from encre.loop.phases.execute import PhaseExecuteMixin
from encre.loop.phases.model import PhaseModelMixin
from encre.loop.phases.prompt import PhasePromptMixin
from encre.loop.phases.recovery import PhaseRecoveryMixin
from encre.loop.phases.tools import PhaseToolsMixin

__all__ = [
    "PhaseCompactMixin",
    "PhaseExecuteMixin",
    "PhaseModelMixin",
    "PhasePromptMixin",
    "PhaseRecoveryMixin",
    "PhaseToolsMixin",
]
