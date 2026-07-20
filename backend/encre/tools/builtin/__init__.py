#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Module: builtin/__init__.py

Init implementation for the Encre tool system.
"""
from encre.tools.builtin.agent import EncreAgentTool
from encre.tools.builtin.apply_patch import EncreApplyPatchTool
from encre.tools.builtin.bash import EncreBashTool
from encre.tools.builtin.bash_io import (
    EncreBashKillTool,
    EncreBashListTool,
    EncreBashOutputTool,
)
from encre.tools.builtin.browser import EncreBrowserTool
from encre.tools.builtin.codebase import (
    EncreCodebaseContextTool,
    EncreCodebaseSearchTool,
)
from encre.tools.builtin.computer_use import EncreComputerUseTool
from encre.tools.builtin.cron_create import EncreCronCreateTool
from encre.tools.builtin.cron_delete import EncreCronDeleteTool
from encre.tools.builtin.cron_list import EncreCronListTool
from encre.tools.builtin.database import EncreDatabaseTool
from encre.tools.builtin.deploy import EncreDeployTool
from encre.tools.builtin.desktop import EncreDesktopTool
from encre.tools.builtin.docker import EncreDockerTool
from encre.tools.builtin.document import EncreDocumentTool
from encre.tools.builtin.file_edit import EncreFileEditTool
from encre.tools.builtin.file_read import EncreFileReadTool
from encre.tools.builtin.file_write import EncreFileWriteTool
from encre.tools.builtin.find_tool import EncreFindToolTool
from encre.tools.builtin.git_tool import EncreGitTool
from encre.tools.builtin.glob import EncreGlobTool
from encre.tools.builtin.grep import EncreGrepTool
from encre.tools.builtin.image import EncreImageTool
from encre.tools.builtin.info import EncreInfoTool
from encre.tools.builtin.generate_image import (
    EncreGenerateImageTool,
    EncreEditImageTool,
    EncreImageVariationTool,
)
from encre.tools.builtin.media_api import (
    EncreTranscribeAudioTool,
    EncreTranslateAudioTool,
    EncreCreateEmbeddingsTool,
    EncreCreateModerationTool,
)
from encre.tools.builtin.platform_api import (
    EncreFileApiTool,
    EncreBatchApiTool,
    EncreFineTuneApiTool,
)
from encre.tools.builtin.lint_format import EncreLintFormatTool
from encre.tools.builtin.manage import EncreManageTool
from encre.tools.builtin.lsp import EncreLSPTool
from encre.tools.builtin.media import EncreMediaTool
from encre.tools.builtin.memory import (
    EncreMemoryCreateTool,
    EncreMemoryDeleteTool,
    EncreMemoryProfileTool,
    EncreMemoryReadTool,
    EncreMemorySearchTool,
    EncreMemoryUpdateTool,
)
from encre.tools.builtin.notebook import EncreNotebookTool
from encre.tools.builtin.pdf import EncrePDFTool
from encre.tools.builtin.presentation import EncrePresentationTool
from encre.tools.builtin.question import EncreQuestionTool
from encre.tools.builtin.rest_client import EncreRESTTool
from encre.tools.builtin.skill import EncreSkillTool
from encre.tools.builtin.spreadsheet import EncreSpreadsheetTool
from encre.tools.builtin.task_create import EncreTaskCreateTool
from encre.tools.builtin.task_get import EncreTaskGetTool
from encre.tools.builtin.task_list import EncreTaskListTool
from encre.tools.builtin.task_output import EncreTaskOutputTool
from encre.tools.builtin.task_stop import EncreTaskStopTool
from encre.tools.builtin.task_update import EncreTaskUpdateTool
from encre.tools.builtin.test_runner import EncreTestRunTool
from encre.tools.builtin.todo import EncreTodoTool
from encre.tools.builtin.vlm_computer_use import EncreVLMComputerUseTool
from encre.tools.builtin.web_fetch import EncreWebFetchTool
from encre.tools.builtin.web_search import EncreWebSearchTool
from encre.tools.builtin.workflow import EncreWorkflowTool

__all__ = [
    "EncreAgentTool",
    "EncreApplyPatchTool",
    "EncreBashKillTool",
    "EncreBashListTool",
    "EncreBashOutputTool",
    "EncreBashTool",
    "EncreBatchApiTool",
    "EncreBrowserTool",
    "EncreCodebaseContextTool",
    "EncreCodebaseSearchTool",
    "EncreComputerUseTool",
    "EncreCreateEmbeddingsTool",
    "EncreCreateModerationTool",
    "EncreCronCreateTool",
    "EncreCronDeleteTool",
    "EncreCronListTool",
    "EncreDatabaseTool",
    "EncreDeployTool",
    "EncreDesktopTool",
    "EncreDockerTool",
    "EncreDocumentTool",
    "EncreEditImageTool",
    "EncreFileApiTool",
    "EncreFileEditTool",
    "EncreFileReadTool",
    "EncreFileWriteTool",
    "EncreFindToolTool",
    "EncreFineTuneApiTool",
    "EncreGenerateImageTool",
    "EncreGitTool",
    "EncreGlobTool",
    "EncreGrepTool",
    "EncreImageTool",
    "EncreImageVariationTool",
    "EncreInfoTool",
    "EncreLSPTool",
    "EncreLintFormatTool",
    "EncreManageTool",
    "EncreMediaTool",
    "EncreMemoryCreateTool",
    "EncreMemoryDeleteTool",
    "EncreMemoryProfileTool",
    "EncreMemoryReadTool",
    "EncreMemorySearchTool",
    "EncreMemoryUpdateTool",
    "EncreNotebookTool",
    "EncrePDFTool",
    "EncrePresentationTool",
    "EncreQuestionTool",
    "EncreRESTTool",
    "EncreSkillTool",
    "EncreSpreadsheetTool",
    "EncreTaskCreateTool",
    "EncreTaskGetTool",
    "EncreTaskListTool",
    "EncreTaskOutputTool",
    "EncreTaskStopTool",
    "EncreTaskUpdateTool",
    "EncreTestRunTool",
    "EncreTodoTool",
    "EncreTranscribeAudioTool",
    "EncreTranslateAudioTool",
    "EncreVLMComputerUseTool",
    "EncreWebFetchTool",
    "EncreWebSearchTool",
    "EncreWorkflowTool",
]
