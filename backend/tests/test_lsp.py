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

"""Tests for encre.lsp -- LSP protocol dataclasses and EncreLSPClient."""


# ===========================================================================
# Position dataclass
# ===========================================================================

class TestPosition:
    """Engineered to validate the LSP Position dataclass construction and equality semantics.

    This test class exercises the :class:`Position` record across 5 scenarios to ensure
    line/character fields are stored verbatim, large coordinate values do not overflow,
    the type is a dataclass (enabling generated __eq__ / __repr__), and value-based
    equality holds for identical coordinates while differing characters break it. Position
    is the atomic coordinate type used by every other LSP structure in this module.
    """

    def test_verify_position_creation_stores_fields(self):
        """Validate that Position stores line and character exactly as passed.

        The test constructs Position(line=10, character=5) and asserts both fields match,
        confirming the dataclass does not transform or clamp coordinate values.
        """
        from encre.capabilities.search.lsp.protocol import Position
        p = Position(line=10, character=5)
        assert p.line == 10, "line must be stored verbatim."
        assert p.character == 5, "character must be stored verbatim."

    def test_verify_zero_position_is_valid(self):
        """Validate that Position(0, 0) is a valid zero-based coordinate.

        LSP uses zero-based indexing; the test asserts both fields are 0, confirming
        the origin coordinate is accepted without error.
        """
        from encre.capabilities.search.lsp.protocol import Position
        p = Position(line=0, character=0)
        assert p.line == 0, "line=0 must be accepted."
        assert p.character == 0, "character=0 must be accepted."

    def test_verify_large_coordinate_values(self):
        """Validate that large line and character values are stored without overflow.

        The test constructs Position(99999, 999) and asserts both fields match, confirming
        the dataclass does not impose an artificial upper bound on coordinates.
        """
        from encre.capabilities.search.lsp.protocol import Position
        p = Position(line=99999, character=999)
        assert p.line == 99999, "Large line value must be stored verbatim."
        assert p.character == 999, "Large character value must be stored verbatim."

    def test_verify_position_is_dataclass(self):
        """Validate that Position is recognised as a dataclass by the stdlib checker.

        The test uses dataclasses.is_dataclass to assert Position is a dataclass,
        confirming the generated __eq__, __repr__, and __init__ are present.
        """
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import Position
        assert is_dataclass(Position), "Position must be a dataclass."

    def test_verify_position_equality(self):
        """Validate that two Positions with identical fields compare equal and differing ones do not.

        The test constructs p1 and p2 with identical coordinates and p3 with a different
        character value, asserting p1 == p2 and p1 != p3, confirming value-based equality.
        """
        from encre.capabilities.search.lsp.protocol import Position
        p1 = Position(line=5, character=10)
        p2 = Position(line=5, character=10)
        p3 = Position(line=5, character=11)
        assert p1 == p2, "Positions with identical fields must compare equal."
        assert p1 != p3, "Positions with differing character values must not compare equal."


# ===========================================================================
# Range dataclass
# ===========================================================================

class TestRange:
    """Engineered to validate the LSP Range dataclass construction and invariants.

    This test class exercises the :class:`Range` record across 3 scenarios to ensure
    start/end positions are stored verbatim, a single-line range preserves line equality
    with end character greater than start, and the type is a dataclass. Range is the
    primary span type used by Diagnostic, Location, and HoverResult.
    """

    def test_verify_range_creation_stores_positions(self):
        """Validate that Range stores start and end Position objects exactly as passed.

        The test constructs a Range spanning lines 0-10 and characters 0-20 and asserts
        all four coordinate fields match, confirming the dataclass does not mutate positions.
        """
        from encre.capabilities.search.lsp.protocol import Position, Range
        start = Position(line=0, character=0)
        end = Position(line=10, character=20)
        r = Range(start=start, end=end)
        assert r.start.line == 0, "start.line must be stored verbatim."
        assert r.start.character == 0, "start.character must be stored verbatim."
        assert r.end.line == 10, "end.line must be stored verbatim."
        assert r.end.character == 20, "end.character must be stored verbatim."

    def test_verify_single_line_range_preserves_line_equality(self):
        """Validate that a single-line Range has equal start and end line with increasing character.

        The test constructs a Range on line 5 from character 3 to 15 and asserts line
        equality and character ordering, confirming the invariants expected of a valid
        single-line selection span.
        """
        from encre.capabilities.search.lsp.protocol import Position, Range
        start = Position(line=5, character=3)
        end = Position(line=5, character=15)
        r = Range(start=start, end=end)
        assert r.start.line == r.end.line, "Single-line range must have equal start and end line."
        assert r.end.character > r.start.character, "End character must be greater than start character."

    def test_verify_range_is_dataclass(self):
        """Validate that Range is recognised as a dataclass by the stdlib checker."""
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import Range
        assert is_dataclass(Range), "Range must be a dataclass."


