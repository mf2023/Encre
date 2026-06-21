#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Any

from encre.native import search_codebase as native_search_codebase
from encre.tools.base import build_tool

_parent_loop: Any = None


def set_parent_loop(loop: Any) -> None:
    global _parent_loop
    _parent_loop = loop


def _resolve_loop() -> Any:
    return _parent_loop


def _workspace_and_index() -> tuple[str, Any | None]:
    loop = _resolve_loop()
    if loop is None:
        return "", None
    ws_path = getattr(getattr(loop, "config", None), "workspace", "") or ""
    idx = getattr(loop, "_code_index", None)
    return ws_path, idx


def _resolve_rel_path(ws_path: str, file_path: str) -> str:
    if not file_path:
        return ""
    if os.path.isabs(file_path):
        try:
            return os.path.relpath(file_path, ws_path).replace("\\", "/")
        except ValueError:
            return file_path.replace("\\", "/")
    return file_path.replace("\\", "/")


async def _codebase_search_execute(**kwargs: Any) -> str:
    query = str(kwargs.get("query") or "").strip()
    limit = int(kwargs.get("limit") or 10)
    ws_path, idx = _workspace_and_index()
    if not query:
        return "Error: query is required"
    if not ws_path:
        return "Error: no active workspace"

    if idx is not None and getattr(idx, "_indexed", False):
        try:
            results = idx.find_relevant(query, limit=max(1, min(limit, 50)))
            if results:
                lines = []
                for path, score in results[:limit]:
                    mod = idx.get_module_info(path)
                    lang = getattr(mod, "language", "") if mod is not None else ""
                    suffix = f" [{lang}]" if lang else ""
                    lines.append(f"{path}{suffix} score={score:.3f}")
                return "\n".join(lines)
        except Exception:
            pass

    try:
        raw = native_search_codebase(query, ws_path)
    except Exception as exc:
        return f"Error: codebase search failed: {exc}"

    if not raw:
        return "(no matches)"

    lines = []
    for item in raw[: max(1, min(limit, 50))]:
        file_path = str(item.get("file_path", ""))
        try:
            rel = os.path.relpath(file_path, ws_path).replace("\\", "/")
        except ValueError:
            rel = file_path.replace("\\", "/")
        line_no = int(item.get("line_number", 0) or 0)
        score = float(item.get("score", 0.0) or 0.0)
        snippet = str(item.get("line_content", "")).strip()
        lines.append(f"{rel}:{line_no} score={score:.3f} | {snippet}")
    return "\n".join(lines)


async def _codebase_context_execute(**kwargs: Any) -> str:
    file_path = str(kwargs.get("file_path") or "").strip()
    ws_path, idx = _workspace_and_index()
    if not file_path:
        return "Error: file_path is required"
    if not ws_path:
        return "Error: no active workspace"
    if idx is None or not getattr(idx, "_indexed", False):
        return "Error: code index is not ready yet"

    rel_path = _resolve_rel_path(ws_path, file_path)
    try:
        result = idx.build_context(rel_path)
    except Exception as exc:
        return f"Error: codebase context failed: {exc}"
    return result or "(file not found in code index)"


EncreCodebaseSearchTool = build_tool(
    name="codebase_search",
    description=(
        "Search the active workspace codebase. Uses the prepared workspace "
        "index when available and falls back to the Rust native code search "
        "engine. Prefer this over grep when the goal is relevant-code lookup."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language or keyword query to search for",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["query"],
    },
    execute=_codebase_search_execute,
    intents=["coding"],
    category="search",
    triggers=["codebase search", "find relevant code", "search workspace code", "search project"],
    is_concurrency_safe=lambda _: True,
)


EncreCodebaseContextTool = build_tool(
    name="codebase_context",
    description=(
        "Return indexed context for a workspace file, including full source, "
        "imports, dependents, and exports."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Workspace-relative or absolute file path",
            },
        },
        "required": ["file_path"],
    },
    execute=_codebase_context_execute,
    intents=["coding"],
    category="search",
    triggers=["codebase context", "file context", "show indexed file details"],
    is_concurrency_safe=lambda _: True,
)
