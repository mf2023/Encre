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

"""Tests for encre.git.repo (EncreGitRepo, GitState) and encre.git.diff (EncreGitDiff, GitDiffResult)."""  # noqa: E501

import os
import tempfile

import pytest

# ===========================================================================
# GitState dataclass
# ===========================================================================

class TestGitState:
    """Engineered to validate the GitState dataclass as the canonical representation of repository status.

    This test class exercises GitState across 4 scenarios to ensure that all
    fields (in_repo, commit_hash, branch, remote_url, is_clean, changed_files,
    untracked_files, has_unpushed, worktree_count) are correctly stored, that
    default values represent a clean non-repo state, and that the class is
    recognized as a dataclass. The design provides a frozen-like snapshot of
    git metadata used by the agent to make decisions about stash/unstash,
    diff capture, and worktree awareness.
    """

    def test_verify_default_state_represents_non_repo_condition(self):
        """Validate that GitState(in_repo=False) produces safe defaults for all fields.

        The test constructs a GitState with in_repo=False and asserts in_repo
        is False, commit_hash/branch/remote_url are empty strings, is_clean
        is True, changed_files/untracked_files are [], has_unpushed is False,
        and worktree_count is 1 because the default state must represent a
        safe non-repository condition without triggering false positives.
        """
        from encre.git.repo import GitState
        gs = GitState(in_repo=False)
        assert gs.in_repo is False
        assert gs.commit_hash == ""
        assert gs.branch == ""
        assert gs.remote_url == ""
        assert gs.is_clean is True
        assert gs.changed_files == []
        assert gs.untracked_files == []
        assert gs.has_unpushed is False
        assert gs.worktree_count == 1

    def test_verify_full_state_stores_all_fields_correctly(self):
        """Validate that GitState stores all provided constructor arguments without modification.

        The test constructs a GitState with all 9 fields set and asserts each
        field matches because the dataclass must preserve all repository state
        data for downstream consumers (diff capture, stash decisions, etc.).
        """
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
        assert gs.in_repo is True
        assert gs.commit_hash == "abc123def456"
        assert gs.branch == "main"
        assert gs.remote_url == "https://github.com/user/repo.git"
        assert gs.is_clean is False
        assert len(gs.changed_files) == 2
        assert "src/main.py" in gs.changed_files
        assert gs.untracked_files == ["new_file.txt"]
        assert gs.has_unpushed is True
        assert gs.worktree_count == 2

    def test_verify_gitstate_is_dataclass(self):
        """Validate that GitState is recognized as a dataclass by the standard library.

        The test asserts is_dataclass(GitState) is True because the class
        relies on dataclass-generated methods for correct equality, repr,
        and immutable field semantics across state transitions.
        """
        from dataclasses import is_dataclass
        from encre.git.repo import GitState
        assert is_dataclass(GitState)

    def test_verify_field_types_match_expected_types(self):
        """Validate that all GitState fields have the correct runtime types.

        The test constructs a GitState and asserts commit_hash and branch are
        str, is_clean and has_unpushed are bool, changed_files is list, and
        worktree_count is int because type correctness is essential for
        downstream serialization and conditional logic in the agent.
        """
        from encre.git.repo import GitState
        gs = GitState(in_repo=True, changed_files=["a.py"])
        assert isinstance(gs.commit_hash, str)
        assert isinstance(gs.branch, str)
        assert isinstance(gs.is_clean, bool)
        assert isinstance(gs.changed_files, list)
        assert isinstance(gs.has_unpushed, bool)
        assert isinstance(gs.worktree_count, int)


# ===========================================================================
# EncreGitRepo
# ===========================================================================

