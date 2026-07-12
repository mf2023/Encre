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

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from encre.agent import EncreAgent
from encre.config import EncreConfig
from encre.utils.types import Finish, ToolCallStart


# ---------------------------------------------------------------------------
# Module summary
# ---------------------------------------------------------------------------
# Lightweight benchmark runner for the Encre agent.
#
# This module drives an end-to-end evaluation of :class:`encre.agent.EncreAgent`
# against a suite of tasks defined in a JSON file. For each task it spins up a
# fresh agent, streams the agent's run loop, extracts the final assistant
# message, and scores it (substring matching against required tokens). It then
# aggregates per-task metrics (duration, tool calls, turns, stuck events,
# delegations, ...) into a summary and writes the whole payload to a results
# JSON file. ``analyze_results.py`` consumes that output.
#
# Entry point: ``python runner.py --tasks <file> --output <file> --model <id>
# --backend <type>`` (see :func:`_main` for the full argument list).
# ---------------------------------------------------------------------------


def _load_tasks(path: str) -> list[dict[str, Any]]:
    """Load and validate a benchmark task file.

    Reads a JSON document that must be an array of objects. Entries that are not
    dictionaries (e.g. stray scalars or arrays) are silently dropped so that the
    runner can tolerate loosely-shaped task files.

    Args:
        path: Filesystem path to a UTF-8 encoded JSON array of task objects.

    Returns:
        The list of task objects (dicts) found in the file.

    Raises:
        ValueError: If the top-level JSON value is not a list.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Task file must be a JSON array.")
    return [item for item in data if isinstance(item, dict)]


def _score_text(task: dict[str, Any], text: str) -> dict[str, Any]:
    """Score an agent response against a task's required tokens.

    A task may declare ``must_include`` tokens; the response "passes" only when
    every required token (compared case-insensitively) appears somewhere in the
    agent's final text. The returned dict also reports which tokens matched and
    which were missing for diagnostics.

    Args:
        task: A task dict; only the ``must_include`` key is consulted.
        text: The agent's final assistant text to be scored.

    Returns:
        A dict with ``passed`` (bool), ``matched``/``required``/``missing``
        token lists.
    """
    required = [str(x).lower() for x in task.get("must_include", [])]
    # Normalize to lower case once so every membership test is case-insensitive.
    text_lower = (text or "").lower()
    matched = [token for token in required if token in text_lower]
    # Pass only when every required token was found in the response.
    passed = len(matched) == len(required)
    return {
        "passed": passed,
        "matched": matched,
        "required": required,
        "missing": [token for token in required if token not in matched],
    }


async def _run_task(agent: EncreAgent, task: dict[str, Any]) -> dict[str, Any]:
    """Execute a single benchmark task and collect its metrics.

    Runs the agent against the task prompt while counting tool-call starts and
    capturing the finish reason from the streamed event loop. After the run it
    inspects the agent session to recover the final assistant message, computes
    a pass/fail score, and gathers session metadata (stuck events, delegation
    history, task stage) plus artifact/reference/turn counts.

    Args:
        agent: A freshly constructed :class:`EncreAgent` for this task.
        task: The task dict; uses ``prompt``, ``id`` and ``category``.

    Returns:
        A dict summarizing the run: ids, timing in milliseconds, counts,
        extracted ``final_text``, and the :func:`_score_text` result.
    """
    started = time.time()
    tool_calls = 0
    final_text = ""
    finish_reason = ""

    # Stream the agent run loop, counting tool invocations and recording why
    # the run finished (e.g. completed, max-turns, error).
    async for event in agent.run(task.get("prompt", "")):
        if isinstance(event, ToolCallStart):
            tool_calls += 1
        elif isinstance(event, Finish):
            finish_reason = event.reason

    # Walk the context messages backwards to find the last non-empty assistant
    # message, which is treated as the agent's final answer for scoring.
    messages = agent.session.get_context_messages()
    for message in reversed(messages):
        if message.get("role") == "assistant":
            final_text = str(message.get("content") or "")
            if final_text:
                break

    elapsed_ms = int((time.time() - started) * 1000)
    score = _score_text(task, final_text)
    meta = agent.session.metadata or {}
    stuck_events = meta.get("stuck_events", []) or []
    delegate_history = meta.get("delegate_history", []) or []
    task_stage = meta.get("task_stage", "discover")
    return {
        "id": task.get("id", ""),
        "category": task.get("category", ""),
        "duration_ms": elapsed_ms,
        "tool_calls": tool_calls,
        "finish_reason": finish_reason,
        "artifacts": len(agent.session.artifacts),
        "references": len(agent.session.references),
        "turn_count": agent.session.turn_count,
        "task_stage": task_stage,
        "stuck_event_count": len(stuck_events),
        "delegate_count": len(delegate_history),
        "final_text": final_text,
        "score": score,
    }


async def _main() -> None:
    """CLI entry point: run the full benchmark suite and write results.

    Parses command-line arguments, loads the task list, then iterates over each
    task building a dedicated :class:`EncreAgent` per task (so sessions never
    leak between tasks). It aggregates pass/fail and averaging metrics into a
    top-level ``summary`` and writes the combined payload to ``--output`` as
    pretty-printed UTF-8 JSON.

    Required arguments: ``--tasks``, ``--output``, ``--model``, ``--backend``.
    Optional: ``--workspace``, ``--base-url``, ``--api-key``.
    """
    parser = argparse.ArgumentParser(description="Run a lightweight Encre benchmark suite.")
    parser.add_argument("--tasks", required=True, help="Path to benchmark tasks JSON.")
    parser.add_argument("--output", required=True, help="Path to write benchmark results JSON.")
    parser.add_argument("--model", required=True, help="Model id.")
    parser.add_argument("--backend", required=True, help="Backend type.")
    parser.add_argument("--workspace", default="", help="Optional workspace path.")
    parser.add_argument("--base-url", default="", help="Optional backend base URL.")
    parser.add_argument("--api-key", default="", help="Optional backend API key.")
    args = parser.parse_args()

    tasks = _load_tasks(args.tasks)
    results: list[dict[str, Any]] = []

    for task in tasks:
        # Build a brand-new agent per task so per-task sessions/states are
        # fully isolated and benchmark runs are reproducible.
        config = EncreConfig(
            model=args.model,
            backend_type=args.backend,
            workspace=args.workspace,
            base_url=args.base_url,
            api_key=args.api_key,
            max_turns=0,
            max_tokens=4096,
            enable_prompt_caching=False,
        )
        agent = EncreAgent(config=config)
        result = await _run_task(agent, task)
        results.append(result)
        # Release the agent's async event loop before moving to the next task.
        await agent.loop.aclose()

    # Tally how many tasks passed the scoring check.
    passed = sum(1 for item in results if item.get("score", {}).get("passed"))
    # Assemble the summary (counts, pass rate, and averages) and serialize the
    # full payload to the requested output path.
    payload = {
        "summary": {
            "task_count": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": (passed / len(results)) if results else 0.0,
            "avg_tool_calls": (sum(int(item.get("tool_calls", 0)) for item in results) / len(results)) if results else 0.0,
            "avg_turn_count": (sum(int(item.get("turn_count", 0)) for item in results) / len(results)) if results else 0.0,
            "total_stuck_events": sum(int(item.get("stuck_event_count", 0)) for item in results),
            "total_delegations": sum(int(item.get("delegate_count", 0)) for item in results),
        },
        "results": results,
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(_main())
