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

"""Pure helper functions extracted from encre.loop.

All functions here are stateless (no reference to EncreLoop or any class).
They operate solely on their parameters.  Extracted to reduce the ~5600-line
loop.py and enable independent testing.
"""

import hashlib
import json
import os
import pathlib
import re
from typing import Any

# ── Constants ───────────────────────────────────────────────────────

_WRITE_TOOL_NAMES = {"file_write", "file_edit", "write_file", "writeFile", "apply_patch"}
_PROMPT_CACHE_TTL_SECONDS = 30.0
_TASK_STAGES = ("discover", "plan", "execute", "verify", "report")
_STUCK_LOOP_THRESHOLD = 6
_SUMMARY_INTERVAL_TURNS = 3

_MAX_TOOL_CONCURRENCY = max(
    1, int(os.environ.get("ENCRE_MAX_TOOL_USE_CONCURRENCY", "10") or "10")
)

_EVOLUTION_ENABLED = os.environ.get("ENCRE_EVOLUTION", "0") == "1"
_WORKING_SET_ARTIFACT_LIMIT = 8
_WORKING_SET_REFERENCE_LIMIT = 8
_WORKING_SET_TOOL_LIMIT = 12

_PLAN_STATUS_MAP = {
    "pending": "pending",
    "in_progress": "active",
    "completed": "done",
}

# ── Helper functions ────────────────────────────────────────────────


def _spillover_dir(session_id: str) -> str | None:
    try:
        from encre.config import get_data_dir

        import pathlib

        d = get_data_dir() / "spillover" / (session_id or "default")
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    except Exception:
        return None


def _apply_result_budget(
    result: str,
    tool: Any,
    max_chars: int = 100_000,
    context_ratio: float = 1.0,
    session_id: str = "",
    tool_name: str = "",
) -> str:
    budget = getattr(tool, "max_result_size_chars", max_chars) or max_chars
    if context_ratio < 0.5:
        scaled = int(budget * context_ratio)
        budget = max(500, min(budget, scaled))
    if len(result) <= budget:
        return result
    excess = len(result) - budget
    spillover_path = None
    if session_id:
        import hashlib

        spillover_dir = _spillover_dir(session_id)
        if spillover_dir:
            digest = hashlib.sha1(result.encode("utf-8", errors="replace")).hexdigest()[:16]
            label = (tool_name or "tool").replace("/", "_")[:32]
            fname = f"spillover_{label}_{digest}.txt"
            import os as _os

            fpath = _os.path.join(spillover_dir, fname)
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(result)
                spillover_path = fpath
            except Exception:
                spillover_path = None
    preview = result[:1000]
    if spillover_path:
        return (
            preview
            + f"\n... (truncated {excess} characters; full output saved to {spillover_path})"
        )
    return result[:budget] + f"\n... (truncated {excess} characters)"


def _extract_file_path(tool_name: str, result: str) -> str | None:
    if tool_name not in _WRITE_TOOL_NAMES:
        return None

    if tool_name == "apply_patch":
        import json as _json

        try:
            json_part = result.split("\n", 1)[1] if "\n" in result else result
            data = _json.loads(json_part)
            files = data.get("files", []) if isinstance(data, dict) else []
            if files:
                fp = files[0].get("new_path") or files[0].get("old_path", "")
                if fp and os.path.isabs(fp) and os.path.exists(fp):
                    return fp
        except (_json.JSONDecodeError, IndexError, KeyError):
            pass
        return None

    for pattern in [
        r"Successfully wrote \d+ characters to (.+)",
        r"Applied \d+ edit\(s\) to (.+?)\.\s*\n",
        r"Wrote .+ to (.+)",
    ]:
        m = re.search(pattern, result, re.IGNORECASE)
        if m:
            path = m.group(1).strip()
            if os.path.isabs(path) and os.path.exists(path):
                return path
    return None


def _extract_diff_text(_tool_name: str, result: str) -> str:
    m = re.search(r"```diff\n(.+?)\n```", result, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def _args_summary(args: dict[str, Any]) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:600]
    except Exception:
        return str(args)[:600]


def _turn_to_message_index(
    messages: list[dict[str, Any]], target_turn: int,
) -> int | None:
    if target_turn <= 0:
        return 0
    seen = 0
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            seen += 1
            if seen == target_turn:
                return i
    return None


