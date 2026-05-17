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

"""Native acceleration bridge.

This module wraps the optional ``yim._native`` Rust extension with
graceful fallback to pure Python implementations for every function.
Tools should import from here instead of _native directly.
"""

from __future__ import annotations

import os
import re
from typing import Any

# ── Try loading the Rust extension ───────────────────────────────────────

try:
    from yim._native import (  # type: ignore[import-untyped]
        apply_diff as _native_apply_diff,
        build_content_length_header as _native_build_content_length_header,
        build_lsp_request as _native_build_lsp_request,
        compute_diff as _native_compute_diff,
        cosine_similarity as _native_cosine_similarity,
        count_tokens as _native_count_tokens,
        glob as _native_glob,
        grep as _native_grep,
        landlock_abi_version as _native_landlock_abi_version,
        landlock_available as _native_landlock_available,
        landlock_full_sandbox as _native_landlock_full_sandbox,
        landlock_restrict_network as _native_landlock_restrict_network,
        landlock_restrict_read_only as _native_landlock_restrict_read_only,
        parse_diagnostics as _native_parse_diagnostics,
        parse_lsp_message as _native_parse_lsp_message,
        read_file as _native_read_file,
        sandbox_execute as _native_sandbox_execute,
        sandbox_read_file as _native_sandbox_read_file,
        sandbox_write_file as _native_sandbox_write_file,
        search_codebase as _native_search_codebase,
        simd_contains as _native_simd_contains,
        simd_find_all as _native_simd_find_all,
        simd_memmem as _native_simd_memmem,
        text_similarity as _native_text_similarity,
        write_file as _native_write_file,
    )
    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False


# ── Public API ────────────────────────────────────────────────────────────

def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Read file content, optionally with line offset/limit."""
    if _HAS_NATIVE:
        try:
            return _native_read_file(path, offset, limit)
        except Exception:
            pass
    return _py_read_file(path, offset, limit)


def write_file(path: str, content: str) -> bool:
    """Write content to file, creating parent directories as needed."""
    if _HAS_NATIVE:
        try:
            return _native_write_file(path, content)
        except Exception:
            pass
    return _py_write_file(path, content)


def grep(
    pattern: str,
    path: str,
    case_insensitive: bool = False,
    glob_filter: str = "",
    output_mode: str = "content",
) -> str:
    """Search files with regex, returning formatted results."""
    # Validate regex before attempting native (Rust silently returns empty)
    try:
        re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    if _HAS_NATIVE:
        try:
            results = _native_grep(
                pattern, path, case_insensitive, glob_filter or None
            )
            return _format_grep_results(list(results), output_mode)
        except Exception:
            pass
    return _py_grep(pattern, path, case_insensitive, glob_filter, output_mode)


def glob_pattern(pattern: str, path: str = ".") -> list[str]:
    """Glob for files matching a pattern."""
    if _HAS_NATIVE:
        try:
            return list(_native_glob(pattern, path))
        except Exception:
            pass
    return _py_glob(pattern, path)


def count_tokens(text: str) -> int:
    """Count approximate tokens in text."""
    if _HAS_NATIVE:
        try:
            return _native_count_tokens(text)
        except Exception:
            pass
    return _py_count_tokens(text)


def compute_diff(old: str, new: str) -> str:
    """Compute unified diff between two strings."""
    if _HAS_NATIVE:
        try:
            return _native_compute_diff(old, new)
        except Exception:
            pass
    return _py_compute_diff(old, new)


def apply_diff(content: str, diff: str) -> str:
    """Apply a unified diff to content."""
    if _HAS_NATIVE:
        try:
            return _native_apply_diff(content, diff)
        except Exception:
            pass
    return _py_apply_diff(content, diff)


def sandbox_execute(command: str, timeout: int = 30) -> dict[str, Any]:
    """Execute command in sandbox, returning {stdout, stderr, exit_code}."""
    if _HAS_NATIVE:
        try:
            return dict(_native_sandbox_execute(command, timeout))
        except Exception:
            pass
    return _py_sandbox_execute(command, timeout)


def sandbox_read_file(path: str) -> str:
    """Read file from sandbox."""
    if _HAS_NATIVE:
        try:
            return _native_sandbox_read_file(path)
        except Exception:
            pass
    return _py_read_file(path, 0, 0)


def sandbox_write_file(path: str, content: str) -> bool:
    """Write file to sandbox."""
    if _HAS_NATIVE:
        try:
            return _native_sandbox_write_file(path, content)
        except Exception:
            pass
    return _py_write_file(path, content)


def search_codebase(query: str, path: str | None = None) -> list[dict[str, Any]]:
    """Full-text search across a codebase directory."""
    if _HAS_NATIVE:
        try:
            return [dict(r) for r in _native_search_codebase(query, path or ".")]
        except Exception:
            pass
    return _py_search_codebase(query, path or ".")


# ── New: embedding ────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two f32 slices."""
    if _HAS_NATIVE:
        try:
            return _native_cosine_similarity(a, b)
        except Exception:
            pass
    return _py_cosine_similarity(a, b)