# ===========================================================================
# Location dataclass
# ===========================================================================

class TestLocation:
    """Engineered to validate the LSP Location dataclass construction and URI invariant.

    This test class exercises the :class:`Location` record across 3 scenarios to ensure
    the file URI and embedded Range are stored verbatim, file:// URIs are accepted,
    and the type is a dataclass. Location bridges LSP references to actual filesystem paths.
    """

    def test_verify_location_creation_stores_uri_and_range(self):
        """Validate that Location stores uri and range exactly as passed.

        The test constructs a Location with a synthetic file URI and a Range spanning
        line 1 characters 0-10, then asserts the URI and start line are preserved.
        """
        from encre.capabilities.search.lsp.protocol import Location, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        loc = Location(uri="file:///test.py", range=r)
        assert loc.uri == "file:///test.py", "URI must be stored verbatim."
        assert loc.range.start.line == 1, "Range start line must be preserved."

    def test_verify_location_file_uri_format(self):
        """Validate that a file:/// URI is accepted and preserved on a Location.

        The test constructs a Location with an absolute POSIX path and asserts the URI
        starts with "file:///", confirming the LSP client accepts standard file URIs.
        """
        from encre.capabilities.search.lsp.protocol import Location, Position, Range
        r = Range(start=Position(line=0, character=0), end=Position(line=0, character=5))
        loc = Location(uri="file:///home/user/project/main.py", range=r)
        assert loc.uri.startswith("file:///"), "URI must use the file:// scheme."

    def test_verify_location_is_dataclass(self):
        """Validate that Location is recognised as a dataclass by the stdlib checker."""
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import Location
        assert is_dataclass(Location), "Location must be a dataclass."


# ===========================================================================
# Diagnostic dataclass
# ===========================================================================

class TestDiagnostic:
    """Engineered to validate the LSP Diagnostic dataclass construction and severity handling.

    This test class exercises the :class:`Diagnostic` record across 4 scenarios to ensure
    message, severity, and source fields are stored verbatim, the default source is the
    empty string, all four standard LSP severity levels (1-4) are accepted, and the
    type is a dataclass. Diagnostics are the primary error/warning surface returned
    by the LSP server to the client.
    """

    def test_verify_diagnostic_creation_stores_fields(self):
        """Validate that Diagnostic stores message, severity, and source exactly as passed.

        The test constructs a severity-2 diagnostic from source "pyright" and asserts
        all three fields match, confirming the dataclass preserves diagnostic metadata.
        """
        from encre.capabilities.search.lsp.protocol import Diagnostic, Position, Range
        r = Range(start=Position(line=5, character=0), end=Position(line=5, character=10))
        diag = Diagnostic(
            range=r,
            message="Unused variable 'x'",
            severity=2,
            source="pyright",
        )
        assert diag.message == "Unused variable 'x'", "message must be stored verbatim."
        assert diag.severity == 2, "severity must be stored verbatim."
        assert diag.source == "pyright", "source must be stored verbatim."

    def test_verify_diagnostic_default_source_is_empty_string(self):
        """Validate that source defaults to the empty string when omitted.

        The test constructs a Diagnostic without passing source and asserts it is "",
        confirming the field has a sensible default rather than None.
        """
        from encre.capabilities.search.lsp.protocol import Diagnostic, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=5))
        diag = Diagnostic(range=r, message="Error", severity=1)
        assert diag.source == "", "Default source must be an empty string."

    def test_verify_diagnostic_severity_levels(self):
        """Validate that all four standard LSP severity codes are accepted without mutation.

        The test constructs diagnostics with severities 1 through 4 and asserts each
        field is preserved, confirming the dataclass does not clamp or remap severity values.
        """
        from encre.capabilities.search.lsp.protocol import Diagnostic, Position, Range
        r = Range(start=Position(line=0, character=0), end=Position(line=0, character=1))
        for sev in [1, 2, 3, 4]:
            diag = Diagnostic(range=r, message=f"Level {sev}", severity=sev)
            assert diag.severity == sev, f"severity {sev} must be stored verbatim."

    def test_verify_diagnostic_is_dataclass(self):
        """Validate that Diagnostic is recognised as a dataclass by the stdlib checker."""
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import Diagnostic
        assert is_dataclass(Diagnostic), "Diagnostic must be a dataclass."


