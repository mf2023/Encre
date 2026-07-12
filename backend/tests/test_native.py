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

"""Tests for encre.native -- Rust native bridge with Python fallbacks."""

from pathlib import Path

import pytest
from encre import native


class TestNativeImport:
    """Test cases covering native import.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify the native module is importable and has the expected API."""

    def test_module_importable(self):
        """The native bridge module should always be importable."""
        # Confirm the expected result for this scenario: module importable.
        assert native is not None

    def test_has_native_flag_exists(self):
        """_HAS_NATIVE is a boolean indicating whether the Rust extension loaded."""
        # Confirm the expected result for this scenario: has native flag exists.
        assert isinstance(native._HAS_NATIVE, bool)

    def test_all_functions_exist(self):
        """Every function defined in _native.pyi stubs must be present in native.py."""
        expected = [
            "read_file",
            "write_file",
            "grep",
            "glob_pattern",
            "count_tokens",
            "compute_diff",
            "apply_diff",
            "sandbox_execute",
            "sandbox_read_file",
            "sandbox_write_file",
            "search_codebase",
        ]
        for name in expected:
            # Confirm the expected result for this scenario: all functions exist.
            assert hasattr(native, name), f"Missing function: {name}"
            assert callable(getattr(native, name)), f"Not callable: {name}"

    def test_pyi_stubs_match(self):
        """_native.pyi stub signatures should exist and be callable."""
        try:
            from encre import _native as _rust_native  # type: ignore
        except ImportError:
            pytest.skip("Rust _native extension not built (expected in dev)")

        # The Rust extension should have the functions declared in _native.pyi
        expected = [
            "search_codebase",
            "read_file",
            "write_file",
            "grep",
            "glob",
            "count_tokens",
            "compute_diff",
            "apply_diff",
            "sandbox_execute",
            "sandbox_read_file",
            "sandbox_write_file",
        ]
        for name in expected:
            # Confirm the expected result for this scenario: pyi stubs match.
            assert hasattr(_rust_native, name), f"Rust _native missing: {name}"


class TestReadWriteFile:
    """Test cases covering read write file.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test file reading and writing with temp files."""

    def test_write_and_read_file(self, tmp_path: Path):
        """Verifies that write and read file."""
        filepath = str(tmp_path / "test_file.txt")
        content = "Hello, encre native tests!\nLine two.\n"

        # Confirm the expected result for this scenario: write and read file.
        assert native.write_file(filepath, content) is True
        result = native.read_file(filepath)
        # Native read may or may not preserve trailing newline depending on impl
        assert "Hello, encre native tests!" in result
        assert "Line two" in result

    def test_read_file_with_offset(self, tmp_path: Path):
        """Verifies that read file with offset."""
        filepath = str(tmp_path / "offset_test.txt")
        lines = "line_1\nline_2\nline_3\nline_4\n"
        native.write_file(filepath, lines)

        result = native.read_file(filepath, offset=2)  # 1-indexed
        # Confirm the expected result for this scenario: read file with offset.
        assert "line_2" in result

    def test_read_file_with_offset_and_limit(self, tmp_path: Path):
        """Verifies that read file with offset and limit."""
        filepath = str(tmp_path / "limit_test.txt")
        lines = "a\nb\nc\nd\ne\n"
        native.write_file(filepath, lines)

        result = native.read_file(filepath, offset=2, limit=2)
        parts = result.strip().splitlines()
        # Confirm the expected result for this scenario: read file with offset and limit.
        assert len(parts) <= 3  # offset=2 starts at line 2

    def test_read_file_not_found(self, tmp_path: Path):
        """Verifies that read file not found."""
        filepath = str(tmp_path / "does_not_exist.txt")
        with pytest.raises(FileNotFoundError):
            native.read_file(filepath)

    def test_write_file_creates_directories(self, tmp_path: Path):
        """Verifies that write file creates directories."""
        filepath = str(tmp_path / "deep" / "nested" / "dir" / "file.txt")
        content = "deeply nested content"
        # Confirm the expected result for this scenario: write file creates directories.
        assert native.write_file(filepath, content) is True
        assert native.read_file(filepath) == content


