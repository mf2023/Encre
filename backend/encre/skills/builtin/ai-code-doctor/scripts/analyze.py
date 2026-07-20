#!/usr/bin/env python3
"""
analyze.py — Static analyzer for the ai-code-doctor skill.

Input:  a Python file or directory (passed as argv[1]).
Output: JSON on stdout with, per file:
  - per-function cyclomatic complexity (McCabe)
  - duplicate code blocks (normalized structural hash)
  - hub functions (called from 2+ distinct callers)
  - I/O and DB call points
  - file-level summary
Plus an aggregate summary across all files.

Robustness contract: never crashes on syntax errors, empty files, binary
files, missing paths, or non-Python input. Always emits valid JSON.
"""

import ast
import json
import os
import sys
from collections import defaultdict


DECISION_TYPES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.Assert,
)

COMP_TYPES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

IO_CALL_NAMES = {
    "open",
    "print",
    "urlopen",
}

IO_MODULES = {
    "requests",
    "urllib",
    "socket",
    "http",
    "aiohttp",
}

IO_CALL_ATTRS = {
    "read",
    "readline",
    "readlines",
    "write",
    "writelines",
    "send",
    "recv",
}

DB_DIRECT_ATTRS = {
    "execute",
    "executemany",
    "executescript",
    "fetchone",
    "fetchall",
    "fetchmany",
    "commit",
    "rollback",
    "bulk_create",
    "aggregate",
    "annotate",
}

ORM_CALL_ATTRS = {
    "filter",
    "all",
    "exclude",
    "get",
    "select_related",
    "prefetch_related",
    "update",
    "delete",
}

DB_ATTR_ACCESS = {
    "objects",
    "query",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "site-packages",
}


def _decision_contribution(node):
    if isinstance(node, ast.BoolOp):
        return max(0, len(node.values) - 1)
    if isinstance(node, COMP_TYPES):
        total = 0
        for gen in node.generators:
            total += 1
            total += len(gen.ifs)
        return total
    if isinstance(node, DECISION_TYPES):
        return 1
    return 0


def _count_complexity(node):
    total = _decision_contribution(node)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        total += _count_complexity(child)
    return total


def function_complexity(func_node):
    """McCabe complexity of a function: 1 + sum of body decision contributions."""
    complexity = 1
    for stmt in func_node.body:
        complexity += _count_complexity(stmt)
    return complexity


def _func_display_name(node):
    parts = []
    cur = node
    while isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        parts.append(cur.name)
        cur = cur.parent if hasattr(cur, "parent") else None
        if cur is None:
            break
    parts.reverse()
    return ".".join(parts) if parts else node.name


def _annotate_parents(tree):
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent


def _struct_sig(node):
    """Structural signature with names/constants stripped, for dup detection."""
    if node is None:
        return "N"
    if isinstance(node, ast.Name):
        return "Name"
    if isinstance(node, ast.Constant):
        return "Const"
    if isinstance(node, ast.Attribute):
        return "Attr(" + _struct_sig(node.value) + ")"
    cls = type(node).__name__
    children = [_struct_sig(c) for c in ast.iter_child_nodes(node)]
    if children:
        return cls + "(" + ",".join(children) + ")"
    return cls


def _called_name(call_node):
    """Return a readable name for what a Call invokes, or None."""
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _enclosing_node(node, node_types):
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, node_types):
            return parent
        parent = getattr(parent, "parent", None)
    return None


def _resolved_call_target(call_node, defined_top_level, defined_qualified):
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id if func.id in defined_top_level else None
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    if func.value.id in {"self", "cls"}:
        class_node = _enclosing_node(call_node, ast.ClassDef)
        if class_node is None:
            return None
        candidate = "%s.%s" % (_func_display_name(class_node), func.attr)
    else:
        candidate = "%s.%s" % (func.value.id, func.attr)
    return candidate if candidate in defined_qualified else None


def _source_segment(source, node):
    """Best-effort source snippet for a node, using its line range."""
    try:
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        lines = source.splitlines()
        seg = "\n".join(lines[start - 1:end])
        return seg
    except Exception:
        return ""


