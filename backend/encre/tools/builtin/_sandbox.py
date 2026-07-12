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

"""Path isolation for file operations.

Provides **strict** path remapping to prevent the agent from reading,
writing, or deleting files outside the allowed sandbox directory.

Security guarantees:
1. Relative paths and ``/workspace/...`` prefixes are resolved into the
   per-session sandbox directory.
2. ``..`` path traversal is detected and rejected.
3. Symlinks are resolved before the boundary check.
4. Paths outside the sandbox are mapped to a **rejection marker** (empty
   string) so callers can safely refuse the operation.
5. In **workspace mode**, paths must resolve **inside** the workspace root.

Workspace mode keeps paths unchanged (they already point to the workspace).
"""

import fnmatch
import os
from pathlib import Path, PurePath


def get_session_files_dir(session_id: str = "") -> Path:
    """Return the per-session files directory for *session_id*.

    In general mode, user-created files are persisted here instead of the
    sandbox so they live alongside the session and survive as artifacts.
    Creates the directory if it does not exist.
    """
    from encre.config import get_data_dir
    root = get_data_dir() / "sessions"
    root = root / session_id / "files" if session_id else root / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_sandbox_root(session_id: str = "") -> Path:
    """Return the sandbox root directory for *session_id*.

    Creates the directory if it does not exist.
    """
    from encre.config import get_data_dir
    root = get_data_dir() / "sandbox"
    if session_id:
        root = root / session_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def remap_tool_path(file_path: str) -> str:
    """Remap a file path from tool context (resolves loop + session).

    Returns the remapped absolute path suitable for the current
    session and workspace mode. In workspace mode, paths are kept
    relative to the workspace root. In general mode, relative paths
    resolve under the session's files directory (``<data_dir>/sessions/<session_id>/files/``).
    Paths that would escape the allowed root are forced back into the
    allowed root by keeping only the filename.
    """
    from encre.tools.builtin.agent import _resolve_loop
    loop = _resolve_loop()
    if loop is None:
        return file_path
    ws = getattr(loop.config, "workspace", "") or ""
    sid = getattr(loop.session, "id", "") or ""

    # Try remapping; if rejected, force-remap into the allowed root
    result = remap_path(file_path, session_id=sid, workspace_root=ws)
    if result:
        return result
    # Path was rejected — force-remap into the session files dir as filename only
    import os
    files_dir = get_session_files_dir(sid)
    # Use only the filename, discarding any directory structure
    safe_name = os.path.basename(file_path) or "output.txt"
    return str(files_dir / safe_name)


def remap_path(
    file_path: str,
    session_id: str = "",
    workspace_root: str = "",
) -> str:
    """Remap *file_path* into the workspace or the session files directory.

    Resolution rules (in priority order):
    1. **Empty / whitespace path** → reject (empty string).
    2. **Workspace mode** (``workspace_root`` is set + exists): keep
       the path relative to the workspace. Must resolve **inside**
       the workspace root (no escaping via ``../``).
    3. **General mode** (no workspace):
       - **Absolute paths** are passed through as-is (the user or context
         explicitly specified a location).
       - **Relative paths** are resolved into ``<sessions>/<session_id>/files/``.
       - ``..`` traversal in relative paths is rejected.

    Returns the resolved absolute path, or ``""`` if the path is unsafe.
    """
    if not file_path or not file_path.strip():
        return ""

    # ── Workspace mode ──────────────────────────────────────────
    if workspace_root and os.path.isdir(workspace_root):
        return _resolve_workspace_path(file_path, workspace_root)

    # ── General mode: session files directory ───────────────────
    files_dir = get_session_files_dir(session_id)
    return _resolve_session_files_path(file_path, str(files_dir))


def _resolve_workspace_path(file_path: str, workspace: str) -> str:
    """Resolve *file_path* relative to the workspace directory.

    Security: the resolved path must be strictly inside the workspace.
    Rejects ``..`` escapes, symlinks pointing outside, and absolute
    paths outside workspace.

    Rules:
    - If *file_path* starts with ``/workspace/``, strip that prefix
      and resolve relative to workspace.
    - Relative paths resolve against workspace root.
    - Absolute paths must be inside workspace to pass.
    """
    p = Path(file_path)
    workspace_abs = Path(workspace).resolve()

    # Strip the model's virtual "/workspace/" prefix
    if p.is_absolute():
        path_str = str(p).replace("\\", "/")
        if path_str.startswith("/workspace/") or path_str == "/workspace":
            p = Path(path_str[11:]) if len(path_str) > 11 else Path(".")

    # ── Relative paths (including stripped /workspace/) ──
    if not p.is_absolute():
        try:
            resolved = (workspace_abs / p).resolve()
        except (OSError, ValueError):
            return ""
        try:
            resolved.relative_to(workspace_abs)
        except ValueError:
            return ""
        return str(resolved)

    # ── Absolute paths ──
    try:
        resolved = p.resolve()
    except (OSError, ValueError):
        return ""
    try:
        resolved.relative_to(workspace_abs)
    except ValueError:
        return ""
    return str(resolved)


