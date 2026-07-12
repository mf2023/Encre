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

import contextlib
import subprocess
from dataclasses import dataclass, field


@dataclass
class GitState:
    """Snapshot of a git repository's status at a point in time.

    Attributes:
        in_repo: Whether the workspace is inside a git repository.
        commit_hash: Current HEAD commit hash (empty if unavailable).
        branch: Current branch name (empty if detached/unavailable).
        remote_url: URL of the ``origin`` remote (empty if none).
        is_clean: True when the working tree has no changes.
        changed_files: Tracked files with modifications.
        untracked_files: Files not yet tracked by git.
        has_unpushed: True when local commits are ahead of upstream.
        worktree_count: Number of linked worktrees (>= 1).
        recent_commits: Recent commit subjects (short hash + first line), newest first.
    """
    in_repo: bool
    commit_hash: str = ""
    branch: str = ""
    remote_url: str = ""
    is_clean: bool = True
    changed_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    has_unpushed: bool = False
    worktree_count: int = 1
    recent_commits: list[str] = field(default_factory=list)


class EncreGitRepo:
    """Thin wrapper around the ``git`` CLI for inspecting a workspace repo."""

    def __init__(self, workspace: str) -> None:
        """Locate the enclosing git repo (if any) for ``workspace``.

        Args:
            workspace: Directory used as the git working directory.
        """
        # Working directory all git commands are executed against.
        self.workspace = workspace
        # Path to the .git directory, or None when not inside a repo.
        self._git_dir = self._find_git_root()
        # Cached boolean of whether we are inside a git repository.
        self._in_repo = self._git_dir is not None

    def is_in_repo(self) -> bool:
        """Return True if the workspace lies within a git repository."""
        return self._in_repo

    def get_state(self) -> GitState:
        """Collect a full :class:`GitState` snapshot of the repository."""
        if not self._in_repo:
            return GitState(in_repo=False)

        # Gather each piece of state via individual git invocations.
        commit_hash = self._get_commit_hash()
        branch = self._get_branch()
        remote_url = self._get_remote_url()
        is_clean = self._is_clean()
        changed_files = self._get_changed_files()
        untracked_files = self._get_untracked_files()
        has_unpushed = self._has_unpushed_commits()
        worktree_count = self._get_worktree_count()
        recent_commits = self._get_recent_commits()

        return GitState(
            in_repo=True,
            commit_hash=commit_hash,
            branch=branch,
            remote_url=remote_url,
            is_clean=is_clean,
            changed_files=changed_files,
            untracked_files=untracked_files,
            has_unpushed=has_unpushed,
            worktree_count=worktree_count,
            recent_commits=recent_commits,
        )

    def get_diff(self, file_path: str | None = None) -> str:
        """Return the diff against HEAD, optionally scoped to one file.

        Args:
            file_path: Optional path to limit the diff to a single file.

        Returns:
            The unified diff text, or an empty string when not in a repo.
        """
        if not self._in_repo:
            return ""
        args = ["git", "diff", "HEAD", "--"]
        if file_path:
            args.append(file_path)
        return self._run_git(args)

    def get_diff_stats(self) -> dict[str, int]:
        """Return aggregate insertion/deletion/file counts against HEAD."""
        if not self._in_repo:
            return {"files": 0, "insertions": 0, "deletions": 0}
        output = self._run_git(["git", "diff", "--numstat", "HEAD"])
        return self._parse_numstat(output)

    def get_changed_files(self) -> list[str]:
        """Return the list of tracked files with pending modifications."""
        if not self._in_repo:
            return []
        return self._get_changed_files()

    def stash_to_clean_state(self) -> str | None:
        """Stash working changes to reach a clean tree.

        Returns:
            The stash message on success, or None if not in a repo or on error.
        """
        if not self._in_repo:
            return None
        try:
            self._run_git(["git", "stash", "push", "-m", "encre-auto-stash"])
            return "encre-auto-stash"
        except Exception:
            return None

    def unstash(self) -> None:
        """Restore the most recently stashed changes (best effort)."""
        if not self._in_repo:
            return
        with contextlib.suppress(Exception):
            self._run_git(["git", "stash", "pop"])

    def is_transient_state(self) -> bool:
        """Return True during an in-progress merge/rebase/cherry-pick/etc."""
        if not self._in_repo:
            return False
        assert self._git_dir is not None
        import os
        # Marker files/dirs that signal an interrupted git operation.
        transient_dirs = ["MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_START", "rebase-merge", "rebase-apply"]
        return any(os.path.exists(os.path.join(self._git_dir, name)) for name in transient_dirs)

    def has_unpushed_commits(self) -> bool:
        """Return True if local commits have not been pushed upstream."""
        if not self._in_repo:
            return False
        return self._has_unpushed_commits()

    def get_commit_hash(self) -> str:
        """Return the current HEAD commit hash (empty when unavailable)."""
        if not self._in_repo:
            return ""
        return self._get_commit_hash()

    def get_branch(self) -> str:
        """Return the current branch name (empty when unavailable)."""
        if not self._in_repo:
            return ""
        return self._get_branch()

    def _get_commit_hash(self) -> str:
        """Resolve HEAD to a commit hash via ``git rev-parse``."""
        try:
            return self._run_git(["git", "rev-parse", "HEAD"]).strip()
        except Exception:
            return ""

    def _get_recent_commits(self, limit: int = 5) -> list[str]:
        """Return the most recent commit subjects as ``<short-hash> <subject>``."""
        if not self._in_repo:
            return []
        try:
            output = self._run_git([
                "git", "log", f"-{limit}", "--format=%h %s",
            ])
            return [line for line in output.splitlines() if line.strip()]
        except Exception:
            return []

    def _get_branch(self) -> str:
        """Determine the current branch, falling back to abbreviated ref."""
        try:
            branch = self._run_git(["git", "branch", "--show-current"]).strip()
            if not branch:
                branch = self._run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
            return branch
        except Exception:
            return ""

    def _get_remote_url(self) -> str:
        """Return the ``origin`` remote URL, or empty when not configured."""
        try:
            return self._run_git(["git", "remote", "get-url", "origin"]).strip()
        except Exception:
            return ""

    def _is_clean(self) -> bool:
        """Return True when ``git status --porcelain`` reports no changes."""
        try:
            output = self._run_git(["git", "status", "--porcelain"])
            return output.strip() == ""
        except Exception:
            return True

    def _get_changed_files(self) -> list[str]:
        """Parse porcelain status output into a de-duplicated file list."""
        try:
            output = self._run_git(["git", "status", "--porcelain"])
            files: list[str] = []
            # Each porcelain line is "XY <path>"; strip the 2-char status code.
            for line in output.strip().split("\n"):
                line = line.strip()
                if len(line) >= 3:
                    path = line[3:].strip()
                    if path and path not in files:
                        files.append(path)
            return files
        except Exception:
            return []

    def _get_untracked_files(self) -> list[str]:
        """List files not tracked by git and not ignored."""
        try:
            output = self._run_git(["git", "ls-files", "--others", "--exclude-standard"])
            return [f for f in output.strip().split("\n") if f]
        except Exception:
            return []

    def _has_unpushed_commits(self) -> bool:
        """Return True if commits exist between upstream and HEAD."""
        try:
            output = self._run_git(["git", "log", "@{u}.."]).strip()
            return bool(output)
        except Exception:
            return False

    def _get_worktree_count(self) -> int:
        """Count linked worktrees; defaults to 1 on error/empty output."""
        try:
            output = self._run_git(["git", "worktree", "list"]).strip()
            if not output:
                return 1
            return len(output.split("\n"))
        except Exception:
            return 1

    @staticmethod
    def _parse_numstat(output: str) -> dict[str, int]:
        """Parse ``git diff --numstat`` output into count totals."""
        files = 0
        insertions = 0
        deletions = 0
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            # numstat columns: added, deleted, path (tab-separated).
            parts = line.split("\t")
            if len(parts) >= 2:
                files += 1
                try:
                    # "-" denotes a binary file with no line counts.
                    add = int(parts[0]) if parts[0] != "-" else 0
                    dlt = int(parts[1]) if parts[1] != "-" else 0
                    insertions += add
                    deletions += dlt
                except ValueError:
                    pass
        return {"files": files, "insertions": insertions, "deletions": deletions}

    def _run_git(self, args: list[str], timeout: float = 15.0) -> str:
        """Run a git command in the workspace and return its stdout.

        Args:
            args: The full argument vector, beginning with ``git``.
            timeout: Maximum seconds to wait before aborting.

        Returns:
            The command's standard output.

        Raises:
            RuntimeError: If git exits with a non-zero status.
        """
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=self.workspace,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def _find_git_root(self) -> str | None:
        """Walk up from the workspace to locate the nearest ``.git`` path.

        Returns:
            The ``.git`` path if found, otherwise None.
        """
        import os
        # Start at the absolute workspace path and ascend toward the filesystem root.
        current = os.path.abspath(self.workspace)
        while True:
            git_path = os.path.join(current, ".git")
            if os.path.exists(git_path):
                return git_path
            parent = os.path.dirname(current)
            # Reached the filesystem root without finding a repo.
            if parent == current:
                return None
            current = parent
