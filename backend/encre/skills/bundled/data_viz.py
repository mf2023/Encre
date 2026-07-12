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

"""Data-analysis & visualization skill prompt loader.

Loads the ``data_viz`` prompt from the ``skills`` category and substitutes the
analysis target supplied by the caller.
"""

from typing import Any

from encre.prompts.loader import PromptLoader

_loader = PromptLoader()


async def _data_viz_prompt(args: str | None, _ctx: dict[str, Any]) -> str:
    """Render the data-viz skill prompt for the given analysis target."""
    target = args or "the specified data"
    return _loader.load_with_context("data_viz", category="skills", target=target)
