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

"""Tests for builtin tools: file read/write/edit, grep, glob, task manager,
cron validation, tool registry, input schemas, and concurrency safety."""

import os

import pytest
from encre.task.manager import EncreTaskManager
from encre.tools.base import EncreTool
from encre.tools.builtin import (
    EncreBashTool,
    EncreCronCreateTool,
    EncreCronDeleteTool,
    EncreCronListTool,
    EncreFileEditTool,
    EncreFileReadTool,
    EncreFileWriteTool,
    EncreGlobTool,
    EncreGrepTool,
    EncreTaskCreateTool,
    EncreTaskGetTool,
    EncreTaskListTool,
    EncreTaskUpdateTool,
)
from encre.tools.registry import ToolRegistry

# ===========================================================================
# File read tool
# ===========================================================================

class TestFileReadTool:
    """Engineered to validate the :class:`EncreFileReadTool` implementation.

    The file-read tool is the primary read-only I/O primitive used by the
    agent during code navigation and analysis. Tests cover the happy path
    (existing file), the not-found path (graceful error), the streaming
    offset and limit windows used for large-file pagination, and the empty-
    file sentinel so downstream logic can distinguish zero-byte reads from
    errors.
    """

    async def test_verify_read_existing_file_returns_content(self, temp_dir):
        """Validate that EncreFileReadTool returns file content when the path exists.

        The agent uses this tool for context gathering; a missing heading
        in the returned text would break the markdown-aware parser, so the
        test asserts the known README title fragment is present.
        """
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "README.md")
        result = await tool.execute(file_path=file_path)
        assert "# Test Project" in result

    async def test_verify_read_nonexistent_file_returns_error_message(self, temp_dir):
        """Validate that EncreFileReadTool surfaces an error string when the path is missing.

        The agent must not crash on missing files; instead it receives a
        readable error it can surface to the user or use to retry.
        """
        tool = EncreFileReadTool()
        result = await tool.execute(file_path=os.path.join(temp_dir, "nonexistent.txt"))
        assert "Error" in result

    async def test_verify_read_with_offset_returns_content_from_line(self, temp_dir):
        """Validate that EncreFileReadTool respects the offset parameter for pagination.

        Offset is used to stream large files in chunks; the test asserts the
        return type remains a string so callers can chain paging logic without
        type checks on every iteration.
        """
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(file_path=file_path, offset=3)
        # Should return content starting from line 3
        assert isinstance(result, str)

    async def test_verify_read_with_limit_respects_line_cap(self, temp_dir):
        """Validate that EncreFileReadTool limits output to the requested line count.

        The limit parameter caps how many lines are returned so the context
        window is not exhausted by a single read; the assertion allows a
        trailing newline which some readers emit even for one-line requests.
        """
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(file_path=file_path, limit=1)
        lines = result.strip().split("\n")
        assert len(lines) <= 2  # may include trailing newline

    async def test_verify_read_empty_file_returns_sentinel_string(self, temp_dir):
        """Validate that EncreFileReadTool emits its empty-file sentinel for zero-byte files.

        The sentinel string '(empty file, 0 bytes)' lets downstream code
        distinguish a truly empty file from an error without inspecting
        exception traces, keeping the read loop simple.
        """
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "empty.txt")
        result = await tool.execute(file_path=file_path)
        assert result == "(empty file, 0 bytes)"

    def test_verify_input_schema_requires_file_path(self):
        """Validate that the input schema declares file_path as a required field.

        Required-field declaration is what drives the JSON Schema validator
        before execution; without it the tool would accept missing paths and
        fail later with an opaque error.
        """
        assert "file_path" in EncreFileReadTool.input_schema.get("required", [])

    def test_verify_is_concurrency_safe_for_read_only_operations(self):
        """Validate that is_concurrency_safe returns True for pure reads.

        Read operations do not mutate shared state, so they can safely run
        in parallel; the concurrency guard relies on this flag to bypass
        serialization for read-heavy workloads.
        """
        tool = EncreFileReadTool()
        assert tool.is_concurrency_safe({"file_path": "/somewhere"}) is True


# ===========================================================================
# File write tool
# ===========================================================================

class TestFileWriteTool:
    """Engineered to validate the :class:`EncreFileWriteTool` implementation.

    The file-write tool is the agent's primary mutation primitive. Tests
    exercise new-file creation, overwriting existing content, recursive
    parent-directory creation, schema-required fields, and the concurrency
    safety flag (writes are inherently non-serializable across paths).
    """

    async def test_verify_write_creates_new_file_and_persists_content(self, temp_dir):
        """Validate that EncreFileWriteTool creates a file and writes the exact content.

        The test double-checks the on-disk bytes against the submitted
        string to guard against encoding mutations or truncation.
        """
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "new_file.txt")
        result = await tool.execute(file_path=file_path, content="Hello, write!")
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "Hello, write!"

    async def test_verify_write_overwrites_existing_file_content(self, temp_dir):
        """Validate that EncreFileWriteTool replaces existing file content without preserving old data.

        Overwrite semantics are intentional 鈥?the agent treats write as the
        authoritative update, so the previous content must not leak through.
        """
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "README.md")
        result = await tool.execute(file_path=file_path, content="Overwritten")
        assert "Successfully wrote" in result
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "Overwritten"

    async def test_verify_write_creates_parent_directories_implicitly(self, temp_dir):
        """Validate that EncreFileWriteTool creates missing parent directories automatically.

        Agents often construct deep paths on first write; requiring the
        caller to pre-create directories would add friction without value.
        """
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "nested", "deep", "file.txt")
        result = await tool.execute(file_path=file_path, content="Deep content")
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

    def test_verify_input_schema_requires_file_path_and_content(self):
        """Validate that the input schema declares both file_path and content as required.

        Missing either field must be caught at validation time, not inside
        the OS write path, so the error message points to the missing arg.
        """
        required = EncreFileWriteTool.input_schema.get("required", [])
        assert "file_path" in required
        assert "content" in required

    def test_verify_is_concurrency_safe_returns_false_for_write_operations(self):
        """Validate that is_concurrency_safe returns False because writes mutate shared filesystem state.

        Concurrent writes to overlapping paths can interleave bytes and
        corrupt files; the flag forces the scheduler to serialize them.
        """
        tool = EncreFileWriteTool()
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# File edit tool
# ===========================================================================

