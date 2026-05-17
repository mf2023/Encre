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

"""Tests for built-in tool implementations (surface-level, no network calls)."""

import asyncio

import pytest

from yim.tools.base import YmiTool


# ===========================================================================
# Tool base class
# ===========================================================================

class TestYmiTool:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            YmiTool()

    def test_concrete_tool_instantiates(self):
        from yim.tools.builtin import YmiFileReadTool
        tool = YmiFileReadTool()
        assert isinstance(tool, YmiTool)

    def test_concrete_tool_has_name(self):
        from yim.tools.builtin import YmiFileReadTool
        tool = YmiFileReadTool()
        assert tool.name == "file_read"

    def test_concrete_tool_has_description(self):
        from yim.tools.builtin import YmiFileReadTool
        tool = YmiFileReadTool()
        assert len(tool.description) > 0


# ===========================================================================
# File tools format
# ===========================================================================

class TestFileToolsFormat:
    def test_file_read_openai_format(self):
        from yim.tools.builtin import YmiFileReadTool
        tool = YmiFileReadTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"
        assert "name" in fmt["function"]
        assert "parameters" in fmt["function"]

    def test_file_read_anthropic_format(self):
        from yim.tools.builtin import YmiFileReadTool
        tool = YmiFileReadTool()
        fmt = tool.to_anthropic_format()
        assert "name" in fmt
        assert "input_schema" in fmt

    def test_file_write_openai_format(self):
        from yim.tools.builtin import YmiFileWriteTool
        tool = YmiFileWriteTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_file_edit_openai_format(self):
        from yim.tools.builtin import YmiFileEditTool
        tool = YmiFileEditTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_bash_openai_format(self):
        from yim.tools.builtin import YmiBashTool
        tool = YmiBashTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_grep_openai_format(self):
        from yim.tools.builtin import YmiGrepTool
        tool = YmiGrepTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_glob_openai_format(self):
        from yim.tools.builtin import YmiGlobTool
        tool = YmiGlobTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Web tools
# ===========================================================================

class TestWebTools:
    def test_web_fetch_format(self):
        from yim.tools.builtin import YmiWebFetchTool
        tool = YmiWebFetchTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"
        assert "url" in str(fmt["function"]["parameters"])

    def test_web_search_format(self):
        from yim.tools.builtin import YmiWebSearchTool
        tool = YmiWebSearchTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"
        assert "query" in str(fmt["function"]["parameters"])


# ===========================================================================
# Task management tools
# ===========================================================================

class TestTaskTools:
    def test_task_create_format(self):
        from yim.tools.builtin import YmiTaskCreateTool
        tool = YmiTaskCreateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_task_list_format(self):
        from yim.tools.builtin import YmiTaskListTool
        tool = YmiTaskListTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_task_get_format(self):
        from yim.tools.builtin import YmiTaskGetTool
        tool = YmiTaskGetTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_task_update_format(self):
        from yim.tools.builtin import YmiTaskUpdateTool
        tool = YmiTaskUpdateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_task_stop_format(self):
        from yim.tools.builtin import YmiTaskStopTool
        tool = YmiTaskStopTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_task_output_format(self):
        from yim.tools.builtin import YmiTaskOutputTool
        tool = YmiTaskOutputTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Cron tools
# ===========================================================================

class TestCronTools:
    def test_cron_create_format(self):
        from yim.tools.builtin import YmiCronCreateTool
        tool = YmiCronCreateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_cron_delete_format(self):
        from yim.tools.builtin import YmiCronDeleteTool
        tool = YmiCronDeleteTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"

    def test_cron_list_format(self):
        from yim.tools.builtin import YmiCronListTool
        tool = YmiCronListTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Agent tool
# ===========================================================================

class TestAgentTool:
    def test_agent_tool_format(self):
        from yim.tools.builtin import YmiAgentTool
        tool = YmiAgentTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# LSP tool
# ===========================================================================

class TestLSPTool:
    def test_lsp_tool_format(self):
        from yim.tools.builtin import YmiLSPTool
        tool = YmiLSPTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Browser tool
# ===========================================================================

class TestBrowserTool:
    def test_browser_tool_format(self):
        from yim.tools.builtin import YmiBrowserTool
        tool = YmiBrowserTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Notebook tool
# ===========================================================================

class TestNotebookTool:
    def test_notebook_tool_format(self):
        from yim.tools.builtin.notebook import YmiNotebookTool
        tool = YmiNotebookTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# Todo tool
# ===========================================================================

class TestTodoTool:
    def test_todo_tool_format(self):
        from yim.tools.builtin import YmiTodoTool
        tool = YmiTodoTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"


# ===========================================================================
# MCP tool
# ===========================================================================

class TestMCPTool:
    def test_mcp_tool_create(self):
        from yim.tools.mcp import YmiMCPTool
        tool = YmiMCPTool(command="echo hello")
        assert tool.name == "mcp"
        assert tool._command == "echo hello"

    def test_mcp_tool_format(self):
        from yim.tools.mcp import YmiMCPTool
        tool = YmiMCPTool(command="echo hello")
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function"
