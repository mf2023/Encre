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

from yim.compact.engine import YmiCompactEngine
from yim.compact.strategies import (
    YmiAlwaysCompactStrategy,
    YmiTokenBudgetStrategy,
    YmiAutoCompactStrategy,
    YmiBudgetReductionStrategy,
    YmiSemanticCompactStrategy,
    YmiSnipStrategy,
    YmiMicroCompactStrategy,
    YmiContextCollapseStrategy,
    YmiMultiStagePipeline,
)
from yim.compact.semantic import (
    SemanticToolOutputCompactor,
    ContextPartitioner,
    ContextPartition,
    ContextTier,
)

__all__ = [
    "YmiCompactEngine",
    "YmiAlwaysCompactStrategy",
    "YmiTokenBudgetStrategy",
    "YmiAutoCompactStrategy",
    "YmiSemanticCompactStrategy",
    "YmiBudgetReductionStrategy",
    "YmiSnipStrategy",
    "YmiMicroCompactStrategy",
    "YmiContextCollapseStrategy",
    "YmiMultiStagePipeline",
    "SemanticToolOutputCompactor",
    "ContextPartitioner",
    "ContextPartition",
    "ContextTier",
]
