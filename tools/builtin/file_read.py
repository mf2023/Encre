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
from yim.native import read_file as _native_read


class YmiFileReadTool(YmiTool):
    name: ClassVar[str] = "file_read"
    description: ClassVar[str] = "Read the contents of a file from the local filesystem"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to read",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-indexed)",
            },
        },
        "required": ["file_path"],
    }

    async def execute(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        limit = kwargs.get("limit", 0)
        offset = kwargs.get("offset", 1)

        try:
            return _native_read(file_path, offset, limit)
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except PermissionError:
            return f"Error: Permission denied: {file_path}"
        except Exception as e:
            return f"Error reading file: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return True