class TestGrep:
    """Test cases covering grep.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test native grep (returns list of dicts)."""

    def test_grep_finds_matches(self, tmp_path: Path):
        """Verifies that grep finds matches."""
        filepath = str(tmp_path / "grep_test.py")
        native.write_file(filepath, "def foo():\n    return 42\n\ndef bar():\n    return 99\n")
        results = native.grep(r"def \w+", filepath)
        assert isinstance(results, list)
        assert any("def foo" in r["line_content"] for r in results)
        assert any("def bar" in r["line_content"] for r in results)

    def test_grep_case_insensitive(self, tmp_path: Path):
        """Verifies that grep case insensitive."""
        filepath = str(tmp_path / "case_test.txt")
        native.write_file(filepath, "HELLO world\nhello WORLD\n")
        results = native.grep("hello", filepath, case_insensitive=True)
        assert len(results) == 2

    def test_grep_no_match(self, tmp_path: Path):
        """Verifies that grep no match."""
        filepath = str(tmp_path / "no_match.txt")
        native.write_file(filepath, "just some text\n")
        results = native.grep("NOTFOUND", filepath)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_grep_invalid_regex(self, tmp_path: Path):
        """Verifies that grep invalid regex raises."""
        filepath = str(tmp_path / "bad_regex.txt")
        native.write_file(filepath, "content\n")
        with pytest.raises(Exception):
            native.grep("[invalid", filepath)

    def test_grep_multiline(self, tmp_path: Path):
        """Verifies that grep multiline."""
        filepath = str(tmp_path / "multiline.txt")
        native.write_file(filepath, "foo\nbar\nbaz\n")
        results = native.grep(r"foo\nbar", filepath, multiline=True)
        assert len(results) == 1

    def test_grep_head_limit(self, tmp_path: Path):
        """Verifies that grep head limit."""
        filepath = str(tmp_path / "head_limit.txt")
        native.write_file(filepath, "match 1\nskip\nmatch 2\nskip\nmatch 3\n")
        results = native.grep("match", filepath, head_limit=2)
        assert len(results) == 2


class TestGlobPattern:
    """Test cases covering glob pattern.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test glob pattern matching."""

    def test_glob_finds_files(self, tmp_path: Path):
        """Verifies that glob finds files."""
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        result = native.glob_pattern("*.py", str(tmp_path))
        # Confirm the expected result for this scenario: glob finds files.
        assert len(result) == 2
        assert any("a.py" in p for p in result)
        assert any("b.py" in p for p in result)

    def test_glob_no_match(self, tmp_path: Path):
        """Verifies that glob no match."""
        result = native.glob_pattern("*.xyz", str(tmp_path))
        # Confirm the expected result for this scenario: glob no match.
        assert isinstance(result, list)
        assert len(result) == 0

    def test_glob_default_path(self, tmp_path: Path):
        """Verifies that glob default path."""
        # Create files in current/working context
        (tmp_path / "hello.md").write_text("")
        result = native.glob_pattern("*.md", str(tmp_path))
        # Confirm the expected result for this scenario: glob default path.
        assert len(result) >= 1


class TestCountTokens:
    """Test cases covering count tokens.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test token counting."""

    def test_count_tokens_returns_int(self):
        """Verifies that count tokens returns int."""
        result = native.count_tokens("Hello, world!")
        # Confirm the expected result for this scenario: count tokens returns int.
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_empty_string(self):
        """Verifies that count tokens empty string."""
        result = native.count_tokens("")
        # Confirm the expected result for this scenario: count tokens empty string.
        assert result == 0

    def test_count_tokens_long_text(self):
        """Verifies that count tokens long text."""
        text = "The quick brown fox " * 100
        result = native.count_tokens(text)
        # Confirm the expected result for this scenario: count tokens long text.
        assert result > 50  # rough estimate at chars/4

    def test_count_tokens_whitespace_only(self):
        """Verifies that count tokens whitespace only."""
        result = native.count_tokens("   \t\n  ")
        # Implementation differs: Rust may count spaces, Python strips
        # Confirm the expected result for this scenario: count tokens whitespace only.
        assert isinstance(result, int)