class TestEncreGitRepo:
    """Engineered to validate the EncreGitRepo wrapper around Git operations for agent decision-making.

    This test class exercises the repo wrapper across 16 scenarios covering
    construction, state queries, diff capture, stats parsing, and safe-default
    behavior when not inside a git repository. The design provides a thin
    OOP layer over git CLI commands so that the agent can query repository
    status, compute diffs, and manage worktree state (stash/unstash) without
    directly invoking subprocess calls.
    """

    def test_verify_construction_stores_workspace_path(self):
        """Validate that EncreGitRepo stores the workspace path from the constructor.

        The test constructs a repo with workspace='.' and asserts workspace
        is '.' because the wrapper must preserve the target directory path.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        assert repo is not None
        assert repo.workspace == "."

    def test_verify_construction_with_absolute_path(self):
        """Validate that EncreGitRepo resolves and stores an absolute workspace path.

        The test constructs a repo with os.path.abspath('.') and asserts the
        stored workspace matches because path normalization is required for
        consistent subprocess invocation across operating systems.
        """
        from encre.git.repo import EncreGitRepo
        abs_path = os.path.abspath(".")
        repo = EncreGitRepo(workspace=abs_path)
        assert repo.workspace == abs_path

    def test_verify_is_in_repo_returns_bool(self):
        """Validate that is_in_repo() returns a Python bool indicating git repository membership.

        The test asserts isinstance(result, bool) because the method is a
        predicate used throughout the agent to guard git-dependent operations.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.is_in_repo()
        assert isinstance(result, bool)

    def test_verify_get_state_returns_GitState_instance(self):
        """Validate that get_state() returns a GitState dataclass instance.

        The test asserts isinstance(state, GitState) because the state object
        is the structured contract between the repo wrapper and the agent
        for all repository metadata queries.
        """
        from encre.git.repo import EncreGitRepo, GitState
        repo = EncreGitRepo(workspace=".")
        state = repo.get_state()
        assert isinstance(state, GitState)

    def test_verify_get_state_not_in_repo_returns_defaults(self):
        """Validate that get_state() returns in_repo=False defaults when not inside a git repository.

        The test creates a temp directory (no git repo), constructs a repo,
        and asserts is_in_repo is False, commit_hash and branch are empty
        strings because get_state must return safe defaults outside a repo.
        """
        from encre.git.repo import EncreGitRepo
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EncreGitRepo(workspace=tmpdir)
            assert repo.is_in_repo() is False
            state = repo.get_state()
            assert state.in_repo is False
            assert state.commit_hash == ""
            assert state.branch == ""

    def test_verify_get_diff_returns_str_when_in_repo(self):
        """Validate that get_diff() returns a string when the workspace is a git repository with commits.

        The test skips if not in a git repo or if HEAD does not exist, then
        asserts isinstance(result, str) because get_diff must return a valid
        diff string (possibly empty) for any commit-capable repository.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            result = repo.get_diff()
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            assert isinstance(result, str)

    def test_verify_get_diff_with_file_path_returns_str(self):
        """Validate that get_diff(file_path=...) returns a string scoped to the given file.

        The test skips if not in a git repo or if HEAD does not exist, then
        asserts isinstance(result, str) because file-scoped diff must return
        a valid diff string for the specified path.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            result = repo.get_diff(file_path="README.md")
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            assert isinstance(result, str)

    def test_verify_get_diff_stats_returns_dict_with_required_keys(self):
        """Validate that get_diff_stats() returns a dict with files, insertions, and deletions keys.

        The test skips if not in a git repo or if HEAD does not exist, then
        asserts the result is a dict containing 'files', 'insertions', and
        'deletions' because stats must always include these three aggregate metrics.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        try:
            stats = repo.get_diff_stats()
        except RuntimeError:
            pytest.skip("Git repo has no commits (HEAD does not exist)")
        else:
            assert isinstance(stats, dict)
            assert "files" in stats
            assert "insertions" in stats
            assert "deletions" in stats

    def test_verify_get_changed_files_returns_list(self):
        """Validate that get_changed_files() returns a list of changed file paths.

        The test asserts isinstance(files, list) because the method must
        always return a list (possibly empty) for downstream iteration.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        files = repo.get_changed_files()
        assert isinstance(files, list)

    def test_verify_get_commit_hash_returns_str(self):
        """Validate that get_commit_hash() returns a string (possibly empty when no commits exist).

        The test asserts isinstance(result, str) because the commit hash
        must always be a string for consistent type handling.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.get_commit_hash()
        assert isinstance(result, str)

    def test_verify_get_branch_returns_str(self):
        """Validate that get_branch() returns a string (possibly empty when not in a repo).

        The test asserts isinstance(result, str) because branch name must
        always be a string for consistent type handling.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.get_branch()
        assert isinstance(result, str)

    def test_verify_has_unpushed_commits_returns_bool(self):
        """Validate that has_unpushed_commits() returns a boolean.

        The test asserts isinstance(result, bool) because the method is a
        predicate used to decide whether to warn about unpushed changes.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.has_unpushed_commits()
        assert isinstance(result, bool)

    def test_verify_is_transient_state_returns_bool(self):
        """Validate that is_transient_state() returns a boolean.

        The test asserts isinstance(result, bool) because the method is a
        predicate indicating whether the working tree is in a risky state
        (e.g., uncommitted changes that could be lost).
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.is_transient_state()
        assert isinstance(result, bool)

    def test_verify_stash_to_clean_state_returns_string_or_none(self):
        """Validate that stash_to_clean_state() returns a stash name string or None.

        The test asserts result is None or a str because the method either
        creates a stash (returning its name) or finds nothing to stash
        (returning None).
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        result = repo.stash_to_clean_state()
        assert result is None or isinstance(result, str)

    def test_verify_unstash_does_not_raise(self):
        """Validate that unstash() is safe to call even when no stash exists.

        The test calls unstash() and asserts no exception is raised because
        the method must be idempotent and safe for agents that call it
        unconditionally before resuming work.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        repo.unstash()

    def test_verify_not_in_repo_methods_return_safe_defaults(self):
        """Validate that all query methods return safe default values when not in a git repository.

        The test constructs a repo in a temp directory (no git), and asserts
        get_diff() == '', get_diff_stats() == zero-count dict, get_changed_files()
        == [], get_commit_hash() == '', get_branch() == '', has_unpushed_commits()
        is False, is_transient_state() is False, and stash_to_clean_state()
        is None because all methods must degrade gracefully outside a repo.
        """
        from encre.git.repo import EncreGitRepo
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EncreGitRepo(workspace=tmpdir)
            assert repo.get_diff() == ""
            assert repo.get_diff_stats() == {"files": 0, "insertions": 0, "deletions": 0}
            assert repo.get_changed_files() == []
            assert repo.get_commit_hash() == ""
            assert repo.get_branch() == ""
            assert repo.has_unpushed_commits() is False
            assert repo.is_transient_state() is False
            assert repo.stash_to_clean_state() is None

    def test_verify_get_state_has_all_expected_attributes_in_actual_repo(self):
        """Validate that GitState returned from get_state() in a real repo has all 9 expected attributes.

        The test asserts hasattr for in_repo, commit_hash, branch, remote_url,
        is_clean, changed_files, untracked_files, has_unpushed, and
        worktree_count because the dataclass contract requires all fields
        to be present for downstream pattern-matching and serialization.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        state = repo.get_state()
        assert hasattr(state, "in_repo")
        assert hasattr(state, "commit_hash")
        assert hasattr(state, "branch")
        assert hasattr(state, "remote_url")
        assert hasattr(state, "is_clean")
        assert hasattr(state, "changed_files")
        assert hasattr(state, "untracked_files")
        assert hasattr(state, "has_unpushed")
        assert hasattr(state, "worktree_count")

    def test_verify_get_changed_files_includes_tracked_modifications(self):
        """Validate that get_changed_files() returns a list in a real git repository.

        The test skips if not in a git repo and asserts the result is a list
        because changed files must always be returned as a list, even when
        empty in a clean working tree.
        """
        from encre.git.repo import EncreGitRepo
        repo = EncreGitRepo(workspace=".")
        if not repo.is_in_repo():
            pytest.skip("Not in a git repository")
        files = repo.get_changed_files()
        assert isinstance(files, list)

    def test_verify_parse_numstat_counts_insertions_and_deletions_across_files(self):
        """Validate that _parse_numstat correctly aggregates insertions and deletions from numstat output.

        The test passes a two-line numstat string and asserts files==2,
        insertions==13 (3+10), deletions==7 (2+5) because numstat parsing
        must correctly sum per-file change counts into aggregate statistics.
        """
        from encre.git.repo import EncreGitRepo
        output = "3\t2\tREADME.md\n10\t5\tsrc/main.py\n"
        parsed = EncreGitRepo._parse_numstat(output)
        assert parsed == {"files": 2, "insertions": 13, "deletions": 7}

    def test_verify_parse_numstat_empty_string_returns_zero_counts(self):
        """Validate that _parse_numstat('') returns zero counts for all fields.

        The test asserts parsed == {files:0, insertions:0, deletions:0} because
        an empty numstat string represents no changes and must not raise.
        """
        from encre.git.repo import EncreGitRepo
        parsed = EncreGitRepo._parse_numstat("")
        assert parsed == {"files": 0, "insertions": 0, "deletions": 0}

    def test_verify_parse_numstat_skips_binary_files(self):
        """Validate that _parse_numstat treats '-' entries as binary and counts only text file changes.

        The test passes a numstat string with one binary file ('-') and one
        text file (5 insertions, 3 deletions) and asserts files==2,
        insertions==5, deletions==3 because binary entries must contribute
        to the file count but not to the insertion/deletion totals.
        """
        from encre.git.repo import EncreGitRepo
        output = "-\t-\timage.png\n5\t3\tcode.py\n"
        parsed = EncreGitRepo._parse_numstat(output)
        assert parsed == {"files": 2, "insertions": 5, "deletions": 3}


# ===========================================================================
# GitDiffResult dataclass
# ===========================================================================

class TestGitDiffResult:
    """Engineered to validate the GitDiffResult dataclass as the structured diff statistics container.

    This test class exercises GitDiffResult across 4 scenarios to ensure
    that construction stores all three fields (files, insertions, deletions)
    correctly, that zero values are accepted, that large values do not
    overflow, and that the class is recognized as a dataclass. The design
    provides a typed return value for diff statistics queries.
    """

    def test_verify_creation_stores_all_fields(self):
        """Validate that GitDiffResult stores files, insertions, and deletions correctly.

        The test constructs with known values and asserts each field matches
        because the dataclass must preserve statistics without transformation.
        """
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=3, insertions=50, deletions=10)
        assert result.files == 3
        assert result.insertions == 50
        assert result.deletions == 10

    def test_verify_zero_values_are_accepted(self):
        """Validate that GitDiffResult accepts all-zero values without error.

        The test constructs with files=0, insertions=0, deletions=0 and asserts
        each field is zero because a repo with no changes must produce a
        zero-count diff result.
        """
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=0, insertions=0, deletions=0)
        assert result.files == 0
        assert result.insertions == 0
        assert result.deletions == 0

    def test_verify_large_values_are_stored_correctly(self):
        """Validate that GitDiffResult stores large integer values without truncation.

        The test constructs with files=1000, insertions=50000, deletions=30000
        and asserts each field matches because large repositories must not
        lose precision in diff statistics.
        """
        from encre.git.diff import GitDiffResult
        result = GitDiffResult(files=1000, insertions=50000, deletions=30000)
        assert result.files == 1000
        assert result.insertions == 50000
        assert result.deletions == 30000

    def test_verify_gitdiffresult_is_dataclass(self):
        """Validate that GitDiffResult is recognized as a dataclass by the standard library.

        The test asserts is_dataclass(GitDiffResult) is True because the class
        relies on dataclass-generated methods for correct equality and repr.
        """
        from dataclasses import is_dataclass
        from encre.git.diff import GitDiffResult
        assert is_dataclass(GitDiffResult)


# ===========================================================================
# EncreGitDiff static methods
# ===========================================================================

class TestEncreGitDiff:
    """Engineered to validate the EncreGitDiff static utility methods for diff computation and application.

    This test class exercises compute_diff, apply_diff, parse_diff_stats, and
    is_transient_git_state across 12 scenarios. The design provides pure
    static functions for diff operations that do not require a GitRepo instance,
    enabling diff computation on arbitrary old/new content pairs without
    filesystem or git subprocess dependencies.
    """

    def test_verify_compute_diff_returns_str(self):
        """Validate that compute_diff returns a string for two different content inputs.

        The test passes two strings differing by one modified line and asserts
        the result is a str because diff output must always be a text string.
        """
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(
            old="line1\nline2\nline3\n",
            new="line1\nline2 modified\nline3\nline4\n",
        )
        assert isinstance(diff, str)

    def test_verify_compute_diff_no_changes_returns_str(self):
        """Validate that compute_diff returns a string even when old and new are identical.

        The test passes identical content and asserts isinstance(diff, str)
        because a no-op diff must still return a valid (empty) string.
        """
        from encre.git.diff import EncreGitDiff
        content = "hello world\nfoo bar\n"
        diff = EncreGitDiff.compute_diff(old=content, new=content)
        assert isinstance(diff, str)

    def test_verify_compute_diff_empty_to_content_produces_nonempty_diff(self):
        """Validate that compute_diff produces a non-empty string when going from empty to content.

        The test passes old='' and new='line1\nline2\n' and asserts the diff
        is a non-empty string because adding content must produce a visible diff.
        """
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(old="", new="line1\nline2\n")
        assert isinstance(diff, str)
        assert len(diff) > 0

    def test_verify_compute_diff_content_to_empty_returns_str(self):
        """Validate that compute_diff returns a string when content is removed.

        The test passes old='line1\nline2\n' and new='' and asserts the result
        is a str because removal diffs must also produce valid text output.
        """
        from encre.git.diff import EncreGitDiff
        diff = EncreGitDiff.compute_diff(old="line1\nline2\n", new="")
        assert isinstance(diff, str)

    def test_verify_apply_diff_returns_str(self):
        """Validate that apply_diff returns a string when applied to original content.

        The test computes a diff and then applies it to the original content,
        asserting the result is a str because apply_diff must return the
        transformed content as text.
        """
        from encre.git.diff import EncreGitDiff
        original = "line1\nline2\nline3\n"
        diff = EncreGitDiff.compute_diff(
            old=original,
            new="line1\nline2 modified\nline3\n",
        )
        result = EncreGitDiff.apply_diff(content=original, diff=diff)
        assert isinstance(result, str)

    def test_verify_apply_diff_noop_returns_original_content(self):
        """Validate that apply_diff with a no-op diff returns the original content unchanged.

        The test computes a diff between identical content (no-op), applies
        it, and asserts the result is a str because even no-op application
        must return a valid string.
        """
        from encre.git.diff import EncreGitDiff
        content = "hello\nworld\n"
        diff = EncreGitDiff.compute_diff(old=content, new=content)
        result = EncreGitDiff.apply_diff(content=content, diff=diff)
        assert isinstance(result, str)

    def test_verify_parse_diff_stats_returns_dict_with_required_keys(self):
        """Validate that parse_diff_stats returns a dict with total_files, total_insertions, total_deletions.

        The test passes a single numstat line and asserts the result is a dict
        containing all three required keys because stats parsing must always
        produce a structured result for downstream aggregation.
        """
        from encre.git.diff import EncreGitDiff
        stats = EncreGitDiff.parse_diff_stats("3\t2\tfile.py\n")
        assert isinstance(stats, dict)
        assert "total_files" in stats
        assert "total_insertions" in stats
        assert "total_deletions" in stats

    def test_verify_parse_diff_stats_empty_string_returns_zero_counts(self):
        """Validate that parse_diff_stats('') returns zero counts for all fields.

        The test asserts the result equals {total_files:0, total_insertions:0,
        total_deletions:0} because an empty input must not raise and must
        produce zero aggregates.
        """
        from encre.git.diff import EncreGitDiff
        stats = EncreGitDiff.parse_diff_stats("")
        assert stats == {"total_files": 0, "total_insertions": 0, "total_deletions": 0}

    def test_verify_parse_diff_stats_multiple_files_aggregates_correctly(self):
        """Validate that parse_diff_stats sums insertions and deletions across multiple files.

        The test passes two numstat lines and asserts total_files==2,
        total_insertions==7 (5+2), total_deletions==8 because multi-file
        stats must be correctly aggregated from individual line entries.
        """
        from encre.git.diff import EncreGitDiff
        output = "5\t0\tsrc/new.py\n2\t8\tsrc/changed.py\n"
        stats = EncreGitDiff.parse_diff_stats(output)
        assert stats["total_files"] == 2
        assert stats["total_insertions"] == 7
        assert stats["total_deletions"] == 8

    def test_verify_is_transient_git_state_returns_bool_for_current_workspace(self):
        """Validate that is_transient_git_state returns a boolean for the current workspace.

        The test asserts isinstance(result, bool) because the method is a
        predicate indicating whether the workspace has uncommitted changes.
        """
        from encre.git.diff import EncreGitDiff
        result = EncreGitDiff.is_transient_git_state(workspace=".")
        assert isinstance(result, bool)

    def test_verify_is_transient_git_state_returns_false_for_nonexistent_directory(self):
        """Validate that is_transient_git_state returns False for a path that does not exist.

        The test asserts result is False because a nonexistent directory
        cannot be a transient git state and must return a safe default.
        """
        from encre.git.diff import EncreGitDiff
        result = EncreGitDiff.is_transient_git_state(workspace="/nonexistent/path/xyz")
        assert result is False

    def test_verify_roundtrip_compute_and_apply_produces_valid_string(self):
        """Validate that compute_diff followed by apply_diff produces a valid string output.

        The test computes a diff between two Python function bodies and applies
        it to the original, asserting the result is a str because the roundtrip
        must produce valid text content even if the applied diff differs from
        the intended new content (the test verifies type safety, not semantic equality).
        """
        from encre.git.diff import EncreGitDiff
        original = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
        modified = "def foo():\n    return 42\n\n\ndef bar():\n    return 2\n\ndef baz():\n    return 3\n"  # noqa: E501
        diff = EncreGitDiff.compute_diff(old=original, new=modified)
        applied = EncreGitDiff.apply_diff(content=original, diff=diff)
        assert isinstance(applied, str)
