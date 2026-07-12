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

"""Module: builtin/glob.py

Glob implementation for the Encre tool system.
"""
import os
from typing import Any

from encre.native import glob_pattern as _native_glob
from encre.tools.base import build_tool


async def _glob_execute(**kwargs: Any) -> str:
    """List files matching a glob pattern. Returns paths sorted alphabetically."""
    pattern = kwargs.get("pattern", "")
    root_path = kwargs.get("path", os.getcwd())

    try:
        results = _native_glob(pattern, root_path)
    except Exception as exc:
        return f"Error: glob failed: {exc}"
    if not results:
        return f"No files match pattern: {pattern}"
    return "\n".join(results)


EncreGlobTool = build_tool(
    name="glob",
    description=(
        "Fast file pattern matching using glob patterns. "
        "Supports patterns like \"**/*.py\", \"src/**/*.ts\", "
        "or \"data/*.csv\". "
        "Returns matching file paths sorted alphabetically. "
        "Skips hidden dirs and common tooling directories.\n\n"
        "Use for: finding files by name patterns, exploring a directory tree, "
        "or narrowing a search before using grep.\n"
        "For open-ended searches that need multiple rounds, consider the agent tool."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match (e.g. **/*.py)",
            },
            "path": {
                "type": "string",
                "description": "Root directory to search in (default: current directory)",
            },
        },
        "required": ["pattern"],
    },
    execute=_glob_execute,
    intents=["general", "coding", "data"],
    category="filesystem",
    triggers=["glob", "ls", "dir", "list files", "find file", "search files", "tree", "stat", "match"],
    semantic_type="search",
    cost_level="low",
    retryability="auto",
    safe_fallback="Broaden the pattern (use **) or check that the root path exists.",
    is_concurrency_safe=lambda _: True,
    is_readonly=True,
)
