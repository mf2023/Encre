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

"""Tests for built-in tool implementations (surface-level, no network calls)."""


import pytest
from encre.tools.base import EncreTool

# ===========================================================================
# Tool base class
# ===========================================================================

class TestEncreTool:
    """Engineered to validate the EncreTool abstract base class and concrete subclass contract.

    This test class exercises the tool base class across 4 scenarios to ensure the ABC
    cannot be instantiated directly (enforcing the subclass contract), that a concrete
    subclass (EncreFileReadTool) instantiates successfully, and that concrete tools
    expose the required name and description fields. These tests form the contract
    boundary for the entire tool subsystem.
    """

    def test_verify_encre_tool_cannot_be_instantiated_directly(self):
        """Validate that EncreTool raises TypeError on direct instantiation.

        The test asserts that calling EncreTool() raises TypeError, confirming the ABC
        machinery prevents direct construction and forces subclasses to implement
        the required abstract methods (name, description, to_openai_format, etc.).
        """
        with pytest.raises(TypeError):
            EncreTool()

    def test_verify_concrete_tool_instantiates_and_is_base_tool_subtype(self):
        """Validate that EncreFileReadTool can be instantiated and is an EncreTool subtype.

        The test constructs the concrete tool and asserts isinstance(tool, EncreTool),
        confirming the subclass implements all required abstract methods.
        """
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        assert isinstance(tool, EncreTool), "EncreFileReadTool must be a valid EncreTool instance."

    def test_verify_concrete_tool_exposes_name(self):
        """Validate that EncreFileReadTool exposes the expected tool name 'file_read'.

        The test asserts tool.name == "file_read", confirming the name contract that
        downstream tool dispatchers use to route JSON-RPC calls to the correct handler.
        """
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        assert tool.name == "file_read", "Tool name must be 'file_read'."

    def test_verify_concrete_tool_exposes_nonempty_description(self):
        """Validate that EncreFileReadTool exposes a non-empty description string.

        The test asserts len(tool.description) > 0, confirming every concrete tool
        provides human-readable documentation for the LLM tool-use prompt builder.
        """
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        assert len(tool.description) > 0, "Tool description must be a non-empty string."


# ===========================================================================
# File tools format
# ===========================================================================

