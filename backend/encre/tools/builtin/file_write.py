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

"""Module: builtin/file_write.py

File write implementation for the Encre tool system.
"""
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
    """Write content to a file, overwriting if it exists. Returns a diff summary."""
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

        # Skip expensive diff for large files.
        large_file = len(before) > 100_000 or len(content) > 100_000
        if large_file:
            before_lines = before.splitlines()
            content_lines = content.splitlines()
            line_delta = len(content_lines) - len(before_lines)
            add_count = max(line_delta, 0)
            del_count = max(-line_delta, 0)
            if line_delta == 0 and before != content:
                changed = sum(1 for o, c in zip(before_lines, content_lines) if o != c)
                add_count = del_count = changed
            return (
                f"Successfully wrote {len(content)} characters to {file_path}\n"
                f"{add_count} insertions(+), {del_count} deletions(-)\n"
                f"(large file \u2014 diff omitted)"
            )

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
        "Create a new file or overwrite an existing one entirely. "
        "No need to read the file first — this tool accepts the full content.\n\n"
        "Use this for: new files, complete rewrites, generating output files.\n"
        "Use file_edit instead for targeted modifications to existing files.\n\n"
        "Returns a unified diff showing what changed, with insertion/deletion counts."
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
    category="filesystem",
    triggers=["write file", "create file", "save file", "overwrite", "put"],
    semantic_type="write",
    cost_level="medium",
    retryability="guarded",
    safe_fallback="Check the file path and content before retrying. For small changes, prefer file_edit instead.",
    is_destructive=True,
)