def text_similarity(a: str, b: str) -> float:
    """Compute Jaccard text similarity on whitespace-delimited tokens."""
    if _HAS_NATIVE:
        try:
            return _native_text_similarity(a, b)
        except Exception:
            pass
    return _py_text_similarity(a, b)


# ── New: simd_search ──────────────────────────────────────────────────────

def simd_contains(haystack: str, needle: str) -> bool:
    """SIMD-accelerated substring check."""
    if _HAS_NATIVE:
        try:
            return _native_simd_contains(haystack, needle)
        except Exception:
            pass
    return _py_simd_contains(haystack, needle)


def simd_find_all(haystack: str, needle: str) -> list[int]:
    """SIMD-accelerated find-all match byte positions."""
    if _HAS_NATIVE:
        try:
            return list(_native_simd_find_all(haystack, needle))
        except Exception:
            pass
    return _py_simd_find_all(haystack, needle)


def simd_memmem(haystack: bytes, needle: bytes) -> int | None:
    """SIMD-accelerated byte-level memmem."""
    if _HAS_NATIVE:
        try:
            return _native_simd_memmem(haystack, needle)
        except Exception:
            pass
    return _py_simd_memmem(haystack, needle)


# ── New: landlock ─────────────────────────────────────────────────────────

def landlock_restrict_read_only(paths: list[str]) -> None:
    """Restrict the current thread to read-only filesystem access."""
    if _HAS_NATIVE:
        try:
            _native_landlock_restrict_read_only(paths)
            return
        except Exception:
            pass
    raise OSError("Landlock is only available on Linux via the Rust native layer")


def landlock_restrict_network() -> None:
    """Restrict the current thread from making network connections."""
    if _HAS_NATIVE:
        try:
            _native_landlock_restrict_network()
            return
        except Exception:
            pass
    raise OSError("Landlock is only available on Linux via the Rust native layer")


def landlock_full_sandbox(workspace: str) -> None:
    """Full Landlock sandbox under workspace."""
    if _HAS_NATIVE:
        try:
            _native_landlock_full_sandbox(workspace)
            return
        except Exception:
            pass
    raise OSError("Landlock is only available on Linux via the Rust native layer")


def landlock_available() -> bool:
    """Check whether Landlock is available on the current kernel."""
    if _HAS_NATIVE:
        try:
            return _native_landlock_available()
        except Exception:
            pass
    return False


def landlock_abi_version() -> int:
    """Return the highest Landlock ABI version (0 if not available)."""
    if _HAS_NATIVE:
        try:
            return _native_landlock_abi_version()
        except Exception:
            pass
    return 0


# ── New: lsp_proto ────────────────────────────────────────────────────────

def parse_lsp_message(raw: str) -> dict[str, Any]:
    """Parse a raw JSON-RPC 2.0 message into a dict."""
    if _HAS_NATIVE:
        try:
            import json as _json
            return _json.loads(_native_parse_lsp_message(raw))
        except Exception:
            pass
    return _py_parse_lsp_message(raw)


