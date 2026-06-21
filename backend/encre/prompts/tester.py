#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prompt testing and validation framework.

Provides tools to version, test, and validate prompt templates so that
changes can be quantified rather than made "by feel".

Usage::

    from encre.prompts.tester import PromptTestSuite, PromptTestCase

    suite = PromptTestSuite()

    @suite.register("tool_usage_has_reasoning")
    def test_tool_usage_has_reasoning(loader):
        content = loader.load("tool_usage")
        assert "<thinking>" in content, "tool_usage must mandate reasoning"
        assert "Always Reason Before You Act" in content
        return True

    results = suite.run_all()
    # results.passed, results.failed, results.errors
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from encre.logging_config import get_logger
from encre.prompts.loader import PromptLoader

logger = get_logger("encre.prompts.tester")


@dataclass
class PromptVersion:
    """A versioned snapshot of a prompt template."""

    name: str
    content: str
    version: str
    hash: str
    created_at: float = 0.0

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def snapshot(loader: PromptLoader, name: str, version: str) -> PromptVersion:
        content = loader.load(name)
        return PromptVersion(
            name=name,
            content=content,
            version=version,
            hash=PromptVersion.compute_hash(content),
            created_at=time.time(),
        )


@dataclass
class PromptTestCase:
    """A single prompt test case with expected behavior."""

    name: str
    fn: Callable[[PromptLoader], bool]
    description: str = ""


@dataclass
class TestResults:
    """Aggregated test results."""

    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.errors)

    @property
    def success(self) -> bool:
        return len(self.failed) == 0 and len(self.errors) == 0


class PromptTestSuite:
    """A suite of prompt validation tests.

    Register test cases with :meth:`register` or :meth:`register_case`,
    then run all tests with :meth:`run_all`.
    """

    def __init__(self) -> None:
        self._cases: list[PromptTestCase] = []

    def register(
        self, name: str, description: str = "",
    ) -> Callable[[Callable[[PromptLoader], bool]], Callable[[PromptLoader], bool]]:
        """Decorator to register a test case."""
        def decorator(fn: Callable[[PromptLoader], bool]) -> Callable[[PromptLoader], bool]:
            self._cases.append(PromptTestCase(name=name, fn=fn, description=description))
            return fn
        return decorator

    def register_case(self, case: PromptTestCase) -> None:
        self._cases.append(case)

    def run_all(self, loader: PromptLoader | None = None) -> TestResults:
        """Run all registered test cases and return aggregated results."""
        if loader is None:
            loader = PromptLoader()
        results = TestResults()
        for case in self._cases:
            try:
                ok = case.fn(loader)
                if ok:
                    results.passed.append(case.name)
                    logger.info("[prompt-test] PASS: %s", case.name)
                else:
                    results.failed.append((case.name, "returned False"))
                    logger.warning("[prompt-test] FAIL: %s", case.name)
            except AssertionError as e:
                results.failed.append((case.name, str(e) or "assertion failed"))
                logger.warning("[prompt-test] FAIL: %s — %s", case.name, e)
            except Exception as e:
                results.errors.append((case.name, f"{type(e).__name__}: {e}"))
                logger.error("[prompt-test] ERROR: %s — %s", case.name, e)
        return results

    def list_cases(self) -> list[PromptTestCase]:
        return list(self._cases)


# ── Built-in validation tests ──────────────────────────────────────

_suite = PromptTestSuite()


@_suite.register("identity_has_core_principles", "identity prompt must include core principles")
def _test_identity_principles(loader: PromptLoader) -> bool:
    content = loader.load("identity")
    required = ["Think before you act", "Be precise and truthful", "Be systematic", "Be minimal", "Be responsible"]
    for phrase in required:
        assert phrase in content, f"identity.prompt missing: {phrase!r}"
    return True


@_suite.register("tool_usage_has_dedicated_tools_table", "tool_usage prompt must include the dedicated tools table")
def _test_tool_usage_table(loader: PromptLoader) -> bool:
    content = loader.load("tool_usage")
    assert "bash is your LAST tool" in content or "bash is your Last Tool" in content or "Tools First, Bash Last" in content
    assert "file_read" in content and "file_edit" in content and "file_write" in content
    return True


@_suite.register("tool_usage_has_reasoning", "tool_usage must mandate reasoning before tool calls")
def _test_tool_usage_reasoning(loader: PromptLoader) -> bool:
    content = loader.load("tool_usage")
    assert "<thinking>" in content, "tool_usage must include <thinking> reasoning block"
    assert "Always Reason Before You Act" in content or "Reason Before You Act" in content
    return True


@_suite.register("output_format_has_diff_requirement", "output_format must require diff format for code")
def _test_output_format_diff(loader: PromptLoader) -> bool:
    content = loader.load("output_format")
    assert "diff" in content
    return True


@_suite.register("safety_has_data_protection", "safety prompt must include data protection rules")
def _test_safety_data(loader: PromptLoader) -> bool:
    content = loader.load("safety")
    assert "secrets" in content or "credentials" in content or "API key" in content
    return True


@_suite.register("safety_has_risk_framework", "safety must include risk/reversibility framework")
def _test_safety_risk(loader: PromptLoader) -> bool:
    content = loader.load("safety")
    assert "blast radius" in content or "reversibility" in content
    assert "Measure twice" in content or "measure twice" in content
    return True


@_suite.register("identity_has_collaborator", "identity must include collaborator mindset")
def _test_identity_collaborator(loader: PromptLoader) -> bool:
    content = loader.load("identity")
    assert "collaborator" in content
    assert "faithfully" in content
    return True


@_suite.register("identity_has_prompt_injection_awareness", "identity must mention prompt injection")
def _test_identity_injection(loader: PromptLoader) -> bool:
    content = loader.load("identity")
    assert "prompt injection" in content
    return True


@_suite.register("output_format_has_user_facing_orientation", "output_format must distinguish user-facing text")
def _test_output_format_user_facing(loader: PromptLoader) -> bool:
    content = loader.load("output_format")
    assert "User-facing text" in content or "tool calls" in content
    assert "no emojis" in content or "No emojis" in content
    return True


@_suite.register("output_format_has_inverted_pyramid", "output_format must have inverted pyramid guidance")
def _test_output_format_pyramid(loader: PromptLoader) -> bool:
    content = loader.load("output_format")
    assert "inverted pyramid" in content or "Lead with the answer" in content
    return True


@_suite.register("coding_has_minimalism_rules", "specialty_coding must include minimalism and faithfulness rules")
def _test_coding_minimalism(loader: PromptLoader) -> bool:
    content = loader.load("specialty_coding")
    assert "premature abstraction" in content or "gold-plate" in content
    assert "faithfully" in content or "outcomes" in content
    return True


@_suite.register("coding_has_comment_discipline", "specialty_coding must have comment rules")
def _test_coding_comments(loader: PromptLoader) -> bool:
    content = loader.load("specialty_coding")
    assert "WHY is non-obvious" in content or "explain WHAT" in content
    return True


def run_builtin_tests() -> TestResults:
    """Run all built-in prompt validation tests."""
    return _suite.run_all()
