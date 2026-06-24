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



import re
from typing import Any

from encre.native import compute_diff as _native_diff
from encre.native import read_file as _native_read
from encre.native import write_file as _native_write
from encre.tools.base import build_tool
from encre.tools.builtin._sandbox import remap_tool_path

_DIFF_ADD_RE = re.compile(r"^\+(?!\+\+)", re.MULTILINE)
_DIFF_DEL_RE = re.compile(r"^-(?!--)", re.MULTILINE)


async def _file_write_execute(**kwargs: Any) -> str:
    file_path = kwargs.get("file_path", "")
    content = kwargs.get("content", "")
    file_path = remap_tool_path(file_path)
    if not file_path:
        return "Error: 路径被沙箱拒绝 (Path rejected by sandbox)"

    try:
        try:
            before = _native_read(file_path, 0, 0)
        except FileNotFoundError:
            before = ""
        if not _native_write(file_path, content):
            return f"Error: Failed to write file: {file_path}"
        diff_text = _native_diff(before, content)
        add_count = len(_DIFF_ADD_RE.findall(diff_text))
        del_count = len(_DIFF_DEL_RE.findall(diff_text))
        return (
            f"Successfully wrote {len(content)} characters to {file_path}\n"
            f"{add_count} insertions(+), {del_count} deletions(-)\n"
            f"```diff\n{diff_text}\n```"
        )
    except PermissionError:
        return f"Error: Permission denied: {file_path}"
    except Exception as e:
        return f"Error: Error writing file: {e}"


EncreFileWriteTool = build_tool(
    name="file_write",
    description=(
        "Writes a file to the local filesystem.\n\n"
        "Usage:\n"
        "- This tool will overwrite the existing file if there is one at the provided path.\n"
        "- If this is an existing file, you MUST use the file_read tool first to read the "
        "file's contents. This tool will fail if you did not read the file first.\n"
        "- Prefer the file_edit tool for modifying existing files — it only sends the diff. "
        "Only use this tool to create new files or for complete rewrites.\n"
        "- NEVER create documentation files (*.md) or README files unless explicitly "
        "requested by the user.\n"
        "- Only use emojis if the user explicitly requests it. Avoid writing emojis to "
        "files unless asked."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file (filename, relative path, or absolute path within the workspace)",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    },
    execute=_file_write_execute,
    intents=["general", "coding", "data"],
)
