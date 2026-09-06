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

"""Tests for codebase indexer, LSP protocol, git, notebook, server types."""


# ===========================================================================
# Codebase Indexer types
# ===========================================================================

class TestCodeIndex:
    """Engineered to validate the codebase indexer type system.

    This test class exercises :class:`ModuleInfo`, :class:`EncreCodeIndex` across
    construction, default-value, and instantiation scenarios to ensure that the
    indexer data model behaves as a reliable foundation for AST-level code
    search and cross-reference resolution.  The design verifies field integrity
    so that downstream consumers (LSP servers, tool plugins) receive consistent
    module metadata.
    """

    def test_verify_module_info_field_integrity(self):
        """Validate that ModuleInfo correctly stores and exposes its fields.

        The test constructs a fully-populated :class:`ModuleInfo` and asserts
        that each populated field round-trips unchanged because downstream
        consumers rely on exact name, language, exports, and imports values
        for symbol resolution and import graph construction.
        """
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(
            path="src/my_module.py",
            name="my_module",
            language="python",
            exports=["func_a", "ClassB"],
            imports=["os", "json"],
        )
        # Name must match the module identifier used by import-system resolution.
        assert mi.name == "my_module"
        # Language field must be preserved so the indexer can route to
        # language-specific AST parsers.
        assert mi.language == "python"
        # Exported symbols must be preserved for symbol-resolution lookups.
        assert "func_a" in mi.exports
        # Imported modules must be preserved for cross-reference analysis.
        assert "os" in mi.imports

    def test_verify_module_info_defaults(self):
        """Validate that ModuleInfo applies correct default values.

        The test constructs a minimal :class:`ModuleInfo` with only required
        fields and asserts default values because the indexer must gracefully
        handle partial module metadata without raising during downstream
        iteration over exports, imported_by, language, and loc.
        """
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="test.py", name="test")
        # Empty imports list must default so that iteration does not fail.
        assert mi.imports == []
        # imported_by defaults to empty so reverse-dependency lookups are safe.
        assert mi.imported_by == []
        # exports defaults to empty so symbol sets remain iterable.
        assert mi.exports == []
        # language defaults to empty string to avoid None comparisons.
        assert mi.language == ""
        # loc (line of code) defaults to zero for unanalyzed modules.
        assert mi.loc == 0

    def test_verify_code_index_instantiation(self):
        """Validate that EncreCodeIndex constructs without error.

        The test creates an :class:`EncreCodeIndex` pointing at the workspace
        root and asserts it is not None because the index must be instantiable
        before any scan or query operation begins.
        """
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        assert ci is not None


# ===========================================================================
# LSP types
# ===========================================================================

