#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Built-in evaluation tasks for measuring agent quality.

Each task tests a specific capability: tool calling, file operations,
web search, code editing, multi-turn reasoning, etc.

Add new tasks here and they will be available via ``BUILTIN_TASKS``.
"""

from encre.eval.runner import EvalTask

BUILTIN_TASKS: list[EvalTask] = [
    EvalTask(
        name="file_write_read",
        prompt="Create a file named /tmp/eval_test.txt containing the text "
               "'Hello from Encre eval', then read it back.",
        success_criteria="File /tmp/eval_test.txt exists with expected content",
        expected_output_patterns=["Hello from Encre eval"],
        required_tools=["file_write", "file_read"],
    ),
    EvalTask(
        name="web_search_basic",
        prompt="Search the web for 'Python 3.13 release date' and summarize.",
        success_criteria="Found recent information about Python 3.13",
        required_tools=["web_search"],
        timeout=30,
    ),
    EvalTask(
        name="code_edit_simple",
        prompt="Create a Python file /tmp/hello.py that prints 'hello world', "
               "then change it to print 'hello encre' instead.",
        success_criteria="File was created and edited successfully",
        expected_output_patterns=["hello encre"],
        required_tools=["file_write", "file_edit"],
    ),
    EvalTask(
        name="grep_search",
        prompt="Search for 'def main' in all Python files under current directory. "
               "Return the file paths and line numbers.",
        success_criteria="Found Python files containing 'def main'",
        required_tools=["grep"],
        timeout=30,
    ),
    EvalTask(
        name="tool_error_recovery",
        prompt="Try to delete a non-existent file /tmp/nonexistent_xyz_2024.txt, "
               "then handle the error gracefully and report what happened.",
        success_criteria="Error was handled without crashing",
        expected_output_patterns=["not found", "exist", "error"],
    ),
]

LIGHT_TASKS = [t for t in BUILTIN_TASKS if t.timeout <= 60]
