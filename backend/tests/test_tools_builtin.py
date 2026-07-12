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

"""Tests for built-in tool implementations (surface-level, no network calls)."""


import pytest
from encre.tools.base import EncreTool

# ===========================================================================
# Tool base class
# ===========================================================================

class TestEncreTool:
    """Test cases covering encre tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_cannot_instantiate_abc(self):
        """Verifies that cannot instantiate abc."""
        with pytest.raises(TypeError):
            EncreTool()

    def test_concrete_tool_instantiates(self):
        """Verifies that concrete tool instantiates."""
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: concrete tool instantiates.
        assert isinstance(tool, EncreTool)

    def test_concrete_tool_has_name(self):
        """Verifies that concrete tool has name."""
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: concrete tool has name.
        assert tool.name == "file_read"

    def test_concrete_tool_has_description(self):
        """Verifies that concrete tool has description."""
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        # Confirm the expected result for this scenario: concrete tool has description.
        assert len(tool.description) > 0


# ===========================================================================
# File tools format
# ===========================================================================

class TestFileToolsFormat:
    """Test cases covering file tools format.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_file_read_openai_format(self):
        """Verifies that file read openai format."""
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: file read openai format.
        assert fmt["type"] == "function"
        assert "name" in fmt["function"]
        assert "parameters" in fmt["function"]

    def test_file_read_anthropic_format(self):
        """Verifies that file read anthropic format."""
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        fmt = tool.to_anthropic_format()
        # Confirm the expected result for this scenario: file read anthropic format.
        assert "name" in fmt
        assert "input_schema" in fmt

    def test_file_write_openai_format(self):
        """Verifies that file write openai format."""
        from encre.tools.builtin import EncreFileWriteTool
        tool = EncreFileWriteTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: file write openai format.
        assert fmt["type"] == "function"

    def test_file_edit_openai_format(self):
        """Verifies that file edit openai format."""
        from encre.tools.builtin import EncreFileEditTool
        tool = EncreFileEditTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: file edit openai format.
        assert fmt["type"] == "function"

    def test_bash_openai_format(self):
        """Verifies that bash openai format."""
        from encre.tools.builtin import EncreBashTool
        tool = EncreBashTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: bash openai format.
        assert fmt["type"] == "function"

    def test_grep_openai_format(self):
        """Verifies that grep openai format."""
        from encre.tools.builtin import EncreGrepTool
        tool = EncreGrepTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: grep openai format.
        assert fmt["type"] == "function"

    def test_glob_openai_format(self):
        """Verifies that glob openai format."""
        from encre.tools.builtin import EncreGlobTool
        tool = EncreGlobTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: glob openai format.
        assert fmt["type"] == "function"


# ===========================================================================
# Web tools
# ===========================================================================

class TestWebTools:
    """Test cases covering web tools.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_web_fetch_format(self):
        """Verifies that web fetch format."""
        from encre.tools.builtin import EncreWebFetchTool
        tool = EncreWebFetchTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: web fetch format.
        assert fmt["type"] == "function"
        assert "url" in str(fmt["function"]["parameters"])

    def test_web_search_format(self):
        """Verifies that web search format."""
        from encre.tools.builtin import EncreWebSearchTool
        tool = EncreWebSearchTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: web search format.
        assert fmt["type"] == "function"
        assert "query" in str(fmt["function"]["parameters"])


# ===========================================================================
# Task management tools
# ===========================================================================

class TestTaskTools:
    """Test cases covering task tools.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_task_create_format(self):
        """Verifies that task create format."""
        from encre.tools.builtin import EncreTaskCreateTool
        tool = EncreTaskCreateTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task create format.
        assert fmt["type"] == "function"

    def test_task_list_format(self):
        """Verifies that task list format."""
        from encre.tools.builtin import EncreTaskListTool
        tool = EncreTaskListTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task list format.
        assert fmt["type"] == "function"

    def test_task_get_format(self):
        """Verifies that task get format."""
        from encre.tools.builtin import EncreTaskGetTool
        tool = EncreTaskGetTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task get format.
        assert fmt["type"] == "function"

    def test_task_update_format(self):
        """Verifies that task update format."""
        from encre.tools.builtin import EncreTaskUpdateTool
        tool = EncreTaskUpdateTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task update format.
        assert fmt["type"] == "function"

    def test_task_stop_format(self):
        """Verifies that task stop format."""
        from encre.tools.builtin import EncreTaskStopTool
        tool = EncreTaskStopTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task stop format.
        assert fmt["type"] == "function"

    def test_task_output_format(self):
        """Verifies that task output format."""
        from encre.tools.builtin import EncreTaskOutputTool
        tool = EncreTaskOutputTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: task output format.
        assert fmt["type"] == "function"


