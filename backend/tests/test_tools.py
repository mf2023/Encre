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
    """Test cases covering file read tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreFileReadTool`."""

    async def test_read_existing_file(self, temp_dir):
        """Verifies that read existing file."""
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "README.md")
        result = await tool.execute(file_path=file_path)
        # Confirm the expected result for this scenario: read existing file.
        assert "# Test Project" in result

    async def test_read_nonexistent_file(self, temp_dir):
        """Verifies that read nonexistent file."""
        tool = EncreFileReadTool()
        result = await tool.execute(file_path=os.path.join(temp_dir, "nonexistent.txt"))
        # Confirm the expected result for this scenario: read nonexistent file.
        assert "Error" in result

    async def test_read_with_offset(self, temp_dir):
        """Verifies that read with offset."""
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(file_path=file_path, offset=3)
        # Should return content starting from line 3
        # Confirm the expected result for this scenario: read with offset.
        assert isinstance(result, str)

    async def test_read_with_limit(self, temp_dir):
        """Verifies that read with limit."""
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(file_path=file_path, limit=1)
        lines = result.strip().split("\n")
        # Confirm the expected result for this scenario: read with limit.
        assert len(lines) <= 2  # may include trailing newline

    async def test_read_empty_file(self, temp_dir):
        """Verifies that read empty file."""
        tool = EncreFileReadTool()
        file_path = os.path.join(temp_dir, "empty.txt")
        result = await tool.execute(file_path=file_path)
        # Confirm the expected result for this scenario: read empty file.
        assert result == ""

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        # Confirm the expected result for this scenario: input schema required.
        assert "file_path" in EncreFileReadTool.input_schema.get("required", [])

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({"file_path": "/somewhere"}) is True


# ===========================================================================
# File write tool
# ===========================================================================

class TestFileWriteTool:
    """Test cases covering file write tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreFileWriteTool`."""

    async def test_write_new_file(self, temp_dir):
        """Verifies that write new file."""
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "new_file.txt")
        result = await tool.execute(file_path=file_path, content="Hello, write!")
        # Confirm the expected result for this scenario: write new file.
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "Hello, write!"

    async def test_write_overwrites_existing(self, temp_dir):
        """Verifies that write overwrites existing."""
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "README.md")
        result = await tool.execute(file_path=file_path, content="Overwritten")
        # Confirm the expected result for this scenario: write overwrites existing.
        assert "Successfully wrote" in result
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "Overwritten"

    async def test_write_creates_parent_dirs(self, temp_dir):
        """Verifies that write creates parent dirs."""
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "nested", "deep", "file.txt")
        result = await tool.execute(file_path=file_path, content="Deep content")
        # Confirm the expected result for this scenario: write creates parent dirs.
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreFileWriteTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "file_path" in required
        assert "content" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreFileWriteTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# File edit tool
# ===========================================================================

class TestFileEditTool:
    """Test cases covering file edit tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreFileEditTool`."""

    async def test_edit_existing_file(self, temp_dir):
        """Verifies that edit existing file."""
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="def hello():",
            new_str="def greeting():",
        )
        # Confirm the expected result for this scenario: edit existing file.
        assert "Edit applied successfully" in result
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        assert "def greeting():" in content
        assert "def hello():" not in content

    async def test_edit_non_unique_match(self, temp_dir):
        """Verifies that edit non unique match."""
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="\n",
            new_str="\n\n",
        )
        # Confirm the expected result for this scenario: edit non unique match.
        assert "Found" in result
        assert "occurrences" in result

    async def test_edit_no_match(self, temp_dir):
        """Verifies that edit no match."""
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="this string does not exist in file",
            new_str="nothing",
        )
        # Confirm the expected result for this scenario: edit no match.
        assert "Error" in result

    async def test_edit_nonexistent_file(self, temp_dir):
        """Verifies that edit nonexistent file."""
        tool = EncreFileEditTool()
        result = await tool.execute(
            file_path=os.path.join(temp_dir, "not_here.txt"),
            old_str="x",
            new_str="y",
        )
        # Confirm the expected result for this scenario: edit nonexistent file.
        assert "Error" in result

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreFileEditTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "file_path" in required
        assert "old_str" in required
        assert "new_str" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreFileEditTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Grep tool
# ===========================================================================