class TestLSPProtocol:
    """Engineered to validate the LSP protocol data model.

    This test class exercises :class:`Position`, :class:`Range`, :class:`Location`,
    :class:`Diagnostic`, :class:`HoverResult`, and :class:`LSPState` across
    construction and field-exposure scenarios to ensure that the protocol types
    behave as a reliable inter-process contract between the LSP server and
    language clients.
    """

    def test_verify_position_fields(self):
        """Validate that Position correctly stores line and character offsets.

        The test constructs a :class:`Position` with explicit line and character
        values and asserts they round-trip because zero-based offset semantics
        are fundamental to all cursor and selection computations.
        """
        from encre.lsp.protocol import Position
        p = Position(line=10, character=5)
        # Line must be stored exactly to locate the correct source row.
        assert p.line == 10
        # Character offset must be stored exactly for column-accurate positioning.
        assert p.character == 5

    def test_verify_range_bounds(self):
        """Validate that Range preserves start and end Position values.

        The test constructs a :class:`Range` spanning lines 0鈥?0 and asserts
        the boundary positions are unchanged because range equality is used
        throughout the LSP protocol for highlights, edits, and selections.
        """
        from encre.lsp.protocol import Position, Range
        start = Position(line=0, character=0)
        end = Position(line=10, character=20)
        r = Range(start=start, end=end)
        # Start position must anchor the range at line 0.
        assert r.start.line == 0
        # End position must cap the range at line 10.
        assert r.end.line == 10

    def test_verify_location_uri_and_range(self):
        """Validate that Location carries URI and Range fields intact.

        The test constructs a :class:`Location` referencing a file URI and a
        single-line range, then asserts both fields survive because locations
        are the primary unit returned by go-to-definition and reference queries.
        """
        from encre.lsp.protocol import Location, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        loc = Location(uri="file:///test.py", range=r)
        # URI must identify the target document unambiguously.
        assert loc.uri == "file:///test.py"
        # Range start line must be preserved for navigation precision.
        assert loc.range.start.line == 1

    def test_verify_diagnostic_fields(self):
        """Validate that Diagnostic carries message, severity, and source.

        The test constructs a :class:`Diagnostic` with a sample error and
        asserts each field because diagnostics drive the IDE underline and
        problem-panel display.
        """
        from encre.lsp.protocol import Diagnostic, Position, Range
        r = Range(start=Position(line=5, character=0), end=Position(line=5, character=10))
        diag = Diagnostic(
            range=r,
            message="Unused variable",
            severity=2,
            source="pyright",
        )
        # Message text must be preserved for user-facing error display.
        assert diag.message == "Unused variable"
        # Severity code must map to the LSP numeric scale (2 = warning).
        assert diag.severity == 2
        # Source identifies the diagnostic producer for filtering.
        assert diag.source == "pyright"

    def test_verify_hover_result_without_range(self):
        """Validate that HoverResult carries contents when no range is set.

        The test constructs a :class:`HoverResult` with an explicit string and
        no range, then asserts the content survives because hover popups rely
        on the contents field being present even when the annotation range is
        omitted (e.g. full-symbol hover).
        """
        from encre.lsp.protocol import HoverResult
        hr = HoverResult(contents="def foo(x: int) -> str", range=None)
        # Contents must be preserved for hover text rendering.
        assert hr.contents == "def foo(x: int) -> str"
        # Range must remain None to signal unbounded hover intent.
        assert hr.range is None

    def test_verify_hover_result_with_range(self):
        """Validate that HoverResult preserves a non-None range.

        The test constructs a :class:`HoverResult` with both contents and a
        :class:`Range` to ensure the range field is retained because precise
        highlight ranges are used for semantic token visual feedback.
        """
        from encre.lsp.protocol import HoverResult, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        hr = HoverResult(contents="def foo()", range=r)
        # Range must be non-None when explicitly provided.
        assert hr.range is not None

    def test_verify_lsp_state_running(self):
        """Validate that LSPState exposes status and optional error cleanly.

        The test constructs a :class:`LSPState` with status 'running' and
        asserts the status is preserved and error is None because the gateway
        uses this state to surface connection readiness to the client.
        """
        from encre.lsp.protocol import LSPState
        state = LSPState(status="running")
        # Status must reflect the live connection state.
        assert state.status == "running"
        # Error must be absent when the state is healthy.
        assert state.error is None

    def test_verify_lsp_state_with_error(self):
        """Validate that LSPState exposes an error message when unhealthy.

        The test constructs a :class:`LSPState` with status 'stopped' and an
        error string, then asserts both fields because error propagation is
        essential for client-side diagnostic reporting.
        """
        from encre.lsp.protocol import LSPState
        state = LSPState(status="stopped", error="connection refused")
        # Status must report the terminal failure state.
        assert state.status == "stopped"
        # Error string must carry the failure reason for display.
        assert state.error == "connection refused"


# ===========================================================================
# Git types
# ===========================================================================

