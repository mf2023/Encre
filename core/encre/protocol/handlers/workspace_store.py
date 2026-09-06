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

"""Workspace persistence: registry, per-workspace config, icons, indices.

Module-level helpers backing the iwork workspace system.  Extracted
verbatim from ``encre.transport.ws`` (architecture refactor Stage 3 /
Task 5.2); behaviour is unchanged, only the layout moved.
"""

import base64
import contextlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("encre.transport.ws")


# 鈹€鈹€ Workspace persistence 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _workspace_config_path(workspace_path: str) -> str:
    """Path to the per-workspace config file (``<workspace>/.encre/config.json``)."""
    return os.path.join(workspace_path, ".encre", "config.json")


def _workspace_context_files(workspace_path: str) -> dict[str, bool]:
    """Report which workspace context files (AGENTS.md / CLAUDE.md) exist."""
    if not workspace_path or not os.path.isdir(workspace_path):
        return {"AGENTS.md": False, "CLAUDE.md": False}
    return {
        name: os.path.isfile(os.path.join(workspace_path, name))
        for name in ("AGENTS.md", "CLAUDE.md")
    }


def _load_workspace_config(workspace_path: str) -> dict[str, Any]:
    """Read the per-workspace config dict; returns ``{}`` when absent/invalid."""
    ws_config_path = _workspace_config_path(workspace_path)
    if not os.path.isfile(ws_config_path):
        return {}
    try:
        with open(ws_config_path, encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                return {}
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
    except Exception:
        logger.warning("Failed to load workspace config from %s", ws_config_path, exc_info=True)
        return {}


def _save_workspace_config(workspace_path: str, partial: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial per-workspace config into ``.encre/config.json``.

    Only known keys are accepted; a ``None`` value removes the key so the
    global config is used for it. Returns the merged config dict.
    """
    known_keys = {
        "system_prompt", "permission_mode", "specialty", "max_turns",
        "language", "models", "models_enabled", "permissions", "mcp", "context_files",
    }
    os.makedirs(os.path.join(workspace_path, ".encre"), exist_ok=True)
    current = _load_workspace_config(workspace_path)
    for key, value in (partial or {}).items():
        if key not in known_keys:
            continue
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    try:
        with open(_workspace_config_path(workspace_path), "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Failed to save workspace config to %s", _workspace_config_path(workspace_path), exc_info=True)
    return current


def _apply_workspace_config(config: Any, workspace_path: str) -> None:
    """Load .encre/config.json from the workspace and apply overrides to config."""
    ws_config = _load_workspace_config(workspace_path)
    if not ws_config:
        return
    try:
        if "system_prompt" in ws_config:
            config.system_prompt = ws_config["system_prompt"]
        if "permission_mode" in ws_config:
            config.permission_mode = ws_config["permission_mode"]
        if "specialty" in ws_config:
            config.default_specialty = ws_config["specialty"]
        if "max_turns" in ws_config:
            config.max_turns = ws_config["max_turns"]
        if "language" in ws_config:
            config.language = ws_config["language"]
        # Restrict which models may serve this workspace's sessions. An empty
        # list (or a null/absent key) means "reuse the global model set". The
        # models_enabled flag is the master switch: when explicitly false,
        # any stored model ids are ignored (selection is off, though the ids
        # may still be kept in the file so the user can re-enable later).
        if ws_config.get("models_enabled") is False:
            config.target_model_ids = []
        elif "models" in ws_config:
            from encre.model_selection import parse_target_model_ids
            config.target_model_ids = parse_target_model_ids(ws_config["models"]) or []
        # Per-file toggles for workspace context files (AGENTS.md / CLAUDE.md).
        # A file listed here is disabled, so its contents never reach the model.
        if "context_files" in ws_config:
            cf = ws_config["context_files"]
            if isinstance(cf, dict):
                config.disabled_context_files = [
                    str(name) for name, enabled in cf.items() if not enabled
                ]
            else:
                config.disabled_context_files = []

        logger.info("Applied workspace config from %s", _workspace_config_path(workspace_path))
    except Exception:
        logger.warning("Failed to load workspace config", exc_info=True)


def _get_yim_data_dir() -> str:
    return os.environ.get("ENCRE_DATA_DIR", os.path.join(os.path.expanduser("~"), ".dunimd", "encre"))


def _build_workspace_tree(ws_path: str, max_depth: int = 4, max_entries: int = 200) -> str:
    """Quickly walk the workspace directory tree without reading file contents.
    Returns a compact tree representation for immediate injection into the
    session's system prompt, so the model sees the project structure on the
    very first turn (before the full code index is built)."""
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv",
                 "target", "build", "dist", ".tox", ".eggs",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache",
                 ".svn", ".hg", ".idea", ".vscode"}
    skip_ext = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe"}
    lines: list[str] = []
    total_files = 0
    try:
        for root, dirs, files in os.walk(ws_path):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d not in skip_dirs]
            rel = os.path.relpath(root, ws_path)
            if rel == ".":
                rel = ""
            depth = rel.count(os.sep) + 1 if rel else 0
            if depth > max_depth:
                continue
            indent = "  " * depth
            if depth == 0:
                lines.append("馃搧 workspace/")
            else:
                basename = os.path.basename(root)
                lines.append(f"{indent}馃搧 {basename}/")
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_ext:
                    continue
                if len(lines) >= max_entries:
                    break
                lines.append(f"{indent}  馃搫 {fname}")
                total_files += 1
            if len(lines) >= max_entries:
                lines.append(f"  ... (truncated at {max_entries} entries)")
                break
    except (OSError, PermissionError):
        pass
    if not lines:
        return ""
    return (
        f"## Workspace Structure\n"
        f"{total_files} files (tree depth 鈮max_depth}). "
        f"Full code index is building in the background.\n"
        f"```\n" + "\n".join(lines) + "\n```"
    )


def _get_workspaces_path() -> str:
    return os.path.join(_get_yim_data_dir(), "iwork", "index.json")


def _make_workspace_id(folder_path: str) -> str:
    """Generate a stable ID from the workspace path."""
    import hashlib
    return hashlib.sha256(folder_path.encode()).hexdigest()[:12]


def _get_workspace_dir(ws_id: str) -> str:
    return os.path.join(_get_yim_data_dir(), "iwork", ws_id)


def _remove_session_from_workspace_indices(session_id: str) -> None:
    """Remove a session_id from ALL workspace index files.

    Workspace ``index.json`` files are separate from the main session
    manager's index. ``list_sessions`` loads them independently, so a
    deleted session would reappear on page refresh if we don't clean
    them up here.
    """
    for ws in _load_workspaces():
        ws_id = ws.get("id") or _make_workspace_id(ws["path"])
        ws_dir = _get_workspace_dir(ws_id)
        idx_file = os.path.join(ws_dir, "sessions", "index.json")
        if not os.path.isfile(idx_file):
            continue
        try:
            with open(idx_file, encoding="utf-8") as f:
                raw = f.read().strip()
            if raw and not raw.startswith("{"):
                from encre.crypto import decrypt
                with contextlib.suppress(Exception):
                    raw = decrypt(raw)
            idx = json.loads(raw)
            if not isinstance(idx, dict):
                continue
            if session_id in idx:
                del idx[session_id]
                new_raw = json.dumps(idx, ensure_ascii=False, separators=(",", ":"))
                try:
                    from encre.crypto import encrypt
                    new_raw = encrypt(new_raw)
                except Exception:
                    pass
                with open(idx_file, "w", encoding="utf-8") as f:
                    f.write(new_raw)
        except Exception:
            continue


def _index_metadata_path(ws_id: str) -> str:
    """Path to the index metadata marker for a workspace."""
    return os.path.join(_get_workspace_dir(ws_id), "index_metadata.json")


def _load_index_metadata(ws_id: str) -> dict[str, Any] | None:
    """Load index metadata for a workspace. Returns None if never indexed."""
    path = _index_metadata_path(ws_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_index_metadata(ws_id: str, file_count: int) -> None:
    """Write index metadata marker to persist that indexing was done."""
    path = _index_metadata_path(ws_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"files": file_count, "indexed_at": time.time()}, f)
    except Exception:
        logger.warning("[codebase] failed to save index metadata for ws=%s", ws_id)


def _ensure_workspace_dirs(ws_id: str) -> str:
    """Create workspace data directories and return the workspace dir path."""
    ws_dir = _get_workspace_dir(ws_id)
    os.makedirs(os.path.join(ws_dir, "sessions"), exist_ok=True)
    return ws_dir


def _load_workspaces() -> list[dict[str, Any]]:
    path = _get_workspaces_path()
    if not os.path.exists(path):
        return []
    try:
        from encre.crypto import decrypt
        with open(path, encoding="utf-8") as f:
            encrypted = f.read()
        if not encrypted.strip():
            return []
        raw = decrypt(encrypted)
        workspaces: list[dict[str, Any]] = json.loads(raw)
        # Migrate old records that lack an id field or a recorded creation time
        migrated = False
        for w in workspaces:
            if "id" not in w:
                w["id"] = _make_workspace_id(w["path"])
                migrated = True
            if "created_at" not in w:
                # Backfill from the oldest recorded timestamp (opened_at was
                # previously the only timestamp we kept), never recompute it.
                w["created_at"] = float(w.get("opened_at") or 0) or time.time()
                migrated = True
            if "icon_data" in w:
                # Icons used to be embedded in the record itself; the on-disk
                # PNG inside the workspace folder is the source of truth now,
                # so flush any embedded copy out and drop it from the record.
                try:
                    ws_id = w["id"]
                    payload = w["icon_data"]
                    ext = "svg" if payload.startswith("data:image/svg") else "png"
                    icon_path = _get_workspace_icon_file(ws_id, ext)
                    if ";base64," in payload and not os.path.exists(icon_path):
                        os.makedirs(os.path.dirname(icon_path), exist_ok=True)
                        with open(icon_path, "wb") as fh:
                            fh.write(base64.b64decode(payload.split(";base64,", 1)[1]))
                except Exception:
                    logger.warning("legacy workspace icon flush failed", exc_info=True)
                finally:
                    w.pop("icon_data", None)
                migrated = True
        if migrated:
            _save_workspaces(workspaces)
        # Filter out invalid entries (empty path or name)
        workspaces = [w for w in workspaces if w.get("path") and w.get("name")]
        return workspaces
    except Exception:
        logger.warning("Failed to load workspaces", exc_info=True)
        return []


def _save_workspaces(workspaces: list[dict[str, Any]]) -> None:
    path = _get_workspaces_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        from encre.crypto import encrypt
        raw = json.dumps(workspaces, ensure_ascii=False)
        encrypted = encrypt(raw)
        with open(path, "w", encoding="utf-8") as f:
            f.write(encrypted)
    except Exception:
        logger.warning("Failed to save workspaces", exc_info=True)


# 鈹€鈹€ Workspace icons 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Each workspace's icon lives as a real file inside its data folder:
# ``icon.svg`` (generated default) or ``icon.png`` (a custom upload). Outgoing
# workspace payloads get the icon attached as a ``data:`` URL by
# ``_workspaces_with_session_counts`` so the frontend never touches the
# filesystem. The default icon is generated as SVG 鈥?hashed random background
# colour plus capitalised first character of the workspace name.
_ICON_SIZE = 128


def _get_workspace_icon_file(ws_id: str, ext: str) -> str:
    """Path of the workspace's on-disk icon file ("svg" or "png")."""
    return os.path.join(_get_workspace_dir(ws_id), f"icon.{ext}")


def _write_workspace_icon_file(ws_id: str, ext: str, data: bytes) -> None:
    """Persist icon bytes as ``<ws_dir>/icon.<ext>`` (atomic replace)."""
    path = _get_workspace_icon_file(ws_id, ext)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _remove_workspace_icon_file(ws_id: str, ext: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(_get_workspace_icon_file(ws_id, ext))


def _read_workspace_icon_data_url(ws_id: str) -> str | None:
    """Load the workspace icon and return it as a ``data:`` URL.

    Custom uploads (``icon.png``) take precedence over the generated default
    (``icon.svg``).
    """
    for ext, mime in (("png", "image/png"), ("svg", "image/svg+xml")):
        try:
            with open(_get_workspace_icon_file(ws_id, ext), "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")
        except OSError:
            continue
    return None


_ICON_FONT_STACK = "'Microsoft YaHei','PingFang SC','Noto Sans SC',Arial,sans-serif"


def _generate_default_workspace_icon(name: str) -> bytes:
    """Render the fallback icon for ``name`` as SVG bytes."""
    import colorsys
    from xml.sax.saxutils import escape as _escape

    # Hash the name into a hue so the colour is arbitrary-looking but stable
    # across restarts (a re-rolled colour on every launch would read as a bug).
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    r, g, b = (int(c * 255) for c in colorsys.hls_to_rgb((h % 360) / 360.0, 0.46, 0.62))
    ch = _escape(name.strip()[:1] or "?").upper()

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_ICON_SIZE}" height="{_ICON_SIZE}" '
        f'viewBox="0 0 {_ICON_SIZE} {_ICON_SIZE}">'
        f'<rect width="{_ICON_SIZE}" height="{_ICON_SIZE}" rx="20" fill="rgb({r},{g},{b})"/>'
        f'<text x="{_ICON_SIZE // 2}" y="{_ICON_SIZE // 2}" text-anchor="middle" '
        f'dominant-baseline="central" font-family="{_ICON_FONT_STACK}" '
        f'font-size="52" font-weight="700" fill="#ffffff">{ch}</text>'
        "</svg>"
    )
    return svg.encode("utf-8")


def _normalize_workspace_icon(raw: bytes) -> bytes | None:
    """Decode uploaded image bytes into square 128px PNG bytes.

    Centre-crops non-square images, composites alpha over white, and returns
    ``None`` when the bytes cannot be decoded as an image.
    """
    from io import BytesIO

    from PIL import Image

    try:
        img = Image.open(BytesIO(raw)).convert("RGBA")
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side)).resize((_ICON_SIZE, _ICON_SIZE))
        flat = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (255, 255, 255, 255))
        flat.alpha_composite(img)
        buf = BytesIO()
        flat.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _workspaces_with_session_counts(workspaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return workspace records enriched with live ``session_count`` and icon.

    The count is derived from each workspace's own session index file and
    excludes automation / sub-agent entries, mirroring the sidebar's
    workspace session listing. The icon is loaded from the workspace folder
    (``icon.png``) and attached as a ``data:`` URL. Enriched values are only
    used when sending records to the frontend; they are never persisted back.
    """
    result: list[dict[str, Any]] = []
    for ws in workspaces:
        entry = dict(ws)
        ws_id = entry.get("id") or _make_workspace_id(entry["path"])
        # Icons live on disk; ignore any legacy in-record copies here (they
        # are flushed to files by the _load_workspaces migration).
        entry.pop("icon_data", None)
        icon_data_url = _read_workspace_icon_data_url(ws_id)
        if icon_data_url:
            entry["icon_data"] = icon_data_url
        idx_file = os.path.join(_get_workspace_dir(ws_id), "sessions", "index.json")
        count = 0
        if os.path.isfile(idx_file):
            try:
                with open(idx_file, encoding="utf-8") as f:
                    raw = f.read().strip()
                if raw and not raw.startswith("{"):
                    from encre.crypto import decrypt as _decrypt
                    with contextlib.suppress(Exception):
                        raw = _decrypt(raw)
                idx = json.loads(raw)
                if isinstance(idx, dict):
                    count = sum(
                        1
                        for e in idx.values()
                        if isinstance(e, dict) and e.get("channel") not in ("automation", "sub_agent")
                    )
            except Exception:
                count = 0
        entry["session_count"] = count
        result.append(entry)
    return result
