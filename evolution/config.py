#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvolutionConfig:
    learner: Any = None
    optimizer: Any = None
    reflex: Any = None
    meta: Any = None
    learner_enabled: bool = True
    optimizer_enabled: bool = True
    reflex_enabled: bool = True
    meta_enabled: bool = True

    @classmethod
    def create_default(cls) -> EvolutionConfig:
        from yim.config import get_data_dir
        from yim.evolution.learner import YmiEvolutionLearner
        from yim.evolution.optimizer import YmiStrategyOptimizer
        from yim.evolution.reflex import YmiReflexLoop
        from yim.evolution.meta import YmiMetaCognition

        return cls(
            learner=YmiEvolutionLearner(storage_path=str(get_data_dir() / "evolution" / "state.json")),
            optimizer=YmiStrategyOptimizer(),
            reflex=YmiReflexLoop(enabled=True),
            meta=YmiMetaCognition(),
        )

    @classmethod
    def create_disabled(cls) -> EvolutionConfig:
        from yim.config import get_data_dir
        from yim.evolution.learner import YmiEvolutionLearner
        from yim.evolution.optimizer import YmiStrategyOptimizer
        from yim.evolution.reflex import YmiReflexLoop
        from yim.evolution.meta import YmiMetaCognition

        return cls(
            learner=YmiEvolutionLearner(storage_path=str(get_data_dir() / "evolution" / "state.json")),
            optimizer=YmiStrategyOptimizer(),
            reflex=YmiReflexLoop(enabled=False),
            meta=YmiMetaCognition(),
            learner_enabled=False,
            optimizer_enabled=False,
            reflex_enabled=False,
            meta_enabled=False,
        )


__all__ = ["EvolutionConfig"]