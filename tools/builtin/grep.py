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

from typing import Any, ClassVar

from yim.tools.base import YmiTool
from yim.native import grep as _native_grep


class YmiGrepTool(YmiTool):
    name: ClassVar[str] = "grep"
    description: ClassVar[str] = "Search for a pattern in files using regular expressions"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regular expression pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in",
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. *.py)",
            },
            "-i": {
                "type": "boolean",
                "description": "Case insensitive search",
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode",
            },
        },
        "required": ["pattern", "path"],
    }

    async def execute(self, **kwargs: Any) -> str:
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", "")
        glob_filter = kwargs.get("glob", "")
        case_insensitive = kwargs.get("-i", False)
        output_mode = kwargs.get("output_mode", "content")

        return _native_grep(pattern, path, case_insensitive, glob_filter, output_mode)

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return True