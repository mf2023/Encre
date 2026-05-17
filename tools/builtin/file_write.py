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
from yim.native import write_file as _native_write


class YmiFileWriteTool(YmiTool):
    name: ClassVar[str] = "file_write"
    description: ClassVar[str] = "Write content to a file, creating it if it does not exist"
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }

    async def execute(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")

        try:
            _native_write(file_path, content)
            return f"Successfully wrote {len(content)} characters to {file_path}"
        except PermissionError:
            return f"Error: Permission denied: {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False