def parse_diagnostics(raw: str) -> list[dict[str, Any]]:
    """Extract diagnostics from publishDiagnostics params."""
    if _HAS_NATIVE:
        try:
            return [dict(d) for d in _native_parse_diagnostics(raw)]
        except Exception:
            pass
    return _py_parse_diagnostics(raw)


def build_lsp_request(id: int, method: str, params: dict[str, Any] | str) -> str:
    """Build a JSON-RPC 2.0 request string."""
    if _HAS_NATIVE:
        try:
            import json as _json
            params_str = params if isinstance(params, str) else _json.dumps(params)
            return _native_build_lsp_request(id, method, params_str)
        except Exception:
            pass
    return _py_build_lsp_request(id, method, params)


def build_content_length_header(content: str) -> str:
    """Build an LSP Content-Length header."""
    if _HAS_NATIVE:
        try:
            return _native_build_content_length_header(content)
        except Exception:
            pass
    return _py_build_content_length_header(content)


# ── Pure-Python fallback implementations ──────────────────────────────────

def _py_read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise
    start = max(0, offset - 1) if offset > 0 else 0
    end = start + limit if limit > 0 else len(lines)
    return "".join(lines[start:end])


def _py_write_file(path: str, content: str) -> bool:
    p = os.path.dirname(os.path.abspath(path))
    if p:
        os.makedirs(p, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def _format_grep_results(
    results: list[dict[str, Any]], output_mode: str
) -> str:
    if not results:
        return "No matches found."
    lines: list[str] = []
    if output_mode == "files_with_matches":
        seen = set()
        for r in results:
            fp = r.get("file_path", "")
            if fp not in seen:
                seen.add(fp)
                lines.append(fp)
    elif output_mode == "count":
        counts: dict[str, int] = {}
        for r in results:
            fp = r.get("file_path", "")
            counts[fp] = counts.get(fp, 0) + 1
        total = 0
        for fp, c in sorted(counts.items()):
            lines.append(f"{fp}: {c} match(es)")
            total += c
        lines.append(f"\nTotal: {total} matches in {len(counts)} files")
    else:
        for r in results:
            lines.append(
                f"{r['file_path']}:{r['line_number']}:{r['line_content']}"
            )
    return "\n".join(lines)


def _py_grep(
    pattern: str,
    path: str,
    case_insensitive: bool = False,
    glob_filter: str = "",
    output_mode: str = "content",
) -> str:
    import fnmatch
    import os as _os

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    target = _os.path.abspath(path)
    if _os.path.isfile(target):
        files = [target]
    elif _os.path.isdir(target):
        files = []
        for root, _dirs, fnames in _os.walk(target):
            for fname in fnames:
                if glob_filter and not fnmatch.fnmatch(fname, glob_filter):
                    continue
                files.append(_os.path.join(root, fname))
    else:
        return f"Error: Path not found: {path}"

    results: list[str] = []
    file_count = 0
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue
        flines = content.splitlines()
        file_matches = 0
        for i, line in enumerate(flines, 1):
            if regex.search(line):
                if output_mode == "content":
                    results.append(f"{fpath}:{i}:{line}")
                file_matches += 1
        if output_mode == "files_with_matches" and file_matches > 0:
            results.append(fpath)
        if output_mode == "count" and file_matches > 0:
            results.append(f"{fpath}: {file_matches} match(es)")
            file_count += file_matches

    if not results:
        return "No matches found."
    if output_mode == "count":
        results.append(f"\nTotal: {file_count} matches in {len(results)} files")
    return "\n".join(results)


def _py_glob(pattern: str, path: str = ".") -> list[str]:
    import fnmatch
    import os as _os

    root = _os.path.abspath(path)
    results: list[str] = []
    for dirpath, _dirnames, filenames in _os.walk(root):
        rel_dir = _os.path.relpath(dirpath, root)
        for fname in filenames:
            rel_path = _os.path.join(rel_dir, fname) if rel_dir != "." else fname
            if fnmatch.fnmatch(rel_path, pattern):
                results.append(_os.path.join(dirpath, fname))
    results.sort()
    return results


def _py_count_tokens(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    return max(1, len(text) // 4)


def _py_compute_diff(old: str, new: str) -> str:
    import difflib
    diff_lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a",
            tofile="b",
        )
    )
    return "".join(diff_lines)


def _py_apply_diff(content: str, diff: str) -> str:
    content_lines = content.splitlines(keepends=True)
    diff_lines = diff.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    in_header = True
    for line in diff_lines:
        if not line or line == "\n":
            continue
        # Skip unified diff header lines
        if in_header:
            stripped = line.strip()
            if stripped.startswith("---") or stripped.startswith("+++") or stripped.startswith("@@"):
                continue
            in_header = False
        tag = line[0]
        rest = line[1:]
        if tag == " ":
            if i < len(content_lines):
                result.append(content_lines[i])
                i += 1
            else:
                result.append(rest)
        elif tag == "+":
            result.append(rest)
        elif tag == "-":
            if i < len(content_lines):
                i += 1
        elif tag in ("@", "\\"):
            # Hunk header or "No newline" marker; skip
            pass
        else:
            if i < len(content_lines):
                result.append(content_lines[i])
                i += 1
    while i < len(content_lines):
        result.append(content_lines[i])
        i += 1
    return "".join(result)


def _py_sandbox_execute(command: str, timeout: int = 30) -> dict[str, Any]:
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            proc = subprocess.run(
                ["cmd", "/C", command],
                capture_output=True,
                timeout=timeout,
                text=True,
            )
        else:
            proc = subprocess.run(
                ["sh", "-c", command],
                capture_output=True,
                timeout=timeout,
                text=True,
            )
        return {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}


def _py_search_codebase(query: str, path: str) -> list[dict[str, Any]]:
    import os as _os

    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    terms = query_lower.split()

    for dirpath, _dirs, filenames in _os.walk(path):
        rel = _os.path.relpath(dirpath, path)
        if rel != "." and (rel.startswith(".") or "node_modules" in rel or "target" in rel):
            continue
        for fname in filenames:
            fpath = _os.path.join(dirpath, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for li, line in enumerate(f, 1):
                        line_lower = line.lower()
                        score = sum(
                            1.0 for t in terms if t in line_lower
                        )
                        if score > 0:
                            results.append({
                                "file_path": fpath,
                                "line_number": li,
                                "line_content": line.rstrip("\n"),
                                "score": score,
                            })
            except Exception:
                continue

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:50]


# ── New fallback: embedding ────────────────────────────────────────────────

def _py_cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    denom = norm_a * norm_b
    if denom == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / denom))


def _py_text_similarity(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


# ── New fallback: simd_search ─────────────────────────────────────────────

def _py_simd_contains(haystack: str, needle: str) -> bool:
    return needle in haystack


def _py_simd_find_all(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _py_simd_memmem(haystack: bytes, needle: bytes) -> int | None:
    idx = haystack.find(needle)
    return idx if idx != -1 else None


# ── New fallback: lsp_proto ───────────────────────────────────────────────

def _py_parse_lsp_message(raw: str) -> dict[str, Any]:
    import json as _json
    return _json.loads(raw)


def _py_parse_diagnostics(raw: str) -> list[dict[str, Any]]:
    import json as _json
    try:
        data = _json.loads(raw)
        return data.get("diagnostics", [])
    except Exception:
        return []


def _py_build_lsp_request(id: int, method: str, params: dict[str, Any] | str) -> str:
    import json as _json
    if isinstance(params, str):
        params = _json.loads(params)
    msg = {"jsonrpc": "2.0", "id": id, "method": method, "params": params}
    return _json.dumps(msg)


def _py_build_content_length_header(content: str) -> str:
    return f"Content-Length: {len(content)}\r\n\r\n"
