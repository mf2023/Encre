#!/usr/bin/env python3

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0

from encre.compact.engine import CompactEngine, EncreCompactEngine

# Legacy strategies kept for backward compatibility
from encre.compact.strategies import (
    EncreAutoCompactStrategy,
    EncreBudgetReductionStrategy,
    EncreContextCollapseStrategy,
    EncreMicroCompactStrategy,
    EncreMultiStagePipeline,
    EncreSemanticCompactStrategy,
    EncreSnipStrategy,
    EncreTokenBudgetStrategy,
)

__all__ = [
    "CompactEngine",
    "EncreAutoCompactStrategy",
    "EncreBudgetReductionStrategy",
    "EncreCompactEngine",
    "EncreContextCollapseStrategy",
    "EncreMicroCompactStrategy",
    "EncreMultiStagePipeline",
    "EncreSemanticCompactStrategy",
    "EncreSnipStrategy",
    "EncreTokenBudgetStrategy",
]