# ===========================================================================
# HoverResult dataclass
# ===========================================================================

class TestHoverResult:
    """Engineered to validate the LSP HoverResult dataclass construction and optional range.

    This test class exercises the :class:`HoverResult` record across 4 scenarios to ensure
    the contents string is stored verbatim, the range field is None when omitted and
    populated when provided, markdown-formatted contents are accepted, and the type is
    a dataclass. HoverResult is the payload for hover requests in the LSP protocol.
    """

    def test_verify_hover_result_without_range(self):
        """Validate that HoverResult stores contents and sets range to None when omitted.

        The test constructs a HoverResult with only a contents string and asserts the
        contents match and range is None, confirming the range field is truly optional.
        """
        from encre.capabilities.search.lsp.protocol import HoverResult
        hr = HoverResult(contents="def foo(x: int) -> str")
        assert hr.contents == "def foo(x: int) -> str", "contents must be stored verbatim."
        assert hr.range is None, "range must be None when not provided."

    def test_verify_hover_result_with_range(self):
        """Validate that HoverResult stores contents and populates range when provided.

        The test constructs a HoverResult with both contents and a Range, then asserts
        the contents match, range is not None, and the range's start line is preserved.
        """
        from encre.capabilities.search.lsp.protocol import HoverResult, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        hr = HoverResult(contents="A string value", range=r)
        assert hr.contents == "A string value", "contents must be stored verbatim."
        assert hr.range is not None, "range must be populated when provided."
        assert hr.range.start.line == 1, "Range start line must be preserved."

    def test_verify_hover_result_accepts_markdown_contents(self):
        """Validate that markdown-formatted contents strings are accepted verbatim.

        The test passes a Python code fence and asserts the backticks are preserved,
        confirming the contents field does not strip or escape markdown syntax.
        """
        from encre.capabilities.search.lsp.protocol import HoverResult
        md = "```python\ndef foo() -> int: ...\n```"
        hr = HoverResult(contents=md)
        assert "```" in hr.contents, "Markdown fence characters must be preserved in contents."

    def test_verify_hover_result_is_dataclass(self):
        """Validate that HoverResult is recognised as a dataclass by the stdlib checker."""
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import HoverResult
        assert is_dataclass(HoverResult), "HoverResult must be a dataclass."


# ===========================================================================
# LSPState dataclass
# ===========================================================================

class TestLSPState:
    """Engineered to validate the LSPState dataclass construction and status invariant.

    This test class exercises the :class:`LSPState` record across 4 scenarios to ensure
    status and error fields are stored verbatim, all four canonical status strings
    ("starting", "running", "stopped", "error") are accepted, and the type is a dataclass.
    LSPState is the top-level status container returned by the LSP client health check.
    """

    def test_verify_lsp_state_creation_running(self):
        """Validate that LSPState stores status='running' and error=None by default.

        The test constructs a running-state instance and asserts both fields match the
        expected defaults, confirming the running state carries no error payload.
        """
        from encre.capabilities.search.lsp.protocol import LSPState
        state = LSPState(status="running")
        assert state.status == "running", "status must be stored verbatim."
        assert state.error is None, "error must be None when not provided."

    def test_verify_lsp_state_creation_with_error(self):
        """Validate that LSPState stores status='stopped' and the provided error string.

        The test constructs a stopped-state instance with an explicit error message and
        asserts both fields match, confirming the error field is preserved for diagnostic
        reporting when the server fails to start.
        """
        from encre.capabilities.search.lsp.protocol import LSPState
        state = LSPState(status="stopped", error="connection refused")
        assert state.status == "stopped", "status must be stored verbatim."
        assert state.error == "connection refused", "error must be stored verbatim."

    def test_verify_lsp_state_accepts_all_canonical_status_values(self):
        """Validate that all four canonical status strings are accepted without mutation.

        The test constructs LSPState instances for "starting", "running", "stopped", and
        "error" and asserts each status field matches, confirming the dataclass does not
        restrict the status to a subset of values.
        """
        from encre.capabilities.search.lsp.protocol import LSPState
        for status in ["starting", "running", "stopped", "error"]:
            s = LSPState(status=status)
            assert s.status == status, f"status '{status}' must be stored verbatim."

    def test_verify_lsp_state_is_dataclass(self):
        """Validate that LSPState is recognised as a dataclass by the stdlib checker."""
        from dataclasses import is_dataclass
        from encre.capabilities.search.lsp.protocol import LSPState
        assert is_dataclass(LSPState), "LSPState must be a dataclass."


# ===========================================================================
# EncreLSPClient
# ===========================================================================