class TestGrepTool:
    """Test cases covering grep tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreGrepTool`."""

    async def test_grep_finds_string(self, temp_dir):
        """Verifies that grep finds string."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def hello", path=temp_dir)
        # Confirm the expected result for this scenario: grep finds string.
        assert "def hello" in result

    async def test_grep_no_match(self, temp_dir):
        """Verifies that grep no match."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="FOOBARBAZQUX", path=temp_dir)
        # Confirm the expected result for this scenario: grep no match.
        assert "no matches" in result.lower()

    async def test_grep_case_insensitive(self, temp_dir):
        """Verifies that grep case insensitive."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="DEF HELLO", path=temp_dir, **{"-i": True})
        # Confirm the expected result for this scenario: grep case insensitive.
        assert "def hello" in result

    async def test_grep_files_with_matches_mode(self, temp_dir):
        """Verifies that grep files with matches mode."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, output_mode="files_with_matches")
        # Confirm the expected result for this scenario: grep files with matches mode.
        assert "main.py" in result or "utils.py" in result

    async def test_grep_count_mode(self, temp_dir):
        """Verifies that grep count mode."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, output_mode="count")
        # Confirm the expected result for this scenario: grep count mode.
        assert "main.py" in result and ":1" in result or "utils.py" in result and ":2" in result
        assert ":1" in result or ":2" in result

    async def test_grep_with_glob_filter(self, temp_dir):
        """Verifies that grep with glob filter."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="def", path=temp_dir, glob="*.py")
        # Confirm the expected result for this scenario: grep with glob filter.
        assert "main.py" in result or "utils.py" in result
        assert "README.md" not in result

    async def test_grep_invalid_regex(self, temp_dir):
        """Verifies that grep invalid regex."""
        tool = EncreGrepTool()
        result = await tool.execute(pattern="[invalid", path=temp_dir)
        # Confirm the expected result for this scenario: grep invalid regex.
        assert "Error" in result

    async def test_grep_specific_file(self, temp_dir):
        """Verifies that grep specific file."""
        tool = EncreGrepTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(pattern="hello", path=file_path)
        # Confirm the expected result for this scenario: grep specific file.
        assert "def hello" in result

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreGrepTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "pattern" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreGrepTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is True


# ===========================================================================
# Glob tool
# ===========================================================================

