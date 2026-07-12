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

"""Diff / file & directory comparison tool.

Produces unified diffs between files or directories, with optional statistics
and patch views to help the model review changes.
"""


import difflib
import json
import os
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _diff_execute(**kwargs: Any) -> str:
    """Diff execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    text1 = kwargs.get("text1", "")
    text2 = kwargs.get("text2", "")
    file1 = kwargs.get("file1", "")
    file2 = kwargs.get("file2", "")
    context_lines = kwargs.get("context_lines", 3)
    ignore_case = kwargs.get("ignore_case", False)
    ignore_whitespace = kwargs.get("ignore_whitespace", False)
    output_format = kwargs.get("output_format", "unified")

    if action == "text":
        if not text1 or not text2:
            return "Missing required fields: text1 and text2"

        lines1 = text1.splitlines(keepends=True)
        lines2 = text2.splitlines(keepends=True)

        if ignore_case:
            lines1 = [line.lower() for line in lines1]
            lines2 = [line.lower() for line in lines2]

        return _format_diff(lines1, lines2, "text1", "text2", context_lines, output_format, ignore_whitespace)

    elif action == "file":
        if not file1 or not file2:
            return "Missing required fields: file1 and file2"
        if not os.path.exists(file1):
            return f"File not found: {file1}"
        if not os.path.exists(file2):
            return f"File not found: {file2}"

        try:
            content1 = Path(file1).read_text(encoding="utf-8")
            content2 = Path(file2).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _binary_diff(file1, file2)
        except OSError as e:
            return f"File error: {e}"

        lines1 = content1.splitlines(keepends=True)
        lines2 = content2.splitlines(keepends=True)

        if ignore_case:
            lines1 = [line.lower() for line in lines1]
            lines2 = [line.lower() for line in lines2]

        name1 = os.path.basename(file1)
        name2 = os.path.basename(file2)
        return _format_diff(lines1, lines2, name1, name2, context_lines, output_format, ignore_whitespace)

    elif action == "directory":
        if not file1 or not file2:
            return "Missing required fields: file1 and file2 (directory paths)"
        if not os.path.isdir(file1):
            return f"Directory not found: {file1}"
        if not os.path.isdir(file2):
            return f"Directory not found: {file2}"

        return _dir_diff(file1, file2)

    elif action == "statistics":
        if not text1 and not file1:
            return "Missing required field: text1 or file1"
        if not text2 and not file2:
            return "Missing required field: text2 or file2"

        try:
            if file1 and file2:
                t1 = Path(file1).read_text(encoding="utf-8")
                t2 = Path(file2).read_text(encoding="utf-8")
            else:
                t1, t2 = text1, text2
        except OSError as e:
            return f"File error: {e}"

        lines1 = t1.splitlines()
        lines2 = t2.splitlines()

        matcher = difflib.SequenceMatcher(
            None,
            [line.lower() if ignore_case else line for line in lines1],
            [line.lower() if ignore_case else line for line in lines2],
        )
        ratio = matcher.ratio()

        added = 0
        removed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                added += j2 - j1
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "replace":
                removed += i2 - i1
                added += j2 - j1

        return json.dumps({
            "file1": file1 or "text1",
            "file2": file2 or "text2",
            "lines_in_file1": len(lines1),
            "lines_in_file2": len(lines2),
            "added_lines": added,
            "removed_lines": removed,
            "changed_lines": added + removed,
            "similarity_ratio": round(ratio, 4),
            "similarity_percent": f"{ratio * 100:.1f}%",
        }, ensure_ascii=False, indent=2)

    return f"Unknown action: {action}. Supported: text, file, directory, statistics"


def _format_diff(
    lines1: list[str],
    lines2: list[str],
    name1: str,
    name2: str,
    context: int,
    output_format: str,
    ignore_ws: bool,
) -> str:
    """Format diff.

    Args:
        lines1: Description of the lines1 parameter.
        lines2: Description of the lines2 parameter.
        name1: Description of the name1 parameter.
        name2: Description of the name2 parameter.
        context: Description of the context parameter.
        output_format: Description of the output_format parameter.
        ignore_ws: Description of the ignore_ws parameter.
    """
    if ignore_ws:
        lines1 = [line.strip() + "\n" for line in lines1]
        lines2 = [line.strip() + "\n" for line in lines2]

    if output_format == "unified":
        diff = difflib.unified_diff(lines1, lines2, fromfile=name1, tofile=name2, n=context)
        result = "".join(diff)
        if not result:
            return "Files are identical"
        return result

    elif output_format == "context":
        diff = difflib.context_diff(lines1, lines2, fromfile=name1, tofile=name2, n=context)
        result = "".join(diff)
        if not result:
            return "Files are identical"
        return result

    elif output_format == "json":
        matcher = difflib.SequenceMatcher(None, lines1, lines2)
        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            change = {
                "type": tag,
            }
            if tag in ("delete", "replace"):
                change["original"] = {
                    "start_line": i1 + 1,
                    "end_line": i2,
                    "content": "".join(lines1[i1:i2]),
                }
            if tag in ("insert", "replace"):
                change["modified"] = {
                    "start_line": j1 + 1,
                    "end_line": j2,
                    "content": "".join(lines2[j1:j2]),
                }
            changes.append(change)
        return json.dumps({
            "file1": name1,
            "file2": name2,
            "changes": changes,
            "total_changes": len(changes),
        }, ensure_ascii=False, indent=2)

    elif output_format == "html":
        from difflib import HtmlDiff
        diff = HtmlDiff(tabsize=4, wrapcolumn=80)
        result = diff.make_table(lines1, lines2, name1, name2, context=True, numlines=context)
        return f"<html><body>{result}</body></html>"

    return f"Unsupported output format: {output_format}"


def _binary_diff(file1: str, file2: str) -> str:
    """Binary diff.

    Args:
        file1: Description of the file1 parameter.
        file2: Description of the file2 parameter.
    """
    try:
        import hashlib
        h1 = hashlib.sha256()
        h2 = hashlib.sha256()
        size1 = 0
        size2 = 0

        with open(file1, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h1.update(chunk)
                size1 += len(chunk)

        with open(file2, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h2.update(chunk)
                size2 += len(chunk)

        return json.dumps({
            "file1": os.path.basename(file1),
            "file2": os.path.basename(file2),
            "type": "binary",
            "size1": size1,
            "size2": size2,
            "same_size": size1 == size2,
            "same_hash": h1.hexdigest() == h2.hexdigest(),
            "hash1": h1.hexdigest(),
            "hash2": h2.hexdigest(),
        }, ensure_ascii=False, indent=2)
    except OSError as e:
        return f"File error: {e}"


def _dir_diff(dir1: str, dir2: str) -> str:
    """Dir diff.

    Args:
        dir1: Description of the dir1 parameter.
        dir2: Description of the dir2 parameter.
    """
    import filecmp

    comparison = filecmp.dircmp(dir1, dir2)

    def _walk(cmp: filecmp.dircmp, path: str = "") -> dict:
        """Walk.

        Args:
            cmp: Description of the cmp parameter.
            path: Description of the path parameter.
        """
        result = {
            "only_in_left": [f"{path}/{f}" if path else f for f in cmp.left_only],
            "only_in_right": [f"{path}/{f}" if path else f for f in cmp.right_only],
            "differing_files": [f"{path}/{f}" if path else f for f in cmp.diff_files],
            "identical_files": [f"{path}/{f}" if path else f for f in cmp.same_files],
            "subdirs": {},
        }
        for subdir, sub_cmp in cmp.subdirs.items():
            sub_path = f"{path}/{subdir}" if path else subdir
            result["subdirs"][subdir] = _walk(sub_cmp, sub_path)
        return result

    return json.dumps(_walk(comparison), ensure_ascii=False, indent=2)


EncreDiffTool = build_tool(
    name="diff",
    description="Compare text/files/directories. Unified/context/JSON/HTML diff. Binary diff (SHA-256), directory diff, statistics.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["text", "file", "directory", "statistics"],
                "description": "Action to perform",
            },
            "text1": {"type": "string", "description": "First text content (for text/statistics actions)"},
            "text2": {"type": "string", "description": "Second text content (for text/statistics actions)"},
            "file1": {"type": "string", "description": "First file or directory path"},
            "file2": {"type": "string", "description": "Second file or directory path"},
            "context_lines": {"type": "integer", "description": "Context lines around changes (default 3)"},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive comparison (default false)"},
            "ignore_whitespace": {"type": "boolean", "description": "Ignore whitespace differences (default false)"},
            "output_format": {
                "type": "string",
                "enum": ["unified", "context", "json", "html"],
                "description": "Output format (default unified)",
            },
        },
        "required": ["action"],
    },
    execute=_diff_execute,
    intents=["general", "coding"],
    category="code_intel",
    semantic_type="read",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_readonly=lambda _: True,
)
