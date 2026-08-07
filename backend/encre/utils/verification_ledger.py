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

from __future__ import annotations

"""Verification evidence ledger (port of Hermes verification_evidence.py).

Tracks which code files were edited this session and what verification evidence
(existing lint/typecheck/test/LSP checks) has been recorded for them, so the
verify-on-stop nudge can be *evidence-driven*: it distinguishes "never checked"
from "checked and failed", and only nags about files that lack passing evidence
after their most recent edit.  Pure state, no loop coupling; independently
testable.
"""

import time
from dataclasses import dataclass, field

# Tools that count as verification evidence.  `bash`/`powershell` are included
# because the model may verify through a shell command (pytest, mypy, ...).
_VERIFY_EVIDENCE_TOOLS = frozenset({"test_run", "lint_format", "lsp", "bash", "powershell"})

# How long (seconds) a passing verification remains valid before it is treated
# as stale and a file returns to "unverified".
_VERIFY_EVIDENCE_STALE_SECONDS = 600.0

_NON_CODE_SUFFIXES = (
    ".md", ".markdown", ".rst", ".txt", ".csv", ".json", ".yaml", ".yml",
    ".toml", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".lock",
)
_NON_CODE_NAMES = ("LICENSE", "README", "CHANGELOG", "NOTICE")


@dataclass
class VerificationEvent:
    """A single recorded verification attempt."""

    tool: str
    passed: bool
    summary: str
    timestamp: float = field(default_factory=time.time)


class VerificationLedger:
    """In-memory ledger of edited files and their verification evidence.

    A file is considered *verified* only if it has passing evidence recorded
    *after* its most recent edit and that evidence is not stale.  Editing a
    file invalidates any prior passing evidence for it.
    """

    def __init__(self, stale_seconds: float = _VERIFY_EVIDENCE_STALE_SECONDS) -> None:
        self._edited: dict[str, float] = {}
        self._events: list[VerificationEvent] = []
        self._passing_after_edit: set[str] = set()
        self._stale_seconds = stale_seconds

    # ── Recording ───────────────────────────────────────────────────

    def mark_edited(self, path: str) -> None:
        """Record that ``path`` was modified, invalidating prior evidence."""
        if not self._is_verifiable_code(path):
            return
        self._edited[path] = time.time()
        self._passing_after_edit.discard(path)

    def record_verification(
        self,
        tool: str,
        passed: bool,
        summary: str = "",
        paths: list[str] | None = None,
    ) -> None:
        """Record a verification attempt.

        If ``passed`` and ``paths`` is None, all currently-edited files are
        treated as verified (the common case: the model ran a suite that
        covered its changes).  If ``paths`` is given, only those that were
        edited are marked verified on success.
        """
        if tool not in _VERIFY_EVIDENCE_TOOLS:
            return
        self._events.append(VerificationEvent(tool=tool, passed=passed, summary=summary))
        if not passed:
            return
        targets = paths if paths is not None else list(self._edited)
        for p in targets:
            if p in self._edited:
                self._passing_after_edit.add(p)

    # ── Queries ─────────────────────────────────────────────────────

    def edited_files(self) -> list[str]:
        return list(self._edited)

    def file_status(self, path: str) -> str:
        """One of ``unverified`` | ``verified`` | ``stale``."""
        if path not in self._edited:
            return "unverified"
        if path not in self._passing_after_edit:
            return "unverified"
        if time.time() - self._edited[path] > self._stale_seconds:
            return "stale"
        return "verified"

    def unverified_files(self) -> list[str]:
        """Edited files lacking current passing evidence."""
        return [p for p in self._edited if self.file_status(p) != "verified"]

    def verify_events(self) -> list[VerificationEvent]:
        return list(self._events)

    def has_failed_evidence(self) -> bool:
        """True if any recorded verification attempt failed since the last edit."""
        return any(not e.passed for e in self._events)

    @staticmethod
    def _is_verifiable_code(path: str) -> bool:
        lower = path.lower()
        if any(lower.endswith(s) for s in _NON_CODE_SUFFIXES):
            return False
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if any(name == n for n in _NON_CODE_NAMES):
            return False
        return True

    def build_nudge_message(self, failed: bool = False) -> str:
        """Evidence-driven nudge for verify-on-stop."""
        files = self.unverified_files()[:6]
        if not files:
            return ""
        _files = "\n".join(f"- `{f}`" for f in files)
        _more = f"\n  ... and {len(self.unverified_files()) - 6} more" if len(self.unverified_files()) > 6 else ""
        if failed:
            head = (
                "[VERIFY-ON-STOP] A verification run you performed reported "
                "failures and the task is not complete until the change passes. "
                "Please fix the reported errors and re-run the check on:\n"
            )
        else:
            head = (
                "[VERIFY-ON-STOP] You changed code files this session and no "
                "verification tool has reported passing on them since the change. "
                "The task is not complete until the change is verified. "
                "Run the appropriate lint/typecheck/test tool on:\n"
            )
        return (
            f"{head}{_files}{_more}\n"
            "Run `test_run`, `lint_format`, or `lsp` (or an equivalent command), "
            "then report the result. Fix any errors you find before finishing."
        )

    def build_forced_review_message(self, files: list[str]) -> str:
        """Escalation message when repeated verify nudges were ignored yet a
        verification still failed.  This is the review stage of the
        implement -> verify -> review -> fix loop: instead of silently
        finishing, the agent is told to run a critical review (the
        ``code-review`` skill or a ``critic`` sub-agent) over the failing
        change before it may stop."""
        shown = files[:10]
        _files = "\n".join(f"- `{f}`" for f in shown)
        _more = f"\n  ... and {len(files) - 10} more" if len(files) > 10 else ""
        return (
            "[FORCED-REVIEW] Verification of your change reported failures and "
            "you attempted to finish without fixing them. The task is not "
            "complete until the failing change is reviewed and resolved.\n"
            "Run a critical code review over your changes (activate the "
            "`code-review` skill, or delegate a `critic` sub-agent), address "
            "every reported failure, re-run the failing check, and confirm it "
            "passes before you finish. Review the following files:\n"
            f"{_files}{_more}"
        )