class TestGitTypes:
    """Engineered to validate the Git repository state model.

    This test class exercises :class:`GitState`, :class:`GitDiffResult`, and
    :class:`EncreGitRepo` across default-state, populated-state, and diff
    scenarios to ensure that the git integration exposes a consistent snapshot
    of repository status for change-aware features such as context injection
    and diff-based retrieval.
    """

    def test_verify_git_state_defaults(self):
        """Validate that GitState applies sensible defaults when out of a repo.

        The test constructs a :class:`GitState` with in_repo=False and asserts
        the default values because codebase-context tools must not crash when
        the workspace is not a git repository.
        """
        from encre.git.repo import GitState
        gs = GitState(in_repo=False)
        # in_repo must remain False to signal no git metadata is available.
        assert gs.in_repo is False
        # is_clean defaults to True when there is no repository to poll.
        assert gs.is_clean is True
        # Empty changed-files and untracked-files lists must be safe to iterate.
        assert gs.changed_files == []
        assert gs.untracked_files == []

    def test_verify_git_state_populated(self):
        """Validate that GitState preserves full repository metadata.

        The test constructs a :class:`GitState` with all fields set and asserts
        they survive because session-level git context injection depends on
        accurate branch, commit, and worktree information.
        """
        from encre.git.repo import GitState
        gs = GitState(
            in_repo=True,
            commit_hash="abc123",
            branch="main",
            remote_url="https://github.com/example/repo",
            is_clean=True,
            changed_files=[],
            untracked_files=[],
            has_unpushed=False,
            worktree_count=1,
        )
        # in_repo must be True to gate all downstream git operations.
        assert gs.in_repo is True
        # Branch name must survive for context-aware prompt enrichment.
        assert gs.branch == "main"
        # Commit hash must be preserved for traceability.
        assert gs.commit_hash == "abc123"
        # Worktree count must reflect multi-worktree setups accurately.
        assert gs.worktree_count == 1

    def test_verify_git_diff_result_fields(self):
        """Validate that GitDiffResult preserves insertion/deletion counts.

        The test constructs a :class:`GitDiffResult` with sample statistics and
        asserts each field because diff metrics are surfaced to the user and
        consumed by cost-accounting and summary generators.
        """
        from encre.git.diff import GitDiffResult
        gdr = GitDiffResult(files=3, insertions=50, deletions=10)
        # File count must reflect the number of changed files.
        assert gdr.files == 3
        # Insertion count must be preserved for delta reporting.
        assert gdr.insertions == 50
        # Deletion count must be preserved for delta reporting.
        assert gdr.deletions == 10

    def test_verify_git_repo_instantiation(self):
        """Validate that EncreGitRepo constructs without error.

        The test creates an :class:`EncreGitRepo` pointing at the current
        workspace and asserts it is not None because the repo wrapper must be
        instantiable before any git-metadata query is issued.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        assert repo is not None

    def test_verify_git_repo_is_in_repo_returns_bool(self):
        """Validate that is_in_repo() returns a strict boolean.

        The test calls :meth:`EncreGitRepo.is_in_repo` and asserts the return
        type is bool because downstream guards use truthiness to gate all
        git-dependent context enrichment.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        # Return value must be a strict bool to avoid truthy-string bugs.
        assert isinstance(repo.is_in_repo(), bool)


# ===========================================================================
# Notebook types
# ===========================================================================

class TestNotebook:
    """Engineered to validate the notebook session model.

    This test class exercises :class:`EncreNotebookSession` across default and
    custom-kernel construction scenarios to ensure the session object exposes
    a reliable kernel identifier for notebook-based agent interactions.
    """

    def test_verify_session_default_kernel(self):
        """Validate that EncreNotebookSession defaults to python3 kernel.

        The test constructs a session with no explicit kernel and asserts
        kernel_name == 'python3' because the default kernel must match the
        runtime environment expected by the notebook execution layer.
        """
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Session must be instantiable without arguments.
        assert sess is not None
        # Default kernel must be python3 for standard notebook execution.
        assert sess.kernel_name == "python3"

    def test_verify_session_custom_kernel(self):
        """Validate that EncreNotebookSession accepts a custom kernel name.

        The test constructs a session with an explicit kernel specifier and
        asserts it is preserved because multi-version Python environments
        require per-session kernel targeting.
        """
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession(kernel_name="python3.12")
        # Kernel name must reflect the explicitly requested version.
        assert sess.kernel_name == "python3.12"


# ===========================================================================
# Server protocol types
# ===========================================================================