# ===========================================================================
# Cron tools
# ===========================================================================

class TestCronTools:
    """Test cases covering cron tools.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_cron_create_format(self):
        """Verifies that cron create format."""
        from encre.tools.builtin import EncreCronCreateTool
        tool = EncreCronCreateTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: cron create format.
        assert fmt["type"] == "function"

    def test_cron_delete_format(self):
        """Verifies that cron delete format."""
        from encre.tools.builtin import EncreCronDeleteTool
        tool = EncreCronDeleteTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: cron delete format.
        assert fmt["type"] == "function"

    def test_cron_list_format(self):
        """Verifies that cron list format."""
        from encre.tools.builtin import EncreCronListTool
        tool = EncreCronListTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: cron list format.
        assert fmt["type"] == "function"


# ===========================================================================
# Agent tool
# ===========================================================================

class TestAgentTool:
    """Test cases covering agent tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_agent_tool_format(self):
        """Verifies that agent tool format."""
        from encre.tools.builtin import EncreAgentTool
        tool = EncreAgentTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: agent tool format.
        assert fmt["type"] == "function"


# ===========================================================================
# LSP tool
# ===========================================================================

class TestLSPTool:
    """Test cases covering l s p tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_lsp_tool_format(self):
        """Verifies that lsp tool format."""
        from encre.tools.builtin import EncreLSPTool
        tool = EncreLSPTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: lsp tool format.
        assert fmt["type"] == "function"


# ===========================================================================
# Browser tool
# ===========================================================================

class TestBrowserTool:
    """Test cases covering browser tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_browser_tool_format(self):
        """Verifies that browser tool format."""
        from encre.tools.builtin import EncreBrowserTool
        tool = EncreBrowserTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: browser tool format.
        assert fmt["type"] == "function"


# ===========================================================================
# Notebook tool
# ===========================================================================

class TestNotebookTool:
    """Test cases covering notebook tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_notebook_tool_format(self):
        """Verifies that notebook tool format."""
        from encre.tools.builtin.notebook import EncreNotebookTool
        tool = EncreNotebookTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: notebook tool format.
        assert fmt["type"] == "function"


# ===========================================================================
# Todo tool
# ===========================================================================

class TestTodoTool:
    """Test cases covering todo tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_todo_tool_format(self):
        """Verifies that todo tool format."""
        from encre.tools.builtin import EncreTodoTool
        tool = EncreTodoTool()
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: todo tool format.
        assert fmt["type"] == "function"


# ===========================================================================
# MCP tool
# ===========================================================================

class TestMCPTool:
    """Test cases covering m c p tool.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_mcp_tool_create(self):
        """Verifies that mcp tool create."""
        from encre.tools.mcp import EncreMCPTool
        tool = EncreMCPTool(command="echo hello")
        # Confirm the expected result for this scenario: mcp tool create.
        assert tool.name == "mcp"
        assert tool._command == "echo hello"

    def test_mcp_tool_format(self):
        """Verifies that mcp tool format."""
        from encre.tools.mcp import EncreMCPTool
        tool = EncreMCPTool(command="echo hello")
        fmt = tool.to_openai_format()
        # Confirm the expected result for this scenario: mcp tool format.
        assert fmt["type"] == "function"