class TestEncreLSPClient:
    """Engineered to validate the EncreLSPClient construction and initial internal state.

    This test class exercises the client across 5 scenarios to ensure the server_name
    is stored, internal flags (_initialized, _process, _reader_task, _request_id) start
    at their documented initial values, calling close() before start() is a safe no-op,
    and all public symbols are importable from the encre.lsp package namespace. These
    tests form the contract boundary for the client's public API.
    """

    def test_verify_construction_stores_server_name_and_initial_flags(self):
        """Validate that EncreLSPClient stores server_name and initializes internal flags correctly.

        The test constructs a client with server_name="pylsp" and asserts _server_name,
        _initialized (False), and _request_id (0) match, confirming the constructor
        sets up the client in a clean pre-start state.
        """
        from encre.capabilities.search.lsp.client import EncreLSPClient
        client = EncreLSPClient(server_name="pylsp")
        assert client is not None, "Client must be instantiated without error."
        assert client._server_name == "pylsp", "server_name must be stored verbatim."
        assert client._initialized is False, "_initialized must start as False."
        assert client._request_id == 0, "_request_id must start at 0."

    def test_verify_construction_with_various_server_names(self):
        """Validate that multiple well-known LSP server names are accepted and stored.

        The test constructs clients for pylsp, pyright, rust-analyzer, gopls, and
        typescript-language-server and asserts each _server_name matches, confirming
        the client accepts any string without validation restrictions.
        """
        from encre.capabilities.search.lsp.client import EncreLSPClient
        for name in ["pylsp", "pyright", "rust-analyzer", "gopls", "typescript-language-server"]:
            client = EncreLSPClient(server_name=name)
            assert client._server_name == name, f"server_name '{name}' must be stored verbatim."

    def test_verify_initial_state_has_no_process_or_reader_task(self):
        """Validate that a fresh client has _process and _reader_task set to None.

        The test asserts both fields are None, confirming the client has not spawned
        any subprocess or background reader task until start() is called.
        """
        from encre.capabilities.search.lsp.client import EncreLSPClient
        client = EncreLSPClient(server_name="test")
        assert client._process is None, "_process must be None before start()."
        assert client._initialized is False, "_initialized must be False before start()."
        assert client._reader_task is None, "_reader_task must be None before start()."

    def test_verify_close_before_start_does_not_raise(self):
        """Validate that close() is safe to call on a client that was never started.

        The test runs close() asynchronously on a fresh client and asserts no exception
        is raised, confirming the cleanup path guards against null-process dereference.
        """
        import asyncio
        from encre.capabilities.search.lsp.client import EncreLSPClient

        async def _test():
            client = EncreLSPClient(server_name="test")
            await client.close()

        asyncio.run(_test())

    def test_verify_public_api_exports(self):
        """Validate that all documented public symbols are importable from encre.capabilities.search.lsp.

        The test imports EncreLSPClient, EncreLSPManager, Position, Range, Location,
        Diagnostic, HoverResult, and LSPState from the package namespace and asserts
        each is not None, confirming the __all__ export list is complete.
        """
        from encre.capabilities.search.lsp import (
            Diagnostic,
            EncreLSPClient,
            EncreLSPManager,
            HoverResult,
            Location,
            LSPState,
            Position,
            Range,
        )
        assert EncreLSPClient is not None, "EncreLSPClient must be exported."
        assert EncreLSPManager is not None, "EncreLSPManager must be exported."
        assert Position is not None, "Position must be exported."
        assert Range is not None, "Range must be exported."
        assert Location is not None, "Location must be exported."
        assert Diagnostic is not None, "Diagnostic must be exported."
        assert HoverResult is not None, "HoverResult must be exported."
        assert LSPState is not None, "LSPState must be exported."


# ===========================================================================
# EncreLSPManager
# ===========================================================================

class TestEncreLSPManager:
    """Engineered to validate the EncreLSPManager construction and basic instantiation.

    This test class exercises the manager across 1 scenario to ensure it can be
    constructed without error and that the instance is non-None. The manager is the
    lifecycle orchestrator for one or more EncreLSPClient instances; this test
    establishes the baseline that construction itself is safe.
    """

    def test_verify_manager_construction(self):
        """Validate that EncreLSPManager can be instantiated without error.

        The test constructs a manager and asserts it is not None, confirming the
        constructor does not raise and the instance is ready for client registration.
        """
        from encre.capabilities.search.lsp.manager import EncreLSPManager
        manager = EncreLSPManager()
        assert manager is not None, "EncreLSPManager must be instantiated without error."
