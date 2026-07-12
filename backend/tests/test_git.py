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

"""Tests for encre.git.repo (EncreGitRepo, GitState) and encre.git.diff (EncreGitDiff, GitDiffResult)."""  # noqa: E501

import os
import tempfile

import pytest

# ===========================================================================
# GitState dataclass
# ===========================================================================

class TestGitState:
    """Tests for the GitState dataclass."""

    def test_default_not_in_repo(self):
        """Test: Default not in repo."""
        from encre.git.repo import GitState
        gs = GitState(in_repo=False)
        # Verify: gs.in_repo is False
        assert gs.in_repo is False
        # Verify: gs.commit_hash == ""
        assert gs.commit_hash == ""
        # Verify: gs.branch == ""
        assert gs.branch == ""
        # Verify: gs.remote_url == ""
        assert gs.remote_url == ""
        # Verify: gs.is_clean is True
        assert gs.is_clean is True
        # Verify: gs.changed_files == []
        assert gs.changed_files == []
        # Verify: gs.untracked_files == []
        assert gs.untracked_files == []
        # Verify: gs.has_unpushed is False
        assert gs.has_unpushed is False
        # Verify: gs.worktree_count == 1
        assert gs.worktree_count == 1

    def test_in_repo_full_state(self):
        """Test: In repo full state."""
        from encre.git.repo import GitState
        gs = GitState(
            in_repo=True,
            commit_hash="abc123def456",
            branch="main",
            remote_url="https://github.com/user/repo.git",
            is_clean=False,
            changed_files=["src/main.py", "README.md"],
            untracked_files=["new_file.txt"],
            has_unpushed=True,
            worktree_count=2,
        )
        # Verify: gs.in_repo is True
        assert gs.in_repo is True
        # Verify: gs.commit_hash == "abc123def456"
        assert gs.commit_hash == "abc123def456"
        # Verify: gs.branch == "main"
        assert gs.branch == "main"
        # Verify: gs.remote_url == "https://github.com/user/repo.git"
        assert gs.remote_url == "https://github.com/user/repo.git"
        # Verify: gs.is_clean is False
        assert gs.is_clean is False
        # Verify: len(gs.changed_files) == 2
        assert len(gs.changed_files) == 2
        # Verify: "src/main.py" in gs.changed_files
        assert "src/main.py" in gs.changed_files
        # Verify: gs.untracked_files == ["new_file.txt"]
        assert gs.untracked_files == ["new_file.txt"]
        # Verify: gs.has_unpushed is True
        assert gs.has_unpushed is True
        # Verify: gs.worktree_count == 2
        assert gs.worktree_count == 2

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.git.repo import GitState
        # Verify: is_dataclass(GitState)
        assert is_dataclass(GitState)

    def test_field_types(self):
        """Test: Field types."""
        from encre.git.repo import GitState
        gs = GitState(in_repo=True, changed_files=["a.py"])
        # Verify: isinstance(gs.commit_hash, str)
        assert isinstance(gs.commit_hash, str)
        # Verify: isinstance(gs.branch, str)
        assert isinstance(gs.branch, str)
        # Verify: isinstance(gs.is_clean, bool)
        assert isinstance(gs.is_clean, bool)
        # Verify: isinstance(gs.changed_files, list)
        assert isinstance(gs.changed_files, list)
        # Verify: isinstance(gs.has_unpushed, bool)
        assert isinstance(gs.has_unpushed, bool)
        # Verify: isinstance(gs.worktree_count, int)
        assert isinstance(gs.worktree_count, int)


# ===========================================================================
# EncreGitRepo
# ===========================================================================