def _resolve_session_files_path(
    file_path: str,
    files_dir: str,
) -> str:
    """Resolve *file_path* into the session files directory.

    Resolution rules:
    - **Relative paths** (``output.txt``, ``./foo``) are resolved **relative
      to the session files directory** — this is the default when no path
      is specified by the user or context.
    - **Absolute paths** are passed through as-is (the user or context
      explicitly specified a location; do not rewrite it).
    - Virtual ``/workspace/...`` prefix is stripped and treated as relative.
    - ``..`` traversal in relative paths is caught via containment check.

    Returns the absolute path, or **empty string** when the path is empty.
    """
    p = Path(file_path)

    # Strip the model's virtual "/workspace/" prefix
    path_str = file_path.replace("\\", "/")
    if path_str.startswith("/workspace/"):
        p = Path(path_str[11:])
    elif path_str == "/workspace":
        p = Path(".")

    files_abs = Path(files_dir).resolve()

    # ── Absolute path: user/context specified a location — pass through ──
    if p.is_absolute():
        # Verify symlinks resolve inside the session files directory
        try:
            resolved = p.resolve(strict=True)
            resolved.relative_to(files_abs)
        except (OSError, ValueError):
            pass
        return str(p)

    # ── Relative paths: resolve against the session files directory ──
    try:
        resolved = (files_abs / p).resolve()
    except (OSError, ValueError):
        return ""
    # Check containment: reject via ".." traversal
    try:
        resolved.relative_to(files_abs)
    except ValueError:
        return ""
    # Symlink escape check
    if resolved.exists() and resolved.is_symlink():
        try:
            resolved.resolve(strict=True).relative_to(files_abs)
        except ValueError:
            return ""
    # Create parent dirs if needed
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


# ── Command-level path safety ─────────────────────────────────────

class PathViolation:
    """Describes a detected path security violation."""
    __slots__ = ("raw_path", "reason", "sanitized")

    def __init__(self, reason: str, raw_path: str, sanitized: str = "") -> None:
        """Init.

        Args:
            reason: Description of the reason parameter.
            raw_path: Description of the raw_path parameter.
            sanitized: Description of the sanitized parameter.
        """
        self.reason = reason
        self.raw_path = raw_path
        self.sanitized = sanitized


def check_path_safety(
    path_str: str,
    sandbox_root: Path,
    workspace_root: str = "",
) -> tuple[PathViolation | None, str]:
    """Check if *path_str* is safe to operate on in the sandbox context.

    Returns ``(None, safe_path)`` when safe, or
    ``(violation, "")`` when unsafe.
    """
    if not path_str or not path_str.strip():
        return PathViolation("empty path", path_str), ""

    # Check for path traversal
    if ".." in PurePath(path_str).parts:
        return PathViolation("path traversal detected (..)", path_str), ""

    # Check for symlink-based escapes
    if path_str.startswith("/proc/") or path_str.startswith("/sys/") or path_str.startswith("/dev/"):
        return PathViolation("procedural filesystem access", path_str), ""

    # Resolve and check containment
    try:
        p = Path(path_str)
        resolved = p.resolve(strict=False)
    except (OSError, ValueError):
        return PathViolation("invalid path", path_str), ""

    # Workspace mode takes priority
    if workspace_root and os.path.isdir(workspace_root):
        try:
            resolved.relative_to(Path(workspace_root).resolve())
            return None, str(resolved)
        except ValueError:
            return PathViolation("path outside workspace", path_str), ""

    # Sandbox mode
    try:
        resolved.relative_to(sandbox_root.resolve())
        return None, str(resolved)
    except ValueError:
        return PathViolation("path outside sandbox", path_str), ""


def filter_allowed_env(
    env_vars: dict[str, str],
    allow_patterns: list[str],
    deny_patterns: list[str],
) -> dict[str, str]:
    """Filter environment variables based on allow/deny patterns.

    Deny patterns take priority over allow patterns.
    Empty allow_patterns means no filtering (all pass through).
    """
    if not allow_patterns and not deny_patterns:
        return env_vars

    result: dict[str, str] = {}
    for name, value in env_vars.items():
        # Deny takes priority
        if deny_patterns and any(fnmatch.fnmatch(name, pat) for pat in deny_patterns):
            continue
        if allow_patterns:
            if any(fnmatch.fnmatch(name, pat) for pat in allow_patterns):
                result[name] = value
        else:
            result[name] = value
    return result
