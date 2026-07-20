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

"""Tests for codebase indexer, LSP protocol, git, notebook, server types."""



# ===========================================================================
# Codebase Indexer types
# ===========================================================================

class TestCodeIndex:
    """Test suite for CodeIndex."""
    def test_module_info(self):
        """Test: Module info."""
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(
            path="src/my_module.py",
            name="my_module",
            language="python",
            exports=["func_a", "ClassB"],
            imports=["os", "json"],
        )
        # Verify: mi.name == "my_module"
        assert mi.name == "my_module"
        # Verify: mi.language == "python"
        assert mi.language == "python"
        # Verify: "func_a" in mi.exports
        assert "func_a" in mi.exports
        # Verify: "os" in mi.imports
        assert "os" in mi.imports

    def test_module_info_defaults(self):
        """Test: Module info defaults."""
        from encre.codebase.indexer import ModuleInfo
        mi = ModuleInfo(path="test.py", name="test")
        # Verify: mi.imports == []
        assert mi.imports == []
        # Verify: mi.imported_by == []
        assert mi.imported_by == []
        # Verify: mi.exports == []
        assert mi.exports == []
        # Verify: mi.language == ""
        assert mi.language == ""
        # Verify: mi.loc == 0
        assert mi.loc == 0

    def test_code_index_create(self):
        """Test: Code index create."""
        from encre.codebase.indexer import EncreCodeIndex
        ci = EncreCodeIndex(workspace=".")
        # Verify: ci is not None
        assert ci is not None


# ===========================================================================
# LSP types
# ===========================================================================

class TestLSPProtocol:
    """Test suite for LSPProtocol."""
    def test_position(self):
        """Test: Position."""
        from encre.lsp.protocol import Position
        p = Position(line=10, character=5)
        # Verify: p.line == 10
        assert p.line == 10
        # Verify: p.character == 5
        assert p.character == 5

    def test_range(self):
        """Test: Range."""
        from encre.lsp.protocol import Position, Range
        start = Position(line=0, character=0)
        end = Position(line=10, character=20)
        r = Range(start=start, end=end)
        # Verify: r.start.line == 0
        assert r.start.line == 0
        # Verify: r.end.line == 10
        assert r.end.line == 10

    def test_location(self):
        """Test: Location."""
        from encre.lsp.protocol import Location, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        loc = Location(uri="file:///test.py", range=r)
        # Verify: loc.uri == "file:///test.py"
        assert loc.uri == "file:///test.py"
        # Verify: loc.range.start.line == 1
        assert loc.range.start.line == 1

    def test_diagnostic(self):
        """Test: Diagnostic."""
        from encre.lsp.protocol import Diagnostic, Position, Range
        r = Range(start=Position(line=5, character=0), end=Position(line=5, character=10))
        diag = Diagnostic(
            range=r,
            message="Unused variable",
            severity=2,
            source="pyright",
        )
        # Verify: diag.message == "Unused variable"
        assert diag.message == "Unused variable"
        # Verify: diag.severity == 2
        assert diag.severity == 2
        # Verify: diag.source == "pyright"
        assert diag.source == "pyright"

    def test_hover_result(self):
        """Test: Hover result."""
        from encre.lsp.protocol import HoverResult
        hr = HoverResult(contents="def foo(x: int) -> str", range=None)
        # Verify: hr.contents == "def foo(x: int) -> str"
        assert hr.contents == "def foo(x: int) -> str"
        # Verify: hr.range is None
        assert hr.range is None

    def test_hover_result_with_range(self):
        """Test: Hover result with range."""
        from encre.lsp.protocol import HoverResult, Position, Range
        r = Range(start=Position(line=1, character=0), end=Position(line=1, character=10))
        hr = HoverResult(contents="def foo()", range=r)
        # Verify: hr.range is not None
        assert hr.range is not None

    def test_lsp_state(self):
        """Test: Lsp state."""
        from encre.lsp.protocol import LSPState
        state = LSPState(status="running")
        # Verify: state.status == "running"
        assert state.status == "running"
        # Verify: state.error is None
        assert state.error is None

    def test_lsp_state_with_error(self):
        """Test: Lsp state with error."""
        from encre.lsp.protocol import LSPState
        state = LSPState(status="stopped", error="connection refused")
        # Verify: state.status == "stopped"
        assert state.status == "stopped"
        # Verify: state.error == "connection refused"
        assert state.error == "connection refused"


# ===========================================================================
# Git types
# ===========================================================================

