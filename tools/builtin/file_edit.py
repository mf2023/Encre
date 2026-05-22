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
from yim.native import write_file as _native_write
from yim.native import compute_diff as _native_diff


class YmiFileEditTool(YmiTool):
    name: ClassVar[str] = "file_edit"
    description: ClassVar[str] = "Apply a search-and-replace edit to an existing file"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to edit",
            },
            "old_str": {
                "type": "string",
                "description": "The exact text to search for (must be unique and contiguous)",
            },
            "new_str": {
                "type": "string",
                "description": "The replacement text",
            },
        },
        "required": ["file_path", "old_str", "new_str"],
    }
    intents: ClassVar[list[str]] = ["general", "coding", "data"]

    async def execute(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        old_str = kwargs.get("old_str", "")
        new_str = kwargs.get("new_str", "")

        try:
            content = _native_read(file_path, 0, 0)
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except PermissionError:
            return f"Error: Permission denied: {file_path}"
        except Exception as e:
            return f"Error reading file: {e}"

        count = content.count(old_str)
        if count == 0:
            return f"Error: Could not find exact match for old_str in {file_path}"
        if count > 1:
            return f"Error: Found {count} occurrences of old_str. The match must be unique."

        new_content = content.replace(old_str, new_str, 1)

        try:
            _native_write(file_path, new_content)
        except PermissionError:
            return f"Error: Permission denied: {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

        diff_text = _native_diff(content, new_content)
        return f"Edit applied successfully.\n```diff\n{diff_text}\n```"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False