def _permission_reason(tool_name: str) -> str:
    return f"Tool {tool_name} requires permission"


def _extract_apply_patch_paths(result: str) -> list[str]:
    import json as _json

    try:
        json_part = result.split("\n", 1)[1] if "\n" in result else result
        data = _json.loads(json_part)
        files = data.get("files", []) if isinstance(data, dict) else []
        paths = []
        for f in files:
            if f.get("status") != "ok":
                continue
            fp = f.get("new_path") or f.get("old_path", "")
            if fp and os.path.isabs(fp) and os.path.exists(fp):
                paths.append(fp)
        return paths
    except (_json.JSONDecodeError, IndexError, KeyError):
        return []


def _extract_write_target_paths(tool_name: str, args: dict[str, Any]) -> set[str]:
    if tool_name not in _WRITE_TOOL_NAMES:
        return set()
    if tool_name == "apply_patch":
        paths: set[str] = set()
        for fd in (args.get("files") or []):
            if isinstance(fd, dict):
                for key in ("old_path", "new_path"):
                    p = fd.get(key) or ""
                    if p:
                        try:
                            paths.add(os.path.abspath(p))
                        except Exception:
                            paths.add(p)
        return paths
    fp = args.get("file_path") or args.get("path") or ""
    if not fp:
        return set()
    try:
        return {os.path.abspath(fp)}
    except Exception:
        return {fp}


def _split_writes_by_path_conflict(
    write_tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path_map: dict[int, set[str]] = {
        i: _extract_write_target_paths(p["name"], p.get("args", {}))
        for i, p in enumerate(write_tools)
    }
    parallel: list[dict[str, Any]] = []
    sequential: list[dict[str, Any]] = []
    for i, p in enumerate(write_tools):
        my_paths = path_map[i]
        if not my_paths:
            sequential.append(p)
            continue
        conflict = any(
            bool(my_paths & path_map[j])
            for j in range(len(write_tools))
            if j != i
        )
        (sequential if conflict else parallel).append(p)
    return parallel, sequential


async def _try_lsp_diagnostics(file_path: str) -> str:
    try:
        from encre.tools.builtin.lsp import _get_manager

        mgr = _get_manager()
        if not getattr(mgr, "_workspace", ""):
            return ""
        diags = await mgr.get_diagnostics(file_path)
        if not diags:
            return ""
        sev_name = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
        lines = [f"\n\n[LSP Diagnostics for {file_path}] ({len(diags)})"]
        for d in diags[:20]:
            sev = sev_name.get(d.severity, "Issue")
            raw_msg = (d.message or "").strip()
            msg = (raw_msg.splitlines()[0][:200] if raw_msg else "")
            loc = ""
            try:
                if d.range and d.range.start is not None:
                    loc = f" line {d.range.start.line}:{d.range.start.character}"
            except Exception:
                pass
            src = f" ({d.source})" if d.source else ""
            lines.append(f"  [{sev}]{loc}{src} {msg}")
        return "\n".join(lines)
    except Exception:
        return ""


def _is_reference_tool(tool_name: str) -> bool:
    name = tool_name.lower()
    if tool_name.startswith("mcp__") or name.startswith("memory_") or name.startswith("web_"):
        return True
    return False


def _extract_ref_summary(tool_name: str, args: dict[str, Any], result: str) -> str:
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) >= 3:
            server = parts[1]
            inner = parts[2]
            sub = args.get("tool_name") or args.get("name") or inner
            return f"MCP {server}: {sub}"
        return f"MCP: {tool_name}"

    name = tool_name.lower()

    if name in ("memory_create", "memory_update"):
        fn = args.get("filename", "") or args.get("name", "")
        return f"Memory: {fn}" if fn else f"Memory: {tool_name}"

    if name == "memory_read":
        fn = args.get("filename", "") or args.get("name", "")
        return f"Read memory: {fn}" if fn else "Read memory"

    if name == "memory_delete":
        fn = args.get("filename", "") or args.get("name", "")
        return f"Deleted memory: {fn}" if fn else "Deleted memory"

    if name == "memory_search":
        q = args.get("query", "")
        return f"Searched memory: {q[:60]}" if q else "Searched memory"

    if name == "memory_profile":
        field = args.get("field", "")
        val = args.get("value", "")
        return f"Profile: {field} = {val[:40]}" if field else "Profile updated"

    if name == "web_search":
        q = args.get("query", "")
        return f"Web search: {q[:80]}" if q else "Web search"

    if name == "web_fetch":
        url = args.get("url", "")
        return f"Fetched: {url[:80]}" if url else "Web fetch"

    return tool_name