class TestFileToolsFormat:
    """Engineered to validate the OpenAI and Anthropic schema formats for file-tool implementations.

    This test class exercises the to_openai_format() and to_anthropic_format() methods
    across 6 scenarios to ensure each file tool (read, write, edit) and the bash/grep/glob
    tools emit a dict with the structurally correct top-level keys. The format methods
    are consumed by the tool dispatcher to build the function-calling schema sent to the
    LLM; incorrect schema structure would cause the model to reject the tool definition.
    """

    def test_verify_file_read_openai_format_structure(self):
        """Validate that EncreFileReadTool.to_openai_format() emits a valid OpenAI function schema.

        The test asserts the top-level type is "function" and that the function dict
        contains both "name" and "parameters" keys, confirming the schema structure
        matches the OpenAI tool-calling contract.
        """
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."
        assert "name" in fmt["function"], "OpenAI function schema must contain a 'name' key."
        assert "parameters" in fmt["function"], "OpenAI function schema must contain a 'parameters' key."

    def test_verify_file_read_anthropic_format_structure(self):
        """Validate that EncreFileReadTool.to_anthropic_format() emits a valid Anthropic tool schema.

        The test asserts the returned dict contains "name" and "input_schema" keys,
        confirming the schema structure matches the Anthropic tool-calling contract.
        """
        from encre.tools.builtin import EncreFileReadTool
        tool = EncreFileReadTool()
        fmt = tool.to_anthropic_format()
        assert "name" in fmt, "Anthropic tool schema must contain a 'name' key."
        assert "input_schema" in fmt, "Anthropic tool schema must contain an 'input_schema' key."

    def test_verify_file_write_openai_format_structure(self):
        """Validate that EncreFileWriteTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreFileWriteTool
        tool = EncreFileWriteTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_file_edit_openai_format_structure(self):
        """Validate that EncreFileEditTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreFileEditTool
        tool = EncreFileEditTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_bash_openai_format_structure(self):
        """Validate that EncreBashTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreBashTool
        tool = EncreBashTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_grep_openai_format_structure(self):
        """Validate that EncreGrepTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreGrepTool
        tool = EncreGrepTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_glob_openai_format_structure(self):
        """Validate that EncreGlobTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreGlobTool
        tool = EncreGlobTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Web tools
# ===========================================================================

class TestWebTools:
    """Engineered to validate the OpenAI schema format for web-tool implementations.

    This test class exercises web_fetch and web_search tool schemas across 2 scenarios
    to ensure each emits a valid OpenAI function schema and that the parameter spec
    includes the expected input field (url for fetch, query for search). These tools
    are the only built-ins that perform external network I/O; their schemas must
    accurately describe the required parameters so the LLM passes correct inputs.
    """

    def test_verify_web_fetch_openai_format_structure(self):
        """Validate that EncreWebFetchTool emits a valid OpenAI function schema with a url parameter.

        The test asserts type=="function" and that the parameters dict contains "url",
        confirming the schema accurately describes the required input for fetch operations.
        """
        from encre.tools.builtin import EncreWebFetchTool
        tool = EncreWebFetchTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."
        assert "url" in str(fmt["function"]["parameters"]), "Parameters must include a 'url' field."

    def test_verify_web_search_openai_format_structure(self):
        """Validate that EncreWebSearchTool emits a valid OpenAI function schema with a query parameter.

        The test asserts type=="function" and that the parameters dict contains "query",
        confirming the schema accurately describes the required input for search operations.
        """
        from encre.tools.builtin import EncreWebSearchTool
        tool = EncreWebSearchTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."
        assert "query" in str(fmt["function"]["parameters"]), "Parameters must include a 'query' field."


# ===========================================================================
# Task management tools
# ===========================================================================

class TestTaskTools:
    """Engineered to validate the OpenAI schema format for task-management tool implementations.

    This test class exercises the six task-tool variants (create, list, get, update,
    stop, output) across 6 scenarios to ensure each emits a valid OpenAI function
    schema. These tools share a common base implementation pattern; the tests confirm
    the format contract holds across the entire task-management surface.
    """

    def test_verify_task_create_openai_format_structure(self):
        """Validate that EncreTaskCreateTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskCreateTool
        tool = EncreTaskCreateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_task_list_openai_format_structure(self):
        """Validate that EncreTaskListTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskListTool
        tool = EncreTaskListTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_task_get_openai_format_structure(self):
        """Validate that EncreTaskGetTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskGetTool
        tool = EncreTaskGetTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_task_update_openai_format_structure(self):
        """Validate that EncreTaskUpdateTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskUpdateTool
        tool = EncreTaskUpdateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_task_stop_openai_format_structure(self):
        """Validate that EncreTaskStopTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskStopTool
        tool = EncreTaskStopTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_task_output_openai_format_structure(self):
        """Validate that EncreTaskOutputTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTaskOutputTool
        tool = EncreTaskOutputTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Cron tools
# ===========================================================================

class TestCronTools:
    """Engineered to validate the OpenAI schema format for cron-tool implementations.

    This test class exercises the three cron-tool variants (create, delete, list) across
    3 scenarios to ensure each emits a valid OpenAI function schema. Cron tools are
    long-running schedule managers; their schemas must be well-formed so the LLM can
    invoke them correctly during plan-and-execute cycles.
    """

    def test_verify_cron_create_openai_format_structure(self):
        """Validate that EncreCronCreateTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreCronCreateTool
        tool = EncreCronCreateTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_cron_delete_openai_format_structure(self):
        """Validate that EncreCronDeleteTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreCronDeleteTool
        tool = EncreCronDeleteTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."

    def test_verify_cron_list_openai_format_structure(self):
        """Validate that EncreCronListTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreCronListTool
        tool = EncreCronListTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Agent tool
# ===========================================================================

