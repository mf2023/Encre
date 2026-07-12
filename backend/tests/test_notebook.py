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

"""Tests for encre.notebook.session -- EncreNotebookSession."""

import uuid

# ===========================================================================
# EncreNotebookSession construction
# ===========================================================================

class TestEncreNotebookSessionConstruction:
    """Test cases covering encre notebook session construction.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Tests for creating EncreNotebookSession instances."""

    def test_construction_default_kernel(self):
        """Verifies that construction default kernel."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Confirm the expected result for this scenario: construction default kernel.
        assert sess is not None
        assert sess.kernel_name == "python3"

    def test_construction_custom_kernel(self):
        """Verifies that construction custom kernel."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession(kernel_name="python3.12")
        # Confirm the expected result for this scenario: construction custom kernel.
        assert sess.kernel_name == "python3.12"

    def test_construction_other_python_versions(self):
        """Verifies that construction other python versions."""
        from encre.notebook.session import EncreNotebookSession
        for kname in ["python3.9", "python3.10", "python3.11", "python3.13"]:
            sess = EncreNotebookSession(kernel_name=kname)
            # Confirm the expected result for this scenario: construction other python versions.
            assert sess.kernel_name == kname

    def test_session_id_is_uuid_string(self):
        """Verifies that session id is uuid string."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Confirm the expected result for this scenario: session id is uuid string.
        assert isinstance(sess.session_id, str)
        # Should be a valid UUID
        uuid.UUID(sess.session_id)

    def test_each_session_has_unique_id(self):
        """Verifies that each session has unique id."""
        from encre.notebook.session import EncreNotebookSession
        a = EncreNotebookSession()
        b = EncreNotebookSession()
        # Confirm the expected result for this scenario: each session has unique id.
        assert a.session_id != b.session_id

    def test_initial_state_not_started(self):
        """Verifies that initial state not started."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Confirm the expected result for this scenario: initial state not started.
        assert sess._started is False
        assert sess._process is None

    def test_initial_cells_empty(self):
        """Verifies that initial cells empty."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Confirm the expected result for this scenario: initial cells empty.
        assert sess._cells == {}
        assert sess._cell_order == []

    def test_kernel_script_is_python_code(self):
        """Verifies that kernel script is python code."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Confirm the expected result for this scenario: kernel script is python code.
        assert "import sys" in sess._kernel_script
        assert "exec(" in sess._kernel_script
        assert "__SHUTDOWN__" in sess._kernel_script


# ===========================================================================
# EncreNotebookSession cell management
# ===========================================================================

