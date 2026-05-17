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

from abc import ABC, abstractmethod
from typing import Any

from yim.compact.strategies import YmiCompactStrategy, YmiMultiStagePipeline


class YmiCompactEngine:
    def __init__(self, strategy: YmiCompactStrategy | None = None) -> None:
        self._strategy = strategy or YmiMultiStagePipeline()

    def set_strategy(self, strategy: YmiCompactStrategy) -> None:
        self._strategy = strategy

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        return await self._strategy.compact(messages, max_tokens)

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        return await self._strategy.should_compact(messages, max_tokens)