class TestGitTypes:
    """Test suite for GitTypes."""
    def test_git_state_default(self):
        """Test: Git state default."""
        from encre.git.repo import GitState
        gs = GitState(in_repo=False)
        # Verify: gs.in_repo is False
        assert gs.in_repo is False
        # Verify: gs.is_clean is True
        assert gs.is_clean is True
        # Verify: gs.changed_files == []
        assert gs.changed_files == []
        # Verify: gs.untracked_files == []
        assert gs.untracked_files == []

    def test_git_state_in_repo(self):
        """Test: Git state in repo."""
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
        # Verify: gs.in_repo is True
        assert gs.in_repo is True
        # Verify: gs.branch == "main"
        assert gs.branch == "main"
        # Verify: gs.commit_hash == "abc123"
        assert gs.commit_hash == "abc123"
        # Verify: gs.worktree_count == 1
        assert gs.worktree_count == 1

    def test_git_diff_result(self):
        """Test: Git diff result."""
        from encre.git.diff import GitDiffResult
        gdr = GitDiffResult(files=3, insertions=50, deletions=10)
        # Verify: gdr.files == 3
        assert gdr.files == 3
        # Verify: gdr.insertions == 50
        assert gdr.insertions == 50
        # Verify: gdr.deletions == 10
        assert gdr.deletions == 10

    def test_git_repo_creation(self):
        """Test: Git repo creation."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        # Verify: repo is not None
        assert repo is not None

    def test_git_repo_is_in_repo(self):
        """Test: Git repo is in repo."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        # Verify: isinstance(repo.is_in_repo(), bool)
        assert isinstance(repo.is_in_repo(), bool)


# ===========================================================================
# Notebook types
# ===========================================================================