class TestEncreNotebookSessionCells:
    """Test cases covering encre notebook session cells.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Tests for cell CRUD operations (no kernel needed)."""

    def test_create_cell_returns_id(self):
        """Verifies that create cell returns id."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        cell_id = sess.create_cell(code="print('hello')")
        # Confirm the expected result for this scenario: create cell returns id.
        assert isinstance(cell_id, str)
        assert len(cell_id) == 8

    def test_create_cell_default_type_code(self):
        """Verifies that create cell default type code."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.create_cell(code="x = 1")
        state = sess.get_state()
        cells = state["cells"]
        # Confirm the expected result for this scenario: create cell default type code.
        assert len(cells) == 1
        assert cells[0]["cell_type"] == "code"

    def test_create_cell_markdown_type(self):
        """Verifies that create cell markdown type."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.create_cell(code="# Title", cell_type="markdown")
        state = sess.get_state()
        cells = state["cells"]
        # Confirm the expected result for this scenario: create cell markdown type.
        assert cells[0]["cell_type"] == "markdown"

    def test_create_multiple_cells_preserves_order(self):
        """Verifies that create multiple cells preserves order."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        id1 = sess.create_cell(code="a = 1")
        id2 = sess.create_cell(code="b = 2")
        id3 = sess.create_cell(code="c = 3")
        state = sess.get_state()
        cell_ids = [c["id"] for c in state["cells"]]
        # Confirm the expected result for this scenario: create multiple cells preserves order.
        assert cell_ids == [id1, id2, id3]

    def test_edit_cell_changes_code(self):
        """Verifies that edit cell changes code."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        cell_id = sess.create_cell(code="original")
        result = sess.edit_cell(cell_id, code="modified")
        # Confirm the expected result for this scenario: edit cell changes code.
        assert result is True
        state = sess.get_state()
        assert state["cells"][0]["code"] == "modified"

    def test_edit_nonexistent_cell_returns_false(self):
        """Verifies that edit nonexistent cell returns false."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        result = sess.edit_cell("nonexistent", code="x = 1")
        # Confirm the expected result for this scenario: edit nonexistent cell returns false.
        assert result is False

    def test_edit_cell_resets_status_and_outputs(self):
        """Verifies that edit cell resets status and outputs."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        cell_id = sess.create_cell(code="print('hi')")
        sess.edit_cell(cell_id, code="print('hello')")
        state = sess.get_state()
        cell = state["cells"][0]
        # Confirm the expected result for this scenario: edit cell resets status and outputs.
        assert cell["status"] == "idle"
        assert cell["output"] == ""
        assert cell["error"] == ""

    def test_delete_cell_removes_from_state(self):
        """Verifies that delete cell removes from state."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        cell_id = sess.create_cell(code="x = 1")
        # Confirm the expected result for this scenario: delete cell removes from state.
        assert sess.delete_cell(cell_id) is True
        state = sess.get_state()
        assert state["cell_count"] == 0
        assert state["cells"] == []

    def test_delete_nonexistent_cell_returns_false(self):
        """Verifies that delete nonexistent cell returns false."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        result = sess.delete_cell("no_such_cell")
        # Confirm the expected result for this scenario: delete nonexistent cell returns false.
        assert result is False

    def test_delete_cell_preserves_order(self):
        """Verifies that delete cell preserves order."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        id1 = sess.create_cell(code="a = 1")
        id2 = sess.create_cell(code="b = 2")
        id3 = sess.create_cell(code="c = 3")
        sess.delete_cell(id2)
        state = sess.get_state()
        cell_ids = [c["id"] for c in state["cells"]]
        # Confirm the expected result for this scenario: delete cell preserves order.
        assert cell_ids == [id1, id3]

    def test_get_output_nonexistent_returns_empty(self):
        """Verifies that get output nonexistent returns empty."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        result = sess.get_output("no_such_cell")
        # Confirm the expected result for this scenario: get output nonexistent returns empty.
        assert result == ""

    def test_get_error_nonexistent_returns_empty(self):
        """Verifies that get error nonexistent returns empty."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        result = sess.get_error("no_such_cell")
        # Confirm the expected result for this scenario: get error nonexistent returns empty.
        assert result == ""

    def test_get_output_for_existing_cell(self):
        """Verifies that get output for existing cell."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        cell_id = sess.create_cell(code="x = 1")
        # Cell hasn't been executed, so output is empty
        # Confirm the expected result for this scenario: get output for existing cell.
        assert sess.get_output(cell_id) == ""


# ===========================================================================
# EncreNotebookSession state
# ===========================================================================

class TestEncreNotebookSessionState:
    """Test cases covering encre notebook session state.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Tests for get_state."""

    def test_get_state_initial(self):
        """Verifies that get state initial."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        state = sess.get_state()
        # Confirm the expected result for this scenario: get state initial.
        assert state["session_id"] == sess.session_id
        assert state["kernel_name"] == "python3"
        assert state["cells"] == []
        assert state["cell_count"] == 0

    def test_get_state_after_creating_cells(self):
        """Verifies that get state after creating cells."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.create_cell(code="x = 1")
        sess.create_cell(code="y = 2")
        state = sess.get_state()
        # Confirm the expected result for this scenario: get state after creating cells.
        assert state["cell_count"] == 2
        assert len(state["cells"]) == 2
        assert state["cells"][0]["code"] == "x = 1"
        assert state["cells"][1]["code"] == "y = 2"

    def test_get_state_keys(self):
        """Verifies that get state keys."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        state = sess.get_state()
        for key in ["session_id", "kernel_name", "cells", "cell_count"]:
            # Confirm the expected result for this scenario: get state keys.
            assert key in state

    def test_cell_state_keys(self):
        """Verifies that cell state keys."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.create_cell(code="print('hi')")
        state = sess.get_state()
        cell = state["cells"][0]
        for key in ["id", "code", "cell_type", "output", "error", "status", "execution_time"]:
            # Confirm the expected result for this scenario: cell state keys.
            assert key in cell

    def test_cell_initial_status_idle(self):
        """Verifies that cell initial status idle."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.create_cell(code="print('hi')")
        state = sess.get_state()
        # Confirm the expected result for this scenario: cell initial status idle.
        assert state["cells"][0]["status"] == "idle"
        assert state["cells"][0]["execution_time"] == 0.0


# ===========================================================================
# EncreNotebookSession close
# ===========================================================================

class TestEncreNotebookSessionClose:
    """Test cases covering encre notebook session close.
    
    Covers the expected behavior and relevant edge cases.
    """
    """Tests for session close behavior."""

    def test_close_before_kernel_started_does_not_raise(self):
        """Verifies that close before kernel started does not raise."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.close()
        # Confirm the expected result for this scenario: close before kernel started does not raise.
        assert sess._started is False
        assert sess._process is None

    def test_close_is_idempotent(self):
        """Verifies that close is idempotent."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        sess.close()
        sess.close()
        # Confirm the expected result for this scenario: close is idempotent.
        assert sess._started is False