def _ensure_plan_items(tool_name: str, args: dict[str, Any]) -> list[dict[str, Any]] | None:
    if tool_name != "todo":
        return None
    todos = args.get("todos")
    if not todos or not isinstance(todos, list):
        return None
    items: list[dict[str, Any]] = []
    for i, todo in enumerate(todos):
        content = todo.get("content", "")
        if not content:
            continue
        status = _PLAN_STATUS_MAP.get(todo.get("status", "pending"), "pending")
        items.append({
            "id": f"plan-{i}",
            "text": content,
            "status": status,
        })
    return items if items else None


def _infer_tool_semantics(tool_name: str, tool: Any) -> dict[str, str]:
    semantic_type = str(getattr(tool, "semantic_type", "") or "").strip().lower()
    cost_level = str(getattr(tool, "cost_level", "") or "").strip().lower()
    retryability = str(getattr(tool, "retryability", "") or "").strip().lower()
    safe_fallback = str(getattr(tool, "safe_fallback", "") or "").strip()
    lowered = tool_name.lower()

    if not semantic_type or semantic_type == "general":
        if lowered in _WRITE_TOOL_NAMES or "write" in lowered or "edit" in lowered or "patch" in lowered or "delete" in lowered:
            semantic_type = "write"
        elif "read" in lowered or "cat" in lowered or "view" in lowered:
            semantic_type = "read"
        elif "search" in lowered or "grep" in lowered or "glob" in lowered or "find" in lowered:
            semantic_type = "search"
        elif lowered in {"bash", "shell", "execute", "run"}:
            semantic_type = "exec"
        elif lowered.startswith("web_") or lowered in {"browser", "rest_client"}:
            semantic_type = "network"
        elif lowered in {"agent", "workflow"}:
            semantic_type = "orchestrate"
        else:
            semantic_type = "general"

    if not cost_level:
        if semantic_type in {"search", "read"}:
            cost_level = "low"
        elif semantic_type in {"write", "exec", "network", "orchestrate"}:
            cost_level = "high"
        else:
            cost_level = "medium"

    if not retryability:
        if semantic_type in {"search", "read", "network"}:
            retryability = "auto"
        elif semantic_type in {"write", "exec", "orchestrate"}:
            retryability = "guarded"
        else:
            retryability = "manual"

    if not safe_fallback:
        fallback_map = {
            "write": "Read the target file again, narrow the scope, and propose a smaller change.",
            "exec": "Inspect the environment and command preconditions before retrying.",
            "search": "Refine the query or switch to a more specific file/path filter.",
            "network": "Use local context first and only retry if an external lookup is necessary.",
            "orchestrate": "Summarize the sub-task and continue in the main thread if delegation is unnecessary.",
        }
        safe_fallback = fallback_map.get(semantic_type, "Gather more context before retrying.")

    return {
        "semantic_type": semantic_type,
        "cost_level": cost_level,
        "retryability": retryability,
        "safe_fallback": safe_fallback,
    }


def _tool_retry_allowed(p: dict[str, Any], repeated_signatures: list[tuple[str, ...]]) -> bool:
    semantics = p.get("semantics", {}) or {}
    retryability = str(semantics.get("retryability", "auto"))
    if retryability == "auto":
        return True
    if not repeated_signatures:
        return True
    sig = f"{p.get('name', '')}:{p.get('args_summary', '')[:80]}"
    if retryability == "manual":
        last = repeated_signatures[-1]
        return not any(sig == item for item in last)
    if retryability == "guarded":
        last = repeated_signatures[-1]
        if any(sig == item for item in last):
            return False
    return True


def _turn_to_message_index(
    messages: list[dict[str, Any]], target_turn: int,
) -> int | None:
    if target_turn <= 0:
        return 0
    seen = 0
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            seen += 1
            if seen == target_turn:
                return i
    return None
