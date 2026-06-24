#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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


def _load_tasks(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Task file must be a JSON array.")
    return [item for item in data if isinstance(item, dict)]


def _score_text(task: dict[str, Any], text: str) -> dict[str, Any]:
    required = [str(x).lower() for x in task.get("must_include", [])]
    text_lower = (text or "").lower()
    matched = [token for token in required if token in text_lower]
    passed = len(matched) == len(required)
    return {
        "passed": passed,
        "matched": matched,
        "required": required,
        "missing": [token for token in required if token not in matched],
    }


async def _run_task(agent: EncreAgent, task: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    tool_calls = 0
    final_text = ""
    finish_reason = ""

    async for event in agent.run(task.get("prompt", "")):
        if isinstance(event, ToolCallStart):
            tool_calls += 1
        elif isinstance(event, Finish):
            finish_reason = event.reason

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
        await agent.loop.aclose()

    passed = sum(1 for item in results if item.get("score", {}).get("passed"))
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