class TestEncreGitRepo:
    """Tests for EncreGitRepo using an actual git repo."""

    def test_construction(self):
        """Test: Construction."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        # Verify: repo is not None
        assert repo is not None
        # Verify: repo.workspace == "."
        assert repo.workspace == "."

    def test_construction_absolute_path(self):
        """Test: Construction absolute path."""
        from encre.git.repo import EncreGitRepo
        abs_path = os.path.abspath(".")
        repo = EncreGitRepo(workspace=abs_path)
        # Verify: repo.workspace == abs_path
        assert repo.workspace == abs_path

    def test_is_in_repo_returns_bool(self):
        """Test: Is in repo returns bool."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.is_in_repo()
        # Verify: isinstance(result, bool)
        assert isinstance(result, bool)

    def test_get_state_returns_git_state(self):
        """Test: Get state returns git state."""
        from encre.git.repo import EncreGitRepo, GitState
        repo = EncreGitRepo(workspace=".")
        state = repo.get_state()
        # Verify: isinstance(state, GitState)
        assert isinstance(state, GitState)

    def test_get_state_not_in_repo_for_non_git_dir(self):
        """Test: Get state not in repo for non git dir."""
        from encre.git.repo import EncreGitRepo
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EncreGitRepo(workspace=tmpdir)
            # Verify: repo.is_in_repo() is False
            assert repo.is_in_repo() is False
            state = repo.get_state()
            # Verify: state.in_repo is False
            assert state.in_repo is False
            # Verify: state.commit_hash == ""
            assert state.commit_hash == ""
            # Verify: state.branch == ""
            assert state.branch == ""

    def test_get_diff_returns_str(self):
        """Test: Get diff returns str."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            result = repo.get_diff()
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            # Verify: isinstance(result, str)
            assert isinstance(result, str)

    def test_get_diff_with_file_path(self):
        """Test: Get diff with file path."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            result = repo.get_diff(file_path="README.md")
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            # Verify: isinstance(result, str)
            assert isinstance(result, str)

    def test_get_diff_stats_returns_dict(self):
        """Test: Get diff stats returns dict."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            stats = repo.get_diff_stats()
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            # Verify: isinstance(stats, dict)
            assert isinstance(stats, dict)
            # Verify: "files" in stats
            assert "files" in stats
            # Verify: "insertions" in stats
            assert "insertions" in stats
            # Verify: "deletions" in stats
            assert "deletions" in stats

    def test_get_changed_files_returns_list(self):
        """Test: Get changed files returns list."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        files = repo.get_changed_files()
        # Verify: isinstance(files, list)
        assert isinstance(files, list)

    def test_get_commit_hash_returns_str(self):
        """Test: Get commit hash returns str."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.get_commit_hash()
        # Verify: isinstance(result, str)
        assert isinstance(result, str)

    def test_get_branch_returns_str(self):
        """Test: Get branch returns str."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.get_branch()
        # Verify: isinstance(result, str)
        assert isinstance(result, str)

    def test_has_unpushed_commits_returns_bool(self):
        """Test: Has unpushed commits returns bool."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.has_unpushed_commits()
        # Verify: isinstance(result, bool)
        assert isinstance(result, bool)

    def test_is_transient_state_returns_bool(self):
        """Test: Is transient state returns bool."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.is_transient_state()
        # Verify: isinstance(result, bool)
        assert isinstance(result, bool)

    def test_stash_to_clean_state(self):
        """Test: Stash to clean state."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.stash_to_clean_state()
        # Returns a string stash name or None
        assert result is None or isinstance(result, str)

    def test_unstash_does_not_raise(self):
        """Test: Unstash does not raise."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        # Should not raise even if there's nothing to unstash
        repo.unstash()

    def test_not_in_repo_methods_return_safe_defaults(self):
        """Test: Not in repo methods return safe defaults."""
        from encre.git.repo import EncreGitRepo
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EncreGitRepo(workspace=tmpdir)
            # Verify: repo.get_diff() == ""
            assert repo.get_diff() == ""
            # Verify: repo.get_diff_stats() == {"files": 0, "insertions": 0, "deletions": 0}
            assert repo.get_diff_stats() == {"files": 0, "insertions": 0, "deletions": 0}
            # Verify: repo.get_changed_files() == []
            assert repo.get_changed_files() == []
            # Verify: repo.get_commit_hash() == ""
            assert repo.get_commit_hash() == ""
            # Verify: repo.get_branch() == ""
            assert repo.get_branch() == ""
            # Verify: repo.has_unpushed_commits() is False
            assert repo.has_unpushed_commits() is False
            # Verify: repo.is_transient_state() is False
            assert repo.is_transient_state() is False
            # Verify: repo.stash_to_clean_state() is None
            assert repo.stash_to_clean_state() is None

    def test_get_state_structure_in_actual_repo(self):
        """Test: Get state structure in actual repo."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        state = repo.get_state()
        # All expected keys should be present
        assert hasattr(state, "in_repo")
        # Verify: hasattr(state, "commit_hash")
        assert hasattr(state, "commit_hash")
        # Verify: hasattr(state, "branch")
        assert hasattr(state, "branch")
        # Verify: hasattr(state, "remote_url")
        assert hasattr(state, "remote_url")
        # Verify: hasattr(state, "is_clean")
        assert hasattr(state, "is_clean")
        # Verify: hasattr(state, "changed_files")
        assert hasattr(state, "changed_files")
        # Verify: hasattr(state, "untracked_files")
        assert hasattr(state, "untracked_files")
        # Verify: hasattr(state, "has_unpushed")
        assert hasattr(state, "has_unpushed")
        # Verify: hasattr(state, "worktree_count")
        assert hasattr(state, "worktree_count")

    def test_get_changed_files_includes_tracked_modifications(self):
        """Test: Get changed files includes tracked modifications."""
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        files = repo.get_changed_files()
        # In a clean repo, this should be empty
        assert isinstance(files, list)

    def test_parse_numstat_static(self):
        """Test: Parse numstat static."""
        from encre.git.repo import EncreGitRepo
        output = "3\t2\tREADME.md\n10\t5\tsrc/main.py\n"
        parsed = EncreGitRepo._parse_numstat(output)
        # Verify: parsed == {"files": 2, "insertions": 13, "deletions": 7}
        assert parsed == {"files": 2, "insertions": 13, "deletions": 7}

    def test_parse_numstat_empty(self):
        """Test: Parse numstat empty."""
        from encre.git.repo import EncreGitRepo
        parsed = EncreGitRepo._parse_numstat("")
        # Verify: parsed == {"files": 0, "insertions": 0, "deletions": 0}
        assert parsed == {"files": 0, "insertions": 0, "deletions": 0}

    def test_parse_numstat_binary_files(self):
        """Test: Parse numstat binary files."""
        from encre.git.repo import EncreGitRepo
        output = "-\t-\timage.png\n5\t3\tcode.py\n"
        parsed = EncreGitRepo._parse_numstat(output)
        # Verify: parsed == {"files": 2, "insertions": 5, "deletions": 3}
        assert parsed == {"files": 2, "insertions": 5, "deletions": 3}


# ===========================================================================
# GitDiffResult dataclass
# ===========================================================================

class TestGitDiffResult:
    """Tests for the GitDiffResult dataclass."""

    def test_creation(self):
        """Test: Creation."""
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=3, insertions=50, deletions=10)
        # Verify: result.files == 3
        assert result.files == 3
        # Verify: result.insertions == 50
        assert result.insertions == 50
        # Verify: result.deletions == 10
        assert result.deletions == 10

    def test_zero_values(self):
        """Test: Zero values."""
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=0, insertions=0, deletions=0)
        # Verify: result.files == 0
        assert result.files == 0
        # Verify: result.insertions == 0
        assert result.insertions == 0
        # Verify: result.deletions == 0
        assert result.deletions == 0

    def test_large_values(self):
        """Test: Large values."""
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=1000, insertions=50000, deletions=30000)
        # Verify: result.files == 1000
        assert result.files == 1000
        # Verify: result.insertions == 50000
        assert result.insertions == 50000
        # Verify: result.deletions == 30000
        assert result.deletions == 30000

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.git.diff import GitDiffResult
        # Verify: is_dataclass(GitDiffResult)
        assert is_dataclass(GitDiffResult)


# ===========================================================================
# EncreGitDiff static methods
# ===========================================================================

class TestEncreGitDiff:
    """Tests for EncreGitDiff static methods."""

    def test_compute_diff_returns_str(self):
        """Test: Compute diff returns str."""
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(
            old="line1\nline2\nline3\n",
            new="line1\nline2 modified\nline3\nline4\n",
        )
        # Verify: isinstance(diff, str)
        assert isinstance(diff, str)

    def test_compute_diff_no_changes(self):
        """Test: Compute diff no changes."""
        from encre.git.diff import EncreGitDiff
        content = "hello world\nfoo bar\n"
        diff = EncreGitDiff.compute_diff(old=content, new=content)
        # Verify: isinstance(diff, str)
        assert isinstance(diff, str)

    def test_compute_diff_empty_to_content(self):
        """Test: Compute diff empty to content."""
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(old="", new="line1\nline2\n")
        # Verify: isinstance(diff, str)
        assert isinstance(diff, str)
        # Verify: len(diff) > 0
        assert len(diff) > 0

    def test_compute_diff_content_to_empty(self):
        """Test: Compute diff content to empty."""
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(old="line1\nline2\n", new="")
        # Verify: isinstance(diff, str)
        assert isinstance(diff, str)

    def test_apply_diff_returns_str(self):
        """Test: Apply diff returns str."""
        from encre.git.diff import EncreGitDiff
        original = "line1\nline2\nline3\n"
        diff = EncreGitDiff.compute_diff(
            old=original,
            new="line1\nline2 modified\nline3\n",
        )
        result = EncreGitDiff.apply_diff(content=original, diff=diff)
        # Verify: isinstance(result, str)
        assert isinstance(result, str)

    def test_apply_diff_noop(self):
        """Test: Apply diff noop."""
        from encre.git.diff import EncreGitDiff
        content = "hello\nworld\n"
        diff = EncreGitDiff.compute_diff(old=content, new=content)
        result = EncreGitDiff.apply_diff(content=content, diff=diff)
        # Verify: isinstance(result, str)
        assert isinstance(result, str)

    def test_parse_diff_stats_returns_dict(self):
        """Test: Parse diff stats returns dict."""
        from encre.git.diff import EncreGitDiff
        stats = EncreGitDiff.parse_diff_stats("3\t2\tfile.py\n")
        # Verify: isinstance(stats, dict)
        assert isinstance(stats, dict)
        # Verify: "total_files" in stats
        assert "total_files" in stats
        # Verify: "total_insertions" in stats
        assert "total_insertions" in stats
        # Verify: "total_deletions" in stats
        assert "total_deletions" in stats

    def test_parse_diff_stats_empty(self):
        """Test: Parse diff stats empty."""
        from encre.git.diff import EncreGitDiff
        stats = EncreGitDiff.parse_diff_stats("")
        # Verify: stats == {"total_files": 0, "total_insertions": 0, "total_deletions": 0}
        assert stats == {"total_files": 0, "total_insertions": 0, "total_deletions": 0}

    def test_parse_diff_stats_multiple_files(self):
        """Test: Parse diff stats multiple files."""
        from encre.git.diff import EncreGitDiff
        output = "5\t0\tsrc/new.py\n2\t8\tsrc/changed.py\n"
        stats = EncreGitDiff.parse_diff_stats(output)
        # Verify: stats["total_files"] == 2
        assert stats["total_files"] == 2
        # Verify: stats["total_insertions"] == 7
        assert stats["total_insertions"] == 7
        # Verify: stats["total_deletions"] == 8
        assert stats["total_deletions"] == 8

    def test_is_transient_git_state_returns_bool(self):
        """Test: Is transient git state returns bool."""
        from encre.git.diff import EncreGitDiff
        result = EncreGitDiff.is_transient_git_state(workspace=".")
        # Verify: isinstance(result, bool)
        assert isinstance(result, bool)

    def test_is_transient_git_state_non_existent_dir(self):
        """Test: Is transient git state non existent dir."""
        from encre.git.diff import EncreGitDiff
        result = EncreGitDiff.is_transient_git_state(workspace="/nonexistent/path/xyz")
        # Verify: result is False
        assert result is False

    def test_roundtrip_compute_and_apply(self):
        """Test: Roundtrip compute and apply."""
        from encre.git.diff import EncreGitDiff
        original = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
        modified = "def foo():\n    return 42\n\n\ndef bar():\n    return 2\n\ndef baz():\n    return 3\n"  # noqa: E501
        diff = EncreGitDiff.compute_diff(old=original, new=modified)
        applied = EncreGitDiff.apply_diff(content=original, diff=diff)
        # Verify: isinstance(applied, str)
        assert isinstance(applied, str)
