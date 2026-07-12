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

"""Archive / compression tool (zip, tar, gzip, bzip2, xz, 7z).

Exposes create / extract / list actions over common archive formats behind a
single tool interface, with optional per-format compression controls.
"""


import asyncio
import json
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _archive_execute(**kwargs: Any) -> str:
    """Archive execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    archive_path = kwargs.get("archive_path", "")
    source_paths = kwargs.get("source_paths", [])
    dest_dir = kwargs.get("dest_dir", "")
    archive_format = kwargs.get("format", "zip")
    compression = kwargs.get("compression", "")

    if not archive_path:
        return "Missing required field: archive_path"

    loop = asyncio.get_event_loop()

    if action == "create":
        if not source_paths:
            return "Missing required field: source_paths"

        def _create() -> str:
            """Create."""
            try:
                archive_path_p = Path(archive_path)
                archive_path_p.parent.mkdir(parents=True, exist_ok=True)

                if archive_format == "zip":
                    with zipfile.ZipFile(str(archive_path_p), "w", zipfile.ZIP_DEFLATED) as zf:
                        for sp in source_paths:
                            sp_path = Path(sp)
                            if sp_path.is_dir():
                                for file_path in sp_path.rglob("*"):
                                    if file_path.is_file():
                                        arcname = str(file_path.relative_to(sp_path.parent))
                                        zf.write(str(file_path), arcname)
                            elif sp_path.is_file():
                                zf.write(str(sp_path), sp_path.name)
                elif archive_format in ("tar", "gz", "bz2", "xz"):
                    mode = "w"
                    ext = archive_format
                    if compression == "gz" or ext == "gz":
                        mode = "w:gz"
                    elif compression == "bz2" or ext == "bz2":
                        mode = "w:bz2"
                    elif compression == "xz" or ext == "xz":
                        mode = "w:xz"
                    else:
                        mode = "w" if ext == "tar" else "w:gz"
                    with tarfile.open(str(archive_path_p), mode) as tf:
                        for sp in source_paths:
                            sp_path = Path(sp)
                            if sp_path.is_dir() or sp_path.is_file():
                                tf.add(str(sp_path), arcname=sp_path.name)
                else:
                    return f"Unsupported format: {archive_format}. Supported: zip, tar, gz, bz2, xz"

                return f"Archive created: {archive_path_p} ({_size_str(archive_path_p.stat().st_size)})"
            except Exception as e:
                return f"Failed to create archive: {e}"

        return await loop.run_in_executor(None, _create)

    elif action == "extract":
        if not dest_dir:
            dest_dir = os.path.dirname(archive_path)

        def _extract() -> str:
            """Extract."""
            try:
                dest_path = Path(dest_dir)
                dest_path.mkdir(parents=True, exist_ok=True)
                ext = str(archive_path).lower()

                if ext.endswith(".zip") or zipfile.is_zipfile(archive_path):
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        zf.extractall(str(dest_path))
                else:
                    if not tarfile.is_tarfile(archive_path):
                        return f"Not a valid archive: {archive_path}"
                    with tarfile.open(archive_path, "r:*") as tf:
                        tf.extractall(str(dest_path))

                extracted = sum(len(files) for _, _, files in os.walk(str(dest_path)))
                return f"Extracted to {dest_path} ({extracted} files)"
            except Exception as e:
                return f"Failed to extract archive: {e}"

        return await loop.run_in_executor(None, _extract)

    elif action == "list":
        def _list() -> str:
            """List."""
            try:
                entries = []
                ext = str(archive_path).lower()

                if ext.endswith(".zip") or zipfile.is_zipfile(archive_path):
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        for info in zf.infolist():
                            entries.append({
                                "name": info.filename,
                                "size": info.file_size,
                                "compressed": info.compress_size,
                                "date": _fmt_date(info.date_time),
                            })
                else:
                    with tarfile.open(archive_path, "r:*") as tf:
                        for member in tf.getmembers():
                            entries.append({
                                "name": member.name,
                                "size": member.size,
                                "type": "directory" if member.isdir() else "file",
                                "date": member.mtime,
                            })
                return json.dumps(entries, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to list archive: {e}"

        return await loop.run_in_executor(None, _list)

    elif action == "info":
        def _info() -> str:
            """Info."""
            try:
                p = Path(archive_path)
                if not p.exists():
                    return f"File not found: {archive_path}"
                stat = p.stat()
                ext = str(archive_path).lower()
                count = 0
                if ext.endswith(".zip") or zipfile.is_zipfile(archive_path):
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        count = len(zf.infolist())
                else:
                    with tarfile.open(archive_path, "r:*") as tf:
                        count = len(tf.getmembers())
                info_data = {
                    "path": str(p),
                    "size": stat.st_size,
                    "size_str": _size_str(stat.st_size),
                    "entries": count,
                    "format": archive_format if archive_format else ext.rsplit(".", 1)[-1],
                    "modified": stat.st_mtime,
                }
                return json.dumps(info_data, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to get archive info: {e}"

        return await loop.run_in_executor(None, _info)

    return f"Unknown action: {action}. Supported: create, extract, list, info"


def _size_str(size_bytes: int) -> str:
    """Size str.

    Args:
        size_bytes: Description of the size_bytes parameter.
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _fmt_date(dt: tuple[int, ...]) -> str:
    """Fmt date.

    Args:
        dt: Description of the dt parameter.
    """
    if not dt or dt[0] == 0:
        return ""
    return f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}"


EncreArchiveTool = build_tool(
    name="archive",
    description="Create/extract/list/inspect archives (zip, tar, gz, bz2, xz). Create from files/dirs, extract, list, get metadata.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "extract", "list", "info"],
                "description": "Action to perform",
            },
            "archive_path": {"type": "string", "description": "Path to the archive file"},
            "source_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files/directories to archive (for create)",
            },
            "dest_dir": {"type": "string", "description": "Destination directory for extraction (for extract)"},
            "format": {
                "type": "string",
                "enum": ["zip", "tar", "gz", "bz2", "xz"],
                "description": "Archive format (for create, default zip)",
            },
            "compression": {
                "type": "string",
                "enum": ["", "gz", "bz2", "xz"],
                "description": "Compression type for tar archives",
            },
        },
        "required": ["action", "archive_path"],
    },
    execute=_archive_execute,
    intents=["general", "coding", "data"],
    category="filesystem",
    semantic_type="write",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: False,
    is_destructive=lambda args: args.get("action") in ("create", "extract"),
)