class TestNotebook:
    """Test suite for Notebook."""
    def test_session_create(self):
        """Test: Session create."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession()
        # Verify: sess is not None
        assert sess is not None
        # Verify: sess.kernel_name == "python3"
        assert sess.kernel_name == "python3"

    def test_session_create_custom_kernel(self):
        """Test: Session create custom kernel."""
        from encre.notebook.session import EncreNotebookSession
        sess = EncreNotebookSession(kernel_name="python3.12")
        # Verify: sess.kernel_name == "python3.12"
        assert sess.kernel_name == "python3.12"


# ===========================================================================
# Server protocol types
# ===========================================================================

class TestServerProtocol:
    """Test suite for ServerProtocol."""
    def test_client_run(self):
        """Test: Client run."""
        from encre.server.protocol import ClientRun
        msg = ClientRun(prompt="Hello", session_id="s1")
        # Verify: msg.type == "run"
        assert msg.type == "run"
        # Verify: msg.prompt == "Hello"
        assert msg.prompt == "Hello"
        # Verify: msg.session_id == "s1"
        assert msg.session_id == "s1"

    def test_client_run_from_dict(self):
        """Test: Client run from dict."""
        from encre.server.protocol import ClientRun
        msg = ClientRun.from_dict({"prompt": "Hello", "session_id": "s1"})
        # Verify: msg.type == "run"
        assert msg.type == "run"
        # Verify: msg.prompt == "Hello"
        assert msg.prompt == "Hello"

    def test_parse_client_message(self):
        """Test: Parse client message."""
        import json

        from encre.server.protocol import parse_client_message
        raw = json.dumps({"type": "run", "prompt": "Hello", "session_id": "s1"})
        msg = parse_client_message(raw)
        # Verify: msg is not None
        assert msg is not None

    def test_parse_client_message_invalid(self):
        """Test: Parse client message invalid."""
        from encre.server.protocol import parse_client_message
        msg = parse_client_message("not json")
        # Verify: msg is None
        assert msg is None

    def test_parse_client_message_ping(self):
        """Test: Parse client message ping."""
        import json

        from encre.server.protocol import parse_client_message
        raw = json.dumps({"type": "ping"})
        msg = parse_client_message(raw)
        # Verify: msg is not None
        assert msg is not None

    def test_encode_server_message(self):
        """Test: Encode server message (plaintext path + encrypted round-trip)."""
        import json

        from encre.crypto import decrypt
        from encre.server.protocol import encode_server_message

        # Plaintext path (encrypt=False) keeps the content readable on the wire.
        plaintext = encode_server_message("text_delta", text="Hello!", encrypt=False)
        assert isinstance(plaintext, str)
        assert "Hello!" in plaintext

        # Encrypted path (the default) round-trips via decrypt: the ciphertext
        # is opaque (the content is NOT visible) and decrypting recovers the
        # exact payload.  This guards against a regression where encryption
        # produces undecryptable output.
        encrypted = encode_server_message("text_delta", text="Hello!")
        assert isinstance(encrypted, str)
        assert "Hello!" not in encrypted
        recovered = json.loads(decrypt(encrypted))
        assert recovered == {"type": "text_delta", "text": "Hello!"}


# ===========================================================================
# Server session manager
# ===========================================================================

class TestSessionManager:
    """Test suite for SessionManager."""
    def test_session_info(self):
        """Test: Session info."""
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionInfo
        agent = EncreAgent(config=EncreConfig(backend_type="openai", api_key="sk-fake"))
        si = SessionInfo(session_id="s1", agent=agent)
        # Verify: si.session_id == "s1"
        assert si.session_id == "s1"
        # Verify: si.is_running is False
        assert si.is_running is False

    def test_session_manager_create(self):
        """Test: Session manager create."""
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        # Verify: sm is not None
        assert sm is not None
        # Verify: sm.active_count == 0
        assert sm.active_count == 0

    def test_session_manager_create_session(self):
        """Test: Session manager create session."""
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        # Verify: info.session_id is not None
        assert info.session_id is not None
        # Verify: sm.active_count == 1
        assert sm.active_count == 1

    def test_session_manager_get_session(self):
        """Test: Session manager get session."""
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        retrieved = sm.get_session(info.session_id)
        # Verify: retrieved is not None
        assert retrieved is not None
        # Verify: retrieved.session_id == info.session_id
        assert retrieved.session_id == info.session_id

    def test_session_manager_list_sessions(self):
        """Test: Session manager list sessions."""
        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        sessions = sm.list_sessions()
        # Verify: len(sessions) == 1
        assert len(sessions) == 1

    def test_session_manager_remove(self):
        """Test: Session manager remove (remove_session is async -- awaiting
        it must drop the session from the active set)."""
        import asyncio

        from encre.config import EncreConfig
        from encre.server.session_manager import SessionManager
        sm = SessionManager()
        info = sm.create_session(EncreConfig(backend_type="openai", api_key="sk-fake"))
        asyncio.run(sm.remove_session(info.session_id))
        # Verify: sm.active_count == 0
        assert sm.active_count == 0
        # Verify: sm.get_session(info.session_id) is None
        assert sm.get_session(info.session_id) is None


# ===========================================================================
# Agent / Loop / Goal types
# ===========================================================================

class TestAgentTypes:
    """Test suite for AgentTypes."""
    def test_goal_definition(self):
        """Test: Goal definition."""
        from encre.goal import GoalDefinition
        gd = GoalDefinition(description="Test feature", success_criteria="All tests pass", max_attempts=5)  # noqa: E501
        # Verify: gd.description == "Test feature"
        assert gd.description == "Test feature"
        # Verify: gd.success_criteria == "All tests pass"
        assert gd.success_criteria == "All tests pass"
        # Verify: gd.max_attempts == 5
        assert gd.max_attempts == 5

    def test_goal_result(self):
        """Test: Goal result."""
        from encre.goal import GoalResult, GoalStatus
        gr = GoalResult(status=GoalStatus.SUCCESS, summary="Done", attempts=3)
        # Verify: gr.status == GoalStatus.SUCCESS
        assert gr.status == GoalStatus.SUCCESS
        # Verify: gr.attempts == 3
        assert gr.attempts == 3

    def test_goal_status(self):
        """Test: Goal status."""
        from encre.goal import GoalStatus
        # Verify: GoalStatus.PENDING is not None
        assert GoalStatus.PENDING is not None
        # Verify: GoalStatus.IN_PROGRESS is not None
        assert GoalStatus.IN_PROGRESS is not None
        # Verify: GoalStatus.SUCCESS is not None
        assert GoalStatus.SUCCESS is not None
        # Verify: GoalStatus.FAILED is not None
        assert GoalStatus.FAILED is not None
        # Verify: GoalStatus.TIMEOUT is not None
        assert GoalStatus.TIMEOUT is not None
        # Verify: GoalStatus.MAX_ATTEMPTS is not None
        assert GoalStatus.MAX_ATTEMPTS is not None

    def test_goal_event(self):
        """Test: Goal event."""
        from encre.goal import GoalEvent, GoalStatus
        ge = GoalEvent(status=GoalStatus.IN_PROGRESS, attempt=1, message="Working...")
        # Verify: ge.status == GoalStatus.IN_PROGRESS
        assert ge.status == GoalStatus.IN_PROGRESS
        # Verify: ge.attempt == 1
        assert ge.attempt == 1
        # Verify: ge.message == "Working..."
        assert ge.message == "Working..."

    def test_session_checkpoint(self):
        """Test: Session checkpoint."""
        from encre.session import SessionCheckpoint
        sc = SessionCheckpoint(
            checkpoint_id="ckpt1",
            label="After turn 5",
            turn_count=5,
            tool_call_count=10,
        )
        # Verify: sc.checkpoint_id == "ckpt1"
        assert sc.checkpoint_id == "ckpt1"
        # Verify: sc.turn_count == 5
        assert sc.turn_count == 5
        # Verify: sc.tool_call_count == 10
        assert sc.tool_call_count == 10

    def test_goal_loop_create(self):
        """Test: Goal loop create."""
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.goal import EncreGoalLoop
        agent = EncreAgent(config=EncreConfig(backend_type="openai", api_key="sk-fake"))
        loop = EncreGoalLoop(agent=agent, description="test", success_criteria="works")
        # Verify: loop is not None
        assert loop is not None
        # Verify: loop._description == "test"
        assert loop._description == "test"

    def test_goal_runner_create(self):
        """Test: Goal runner create."""
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
        # Verify: runner is not None
        assert runner is not None