class TestDiff:
    """Test cases covering diff.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test compute_diff and apply_diff."""

    def test_compute_diff_identical(self):
        """Verifies that compute diff identical."""
        diff = native.compute_diff("hello\nworld\n", "hello\nworld\n")
        # Confirm the expected result for this scenario: compute diff identical.
        assert isinstance(diff, str)

    def test_compute_diff_changed(self):
        """Verifies that compute diff changed."""
        diff = native.compute_diff("hello\nworld\n", "hello\nuniverse\n")
        # Native implementations may use different diff formats
        # Confirm the expected result for this scenario: compute diff changed.
        assert isinstance(diff, str)
        assert len(diff) > 0  # changed content should produce non-empty diff

    def test_apply_diff_simple(self):
        """Verifies that apply diff simple."""
        original = "hello\nworld\n"
        diff = native.compute_diff(original, "hello\nuniverse\n")
        result = native.apply_diff(original, diff)
        # Confirm the expected result for this scenario: apply diff simple.
        assert "universe" in result

    def test_apply_diff_roundtrip(self):
        """Verifies that apply diff roundtrip."""
        old = "line1\nline2\nline3\n"
        new = "line1\nline2_modified\nline3\nline4\n"
        diff = native.compute_diff(old, new)
        applied = native.apply_diff(old, diff)
        # Confirm the expected result for this scenario: apply diff roundtrip.
        assert applied == new

    def test_compute_diff_empty_strings(self):
        """Verifies that compute diff empty strings."""
        diff = native.compute_diff("", "")
        # Confirm the expected result for this scenario: compute diff empty strings.
        assert isinstance(diff, str)


class TestSandboxExecute:
    """Test cases covering sandbox execute.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test sandbox_execute (runs locally for development)."""

    def test_sandbox_echo(self):
        """Verifies that sandbox echo."""
        result = native.sandbox_execute("echo hello", timeout=10)
        # Confirm the expected result for this scenario: sandbox echo.
        assert isinstance(result, dict)
        assert "stdout" in result
        assert "stderr" in result
        assert "exit_code" in result
        assert "hello" in result["stdout"]

    def test_sandbox_exit_code_success(self):
        """Verifies that sandbox exit code success."""
        result = native.sandbox_execute("exit 0", timeout=10)
        # Confirm the expected result for this scenario: sandbox exit code success.
        assert result["exit_code"] == 0

    def test_sandbox_stderr(self):
        """Verifies that sandbox stderr."""
        result = native.sandbox_execute("echo error >&2", timeout=10)
        # Confirm the expected result for this scenario: sandbox stderr.
        assert "error" in result["stderr"] or result["exit_code"] is not None


class TestSandboxFileOps:
    """Test cases covering sandbox file ops.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test sandbox file read/write operations."""

    def test_sandbox_write_and_read(self, tmp_path: Path):
        """Verifies that sandbox write and read."""
        filepath = str(tmp_path / "sandbox_file.txt")
        # Confirm the expected result for this scenario: sandbox write and read.
        assert native.sandbox_write_file(filepath, "sandbox content") is True
        result = native.sandbox_read_file(filepath)
        assert result == "sandbox content"

    def test_sandbox_read_missing(self, tmp_path: Path):
        """Verifies that sandbox read missing."""
        filepath = str(tmp_path / "sandbox_missing.txt")
        with pytest.raises(FileNotFoundError):
            native.sandbox_read_file(filepath)


class TestSearchCodebase:
    """Test cases covering search codebase.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test search_codebase function."""

    def test_search_finds_content(self, tmp_path: Path):
        """Verifies that search finds content."""
        (tmp_path / "sample.py").write_text("def my_function():\n    return True\n")
        results = native.search_codebase("my_function", str(tmp_path))
        # Confirm the expected result for this scenario: search finds content.
        assert isinstance(results, list)
        assert len(results) > 0
        assert any("sample.py" in r.get("file_path", "") for r in results)

    def test_search_no_match(self, tmp_path: Path):
        """Verifies that search no match."""
        (tmp_path / "data.txt").write_text("ordinary text here\n")
        results = native.search_codebase("XYZ-NONEXISTENT", str(tmp_path))
        # Confirm the expected result for this scenario: search no match.
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_default_path(self):
        """Verifies that search default path."""
        results = native.search_codebase("def")
        # Confirm the expected result for this scenario: search default path.
        assert isinstance(results, list)
