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



import os
from typing import Any

from encre.native import glob_pattern as _native_glob
from encre.tools.base import build_tool


async def _glob_execute(**kwargs: Any) -> str:
    pattern = kwargs.get("pattern", "")
    root_path = kwargs.get("path", os.getcwd())

    results = _native_glob(pattern, root_path)
    if not results:
        return f"No files match pattern: {pattern}"
    return "\n".join(results)


EncreGlobTool = build_tool(
    name="glob",
    description=(
        "- Fast file pattern matching tool that works with any codebase size\n"
        "- Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\"\n"
        "- Returns matching file paths sorted by modification time\n"
        "- Use this tool when you need to find files by name patterns\n"
        "- When you are doing an open ended search that may require multiple "
        "rounds of globbing and grepping, use the agent tool instead"
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
    is_concurrency_safe=lambda _: True,
)