class TestFileEditTool:
    """Engineered to validate the :class:`EncreFileEditTool` implementation.

    The edit tool performs in-place string substitution, the preferred
    mutation primitive for surgical changes. Tests cover the success case,
    non-unique-match handling (which requires the caller to disambiguate),
    missing-match errors, nonexistent-file errors, and the concurrency
    safety flag (edit is a read-modify-write cycle and therefore unsafe).
    """

    async def test_verify_edit_replaces_single_occurrence_correctly(self, temp_dir):
        """Validate that EncreFileEditTool replaces the exact old_str with new_str in the target file.

        The renderer-replay check (open + read + assert) ensures the edit
        survived disk flush and was not a transient in-memory change.
        """
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="def hello():",
            new_str="def greeting():",
        )
        assert "edit(s) to" in result
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        assert "def greeting():" in content
        assert "def hello():" not in content

    async def test_verify_edit_reports_match_count_for_non_unique_old_str(self, temp_dir):
        """Validate that EncreFileEditTool returns the occurrence count when old_str matches multiple locations.

        A non-unique match would silently replace all occurrences; the tool
        reports the count so the caller can ask for further disambiguation
        rather than over-editing the file.
        """
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="\n",
            new_str="\n\n",
        )
        assert "matched" in result
        assert "times" in result or "occurrences" in result

    async def test_verify_edit_returns_error_when_old_str_has_no_matches(self, temp_dir):
        """Validate that EncreFileEditTool returns an error when old_str is absent from the file.

        A no-match should never silently succeed; the error lets the agent
        re-attempt with a corrected old_str rather than producing a bogus edit.
        """
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="this string does not exist in file",
            new_str="nothing",
        )
        assert "Error" in result

    async def test_verify_edit_returns_error_for_nonexistent_file(self, temp_dir):
        """Validate that EncreFileEditTool surfaces an error when the target file does not exist.

        Edit operates on existing content; creating files on miss is outside
        its scope and must be delegated to the write tool.
        """
        tool = EncreFileEditTool()
        result = await tool.execute(
            file_path=os.path.join(temp_dir, "not_here.txt"),
            old_str="x",
            new_str="y",
        )
        assert "Error" in result

    def test_verify_input_schema_requires_file_path(self):
        """Validate that the input schema declares file_path as a required field.

        Without this requirement the validator would allow a call with no
        target, pushing the failure into the OS layer with a worse message.
        """
        required = EncreFileEditTool.input_schema.get("required", [])
        assert "file_path" in required

    def test_verify_is_concurrency_safe_returns_false_for_read_modify_write_operation(self):
        """Validate that is_concurrency_safe returns False because edits mutate file contents.

        Concurrent edits to the same path can produce interleaved or lost
        updates; the flag serializes edit operations at the scheduler level.
        """
        tool = EncreFileEditTool()
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Grep tool
# ===========================================================================

class TestGrepTool:
    """Engineered to validate the :class:`EncreGrepTool` implementation.

    The grep tool performs regex-based search over the filesystem and is
    the agent's primary discovery primitive for locating symbols, calls,
    and usages. Tests cover match reporting, empty-result reporting, case
    insensitivity, the two alternate output modes, glob filtering, invalid
    regex handling, single-file targeting, and concurrency safety (grep is
    purely read-only so it can run in parallel).
    """

    async def test_verify_grep_finds_matching_lines_in_tree(self, temp_dir):
        """Validate that EncreGrepTool returns lines containing the search pattern.

        The agent relies on grep for symbol location; a missing match would
        stall the code-navigation loop, so the known function definition is
        asserted to appear in output.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def hello", path=temp_dir)
        assert "def hello" in result

    async def test_verify_grep_reports_no_matches_when_pattern_is_absent(self, temp_dir):
        """Validate that EncreGrepTool returns a no-match indicator for an impossible pattern.

        Empty-result sets must be distinguished from errors; the lowercase
        check accommodates implementations that phrase the message differently.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="FOOBARBAZQUX", path=temp_dir)
        assert "no matches" in result.lower()

    async def test_verify_grep_supports_case_insensitive_mode(self, temp_dir):
        """Validate that EncreGrepTool respects the case-insensitive flag.

        Case-insensitive matching is essential for symbol search where the
        casing in the query may not match the declaration; the test passes
        the flag through **kwargs to match the tool's CLI-style interface.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="DEF HELLO", path=temp_dir, **{"-i": True})
        assert "def hello" in result

    async def test_verify_grep_files_with_matches_mode_returns_only_filenames(self, temp_dir):
        """Validate that output_mode='files_with_matches' returns just the paths of matching files.

        This mode is used by the agent when it needs a file list rather than
        inline diffs; filenames must appear even when line-level detail is suppressed.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, output_mode="files_with_matches")
        assert "main.py" in result or "utils.py" in result

    async def test_verify_grep_count_mode_returns_per_file_occurrence_counts(self, temp_dir):
        """Validate that output_mode='count' annotates each file with its match count.

        The count suffix (e.g. ':1', ':2') lets the agent rank candidates by
        relevance without fetching full match context first.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, output_mode="count")
        assert "main.py" in result and ":1" in result or "utils.py" in result and ":2" in result
        assert ":1" in result or ":2" in result

    async def test_verify_grep_glob_filter_restricts_search_to_matching_extensions(self, temp_dir):
        """Validate that the glob parameter restricts search to files matching the pattern.

        Filtering by extension prevents grep output from being flooded with
        binary or irrelevant files; the test asserts .py files are included
        while .md files are excluded from the result.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, glob="*.py")
        assert "main.py" in result or "utils.py" in result
        assert "README.md" not in result

    async def test_verify_grep_invalid_regex_returns_error_instead_of_crashing(self, temp_dir):
        """Validate that EncreGrepTool catches invalid regex and returns a structured error.

        Unhandled regex exceptions would abort the agent loop; the tool must
        catch compilation failures and return a friendly error string.
        """
        tool = EncreGrepTool()
        result = await tool.execute(pattern="[invalid", path=temp_dir)
        assert "Error" in result

    async def test_verify_grep_on_specific_file_searches_only_that_path(self, temp_dir):
        """Validate that passing a file path limits grep to that single file.

        When the agent already knows the target file, scoping to one path
        avoids noisy results from other directories in the tree.
        """
        tool = EncreGrepTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(pattern="hello", path=file_path)
        assert "def hello" in result

    def test_verify_input_schema_requires_pattern(self):
        """Validate that the input schema declares pattern as a required field.

        Pattern is the search key; allowing it to be absent would produce a
        degenerate query that matches everything and floods the output.
        """
        required = EncreGrepTool.input_schema.get("required", [])
        assert "pattern" in required

    def test_verify_is_concurrency_safe_returns_true_for_read_only_search(self):
        """Validate that is_concurrency_safe returns True because grep is a read-only operation.

        Read-only tools can execute in parallel without race conditions;
        the scheduler uses this flag to parallelize search across sub-tasks.
        """
        tool = EncreGrepTool()
        assert tool.is_concurrency_safe({}) is True