def analyze_tree(tree, source, path):
    """Analyze a parsed AST. Returns a dict of findings for one file."""
    _annotate_parents(tree)

    functions = []
    dup_groups = defaultdict(list)
    calls_by_target = defaultdict(set)   # called_name -> set of caller func names
    io_db_points = []

    defined_top_level = set()
    defined_qualified = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_qualified.add(_func_display_name(node))
            if isinstance(getattr(node, "parent", None), ast.Module):
                defined_top_level.add(node.name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = _func_display_name(node)
            complexity = function_complexity(node)
            sig = _struct_sig(node)
            functions.append({
                "name": name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "complexity": complexity,
                "arg_count": len(node.args.args),
                "struct_hash": sig,
            })
            dup_groups[sig].append({"name": name, "line": node.lineno})

        if isinstance(node, ast.Call):
            called = _called_name(node)
            caller_node = _enclosing_node(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            caller = _func_display_name(caller_node) if caller_node is not None else None

            if called is not None:
                target = _resolved_call_target(node, defined_top_level, defined_qualified)
                if caller is not None and target is not None and caller != target:
                    calls_by_target[target].add(caller)

                is_io = False
                is_db = False
                func = node.func
                if isinstance(func, ast.Name) and func.id in IO_CALL_NAMES:
                    is_io = True
                if isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name) and func.value.id in IO_MODULES:
                        is_io = True
                    elif func.attr in IO_CALL_ATTRS:
                        is_io = True
                    elif func.attr in DB_DIRECT_ATTRS:
                        is_db = True
                    elif (
                        func.attr in ORM_CALL_ATTRS
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr in DB_ATTR_ACCESS
                    ):
                        is_db = True

                if is_io or is_db:
                    io_db_points.append({
                        "line": node.lineno,
                        "caller": caller or "<module>",
                        "kind": "db" if is_db else "io",
                        "call": called,
                    })

        if isinstance(node, ast.Attribute):
            if node.attr in DB_ATTR_ACCESS:
                parent = getattr(node, "parent", None)
                call_parent = getattr(parent, "parent", None)
                if (
                    isinstance(parent, ast.Attribute)
                    and isinstance(call_parent, ast.Call)
                    and call_parent.func is parent
                ):
                    continue
                caller_node = _enclosing_node(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                caller = _func_display_name(caller_node) if caller_node is not None else None
                io_db_points.append({
                    "line": node.lineno,
                    "caller": caller or "<module>",
                    "kind": "db",
                    "call": "." + node.attr,
                })

    duplicates = []
    for sig, group in dup_groups.items():
        if len(group) >= 2:
            duplicates.append({
                "count": len(group),
                "members": group,
            })
    duplicates.sort(key=lambda g: g["count"], reverse=True)

    hubs = []
    for called, callers in calls_by_target.items():
        if len(callers) >= 2:
            hubs.append({
                "name": called,
                "caller_count": len(callers),
                "callers": sorted(callers),
            })
    hubs.sort(key=lambda h: h["caller_count"], reverse=True)

    max_complexity = max((f["complexity"] for f in functions), default=0)

    return {
        "functions": functions,
        "max_complexity": max_complexity,
        "duplicates": duplicates,
        "hubs": hubs,
        "io_db_points": io_db_points,
    }


def analyze_file(path):
    """Analyze a single file. Never raises; returns error info on failure."""
    result = {"file": path}

    if not path.endswith(".py"):
        result["error"] = "not_python"
        result["skipped"] = True
        return result

    try:
        # utf-8-sig accepts ordinary UTF-8 and Python files carrying a BOM.
        with open(path, "r", encoding="utf-8-sig") as f:
            source = f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                source = f.read()
        except Exception as e:
            result["error"] = "read_failed: %s" % str(e)
            result["skipped"] = True
            return result
    except Exception as e:
        result["error"] = "read_failed: %s" % str(e)
        result["skipped"] = True
        return result

    if not source.strip():
        result["error"] = "empty_file"
        result["skipped"] = True
        return result

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        result["error"] = "syntax_error: %s (line %s)" % (e.msg, e.lineno or "?")
        result["syntax_error"] = True
        result["skipped"] = True
        return result
    except Exception as e:
        result["error"] = "parse_failed: %s" % str(e)
        result["skipped"] = True
        return result

    try:
        findings = analyze_tree(tree, source, path)
        result.update(findings)
        result["function_count"] = len(findings["functions"])
        result["skipped"] = False
    except Exception as e:
        result["error"] = "analyze_failed: %s" % str(e)
        result["skipped"] = True

    return result


def collect_files(path):
    if os.path.isdir(path):
        files = []
        for root, dirs, names in os.walk(path):
            dirs[:] = sorted(name for name in dirs if name.lower() not in EXCLUDED_DIR_NAMES)
            for n in sorted(names):
                if n.endswith(".py"):
                    files.append(os.path.join(root, n))
        return sorted(files)
    if os.path.isfile(path):
        return [path]
    return []


def analyze(path):
    files = collect_files(path)
    if not files:
        return {
            "input": path,
            "error": "no_python_files_found" if os.path.isdir(path) else "path_not_found",
            "file_count": 0,
            "files": [],
            "summary": {
                "total_functions": 0,
                "max_complexity": 0,
                "duplicate_groups": 0,
                "hub_functions": 0,
                "io_db_points": 0,
            },
        }

    per_file = [analyze_file(f) for f in files]

    total_functions = sum(
        f.get("function_count", 0) for f in per_file if not f.get("skipped")
    )
    max_complexity = max(
        (f.get("max_complexity", 0) for f in per_file if not f.get("skipped")),
        default=0,
    )
    duplicate_groups = sum(len(f.get("duplicates", [])) for f in per_file)
    hub_functions = sum(len(f.get("hubs", [])) for f in per_file)
    io_db_points = sum(len(f.get("io_db_points", [])) for f in per_file)
    skipped = sum(1 for f in per_file if f.get("skipped"))

    return {
        "input": path,
        "file_count": len(files),
        "files": per_file,
        "summary": {
            "total_functions": total_functions,
            "max_complexity": max_complexity,
            "duplicate_groups": duplicate_groups,
            "hub_functions": hub_functions,
            "io_db_points": io_db_points,
            "skipped_files": skipped,
        },
    }


def main(argv):
    if len(argv) < 2:
        print(json.dumps({
            "error": "usage: analyze.py <file_or_dir>",
            "files": [],
        }))
        return 1

    path = argv[1]
    try:
        result = analyze(path)
    except Exception as e:
        result = {
            "input": path,
            "error": "fatal: %s" % str(e),
            "file_count": 0,
            "files": [],
            "summary": {},
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