class TestServerProtocol:
    """Engineered to validate the server message protocol types.

    This test class exercises :class:`ClientRun`, :func:`parse_client_message`,
    and :func:`encode_server_message` across plaintext and encrypted transport
    paths to ensure the gateway's serialization layer round-trips messages
    correctly while preserving the encryption contract.
    """

    def test_verify_client_run_fields(self):
        """Validate that ClientRun exposes type, prompt, and session_id.

        The test constructs a :class:`ClientRun` message and asserts all three
        fields because the server dispatches on type, prompt content, and
        session routing independently.
        """
        from encre.server.protocol import ClientRun
        msg = ClientRun(prompt="Hello", session_id="s1")
        # Type discriminator must identify the message kind for dispatch.
        assert msg.type == "run"
        # Prompt text must be preserved verbatim for agent processing.
        assert msg.prompt == "Hello"
        # Session ID must route the message to the correct agent session.
        assert msg.session_id == "s1"

    def test_verify_client_run_from_dict(self):
        """Validate that ClientRun.from_dict reconstructs the message.

        The test deserializes a raw dictionary into a :class:`ClientRun` and
        asserts the resulting object exposes the expected type and prompt
        because the server accepts JSON over the wire and must parse reliably.
        """
        from encre.server.protocol import ClientRun
        msg = ClientRun.from_dict({"prompt": "Hello", "session_id": "s1"})
        # Deserialized type must still resolve to 'run'.
        assert msg.type == "run"
        # Deserialized prompt must match the original input.
        assert msg.prompt == "Hello"

    def test_verify_parse_client_message_valid_json(self):
        """Validate that parse_client_message returns a message for valid JSON.

        The test sends a JSON-encoded run message and asserts the parser
        returns a non-None result because the gateway must handle well-formed
        client frames without error.
        """
        import json

        from encre.server.protocol import parse_client_message
        raw = json.dumps({"type": "run", "prompt": "Hello", "session_id": "s1"})
        msg = parse_client_message(raw)
        # Parser must produce a message object for valid JSON input.
        assert msg is not None

    def test_verify_parse_client_message_invalid_json(self):
        """Validate that parse_client_message returns None for invalid input.

        The test sends a non-JSON string and asserts None is returned because
        the gateway must gracefully reject malformed frames rather than crash.
        """
        from encre.server.protocol import parse_client_message
        msg = parse_client_message("not json")
        # Parser must return None rather than raise on unparseable input.
        assert msg is None

    def test_verify_parse_client_message_ping(self):
        """Validate that ping frames are parsed successfully.

        The test sends a minimal JSON ping and asserts the result is not None
        because keepalive frames must never be treated as protocol errors.
        """
        import json

        from encre.server.protocol import parse_client_message
        raw = json.dumps({"type": "ping"})
        msg = parse_client_message(raw)
        # Ping frames must parse cleanly so the connection stays alive.
        assert msg is not None

    def test_verify_encode_server_message_plaintext_and_encrypted(self):
        """Validate plaintext and encrypted server-message paths.

        The test exercises both the ``encrypt=False`` path (content readable
        on the wire) and the default encrypted path (content opaque until
        decrypted) to guard against regressions where encryption breaks
        round-trip integrity.
        """
        import json

        from encre.crypto import decrypt
        from encre.server.protocol import encode_server_message

        # Plaintext path: the payload must remain visible without encryption.
        plaintext = encode_server_message("text_delta", text="Hello!", encrypt=False)
        assert isinstance(plaintext, str)
        assert "Hello!" in plaintext

        # Encrypted path: the ciphertext must hide the content and decrypt
        # must recover the exact original payload, guarding against
        # undecryptable-output regressions.
        encrypted = encode_server_message("text_delta", text="Hello!")
        assert isinstance(encrypted, str)
        assert "Hello!" not in encrypted
        recovered = json.loads(decrypt(encrypted))
        assert recovered == {"type": "text_delta", "text": "Hello!"}


# ===========================================================================
# Server session manager
# ===========================================================================