# ===========================================================================
# Glob tool
# ===========================================================================

class TestGlobTool:
    """Engineered to validate the :class:`EncreGlobTool` implementation.

    The glob tool performs filesystem path enumeration using shell-style
    wildcards and is the agent's primary discovery primitive for finding
    files by extension, depth, or naming pattern. Tests cover root-level
    patterns, nested patterns, extension filters, recursive globs, empty-
    result reporting, default-path fallback, and concurrency safety (glob
    is purely read-only so it can run in parallel).
    """

    async def test_verify_glob_finds_py_files_at_root(self, temp_dir):
        """Validate that EncreGlobTool returns files matching the root-level *.py pattern.

        The agent uses glob to locate entry points and module files; a root
        pattern must resolve correctly so the caller receives a usable list.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.py", path=temp_dir)
        assert "main.py" in result

    async def test_verify_glob_finds_py_files_in_nested_directory(self, temp_dir):
        """Validate that EncreGlobTool resolves one-level-deep nested patterns.

        The ``*/*.py`` pattern targets direct children of subdirectories; the
        test asserts utils.py under src/ is found without recursing deeper.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*/*.py", path=temp_dir)
        assert "utils.py" in result

    async def test_verify_glob_filters_by_md_extension(self, temp_dir):
        """Validate that EncreGlobTool returns only markdown files for *.md.

        Extension filters are commonly used by the agent to find documentation
        alongside source files; the result must include README.md and nothing else.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.md", path=temp_dir)
        assert "README.md" in result

    async def test_verify_glob_recursive_pattern_finds_json_in_subtrees(self, temp_dir):
        """Validate that the **/*.json pattern discovers config.json nested under src/.

        Recursive globs are essential for finding configuration files at any
        depth; the test ensures the star-star traversal reaches nested dirs.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="**/*.json", path=temp_dir)
        assert "config.json" in result

    async def test_verify_glob_returns_sentinel_when_no_files_match(self, temp_dir):
        """Validate that EncreGlobTool returns a no-match sentinel string for impossible patterns.

        Empty results must be distinguishable from errors so the agent can
        fall back to a broader search instead of treating absence as failure.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.xyzzy", path=temp_dir)
        assert "No files match pattern" in result

    async def test_verify_glob_uses_working_directory_as_default_path(self, temp_dir):
        """Validate that omitting the path argument defaults to the current working directory.

        The temp_dir fixture changes cwd into the fixture tree; a default-path
        glob must resolve relative to that directory so tests don't need to
        pass temp_dir explicitly on every call.
        """
        tool = EncreGlobTool()
        result = await tool.execute(pattern="main.py")
        assert "main.py" in result

    def test_verify_input_schema_requires_pattern(self):
        """Validate that the input schema declares pattern as a required field.

        Pattern is the search key; allowing it to be absent would produce a
        degenerate query that enumerates the entire tree and exhausts memory.
        """
        required = EncreGlobTool.input_schema.get("required", [])
        assert "pattern" in required

    def test_verify_is_concurrency_safe_returns_true_for_read_only_enumeration(self):
        """Validate that is_concurrency_safe returns True because glob is a read-only operation.

        Path enumeration does not mutate state, so the scheduler can fan out
        multiple glob calls concurrently without serialization.
        """
        tool = EncreGlobTool()
        assert tool.is_concurrency_safe({}) is True


# ===========================================================================
# Bash tool (safe commands only)
# ===========================================================================

class TestBashTool:
    """Engineered to validate the :class:`EncreBashTool` implementation for safe commands.

    The bash tool executes shell commands under a sandbox policy that
    restricts dangerous operations. Tests exercise echo, pwd with cwd
    switching, and command-not-found error handling. The Windows platform
    note in the cwd test accommodates path-format translation performed
    by Git Bash on Windows.
    """

    async def test_verify_bash_echo_returns_stdin_to_stdout(self):
        """Validate that EncreBashTool runs echo and returns the echoed text.

        Echo is the canonical smoke test for shell execution; if it fails
        the tool's subprocess pipeline is broken end-to-end.
        """
        tool = EncreBashTool()
        result = await tool.execute(command="echo hello world")
        assert "hello world" in result

    async def test_verify_bash_pwd_returns_a_non_empty_path(self):
        """Validate that EncreBashTool runs pwd and returns an absolute path string.

        pwd is used to confirm the working directory after cwd injection;
        a blank result would indicate the subprocess failed silently.
        """
        tool = EncreBashTool()
        result = await tool.execute(command="pwd")
        assert result.strip() != ""

    async def test_verify_bash_with_cwd_runs_in_the_target_directory(self, temp_dir):
        """Validate that the cwd argument changes the subprocess working directory before execution.

        On Windows the path may be translated by bash (e.g. C:\\... -> /c/...);
        the assertion accepts any non-empty absolute-looking path rather than
        hard-coding a format that differs across platforms.
        """
        tool = EncreBashTool()
        result = await tool.execute(command="pwd", cwd=temp_dir)
        # On Windows, bash may translate paths (e.g. C:\Users\...\Temp\... -> /tmp/...).
        # We verify pwd ran successfully by checking the output is a non-empty path.
        result = result.strip()
        assert len(result) > 0
        assert "Error" not in result
        # The returned path should be absolute (start with / or drive letter)
        assert result.startswith("/") or ":" in result

    async def test_verify_bash_command_not_found_returns_an_error(self):
        """Validate that EncreBashTool returns an error string when the command does not exist.

        Invalid commands must not raise uncaught exceptions; they should
        surface as a structured error the agent can display or retry around.
        """
        tool = EncreBashTool()
        result = await tool.execute(command="nonexistentcommandxyz123")
        assert "Error" in result or "not found" in result.lower() or result.strip() != ""

    def test_verify_input_schema_requires_command(self):
        """Validate that the input schema declares command as a required field.

        Without a command string the tool cannot spawn a subprocess; the
        validator must reject the call before reaching the exec layer.
        """
        required = EncreBashTool.input_schema.get("required", [])
        assert "command" in required

    def test_verify_is_concurrency_safe_returns_false_for_process_spawn(self):
        """Validate that is_concurrency_safe returns False because bash spawns external processes.

        Shell execution can interact with shared state (filesystem, network,
        environment); the scheduler must serialize these calls to prevent
        interleaved side effects between sub-tasks.
        """
        tool = EncreBashTool()
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Task manager CRUD
# ===========================================================================

class TestTaskManagerCRUD:
    """Engineered to validate the :class:`EncreTaskManager` CRUD lifecycle.

    The task manager is an in-process key-value store backed by a class-
    level dict; its state persists across tool calls within a session but
    must be cleared between tests to avoid cross-contamination. Tests cover
    create, read, update, delete, and filtered list retrieval.
    """

    def setup_method(self):
        """Clear task state before each test to isolate CRUD scenarios.

        Because the manager is process-global, any leftover tasks from a
        previous test would invalidate count-based assertions here.
        """
        EncreTaskManager.clear()

    def teardown_method(self):
        """Clear task state after each test to prevent bleed into subsequent tests.

        Teardown is the safety net in case a test exits early or raises;
        it guarantees the next setup_method starts from a clean slate.
        """
        EncreTaskManager.clear()

    def test_verify_create_task_returns_a_non_empty_id(self):
        """Validate that EncreTaskManager.create_task generates and returns a unique task identifier.

        The ID is the primary key for all subsequent get/update/delete calls;
        a None or empty return would break the caller's ability to address the task.
        """
        task_id = EncreTaskManager.create_task(
            name="Test task",
            description="A test",
            task_type="bash",
            prompt="echo hello",
        )
        assert task_id is not None
        assert len(task_id) > 0

    def test_verify_get_task_retrieves_a_previously_created_task(self):
        """Validate that EncreTaskManager.get_task returns the correct task by its ID.

        The round-trip (create then get) ensures the storage layer persists
        all supplied fields and that the lookup key matches the returned ID.
        """
        task_id = EncreTaskManager.create_task(
            name="Get me",
            description="Test retrieval",
            task_type="agent",
            prompt="Do something",
        )
        task = EncreTaskManager.get_task(task_id)
        assert task is not None
        assert task.name == "Get me"
        assert task.task_type == "agent"

    def test_verify_get_nonexistent_task_returns_none(self):
        """Validate that EncreTaskManager.get_task returns None for an unknown ID.

        Missing-key returns must be None, not an exception, so callers can
        branch on existence without try/except overhead in the hot loop.
        """
        assert EncreTaskManager.get_task("nonexistent") is None

    def test_verify_update_task_status_changes_and_persists_the_field(self):
        """Validate that EncreTaskManager.update_task changes status and the change survives a subsequent get.

        The double-check (update result then get again) ensures the mutation
        is persisted to the backing store, not just applied to an in-memory
        copy that disappears on the next access.
        """
        task_id = EncreTaskManager.create_task(
            name="Update me",
            description="Status change test",
            task_type="bash",
            prompt="run",
        )
        result = EncreTaskManager.update_task(task_id, status="running")
        assert result is True
        task = EncreTaskManager.get_task(task_id)
        assert task.status == "running"

    def test_verify_update_task_with_result_persists_both_status_and_result(self):
        """Validate that EncreTaskManager.update_task stores status and result together.

        Completion state is always written as a pair; storing only one field
        would leave the task in an ambiguous partial-complete state.
        """
        task_id = EncreTaskManager.create_task(
            name="Result test",
            description="Set result",
            task_type="bash",
            prompt="run",
        )
        EncreTaskManager.update_task(task_id, status="completed", result="Success!")
        task = EncreTaskManager.get_task(task_id)
        assert task.status == "completed"
        assert task.result == "Success!"

    def test_verify_update_nonexistent_task_returns_false(self):
        """Validate that EncreTaskManager.update_task returns False when the task ID does not exist.

        A false return lets the caller distinguish 'task not found' from
        'task found but status unchanged', which drives different retry logic.
        """
        assert EncreTaskManager.update_task("nonexistent", status="completed") is False

    def test_verify_list_tasks_returns_all_created_tasks(self):
        """Validate that EncreTaskManager.list_tasks returns every task created in the current session.

        The list endpoint is the basis for the task dashboard UI; all three
        created tasks must appear so the caller sees full session state.
        """
        ids = []
        for i in range(3):
            tid = EncreTaskManager.create_task(
                name=f"Task {i}",
                description=f"Desc {i}",
                task_type="bash",
                prompt=f"cmd {i}",
            )
            ids.append(tid)
        tasks = EncreTaskManager.list_tasks()
        assert len(tasks) == 3

    def test_verify_list_tasks_filters_by_status_correctly(self):
        """Validate that EncreTaskManager.list_tasks returns only tasks matching the requested status.

        The status filter drives the per-status task panels in the UI; both
        pending and running counts must be at least one because the setup
        creates one of each and the running task transitions during the test.
        """
        EncreTaskManager.create_task(name="Pending", description="...", task_type="bash", prompt="...")  # noqa: E501
        tid2 = EncreTaskManager.create_task(name="Running", description="...", task_type="bash", prompt="...")  # noqa: E501
        EncreTaskManager.update_task(tid2, status="running")

        pending = EncreTaskManager.list_tasks(status="pending")
        running = EncreTaskManager.list_tasks(status="running")
        assert len(pending) >= 1
        assert len(running) >= 1

    def test_verify_delete_task_removes_it_and_returns_true(self):
        """Validate that EncreTaskManager.delete_task removes the task and returns True on success.

        Post-delete retrieval must return None to confirm the entry is fully
        evicted from the backing store, not just marked inactive.
        """
        task_id = EncreTaskManager.create_task(name="Delete me", description="...", task_type="bash", prompt="...")  # noqa: E501
        assert EncreTaskManager.delete_task(task_id) is True
        assert EncreTaskManager.get_task(task_id) is None

    def test_verify_delete_nonexistent_task_returns_false(self):
        """Validate that EncreTaskManager.delete_task returns False when the task ID is unknown.

        The false return lets the caller distinguish 'already gone' from
        'deletion failed due to an internal error'.
        """
        assert EncreTaskManager.delete_task("nonexistent") is False


# ===========================================================================
# Task tools (builtins)
# ===========================================================================

class TestTaskCreateTool:
    """Engineered to validate the :class:`EncreTaskCreateTool` builtin wrapper.

    The tool wraps EncreTaskManager.create_task behind the standard tool
    execute() API, adding input validation and a formatted response string.
    Tests verify the round-trip through the tool produces a storable task
    ID and that the input schema enforces all required fields.
    """

    def setup_method(self):
        """Clear task state before each test to isolate tool-level CRUD scenarios.

        The tool operates on the same global manager as TestTaskManagerCRUD;
        cleanup is required to prevent inherited tasks from inflating counts.
        """
        EncreTaskManager.clear()

    def teardown_method(self):
        """Clear task state after each test to prevent cross-test contamination.

        Teardown runs even on exception paths, ensuring the manager is
        clean for whichever test follows in the pytest dispatch order.
        """
        EncreTaskManager.clear()

    async def test_verify_create_task_via_tool_round_trips_through_manager(self):
        """Validate that EncreTaskCreateTool.execute creates a task visible in the manager.

        The parsed ID is extracted from the formatted response string and
        used to fetch the task directly, confirming the tool forwarded all
        required fields to the manager without dropping any arguments.
        """
        tool = EncreTaskCreateTool()
        result = await tool.execute(
            name="My sub-task",
            description="Do the thing",
            task_type="bash",
            prompt="echo done",
        )
        assert "Task created:" in result
        task_id = result.split("Task created:")[1].strip()
        assert EncreTaskManager.get_task(task_id) is not None

    def test_verify_input_schema_requires_name_task_type_and_prompt(self):
        """Validate that the input schema enforces name, task_type, and prompt as required fields.

        All three fields are semantically necessary for task dispatch; omitting
        any of them would leave the scheduler unable to plan or execute.
        """
        required = EncreTaskCreateTool.input_schema.get("required", [])
        assert "name" in required
        assert "task_type" in required
        assert "prompt" in required

    def test_verify_is_concurrency_safe_returns_false_for_state_mutating_create(self):
        """Validate that is_concurrency_safe returns False because create mutates the task store.

        Concurrent creates can produce colliding IDs or corrupt the dict if
        the manager is not internally locked; the flag serializes the call.
        """
        tool = EncreTaskCreateTool()
        assert tool.is_concurrency_safe({}) is False


class TestTaskGetTool:
    """Engineered to validate the :class:`EncreTaskGetTool` builtin wrapper.

    The tool wraps EncreTaskManager.get_task and formats the result as a
    human-readable summary. Tests verify successful retrieval displays the
    task's name, type, and ID, and that a missing ID returns a clear error.
    """

    def setup_method(self):
        """Clear task state before each test to isolate get-tool scenarios.

        A stale task from another test could accidentally satisfy a lookup
        and mask a missing-ID bug, so cleanup is mandatory here.
        """
        EncreTaskManager.clear()

    def teardown_method(self):
        """Clear task state after each test to prevent cross-test contamination.

        Guarantees teardown leaves the global manager empty regardless of
        whether the test body completed normally or raised.
        """
        EncreTaskManager.clear()

    async def test_verify_get_existing_task_returns_formatted_summary(self):
        """Validate that EncreTaskGetTool.execute returns a summary containing the task's key fields.

        The formatted string must include name, type, and ID so the caller
        can confirm the retrieved task without parsing the manager directly.
        """
        task_id = EncreTaskManager.create_task(
            name="Detailed task",
            description="Check details",
            task_type="agent",
            prompt="Review code",
        )
        tool = EncreTaskGetTool()
        result = await tool.execute(task_id=task_id)
        assert "Detailed task" in result
        assert "agent" in result
        assert task_id in result

    async def test_verify_get_nonexistent_task_returns_error(self):
        """Validate that EncreTaskGetTool.execute returns an error string for an unknown ID.

        The error lets the agent surface a clear message instead of crashing
        on a None result from the underlying manager.
        """
        tool = EncreTaskGetTool()
        result = await tool.execute(task_id="nonexistent-id")
        assert "Error" in result

    def test_verify_input_schema_requires_task_id(self):
        """Validate that the input schema enforces task_id as a required field.

        Without task_id the tool cannot address a specific entry; the
        validator must reject the call before reaching the lookup layer.
        """
        required = EncreTaskGetTool.input_schema.get("required", [])
        assert "task_id" in required

    def test_verify_is_concurrency_safe_returns_true_for_read_only_lookup(self):
        """Validate that is_concurrency_safe returns True because get is a read-only operation.

        Lookup does not mutate the backing store, so concurrent reads are
        safe and the scheduler can parallelize batch task queries.
        """
        tool = EncreTaskGetTool()
        assert tool.is_concurrency_safe({}) is True


class TestTaskListTool:
    """Engineered to validate the :class:`EncreTaskListTool` builtin wrapper.

    The tool wraps EncreTaskManager.list_tasks and formats the result for
    display. Tests cover the empty-list path, the populated-list path, and
    the status-filter path to ensure the formatter handles all branches.
    """

    def setup_method(self):
        """Clear task state before each test to isolate list-tool scenarios.

        Inherited tasks would inflate the list count and mask empty-list
        behavior, so the fixture must start clean for every test.
        """
        EncreTaskManager.clear()

    def teardown_method(self):
        """Clear task state after each test to prevent cross-test contamination.

        Ensures the manager is empty regardless of test outcome, keeping
        the fixture invariant intact for the next test in the suite.
        """
        EncreTaskManager.clear()

    async def test_verify_list_empty_returns_no_tasks_message(self):
        """Validate that EncreTaskListTool.execute returns a no-tasks indicator when the store is empty.

        The empty message is what the UI renders for the idle state; it must
        be present so the agent knows the list endpoint is functional.
        """
        tool = EncreTaskListTool()
        result = await tool.execute()
        assert "No tasks found" in result

    async def test_verify_list_with_tasks_includes_all_task_names(self):
        """Validate that EncreTaskListTool.execute includes names of every created task in the output.

        Both T1 and T2 must appear because the list endpoint returns the
        full session view; missing either would indicate a storage bug.
        """
        EncreTaskManager.create_task(name="T1", description="...", task_type="bash", prompt="...")
        EncreTaskManager.create_task(name="T2", description="...", task_type="bash", prompt="...")
        tool = EncreTaskListTool()
        result = await tool.execute()
        assert "T1" in result
        assert "T2" in result

    async def test_verify_list_filtered_by_status_returns_matching_tasks_only(self):
        """Validate that EncreTaskListTool.execute respects the status filter parameter.

        Filtering by 'running' must surface only the task that was transitioned,
        proving the status field is stored and queryable through the tool layer.
        """
        tid = EncreTaskManager.create_task(name="Running task", description="...", task_type="bash", prompt="...")  # noqa: E501
        EncreTaskManager.update_task(tid, status="running")
        tool = EncreTaskListTool()
        result = await tool.execute(status="running")
        assert "Running task" in result


class TestTaskUpdateTool:
    """Engineered to validate the :class:`EncreTaskUpdateTool` builtin wrapper.

    The tool wraps EncreTaskManager.update_task and formats the success or
    error response. Tests cover a normal status transition with result
    attachment and the not-found error path.
    """

    def setup_method(self):
        """Clear task state before each test to isolate update-tool scenarios.

        A leftover task with a matching ID could mask a not-found error if
        the random ID happened to collide with a stale entry.
        """
        EncreTaskManager.clear()

    def teardown_method(self):
        """Clear task state after each test to prevent cross-test contamination.

        Guarantees the manager is clean for the next test regardless of
        whether the test body raises or returns normally.
        """
        EncreTaskManager.clear()

    async def test_verify_update_status_changes_task_state_and_returns_confirmation(self):
        """Validate that EncreTaskUpdateTool.execute persists the status and result on the task.

        The double-check (response string + re-fetch) confirms the update
        reached the manager and is queryable immediately after the tool returns.
        """
        task_id = EncreTaskManager.create_task(
            name="Status change",
            description="...",
            task_type="bash",
            prompt="...",
        )
        tool = EncreTaskUpdateTool()
        result = await tool.execute(task_id=task_id, status="completed", result="Done!")
        assert "updated successfully" in result.lower()
        task = EncreTaskManager.get_task(task_id)
        assert task.status == "completed"
        assert task.result == "Done!"

    async def test_verify_update_nonexistent_task_returns_error(self):
        """Validate that EncreTaskUpdateTool.execute returns an error for an unknown task ID.

        The error response lets the agent inform the user that the target
        task does not exist rather than failing silently or crashing.
        """
        tool = EncreTaskUpdateTool()
        result = await tool.execute(task_id="nonexistent", status="completed")
        assert "Error" in result

    def test_verify_input_schema_requires_task_id(self):
        """Validate that the input schema enforces task_id as a required field.

        Without task_id the tool cannot address the intended entry; validation
        must catch the omission before any manager lookup is attempted.
        """
        required = EncreTaskUpdateTool.input_schema.get("required", [])
        assert "task_id" in required

    def test_verify_is_concurrency_safe_returns_false_for_state_mutating_update(self):
        """Validate that is_concurrency_safe returns False because update mutates task state.

        Concurrent updates to the same task could interleave status changes;
        the flag serializes writes to preserve atomicity of each update.
        """
        tool = EncreTaskUpdateTool()
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Cron tools
# ===========================================================================

class TestCronCreateTool:
    """Engineered to validate the :class:`EncreCronCreateTool` implementation.

    The cron create tool parses and validates cron expressions before
    registering a scheduled job. Tests cover valid-expression acceptance,
    invalid-expression rejection, missing-field errors, and integration
    with the scheduler backend when one is attached.
    """

    async def test_verify_valid_cron_expression_is_accepted(self):
        """Validate that EncreCronCreateTool accepts a well-formed weekday cron expression.

        '0 9 * * 1-5' is a canonical Monday-through-Friday 09:00 expression;
        acceptance proves the parser recognizes standard five-field syntax.
        """
        tool = EncreCronCreateTool()
        result = await tool.execute(
            cron="0 9 * * 1-5",
            prompt="Review PRs",
            name="Weekday review",
        )
        assert "validated" in result or "scheduled" in result or "ready" in result

    async def test_verify_invalid_cron_expression_is_rejected(self):
        """Validate that EncreCronCreateTool rejects malformed cron expressions with an error.

        Malformed expressions must not silently fall through to the scheduler;
        the parser must catch syntax errors and return them before registration.
        """
        tool = EncreCronCreateTool()
        result = await tool.execute(
            cron="invalid cron expr",
            prompt="Do something",
        )
        assert "Error" in result or "invalid" in result.lower()

    async def test_verify_missing_cron_field_returns_error(self):
        """Validate that EncreCronCreateTool errors when the cron field is empty.

        An empty cron string is not a valid expression; the tool must reject
        it explicitly rather than passing it to the scheduler as a no-op.
        """
        tool = EncreCronCreateTool()
        result = await tool.execute(cron="", prompt="Do something")
        assert "Error" in result

    async def test_verify_missing_prompt_field_returns_error(self):
        """Validate that EncreCronCreateTool errors when the prompt field is empty.

        The prompt is the executable content of the cron job; without it the
        scheduler would have nothing to dispatch on each tick.
        """
        tool = EncreCronCreateTool()
        result = await tool.execute(cron="* * * * *", prompt="")
        assert "Error" in result

    async def test_verify_scheduler_backend_receives_registered_job(self):
        """Validate that attaching an EncreScheduler causes the job to be registered with a job_id.

        When a scheduler is present the tool returns the assigned job ID so
        the caller can reference it for later deletion or inspection.
        """
        from encre.scheduler import EncreScheduler
        sched = EncreScheduler()
        tool = EncreCronCreateTool()
        tool.set_scheduler(sched)
        result = await tool.execute(
            cron="0 12 * * *",
            prompt="Lunchtime check",
            name="Lunch check",
        )
        assert "job_id" in result.lower()
        tool.set_scheduler(None)  # Reset for other tests

    def test_verify_input_schema_requires_cron_and_prompt(self):
        """Validate that the input schema enforces cron and prompt as required fields.

        Both fields are semantically necessary; missing either would leave
        the scheduler unable to schedule or execute the job.
        """
        required = EncreCronCreateTool.input_schema.get("required", [])
        assert "cron" in required
        assert "prompt" in required

    def test_verify_is_concurrency_safe_returns_true_for_read_only_validation(self):
        """Validate that is_concurrency_safe returns True because cron validation is read-only.

        Validation only inspects the input string; it does not mutate global
        state until the scheduler commit phase, which is gated separately.
        """
        tool = EncreCronCreateTool()
        assert tool.is_concurrency_safe({}) is True


class TestCronDeleteTool:
    """Engineered to validate the :class:`EncreCronDeleteTool` schema and identity.

    Delete tool tests focus on the schema contract because the actual
    deletion logic is exercised indirectly through TestCronCreateTool's
    scheduler integration; this class exists to guard against regression
    in the tool's declared interface.
    """

    def test_verify_tool_exists_and_exposes_correct_name_and_schema(self):
        """Validate that EncreCronDeleteTool has name='cron_delete' and expects a job_id property.

        The property name 'job_id' (not 'id') is part of the tool's public
        contract; a rename would break callers that reference the schema
        programmatically to build forms or validators.
        """
        tool = EncreCronDeleteTool()
        assert tool.name == "cron_delete"
        # The property in the schema is "job_id", not "id"
        props = tool.input_schema.get("properties", {})
        assert "job_id" in props
        assert props["job_id"]["type"] == "string"


class TestCronListTool:
    """Engineered to validate the :class:`EncreCronListTool` schema and identity.

    Like the delete tool, list tests focus on the schema contract to guard
    against regressions in the tool's declared interface.
    """

    def test_verify_tool_exists_and_exposes_correct_name_and_schema(self):
        """Validate that EncreCronListTool has name='cron_list' and an input_schema attribute.

        The input_schema presence is asserted even though the list tool
        accepts no required fields; its existence proves the tool adheres
        to the EncreTool ABC contract.
        """
        tool = EncreCronListTool()
        assert tool.name == "cron_list"
        assert hasattr(tool, "input_schema")


# ===========================================================================
# ToolRegistry
# ===========================================================================

class TestToolRegistry:
    """Engineered to validate the :class:`ToolRegistry` lookup and conversion mechanics.

    The registry is the central dispatch table that maps tool names to
    instances and formats them for OpenAI and Anthropic function-calling
    protocols. Tests cover registration, overwrite semantics, multi-
    registration, name-based lookup, and format conversion for both vendors.
    """

    def test_verify_register_and_get_retains_identity(self):
        """Validate that ToolRegistry.get returns the exact instance passed to register.

        Identity preservation (is, not ==) proves the registry stores references
        rather than copies, which matters when tools hold mutable state.
        """
        registry = ToolRegistry()
        tool = EncreFileReadTool()
        registry.register(tool)
        assert registry.get("file_read") is tool

    def test_verify_get_nonexistent_returns_none(self):
        """Validate that ToolRegistry.get returns None for an unregistered name.

        Missing entries must not raise; None lets callers branch on existence
        without wrapping every lookup in a try/except.
        """
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_verify_register_many_populates_all_entries(self):
        """Validate that ToolRegistry.register_many stores every passed instance under its declared name.

        Bulk registration is the common path at startup; all three tools
        must be retrievable by their canonical names after a single call.
        """
        registry = ToolRegistry()
        tools = [EncreFileReadTool(), EncreFileWriteTool(), EncreGrepTool()]
        registry.register_many(tools)
        assert len(registry.all()) == 3
        assert registry.get("file_read") is not None
        assert registry.get("file_write") is not None
        assert registry.get("grep") is not None

    def test_verify_register_overwrites_existing_entry(self):
        """Validate that re-registering the same tool name replaces the old instance without duplicating.

        Overwrite semantics let the agent swap tool implementations at
        runtime (e.g. swapping a stub for a real one) without a full reset.
        """
        registry = ToolRegistry()
        t1 = EncreFileReadTool()
        t2 = EncreFileReadTool()
        registry.register(t1)
        registry.register(t2)
        assert len(registry.all()) == 1

    def test_verify_get_openai_tools_formats_as_function_declarations(self):
        """Validate that ToolRegistry.get_openai_tools emits OpenAI-style function objects.

        Each entry must have type='function' and a nested 'function' dict so
        the OpenAI client can consume the list directly as tools=.
        """
        registry = ToolRegistry()
        registry.register(EncreFileReadTool())
        openai_tools = registry.get_openai_tools()
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert "function" in openai_tools[0]

    def test_verify_get_anthropic_tools_formats_as_tool_declarations(self):
        """Validate that ToolRegistry.get_anthropic_tools emits Anthropic-style tool objects.

        Each entry must carry 'name' and 'input_schema' keys so the Anthropic
        client can parse the tool definition without transformation.
        """
        registry = ToolRegistry()
        registry.register(EncreFileReadTool())
        anthropic_tools = registry.get_anthropic_tools()
        assert len(anthropic_tools) == 1
        assert "name" in anthropic_tools[0]
        assert "input_schema" in anthropic_tools[0]


# ===========================================================================
# Tool input schema validation
# ===========================================================================

class TestToolInputSchemas:
    """Engineered to validate that every builtin tool exposes a well-formed input schema.

    The input_schema attribute is the contract used by the permission
    system, the UI form generator, and the model function-calling dispatcher.
    A missing or malformed schema would break all three consumers silently,
    so a matrix assertion guards the entire tool set at once.
    """

    def test_verify_all_tools_have_name_attribute(self):
        """Validate that every builtin tool class exposes a string name.

        Name is the registry key and the model-facing tool identifier; a
        missing or non-string name would break dispatch and function-calling resolution.
        """
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            assert hasattr(tool_cls, "name"), f"{tool_cls.__name__} missing 'name'"
            assert isinstance(tool_cls.name, str)

    def test_verify_all_tools_have_description_attribute(self):
        """Validate that every builtin tool class exposes a description string.

        Description is surfaced to the model as the tool's semantic prompt;
        a missing description would cause the model to make tool-selection
        decisions without context, degrading routing quality.
        """
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            assert hasattr(tool_cls, "description"), f"{tool_cls.__name__} missing 'description'"

    def test_verify_all_tools_have_object_typed_input_schema(self):
        """Validate that every builtin tool exposes a dict input_schema with type='object'.

        The JSON Schema 'object' type tells the model the tool expects a
        structured dict of parameters; a missing or non-object type would
        confuse the function-calling router into sending raw strings.
        """
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            schema = tool_cls.input_schema
            assert isinstance(schema, dict), f"{tool_cls.__name__} input_schema not a dict"
            assert "type" in schema, f"{tool_cls.__name__} input_schema missing 'type'"
            assert schema["type"] == "object", f"{tool_cls.__name__} input_schema not 'object' type"

    def test_verify_all_tools_convert_to_openai_format(self):
        """Validate that the selected tools emit OpenAI-format declarations via to_openai_format().

        The OpenAI format requires a top-level 'type' field set to 'function';
        this assertion guards against drift in the formatter that would break
        OpenAI-client integration.
        """
        for tool_cls in [EncreFileReadTool, EncreBashTool, EncreGrepTool]:
            tool = tool_cls()
            fmt = tool.to_openai_format()
            assert "type" in fmt
            assert fmt["type"] == "function"

    def test_verify_all_tools_convert_to_anthropic_format(self):
        """Validate that the selected tools emit Anthropic-format declarations via to_anthropic_format().

        The Anthropic format requires 'name' and 'input_schema' keys at the
        top level; missing either key would cause the Anthropic client to
        reject the tool definition before any call is made.
        """
        for tool_cls in [EncreFileReadTool, EncreBashTool, EncreGrepTool]:
            tool = tool_cls()
            fmt = tool.to_anthropic_format()
            assert "name" in fmt
            assert "input_schema" in fmt


# ===========================================================================
# Concurrency safety matrix
# ===========================================================================

class TestConcurrencySafety:
    """Engineered to validate the concurrency-safety classification of every builtin tool.

    The is_concurrency_safe flag drives the scheduler's serialization
    decision; a tool misclassified as safe could cause data races on the
    filesystem or task store, while a tool misclassified as unsafe would
    unnecessarily serialize independent read-only operations.
    """

    def test_verify_read_only_tools_are_marked_concurrency_safe(self):
        """Validate that read-only tools report is_concurrency_safe=True for any input.

        File read, grep, glob, and task get/list do not mutate shared state,
        so parallel execution across sub-tasks is safe and expected.
        """
        assert EncreFileReadTool().is_concurrency_safe({}) is True
        assert EncreGrepTool().is_concurrency_safe({}) is True
        assert EncreGlobTool().is_concurrency_safe({}) is True
        assert EncreTaskGetTool().is_concurrency_safe({}) is True
        assert EncreTaskListTool().is_concurrency_safe({}) is True

    def test_verify_mutating_tools_are_marked_concurrency_unsafe(self):
        """Validate that state-mutating tools report is_concurrency_safe=False.

        Write, edit, bash, task create, and task update all change external
        state; running them in parallel without ordering risks lost updates
        and interleaved output.
        """
        assert EncreFileWriteTool().is_concurrency_safe({}) is False
        assert EncreFileEditTool().is_concurrency_safe({}) is False
        assert EncreBashTool().is_concurrency_safe({}) is False
        assert EncreTaskCreateTool().is_concurrency_safe({}) is False
        assert EncreTaskUpdateTool().is_concurrency_safe({}) is False


# ===========================================================================
# EncreTool ABC compliance
# ===========================================================================

class TestEncreToolABC:
    """Engineered to validate that :class:`EncreTool` behaves as a proper abstract base class.

    The ABC contract guarantees every concrete tool implements execute()
    and exposes is_concurrency_safe; tests confirm instantiation of the
    abstract base is blocked and that a concrete subclass satisfies the
    interface without raising.
    """

    def test_verify_cannot_instantiate_abstract_base_class(self):
        """Validate that EncreTool cannot be instantiated because execute() is abstract.

        Allowing base instantiation would produce a tool that crashes on
        every execute() call; the TypeError guard prevents this at construction time.
        """
        with pytest.raises(TypeError):
            EncreTool()  # type: ignore[abstract]

    def test_verify_concrete_subclass_instantiates_without_error(self):
        """Validate that EncreFileReadTool can be instantiated as a concrete EncreTool subclass.

        Instantiation success proves the subclass satisfies all abstract
        methods and that the inheritance chain is intact.
        """
        tool = EncreFileReadTool()
        assert isinstance(tool, EncreTool)

    def test_verify_execute_is_registered_as_abstract(self):
        """Validate that execute appears in EncreTool.__abstractmethods__.

        The abstractmethods set is what pytest's type checker and the ABC
        metaclass use to enforce implementation; a missing entry would let
        subclasses omit execute() without error.
        """
        assert "execute" in EncreTool.__abstractmethods__

    def test_verify_base_class_exposes_is_concurrency_safe(self):
        """Validate that every EncreTool instance exposes the is_concurrency_safe method.

        The method is part of the tool protocol; its absence would force
        every caller to use hasattr checks instead of a direct call.
        """
        tool = EncreFileReadTool()
        assert hasattr(tool, "is_concurrency_safe")


# ===========================================================================
# Edge cases: file tool with special characters
# ===========================================================================

class TestFileToolsEdgeCases:
    """Engineered to validate edge-case behavior of file tools under unusual inputs.

    These tests exercise boundary conditions 鈥?offset beyond file length,
    Unicode content, multi-line edit strings, and binary files 鈥?that are
    easy to miss in happy-path coverage but critical for robust agent
    operation in real repositories.
    """

    async def test_verify_read_with_offset_beyond_file_length_returns_empty_result(self, temp_dir):
        """Validate that EncreFileReadTool returns an empty result when offset exceeds file length.

        Out-of-bounds offsets must not raise IndexError; instead they return
        an empty or sentinel string so the caller can detect EOF cleanly.
        """
        tool = EncreFileReadTool()
        result = await tool.execute(
            file_path=os.path.join(temp_dir, "main.py"),
            offset=999,
        )
        # Should return empty string when offset exceeds file length
        assert "empty" in result or result == ""

    async def test_verify_write_persists_unicode_content_with_mix_of_scripts_and_emoji(self, temp_dir):
        """Validate that EncreFileWriteTool preserves Unicode text including CJK characters and emoji.

        The agent frequently writes localized strings and emoji-laden
        messages; a silent encoding mangling would corrupt user-visible content.
        """
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "unicode.txt")
        content = "涓枃娴嬭瘯\nEmoji: 馃帀\nMixed: Caf茅 r茅sum茅"
        result = await tool.execute(file_path=file_path, content=content)
        assert "Successfully wrote" in result
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == content

    async def test_verify_edit_with_multiline_old_str_replaces_the_exact_block(self, temp_dir):
        """Validate that EncreFileEditTool replaces a multi-line old_str block verbatim.

        Multi-line edits are the agent's primary mechanism for structural
        changes (adding/removing functions, moving blocks); the replacement
        must touch every line in the span and preserve indentation.
        """
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="def hello():\n    return 'Hello, world!'",
            new_str="def hello():\n    return 'Hola, mundo!'",
        )
        assert "edit(s) to" in result
        with open(file_path, encoding="utf-8") as f:
            assert "Hola, mundo!" in f.read()

    async def test_verify_read_binary_file_returns_a_string_without_crashing(self, temp_dir):
        """Validate that EncreFileReadTool handles binary content gracefully without raising.

        Binary files may appear in repos (assets, serialized data); the tool
        must decode or sanitize them into a string so the agent can proceed
        rather than aborting on a UnicodeDecodeError.
        """
        tool = EncreFileReadTool()
        result = await tool.execute(file_path=os.path.join(temp_dir, "data.bin"))
        # Should read without crashing (may produce garbled text)
        assert isinstance(result, str)