class TestGlobTool:
    """Test cases covering glob tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreGlobTool`."""

    async def test_glob_py_files_root(self, temp_dir):
        """Verifies that glob py files root."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.py", path=temp_dir)
        # Confirm the expected result for this scenario: glob py files root.
        assert "main.py" in result

    async def test_glob_py_files_nested(self, temp_dir):
        """Verifies that glob py files nested."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*/*.py", path=temp_dir)
        # Confirm the expected result for this scenario: glob py files nested.
        assert "utils.py" in result

    async def test_glob_md_files(self, temp_dir):
        """Verifies that glob md files."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.md", path=temp_dir)
        # Confirm the expected result for this scenario: glob md files.
        assert "README.md" in result

    async def test_glob_json_files(self, temp_dir):
        """Verifies that glob json files."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="**/*.json", path=temp_dir)
        # Confirm the expected result for this scenario: glob json files.
        assert "config.json" in result

    async def test_glob_no_match(self, temp_dir):
        """Verifies that glob no match."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="*.xyzzy", path=temp_dir)
        # Confirm the expected result for this scenario: glob no match.
        assert "No files match pattern" in result

    async def test_glob_default_path(self, temp_dir):
        """Verifies that glob default path."""
        tool = EncreGlobTool()
        result = await tool.execute(pattern="main.py")
        # Confirm the expected result for this scenario: glob default path.
        assert "main.py" in result

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreGlobTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "pattern" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreGlobTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is True


# ===========================================================================
# Bash tool (safe commands only)
# ===========================================================================

class TestBashTool:
    """Test cases covering bash tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreBashTool` with safe commands."""

    async def test_bash_echo(self):
        """Verifies that bash echo."""
        tool = EncreBashTool()
        result = await tool.execute(command="echo hello world")
        # Confirm the expected result for this scenario: bash echo.
        assert "hello world" in result

    async def test_bash_pwd(self):
        """Verifies that bash pwd."""
        tool = EncreBashTool()
        result = await tool.execute(command="pwd")
        # Confirm the expected result for this scenario: bash pwd.
        assert result.strip() != ""

    async def test_bash_with_cwd(self, temp_dir):
        """Verifies that bash with cwd."""
        tool = EncreBashTool()
        result = await tool.execute(command="pwd", cwd=temp_dir)
        # On Windows, bash may translate paths (e.g. C:\Users\...\Temp\... -> /tmp/...).
        # We verify pwd ran successfully by checking the output is a non-empty path.
        result = result.strip()
        # Confirm the expected result for this scenario: bash with cwd.
        assert len(result) > 0
        assert "Error" not in result
        # The returned path should be absolute (start with / or drive letter)
        assert result.startswith("/") or ":" in result

    async def test_bash_command_not_found(self):
        """Verifies that bash command not found."""
        tool = EncreBashTool()
        result = await tool.execute(command="nonexistentcommandxyz123")
        # Confirm the expected result for this scenario: bash command not found.
        assert "Error" in result or "not found" in result.lower() or result.strip() != ""

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreBashTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "command" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreBashTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Task manager CRUD
# ===========================================================================

class TestTaskManagerCRUD:
    """Test cases covering task manager c r u d.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreTaskManager` operations."""

    def setup_method(self):
        """Verifies that setup method."""
        EncreTaskManager.clear()

    def teardown_method(self):
        """Verifies that teardown method."""
        EncreTaskManager.clear()

    def test_create_task(self):
        """Verifies that create task."""
        task_id = EncreTaskManager.create_task(
            name="Test task",
            description="A test",
            task_type="bash",
            prompt="echo hello",
        )
        # Confirm the expected result for this scenario: create task.
        assert task_id is not None
        assert len(task_id) > 0

    def test_get_task(self):
        """Verifies that get task."""
        task_id = EncreTaskManager.create_task(
            name="Get me",
            description="Test retrieval",
            task_type="agent",
            prompt="Do something",
        )
        task = EncreTaskManager.get_task(task_id)
        # Confirm the expected result for this scenario: get task.
        assert task is not None
        assert task.name == "Get me"
        assert task.task_type == "agent"

    def test_get_nonexistent_task(self):
        """Verifies that get nonexistent task."""
        # Confirm the expected result for this scenario: get nonexistent task.
        assert EncreTaskManager.get_task("nonexistent") is None

    def test_update_task_status(self):
        """Verifies that update task status."""
        task_id = EncreTaskManager.create_task(
            name="Update me",
            description="Status change test",
            task_type="bash",
            prompt="run",
        )
        result = EncreTaskManager.update_task(task_id, status="running")
        # Confirm the expected result for this scenario: update task status.
        assert result is True
        task = EncreTaskManager.get_task(task_id)
        assert task.status == "running"

    def test_update_task_with_result(self):
        """Verifies that update task with result."""
        task_id = EncreTaskManager.create_task(
            name="Result test",
            description="Set result",
            task_type="bash",
            prompt="run",
        )
        EncreTaskManager.update_task(task_id, status="completed", result="Success!")
        task = EncreTaskManager.get_task(task_id)
        # Confirm the expected result for this scenario: update task with result.
        assert task.status == "completed"
        assert task.result == "Success!"

    def test_update_nonexistent_task(self):
        """Verifies that update nonexistent task."""
        # Confirm the expected result for this scenario: update nonexistent task.
        assert EncreTaskManager.update_task("nonexistent", status="completed") is False

    def test_list_tasks_all(self):
        """Verifies that list tasks all."""
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
        # Confirm the expected result for this scenario: list tasks all.
        assert len(tasks) == 3

    def test_list_tasks_filter_by_status(self):
        """Verifies that list tasks filter by status."""
        EncreTaskManager.create_task(name="Pending", description="...", task_type="bash", prompt="...")  # noqa: E501
        tid2 = EncreTaskManager.create_task(name="Running", description="...", task_type="bash", prompt="...")  # noqa: E501
        EncreTaskManager.update_task(tid2, status="running")

        pending = EncreTaskManager.list_tasks(status="pending")
        running = EncreTaskManager.list_tasks(status="running")
        # Confirm the expected result for this scenario: list tasks filter by status.
        assert len(pending) >= 1
        assert len(running) >= 1

    def test_delete_task(self):
        """Verifies that delete task."""
        task_id = EncreTaskManager.create_task(name="Delete me", description="...", task_type="bash", prompt="...")  # noqa: E501
        # Confirm the expected result for this scenario: delete task.
        assert EncreTaskManager.delete_task(task_id) is True
        assert EncreTaskManager.get_task(task_id) is None

    def test_delete_nonexistent_task(self):
        """Verifies that delete nonexistent task."""
        # Confirm the expected result for this scenario: delete nonexistent task.
        assert EncreTaskManager.delete_task("nonexistent") is False


# ===========================================================================
# Task tools (builtins)
# ===========================================================================

class TestTaskCreateTool:
    """Test cases covering task create tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreTaskCreateTool`."""

    def setup_method(self):
        """Verifies that setup method."""
        EncreTaskManager.clear()

    def teardown_method(self):
        """Verifies that teardown method."""
        EncreTaskManager.clear()

    async def test_create_task_via_tool(self):
        """Verifies that create task via tool."""
        tool = EncreTaskCreateTool()
        result = await tool.execute(
            name="My sub-task",
            description="Do the thing",
            task_type="bash",
            prompt="echo done",
        )
        # Confirm the expected result for this scenario: create task via tool.
        assert "Task created:" in result
        task_id = result.split("Task created:")[1].strip()
        assert EncreTaskManager.get_task(task_id) is not None

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreTaskCreateTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "name" in required
        assert "task_type" in required
        assert "prompt" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreTaskCreateTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


class TestTaskGetTool:
    """Test cases covering task get tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreTaskGetTool`."""

    def setup_method(self):
        """Verifies that setup method."""
        EncreTaskManager.clear()

    def teardown_method(self):
        """Verifies that teardown method."""
        EncreTaskManager.clear()

    async def test_get_existing_task(self):
        """Verifies that get existing task."""
        task_id = EncreTaskManager.create_task(
            name="Detailed task",
            description="Check details",
            task_type="agent",
            prompt="Review code",
        )
        tool = EncreTaskGetTool()
        result = await tool.execute(task_id=task_id)
        # Confirm the expected result for this scenario: get existing task.
        assert "Detailed task" in result
        assert "agent" in result
        assert task_id in result

    async def test_get_nonexistent_task(self):
        """Verifies that get nonexistent task."""
        tool = EncreTaskGetTool()
        result = await tool.execute(task_id="nonexistent-id")
        # Confirm the expected result for this scenario: get nonexistent task.
        assert "Error" in result

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreTaskGetTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "task_id" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreTaskGetTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is True


class TestTaskListTool:
    """Test cases covering task list tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreTaskListTool`."""

    def setup_method(self):
        """Verifies that setup method."""
        EncreTaskManager.clear()

    def teardown_method(self):
        """Verifies that teardown method."""
        EncreTaskManager.clear()

    async def test_list_empty(self):
        """Verifies that list empty."""
        tool = EncreTaskListTool()
        result = await tool.execute()
        # Confirm the expected result for this scenario: list empty.
        assert "No tasks found" in result

    async def test_list_with_tasks(self):
        """Verifies that list with tasks."""
        EncreTaskManager.create_task(name="T1", description="...", task_type="bash", prompt="...")
        EncreTaskManager.create_task(name="T2", description="...", task_type="bash", prompt="...")
        tool = EncreTaskListTool()
        result = await tool.execute()
        # Confirm the expected result for this scenario: list with tasks.
        assert "T1" in result
        assert "T2" in result

    async def test_list_filtered(self):
        """Verifies that list filtered."""
        tid = EncreTaskManager.create_task(name="Running task", description="...", task_type="bash", prompt="...")  # noqa: E501
        EncreTaskManager.update_task(tid, status="running")
        tool = EncreTaskListTool()
        result = await tool.execute(status="running")
        # Confirm the expected result for this scenario: list filtered.
        assert "Running task" in result


class TestTaskUpdateTool:
    """Test cases covering task update tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreTaskUpdateTool`."""

    def setup_method(self):
        """Verifies that setup method."""
        EncreTaskManager.clear()

    def teardown_method(self):
        """Verifies that teardown method."""
        EncreTaskManager.clear()

    async def test_update_status(self):
        """Verifies that update status."""
        task_id = EncreTaskManager.create_task(
            name="Status change",
            description="...",
            task_type="bash",
            prompt="...",
        )
        tool = EncreTaskUpdateTool()
        result = await tool.execute(task_id=task_id, status="completed", result="Done!")
        # Confirm the expected result for this scenario: update status.
        assert "updated successfully" in result.lower()
        task = EncreTaskManager.get_task(task_id)
        assert task.status == "completed"
        assert task.result == "Done!"

    async def test_update_nonexistent(self):
        """Verifies that update nonexistent."""
        tool = EncreTaskUpdateTool()
        result = await tool.execute(task_id="nonexistent", status="completed")
        # Confirm the expected result for this scenario: update nonexistent.
        assert "Error" in result

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreTaskUpdateTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "task_id" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreTaskUpdateTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


# ===========================================================================
# Cron tools
# ===========================================================================

class TestCronCreateTool:
    """Test cases covering cron create tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreCronCreateTool`."""

    async def test_validate_valid_cron(self):
        """Verifies that validate valid cron."""
        tool = EncreCronCreateTool()
        result = await tool.execute(
            cron="0 9 * * 1-5",
            prompt="Review PRs",
            name="Weekday review",
        )
        # Confirm the expected result for this scenario: validate valid cron.
        assert "validated" in result or "scheduled" in result or "ready" in result

    async def test_invalid_cron_rejected(self):
        """Verifies that invalid cron rejected."""
        tool = EncreCronCreateTool()
        result = await tool.execute(
            cron="invalid cron expr",
            prompt="Do something",
        )
        # Confirm the expected result for this scenario: invalid cron rejected.
        assert "Error" in result or "invalid" in result.lower()

    async def test_missing_cron(self):
        """Verifies that missing cron."""
        tool = EncreCronCreateTool()
        result = await tool.execute(cron="", prompt="Do something")
        # Confirm the expected result for this scenario: missing cron.
        assert "Error" in result

    async def test_missing_prompt(self):
        """Verifies that missing prompt."""
        tool = EncreCronCreateTool()
        result = await tool.execute(cron="* * * * *", prompt="")
        # Confirm the expected result for this scenario: missing prompt.
        assert "Error" in result

    async def test_with_scheduler_backend(self):
        """Verifies that with scheduler backend."""
        from encre.scheduler import EncreScheduler
        sched = EncreScheduler()
        tool = EncreCronCreateTool()
        tool.set_scheduler(sched)
        result = await tool.execute(
            cron="0 12 * * *",
            prompt="Lunchtime check",
            name="Lunch check",
        )
        # Confirm the expected result for this scenario: with scheduler backend.
        assert "job_id" in result.lower()
        tool.set_scheduler(None)  # Reset for other tests

    def test_input_schema_required(self):
        """Verifies that input schema required."""
        required = EncreCronCreateTool.input_schema.get("required", [])
        # Confirm the expected result for this scenario: input schema required.
        assert "cron" in required
        assert "prompt" in required

    def test_is_concurrency_safe(self):
        """Verifies that is concurrency safe."""
        tool = EncreCronCreateTool()
        # Confirm the expected result for this scenario: is concurrency safe.
        assert tool.is_concurrency_safe({}) is False


class TestCronDeleteTool:
    """Test cases covering cron delete tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreCronDeleteTool`."""

    def test_tool_exists_and_has_schema(self):
        """Verifies that tool exists and has schema."""
        tool = EncreCronDeleteTool()
        # Confirm the expected result for this scenario: tool exists and has schema.
        assert tool.name == "cron_delete"
        # The property in the schema is "job_id", not "id"
        props = tool.input_schema.get("properties", {})
        assert "job_id" in props
        assert props["job_id"]["type"] == "string"


class TestCronListTool:
    """Test cases covering cron list tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`EncreCronListTool`."""

    def test_tool_exists_and_has_schema(self):
        """Verifies that tool exists and has schema."""
        tool = EncreCronListTool()
        # Confirm the expected result for this scenario: tool exists and has schema.
        assert tool.name == "cron_list"
        assert hasattr(tool, "input_schema")


# ===========================================================================
# ToolRegistry
# ===========================================================================

class TestToolRegistry:
    """Test cases covering tool registry.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test :class:`ToolRegistry`."""

    def test_register_and_get(self):
        """Verifies that register and get."""
        registry = ToolRegistry()
        tool = EncreFileReadTool()
        registry.register(tool)
        # Confirm the expected result for this scenario: register and get.
        assert registry.get("file_read") is tool

    def test_get_nonexistent(self):
        """Verifies that get nonexistent."""
        registry = ToolRegistry()
        # Confirm the expected result for this scenario: get nonexistent.
        assert registry.get("nonexistent") is None

    def test_register_many(self):
        """Verifies that register many."""
        registry = ToolRegistry()
        tools = [EncreFileReadTool(), EncreFileWriteTool(), EncreGrepTool()]
        registry.register_many(tools)
        # Confirm the expected result for this scenario: register many.
        assert len(registry.all()) == 3
        assert registry.get("file_read") is not None
        assert registry.get("file_write") is not None
        assert registry.get("grep") is not None

    def test_register_overwrites(self):
        """Verifies that register overwrites."""
        registry = ToolRegistry()
        t1 = EncreFileReadTool()
        t2 = EncreFileReadTool()
        registry.register(t1)
        registry.register(t2)
        # Confirm the expected result for this scenario: register overwrites.
        assert len(registry.all()) == 1

    def test_get_openai_tools(self):
        """Verifies that get openai tools."""
        registry = ToolRegistry()
        registry.register(EncreFileReadTool())
        openai_tools = registry.get_openai_tools()
        # Confirm the expected result for this scenario: get openai tools.
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert "function" in openai_tools[0]

    def test_get_anthropic_tools(self):
        """Verifies that get anthropic tools."""
        registry = ToolRegistry()
        registry.register(EncreFileReadTool())
        anthropic_tools = registry.get_anthropic_tools()
        # Confirm the expected result for this scenario: get anthropic tools.
        assert len(anthropic_tools) == 1
        assert "name" in anthropic_tools[0]
        assert "input_schema" in anthropic_tools[0]


# ===========================================================================
# Tool input schema validation
# ===========================================================================

class TestToolInputSchemas:
    """Test cases covering tool input schemas.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify every builtin tool has a well-formed input schema."""

    def test_all_tools_have_name(self):
        """Verifies that all tools have name."""
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            # Confirm the expected result for this scenario: all tools have name.
            assert hasattr(tool_cls, "name"), f"{tool_cls.__name__} missing 'name'"
            assert isinstance(tool_cls.name, str)

    def test_all_tools_have_description(self):
        """Verifies that all tools have description."""
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            # Confirm the expected result for this scenario: all tools have description.
            assert hasattr(tool_cls, "description"), f"{tool_cls.__name__} missing 'description'"

    def test_all_tools_have_input_schema(self):
        """Verifies that all tools have input schema."""
        for tool_cls in [
            EncreFileReadTool, EncreFileWriteTool, EncreFileEditTool,
            EncreGrepTool, EncreGlobTool, EncreBashTool,
            EncreTaskCreateTool, EncreTaskGetTool, EncreTaskListTool, EncreTaskUpdateTool,
            EncreCronCreateTool, EncreCronDeleteTool, EncreCronListTool,
        ]:
            schema = tool_cls.input_schema
            # Confirm the expected result for this scenario: all tools have input schema.
            assert isinstance(schema, dict), f"{tool_cls.__name__} input_schema not a dict"
            assert "type" in schema, f"{tool_cls.__name__} input_schema missing 'type'"
            assert schema["type"] == "object", f"{tool_cls.__name__} input_schema not 'object' type"

    def test_all_tools_have_to_openai_format(self):
        """Verifies that all tools have to openai format."""
        for tool_cls in [EncreFileReadTool, EncreBashTool, EncreGrepTool]:
            tool = tool_cls()
            fmt = tool.to_openai_format()
            # Confirm the expected result for this scenario: all tools have to openai format.
            assert "type" in fmt
            assert fmt["type"] == "function"

    def test_all_tools_have_to_anthropic_format(self):
        """Verifies that all tools have to anthropic format."""
        for tool_cls in [EncreFileReadTool, EncreBashTool, EncreGrepTool]:
            tool = tool_cls()
            fmt = tool.to_anthropic_format()
            # Confirm the expected result for this scenario: all tools have to anthropic format.
            assert "name" in fmt
            assert "input_schema" in fmt


# ===========================================================================
# Concurrency safety matrix
# ===========================================================================

class TestConcurrencySafety:
    """Test cases covering concurrency safety.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Verify is_concurrency_safe() returns expected values for each tool."""

    def test_read_only_tools_are_safe(self):
        """Verifies that read only tools are safe."""
        # Confirm the expected result for this scenario: read only tools are safe.
        assert EncreFileReadTool().is_concurrency_safe({}) is True
        assert EncreGrepTool().is_concurrency_safe({}) is True
        assert EncreGlobTool().is_concurrency_safe({}) is True
        assert EncreTaskGetTool().is_concurrency_safe({}) is True
        assert EncreTaskListTool().is_concurrency_safe({}) is True

    def test_write_tools_are_not_safe(self):
        """Verifies that write tools are not safe."""
        # Confirm the expected result for this scenario: write tools are not safe.
        assert EncreFileWriteTool().is_concurrency_safe({}) is False
        assert EncreFileEditTool().is_concurrency_safe({}) is False
        assert EncreBashTool().is_concurrency_safe({}) is False
        assert EncreTaskCreateTool().is_concurrency_safe({}) is False
        assert EncreTaskUpdateTool().is_concurrency_safe({}) is False
        assert EncreCronCreateTool().is_concurrency_safe({}) is False


# ===========================================================================
# EncreTool ABC compliance
# ===========================================================================

class TestEncreToolABC:
    """Test cases covering encre tool a b c.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Test that :class:`EncreTool` ABC is properly defined."""

    def test_cannot_instantiate_abc(self):
        """Verifies that cannot instantiate abc."""
        with pytest.raises(TypeError):
            EncreTool()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        """Verifies that concrete subclass instantiates."""
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: concrete subclass instantiates.
        assert isinstance(tool, EncreTool)

    def test_execute_is_abstract(self):
        """Verifies that execute is abstract."""
        # Confirm the expected result for this scenario: execute is abstract.
        assert "execute" in EncreTool.__abstractmethods__

    def test_base_has_is_concurrency_safe(self):
        """Verifies that base has is concurrency safe."""
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: base has is concurrency safe.
        assert hasattr(tool, "is_concurrency_safe")


# ===========================================================================
# Edge cases: file tool with special characters
# ===========================================================================

class TestFileToolsEdgeCases:
    """Test cases covering file tools edge cases.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Edge-case tests for file tools."""

    async def test_read_with_offset_beyond_length(self, temp_dir):
        """Verifies that read with offset beyond length."""
        tool = EncreFileReadTool()
        result = await tool.execute(
            file_path=os.path.join(temp_dir, "main.py"),
            offset=999,
        )
        # Should return empty string when offset exceeds file length
        # Confirm the expected result for this scenario: read with offset beyond length.
        assert result == ""

    async def test_write_unicode_content(self, temp_dir):
        """Verifies that write unicode content."""
        tool = EncreFileWriteTool()
        file_path = os.path.join(temp_dir, "unicode.txt")
        content = "中文测试\nEmoji: 🎉\nMixed: Café résumé"
        result = await tool.execute(file_path=file_path, content=content)
        # Confirm the expected result for this scenario: write unicode content.
        assert "Successfully wrote" in result
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == content

    async def test_edit_multiline_match(self, temp_dir):
        """Verifies that edit multiline match."""
        tool = EncreFileEditTool()
        file_path = os.path.join(temp_dir, "main.py")
        result = await tool.execute(
            file_path=file_path,
            old_str="def hello():\n    return 'Hello, world!'",
            new_str="def hello():\n    return 'Hola, mundo!'",
        )
        # Confirm the expected result for this scenario: edit multiline match.
        assert "Edit applied successfully" in result
        with open(file_path, encoding="utf-8") as f:
            assert "Hola, mundo!" in f.read()

    async def test_read_binary_file(self, temp_dir):
        """Verifies that read binary file."""
        tool = EncreFileReadTool()
        result = await tool.execute(file_path=os.path.join(temp_dir, "data.bin"))
        # Should read without crashing (may produce garbled text)
        # Confirm the expected result for this scenario: read binary file.
        assert isinstance(result, str)