class TestSessionManager:
    """Engineered to validate the server session lifecycle.

    This test class exercises :class:`SessionInfo` and :class:`SessionManager`
    across creation, lookup, listing, and async removal scenarios to ensure
    the session registry maintains accurate active-session state during
    concurrent and sequential request handling.
    """

    def test_verify_session_info_fields(self):
        """Validate that SessionInfo exposes session_id and is_running.

        The test constructs a :class:`SessionInfo` with an agent and asserts
        the fields because session metadata drives UI indicators and routing.
        """
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionInfo
        agent = EncreAgent(config=EncreConfig(backend_type="openai", api_key="sk-fake"))
        si = SessionInfo(session_id="s1", agent=agent)
        # Session ID must identify the session in the registry.
        assert si.session_id == "s1"
        # is_running must default to False before any agent work begins.
        assert si.is_running is False

    def test_verify_session_manager_creation(self):
        """Validate that SessionManager starts with zero active sessions.

        The test constructs a fresh :class:`SessionManager` and asserts
        active_count == 0 because the registry must begin in a clean state
        before any client connects.
        """
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        # Manager must be instantiable.
        assert sm is not None
        # No sessions should be active on a fresh manager.
        assert sm.active_count == 0

    def test_verify_session_manager_create_session(self):
        """Validate that create_session increments the active count.

        The test creates a session via :meth:`SessionManager.create_session`
        and asserts the session ID is assigned and the active count rises to
        one because session allocation is the entry point for all requests.
        """
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        # A new session must receive a non-empty identifier.
        assert info.session_id is not None
        # Active count must increment to reflect the newly created session.
        assert sm.active_count == 1

    def test_verify_session_manager_get_session(self):
        """Validate that get_session retrieves a previously created session.

        The test creates a session and then fetches it by ID and asserts the
        retrieved object matches the original because session retrieval is
        the primary lookup path for every incoming request.
        """
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        retrieved = sm.get_session(info.session_id)
        # Retrieved session must not be None for an existing ID.
        assert retrieved is not None
        # Retrieved session ID must match the original allocation.
        assert retrieved.session_id == info.session_id

    def test_verify_session_manager_list_sessions(self):
        """Validate that list_sessions reflects currently active sessions.

        The test creates one session and asserts the list length equals one
        because external monitors and admin endpoints rely on accurate counts.
        """
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        sessions = sm.list_sessions()
        # List length must match the number of created sessions.
        assert len(sessions) == 1

    def test_verify_session_manager_remove_session(self):
        """Validate that remove_session decrements the active count asynchronously.

        The test creates a session, awaits :meth:`SessionManager.remove_session`,
        and asserts the active count drops to zero and the session is no longer
        retrievable because session cleanup must be idempotent and leak-free.
        """
        import asyncio

        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        asyncio.run(sm.remove_session(info.session_id))
        # Active count must drop to zero after removal.
        assert sm.active_count == 0
        # Removed session must no longer be retrievable.
        assert sm.get_session(info.session_id) is None


# ===========================================================================
# Agent / Loop / Goal types
# ===========================================================================