class TestAgentTool:
    """Engineered to validate the OpenAI schema format for the agent-delegation tool.

    This test class exercises EncreAgentTool across 1 scenario to ensure it emits a
    valid OpenAI function schema. The agent tool is the mechanism by which the main
    loop delegates sub-tasks to child agents; its schema must be well-formed so the
    LLM can pass correct delegation parameters.
    """

    def test_verify_agent_tool_openai_format_structure(self):
        """Validate that EncreAgentTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreAgentTool
        tool = EncreAgentTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# LSP tool
# ===========================================================================

class TestLSPTool:
    """Engineered to validate the OpenAI schema format for the LSP integration tool.

    This test class exercises EncreLSPTool across 1 scenario to ensure it emits a
    valid OpenAI function schema. The LSP tool exposes language-server capabilities
    (go-to-definition, hover, diagnostics) to the agent; its schema must be well-formed
    so the LLM can request LSP operations during code-navigation tasks.
    """

    def test_verify_lsp_tool_openai_format_structure(self):
        """Validate that EncreLSPTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreLSPTool
        tool = EncreLSPTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Browser tool
# ===========================================================================

class TestBrowserTool:
    """Engineered to validate the OpenAI schema format for the browser automation tool.

    This test class exercises EncreBrowserTool across 1 scenario to ensure it emits a
    valid OpenAI function schema. The browser tool is the agent's interface to web
    interaction; its schema must be well-formed so the LLM can pass correct navigation
    and interaction parameters.
    """

    def test_verify_browser_tool_openai_format_structure(self):
        """Validate that EncreBrowserTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreBrowserTool
        tool = EncreBrowserTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Notebook tool
# ===========================================================================

class TestNotebookTool:
    """Engineered to validate the OpenAI schema format for the Jupyter notebook tool.

    This test class exercises EncreNotebookTool across 1 scenario to ensure it emits
    a valid OpenAI function schema. The notebook tool exposes cell execution and
    inspection to the agent; its schema must be well-formed so the LLM can pass
    correct cell-id and code parameters.
    """

    def test_verify_notebook_tool_openai_format_structure(self):
        """Validate that EncreNotebookTool emits a valid OpenAI function schema."""
        from encre.tools.builtin.notebook import EncreNotebookTool
        tool = EncreNotebookTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# Todo tool
# ===========================================================================

class TestTodoTool:
    """Engineered to validate the OpenAI schema format for the todo/task-reminders tool.

    This test class exercises EncreTodoTool across 1 scenario to ensure it emits a
    valid OpenAI function schema. The todo tool is the agent's interface to the
    platform's reminder system; its schema must be well-formed so the LLM can pass
    correct title, due-date, and priority parameters.
    """

    def test_verify_todo_tool_openai_format_structure(self):
        """Validate that EncreTodoTool emits a valid OpenAI function schema."""
        from encre.tools.builtin import EncreTodoTool
        tool = EncreTodoTool()
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."


# ===========================================================================
# MCP tool
# ===========================================================================

class TestMCPTool:
    """Engineered to validate the MCP (Model Context Protocol) tool construction and schema format.

    This test class exercises EncreMCPTool across 2 scenarios: constructor field storage
    and OpenAI schema emission. The MCP tool wraps an arbitrary subprocess as an LLM- callable
    tool; these tests confirm the command string is stored and the emitted schema is
    structurally valid so the tool can be registered in the function-calling registry.
    """

    def test_verify_mcp_tool_construction_stores_command(self):
        """Validate that EncreMCPTool stores the command string and sets name to 'mcp'.

        The test constructs the tool with command="echo hello" and asserts name=="mcp"
        and _command=="echo hello", confirming the constructor fields are preserved.
        """
        from encre.tools.mcp import EncreMCPTool
        tool = EncreMCPTool(command="echo hello")
        assert tool.name == "mcp", "MCP tool name must be 'mcp'."
        assert tool._command == "echo hello", "Command string must be stored verbatim."

    def test_verify_mcp_tool_openai_format_structure(self):
        """Validate that EncreMCPTool emits a valid OpenAI function schema."""
        from encre.tools.mcp import EncreMCPTool
        tool = EncreMCPTool(command="echo hello")
        fmt = tool.to_openai_format()
        assert fmt["type"] == "function", "OpenAI format must use type='function'."
