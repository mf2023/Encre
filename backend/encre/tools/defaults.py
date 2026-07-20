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

"""Module: defaults.py

Defaults implementation for the Encre tool system.
"""
from encre.tools.builtin import (
    EncreAgentTool,
    EncreManageTool,
    EncreApplyPatchTool,
    EncreBashKillTool,
    EncreBashListTool,
    EncreBashOutputTool,
    EncreBashTool,
    EncreBrowserTool,
    EncreCodebaseContextTool,
    EncreCodebaseSearchTool,
    EncreCronCreateTool,
    EncreCronDeleteTool,
    EncreCronListTool,
    EncreDatabaseTool,
    EncreDeployTool,
    EncreDesktopTool,
    EncreDockerTool,
    EncreDocumentTool,
    EncreFileEditTool,
    EncreFileReadTool,
    EncreFileWriteTool,
    EncreFindToolTool,
    EncreGitTool,
    EncreGlobTool,
    EncreGrepTool,
    EncreImageTool,
    EncreInfoTool,
    EncreLintFormatTool,
    EncreLSPTool,
    EncreMediaTool,
    EncreMemoryCreateTool,
    EncreMemoryDeleteTool,
    EncreMemoryProfileTool,
    EncreMemoryReadTool,
    EncreMemorySearchTool,
    EncreMemoryUpdateTool,
    EncreNotebookTool,
    EncrePDFTool,
    EncrePresentationTool,
    EncreQuestionTool,
    EncreRESTTool,
    EncreSkillTool,
    EncreSpreadsheetTool,
    EncreTaskCreateTool,
    EncreTaskGetTool,
    EncreTaskListTool,
    EncreTaskOutputTool,
    EncreTaskStopTool,
    EncreTaskUpdateTool,
    EncreTestRunTool,
    EncreTodoTool,
    EncreWebFetchTool,
    EncreWebSearchTool,
    EncreWorkflowTool,
    EncreSwarmTool,
)
from encre.tools.builtin.computer_use import EncreComputerUseTool
from encre.tools.builtin.vlm_computer_use import EncreVLMComputerUseTool
from encre.tools.registry import ToolRegistry


def register_default_tools(registry: ToolRegistry) -> ToolRegistry:
    """Register default tools.

    Args:
        registry: Description of the registry parameter.
    """
    registry.register_many([
        EncreFileReadTool(),
        EncreFileWriteTool(),
        EncreFileEditTool(),
        EncreApplyPatchTool(),
        EncreBashTool(),
        EncreBashOutputTool(),
        EncreBashKillTool(),
        EncreBashListTool(),
        EncreGrepTool(),
        EncreGlobTool(),
        EncreCodebaseSearchTool(),
        EncreCodebaseContextTool(),
        EncreWebFetchTool(),
        EncreWebSearchTool(),
        EncreTodoTool(),
        EncreTaskCreateTool(),
        EncreTaskGetTool(),
        EncreTaskListTool(),
        EncreTaskUpdateTool(),
        EncreTaskStopTool(),
        EncreTaskOutputTool(),
        EncreTestRunTool(),
        EncreCronCreateTool(),
        EncreCronDeleteTool(),
        EncreCronListTool(),
        EncreAgentTool(),
        EncreManageTool(),
        EncreFindToolTool(),
        EncreLSPTool(),
        EncreBrowserTool(),
        EncreNotebookTool(),
        EncreDatabaseTool(),
        EncreDockerTool(),
        EncreGitTool(),
        EncreRESTTool(),
        EncreSkillTool(),
        EncrePDFTool(),
        EncreSpreadsheetTool(),
        EncreImageTool(),
        EncreInfoTool(),
        EncreDocumentTool(),
        EncrePresentationTool(),
        EncreMediaTool(),
        EncreLintFormatTool(),
        EncreDeployTool(),
        EncreDesktopTool(),
        EncreMemoryCreateTool(),
        EncreMemoryReadTool(),
        EncreMemoryUpdateTool(),
        EncreMemoryDeleteTool(),
        EncreMemorySearchTool(),
        EncreMemoryProfileTool(),
        EncreQuestionTool(),
        EncreWorkflowTool(),
        EncreSwarmTool(),
        EncreComputerUseTool(),
        EncreVLMComputerUseTool(),
    ])
    return registry

