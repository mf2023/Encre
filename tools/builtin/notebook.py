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

import json
from typing import Any, ClassVar

from yim.notebook.session import YmiNotebookSession
from yim.tools.base import YmiTool


class YmiNotebookTool(YmiTool):
    name: ClassVar[str] = "notebook"
    description: ClassVar[str] = (
        "Manage an interactive Jupyter-style notebook session. "
        "Supports creating cells, editing cells, executing code, and inspecting results. "
        "Use this for iterative data exploration, visualization, or long-running computations."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_cell",
                    "edit_cell",
                    "execute_cell",
                    "execute_all",
                    "get_output",
                    "get_state",
                    "delete_cell",
                    "reset",
                ],
                "description": "The notebook action to perform",
            },
            "code": {
                "type": "string",
                "description": "Python code for the cell (used with create_cell, edit_cell)",
            },
            "cell_id": {
                "type": "string",
                "description": "Cell ID (used with edit_cell, execute_cell, get_output, delete_cell)",
            },
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown"],
                "description": "Type of cell (default: code)",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 60 for single, 300 for all)",
            },
            "kernel_name": {
                "type": "string",
                "description": "Kernel name for reset action (default: python3)",
            },
        },
        "required": ["action"],
    }
    intents: ClassVar[list[str]] = ["data"]

    _session: YmiNotebookSession | None = None

    @classmethod
    def _get_session(cls) -> YmiNotebookSession:
        if cls._session is None:
            cls._session = YmiNotebookSession()
        return cls._session

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        session = self._get_session()

        if action == "create_cell":
            code = kwargs.get("code", "")
            cell_type = kwargs.get("cell_type", "code")
            cell_id = session.create_cell(code, cell_type)
            return json.dumps({"ok": True, "cell_id": cell_id})

        elif action == "edit_cell":
            cell_id = kwargs.get("cell_id", "")
            code = kwargs.get("code", "")
            ok = session.edit_cell(cell_id, code)
            return json.dumps({"ok": ok, "cell_id": cell_id})

        elif action == "execute_cell":
            cell_id = kwargs.get("cell_id", "")
            timeout = kwargs.get("timeout", 60)
            result = await session.execute_cell(cell_id, timeout)
            return json.dumps({"ok": True, **result}, ensure_ascii=False)

        elif action == "execute_all":
            timeout = kwargs.get("timeout", 300)
            results = await session.execute_all(timeout)
            return json.dumps({"ok": True, "results": results}, ensure_ascii=False)

        elif action == "get_output":
            cell_id = kwargs.get("cell_id", "")
            output = session.get_output(cell_id)
            error = session.get_error(cell_id)
            return json.dumps({"ok": True, "output": output, "error": error}, ensure_ascii=False)

        elif action == "get_state":
            state = session.get_state()
            return json.dumps(state, ensure_ascii=False)

        elif action == "delete_cell":
            cell_id = kwargs.get("cell_id", "")
            ok = session.delete_cell(cell_id)
            return json.dumps({"ok": ok})

        elif action == "reset":
            if YmiNotebookTool._session is not None:
                YmiNotebookTool._session.close()
            kernel_name = kwargs.get("kernel_name", "python3")
            YmiNotebookTool._session = YmiNotebookSession(kernel_name)
            return json.dumps({"ok": True, "message": "Notebook session reset"})

        else:
            return json.dumps({"ok": False, "error": f"Unknown action: {action}"})

    def is_concurrency_safe(self, input_data: dict[str, Any]) -> bool:
        return False