class TestAgentTypes:
    """Engineered to validate the agent goal-loop and checkpoint model.

    This test class exercises :class:`GoalDefinition`, :class:`GoalResult`,
    :class:`GoalStatus`, :class:`GoalEvent`, :class:`SessionCheckpoint`,
    :class:`EncreGoalLoop`, and :class:`EncreGoalRunner` to ensure the
    agent's high-level orchestration types behave correctly during goal
    execution, status tracking, and checkpoint recording.
    """

    def test_verify_goal_definition_fields(self):
        """Validate that GoalDefinition stores description and criteria.

        The test constructs a :class:`GoalDefinition` with all key fields and
        asserts they survive because the goal loop reads these to drive
        planning and success evaluation.
        """
        from encre.goal import GoalDefinition
        gd = GoalDefinition(description="Test feature", success_criteria="All tests pass", max_attempts=5)  # noqa: E501
        # Description must be preserved for planner visibility.
        assert gd.description == "Test feature"
        # Success criteria must be preserved for goal-evaluation gating.
        assert gd.success_criteria == "All tests pass"
        # Max attempts must constrain retry budget correctly.
        assert gd.max_attempts == 5

    def test_verify_goal_result_status(self):
        """Validate that GoalResult exposes status and attempt count.

        The test constructs a :class:`GoalResult` with SUCCESS status and
        asserts the fields because the agent loop reads this to decide
        whether to continue or terminate the goal cycle.
        """
        from encre.goal import GoalResult, GoalStatus
        gr = GoalResult(status=GoalStatus.SUCCESS, summary="Done", attempts=3)
        # Status must reflect successful completion.
        assert gr.status == GoalStatus.SUCCESS
        # Attempt count must record how many cycles were executed.
        assert gr.attempts == 3

    def test_verify_goal_status_constants(self):
        """Validate that all GoalStatus enum members are defined and non-None.

        The test asserts each status constant exists because the goal loop
        and result models depend on a complete status alphabet to encode
        every lifecycle transition.
        """
        from encre.goal import GoalStatus
        # PENDING must be defined to represent the initial unsatisfied state.
        assert GoalStatus.PENDING is not None
        # IN_PROGRESS must be defined to represent active execution.
        assert GoalStatus.IN_PROGRESS is not None
        # SUCCESS must be defined to represent completion without failure.
        assert GoalStatus.SUCCESS is not None
        # FAILED must be defined to represent an unrecoverable error state.
        assert GoalStatus.FAILED is not None
        # TIMEOUT must be defined to represent a time-bound exit condition.
        assert GoalStatus.TIMEOUT is not None
        # MAX_ATTEMPTS must be defined to represent budget exhaustion.
        assert GoalStatus.MAX_ATTEMPTS is not None

    def test_verify_goal_event_fields(self):
        """Validate that GoalEvent carries status, attempt, and message.

        The test constructs a :class:`GoalEvent` during an in-progress cycle
        and asserts each field because event streams are consumed by the
        UI and by checkpoint serializers.
        """
        from encre.goal import GoalEvent, GoalStatus
        ge = GoalEvent(status=GoalStatus.IN_PROGRESS, attempt=1, message="Working...")
        # Event status must reflect the current goal state.
        assert ge.status == GoalStatus.IN_PROGRESS
        # Attempt number must increment across cycles for auditability.
        assert ge.attempt == 1
        # Message must carry human-readable progress context.
        assert ge.message == "Working..."

    def test_verify_session_checkpoint_fields(self):
        """Validate that SessionCheckpoint records turn and tool-call counts.

        The test constructs a :class:`SessionCheckpoint` and asserts the
        counter fields because checkpoints are used to resume sessions and
        to bound per-cycle resource usage.
        """
        from encre.session import SessionCheckpoint
        sc = SessionCheckpoint(
            checkpoint_id="ckpt1",
            label="After turn 5",
            turn_count=5,
            tool_call_count=10,
        )
        # Checkpoint ID must identify the resume point uniquely.
        assert sc.checkpoint_id == "ckpt1"
        # Turn count must reflect completed interaction cycles.
        assert sc.turn_count == 5
        # Tool-call count must reflect resource consumption at the checkpoint.
        assert sc.tool_call_count == 10

    def test_verify_goal_loop_instantiation(self):
        """Validate that EncreGoalLoop constructs with the provided agent.

        The test creates an :class:`EncreGoalLoop` backed by a fake agent and
        asserts the internal description field is set because the loop uses
        this to drive planning and to report progress back to callers.
        """
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop
        agent = EncreAgent(config=EncreConfig(backend_type="openai", api_key="sk-fake"))
        loop = EncreGoalLoop(agent=agent, description="test", success_criteria="works")
        # Loop must be instantiable without raising.
        assert loop is not None
        # Internal description must match the constructor argument.
        assert loop._description == "test"

    def test_verify_goal_runner_instantiation(self):
        """Validate that EncreGoalRunner wires all required subsystems.

        The test constructs an :class:`EncreGoalRunner` with a config, tool
        registry, hook system, and safety engine, then asserts it is not None
        because the runner is the central orchestrator that must exist before
        any goal-execution cycle begins.
        """
        from encre.config import EncreConfig
        from encre.goal import EncreGoalRunner
        from encre.hooks.system import EncreHookSystem
        from encre.safety import EncreSafetyEngine
        from encre.tools.registry import ToolRegistry
        config = EncreConfig(backend_type="openai", api_key="sk-fake")
        registry = ToolRegistry()
        hooks = EncreHookSystem()
        safety = EncreSafetyEngine(config=config)
        runner = EncreGoalRunner(
            config=config,
            tool_registry=registry,
            hook_system=hooks,
            safety=safety,
        )
        # Runner must be instantiable with all dependencies wired.
        assert runner is not None
