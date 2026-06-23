#!/usr/bin/env python3

"""End-to-end evaluation framework for Encre agent.

Allows defining benchmark tasks, running the agent against them, and
scoring results against success criteria.  Provides a quantitative
baseline for measuring improvement over time.

Usage::

    from encre.eval import EvalRunner, EvalTask

    task = EvalTask(
        name="file_edit_roundtrip",
        prompt="Create a file test.txt with content 'hello', "
               "then read it back and confirm the content.",
        success_criteria="The file test.txt exists and contains 'hello'",
        evaluator_template="Check if {criteria} was met. "
                           "Evidence: {output}",
        timeout=60,
    )

    runner = EvalRunner(config)
    result = await runner.run(task)
    print(f"Passed: {result.passed}, Score: {result.score}")
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime

from encre.agent import EncreAgent
from encre.config import EncreConfig
from encre.logging_config import get_logger
from encre.utils.types import Finish, TextDelta, ToolResult

logger = get_logger("encre.eval")


@dataclass
class EvalTask:
    """A single evaluation task for the agent."""

    name: str
    prompt: str
    success_criteria: str
    evaluator_template: str = ""
    timeout: int = 120
    required_tools: list[str] = field(default_factory=list)
    expected_output_patterns: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of a single evaluation task."""

    name: str
    passed: bool
    score: float
    output: str
    error: str = ""
    latency_ms: float = 0.0
    tool_calls: int = 0
    turns: int = 0


@dataclass
class EvalSummary:
    """Aggregated results across multiple tasks."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    total_score: float = 0.0
    tasks: list[EvalResult] = field(default_factory=list)
    started_at: str = ""
    duration_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def average_score(self) -> float:
        return self.total_score / self.total if self.total > 0 else 0.0


class EvalRunner:
    """Runs evaluation tasks against an Encre agent.

    Creates a fresh agent for each task by default.  Use
    ``keep_session=True`` to reuse across tasks.
    """

    def __init__(
        self,
        config: EncreConfig,
        keep_session: bool = False,
    ) -> None:
        self.config = config
        self.keep_session = keep_session
        self._agent: EncreAgent | None = None

    async def _get_agent(self) -> EncreAgent:
        if self._agent is None or not self.keep_session:
            self._agent = EncreAgent(config=self.config)
        return self._agent

    async def run(self, task: EvalTask) -> EvalResult:
        """Run a single evaluation task and return the result."""
        agent = await self._get_agent()
        start = time.time()
        output_parts: list[str] = []
        tool_count = 0
        turn_count = 0
        error = ""

        try:
            async for event in agent.run(prompt=task.prompt):
                if isinstance(event, TextDelta):
                    output_parts.append(event.text)
                elif isinstance(event, ToolResult):
                    tool_count += 1
                elif isinstance(event, Finish):
                    turn_count = getattr(event, "turn_count", 0) or 0
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.error("[eval] task=%s failed: %s", task.name, error)

        latency = (time.time() - start) * 1000
        output = "".join(output_parts)

        # Score: check success criteria against output
        score = self._score_output(output, task)
        passed = score >= 0.7 and not error

        return EvalResult(
            name=task.name,
            passed=passed,
            score=score,
            output=output[:2000],
            error=error,
            latency_ms=latency,
            tool_calls=tool_count,
            turns=turn_count,
        )

    def _score_output(self, output: str, task: EvalTask) -> float:
        """Score the agent output against success criteria.

        Returns 0.0-1.0 based on keyword presence and pattern matching.
        """
        score = 0.0
        checks = 0

        # Check success criteria keywords present in output
        if task.success_criteria:
            criteria_keywords = [
                w for w in task.success_criteria.split()
                if len(w) > 3 and w not in ("the", "that", "this", "with", "from", "been", "were", "have", "your")
            ]
            if criteria_keywords:
                matches = sum(1 for kw in criteria_keywords if kw.lower() in output.lower())
                score += matches / len(criteria_keywords)
                checks += 1

        # Check expected output patterns
        for pattern in task.expected_output_patterns:
            if pattern.lower() in output.lower():
                score += 1.0
            checks += 1

        return score / max(checks, 1)

    async def run_batch(
        self,
        tasks: list[EvalTask],
        parallel: bool = False,
    ) -> EvalSummary:
        """Run multiple evaluation tasks and return aggregated results."""
        started = datetime.now().isoformat()
        start = time.time()
        results: list[EvalResult] = []

        if parallel:
            import asyncio
            coros = [self.run(t) for t in tasks]
            results = await asyncio.gather(*coros)
        else:
            for task in tasks:
                result = await self.run(task)
                results.append(result)
                logger.info(
                    "[eval] %s: %s (score=%.2f, latency=%.0fms, tools=%d)",
                    task.name, "PASS" if result.passed else "FAIL",
                    result.score, result.latency_ms, result.tool_calls,
                )

        duration = (time.time() - start) * 1000
        summary = EvalSummary(
            total=len(results),
            passed=sum(1 for r in results if r.passed),
            failed=sum(1 for r in results if not r.passed),
            total_score=sum(r.score for r in results),
            tasks=results,
            started_at=started,
            duration_ms=duration,
        )
        logger.info(
            "[eval] batch complete: %d/%d passed (%.1f%%), avg score=%.2f, duration=%.0fms",
            summary.passed, summary.total,
            summary.pass_rate * 100, summary.average_score,
            summary.duration_ms,
        )
        return summary

    def summary_to_json(self, summary: EvalSummary) -> str:
        """Serialize evaluation summary to JSON."""
        return json.dumps({
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "pass_rate": summary.pass_rate,
            "avg_score": summary.average_score,
            "duration_ms": summary.duration_ms,
            "started_at": summary.started_at,
            "tasks": [
                {
                    "name": t.name,
                    "passed": t.passed,
                    "score": t.score,
                    "latency_ms": t.latency_ms,
                    "tool_calls": t.tool_calls,
                    "error": t.error,
                }
                for t in summary.tasks
            ],
        }, indent=2, ensure_ascii=False)
