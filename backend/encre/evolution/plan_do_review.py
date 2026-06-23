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

"""
Plan-Do-Review 自主循环引擎 -- 旗舰级 AI Agent 的核心能力。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class StepStatus(Enum):
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    BLOCKED = auto()
    SKIPPED = auto()


class ReviewGrade(Enum):
    PASS = auto()
    PASS_WITH_ISSUES = auto()
    FAIL = auto()
    NEEDS_RETRY = auto()


@dataclass
class ToolCallRecord:
    """每次工具调用的记录"""
    turn: int
    tool_name: str
    args_summary: str
    result_summary: str
    is_error: bool
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class StepNode:
    """Plan 中的一个步骤"""
    id: str
    description: str
    success_criteria: str
    status: StepStatus = StepStatus.PENDING
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    result_summary: str = ""
    error: str = ""
    retry_count: int = 0
    max_retries: int = 2
    depends_on: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        icon = {
            StepStatus.PENDING: "--",
            StepStatus.IN_PROGRESS: ">>",
            StepStatus.COMPLETED: "OK",
            StepStatus.FAILED: "XX",
            StepStatus.BLOCKED: "!!",
            StepStatus.SKIPPED: "--",
        }.get(self.status, "??")
        return f"[{icon}] {self.description}  ({self.status.name})"


@dataclass
class RuntimePlan:
    """当前会话的运行中计划"""
    original_task: str = ""
    steps: list[StepNode] = field(default_factory=list)
    current_step_index: int = -1
    created_at: float = field(default_factory=time.time)
    completed_steps: int = 0
    failed_steps: int = 0
    total_tool_calls: int = 0
    retry_count: int = 0
    deep_reviews_done: int = 0

    @property
    def current_step(self) -> StepNode | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)

    def to_prompt_context(self) -> str:
        """生成注入 system prompt 的上下文块"""
        if not self.steps:
            return ""
        lines = ["## Plan-Do-Review 进度", ""]
        done = self.completed_steps
        total = len(self.steps)
        pct = int(done / total * 100) if total > 0 else 0
        lines.append(f"进度: {done}/{total} ({pct}%)")
        lines.append("")
        lines.append("步骤:")
        for i, step in enumerate(self.steps):
            marker = "<-- 当前" if i == self.current_step_index else ""
            lines.append(f"  {i+1}. {step.summary_line()} {marker}")
            if step.notes:
                for note in step.notes[-2:]:
                    lines.append(f"      | {note}")
        lines.append("")
        if self.completed_steps + self.failed_steps > 0:
            parts = []
            if self.completed_steps > 0:
                parts.append(f"完成: {self.completed_steps}")
            if self.failed_steps > 0:
                parts.append(f"失败: {self.failed_steps}")
            if self.retry_count > 0:
                parts.append(f"重试: {self.retry_count}")
            if parts:
                lines.append(f"摘要: {' | '.join(parts)}")
                lines.append("")
        curr = self.current_step
        if curr and curr.status == StepStatus.IN_PROGRESS:
            lines.append(f"当前任务: {curr.description}")
            if curr.success_criteria:
                lines.append(f"成功标准: {curr.success_criteria}")
            if curr.tool_calls:
                last = curr.tool_calls[-1]
                icon = "!" if last.is_error else ">"
                lines.append(f"{icon} 上一步调用: `{last.tool_name}` > {last.result_summary[:120]}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Complex task detection
# ---------------------------------------------------------------------------

_PLAN_TRIGGER_KEYWORDS = [
    "build", "create", "implement", "develop", "write a", "make a",
    "refactor", "migrate", "convert", "multi-step", "pipeline", "workflow",
    "analyze", "research", "investigate",
]

_SIMPLE_KEYWORDS = [
    "what is", "what's", "how do i", "how to", "explain",
    "hello", "hi", "help",
]


def _estimate_complexity(task: str, max_turns: int = 0) -> float:
    text = task.lower()
    for kw in _SIMPLE_KEYWORDS:
        if text.startswith(kw) or text.strip().startswith(kw):
            return 0.0
    trigger_count = sum(1 for kw in _PLAN_TRIGGER_KEYWORDS if kw in text)
    base = min(trigger_count * 0.15, 0.6)
    length_factor = min(len(task) / 1000, 0.3)
    if max_turns > 10:
        base += 0.15
    newlines = task.count("\n")
    if newlines > 2:
        base += min(newlines * 0.05, 0.15)
    return min(base + length_factor, 1.0)


def should_plan(task: str, max_turns: int = 0) -> bool:
    return _estimate_complexity(task, max_turns) >= 0.45


# ---------------------------------------------------------------------------
# Plan decomposer
# ---------------------------------------------------------------------------

def decompose_task(task: str) -> list[dict[str, str]]:
    text = task.strip()
    steps = _parse_numbered_list(text)
    if steps and len(steps) >= 2:
        return steps
    steps = _parse_bullet_list(text)
    if steps and len(steps) >= 2:
        return steps
    return _heuristic_decompose(text)


def _parse_numbered_list(text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'(?:^|\n)\s*(?:\d+[\.\)]|Step\s+\d+[:\-])\s*(.+?)(?=\n\s*(?:\d+[\.\)]|Step\s+\d+[:\-]|\Z))',
        re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if len(matches) >= 2:
        return [
            {"id": f"step_{i+1}", "description": m.group(1).strip().rstrip("."),
             "success_criteria": f"Step {i+1} completed successfully"}
            for i, m in enumerate(matches)
        ]
    return []


def _parse_bullet_list(text: str) -> list[dict[str, str]]:
    items = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and stripped[0] in ("-", "*") and len(stripped) > 2:
            items.append(stripped[1:].strip())
    if len(items) >= 2:
        return [
            {"id": f"step_{i+1}", "description": item,
             "success_criteria": f"Step {i+1} completed successfully"}
            for i, item in enumerate(items)
        ]
    return []


def _heuristic_decompose(text: str) -> list[dict[str, str]]:
    key_phrases = [
        r'\bfirst\b', r'\bfirstly\b', r'\bfirst of all\b',
        r'\bnext\b', r'\bthen\b', r'\bafter that\b',
        r'\bfinally\b', r'\blastly\b', r'\bin the end\b',
        r'\bstep\s+\d+\b',
    ]
    compound = re.compile("|".join(key_phrases), re.IGNORECASE)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    if len(text) > 200:
        blocks = re.split(r'\n\s*\n', text)
        if len(blocks) >= 3:
            steps = []
            for i, block in enumerate(blocks[:6]):
                clean = block.strip()
                if clean and len(clean) > 15:
                    first_sent = re.split(r'(?<=[.!?])\s+', clean)[0].strip()
                    steps.append({
                        "id": f"step_{i+1}",
                        "description": first_sent[:200],
                        "success_criteria": _infer_criteria(first_sent),
                    })
            if len(steps) >= 2:
                return steps

    if compound.search(text) and len(sentences) >= 3:
        steps = []
        for i, sent in enumerate(sentences[:8]):
            clean = sent.strip()
            if clean and len(clean) > 10:
                steps.append({
                    "id": f"step_{i+1}",
                    "description": clean[:200],
                    "success_criteria": _infer_criteria(clean),
                })
        if len(steps) >= 2:
            return steps

    return [
        {"id": "step_1", "description": text[:300],
         "success_criteria": "Task completed successfully"},
    ]


def _infer_criteria(text: str) -> str:
    t = text.lower()
    if "test" in t:
        return "All tests pass without errors"
    if "implement" in t or "write" in t or "create" in t:
        return "Implementation is complete and correct"
    if "analyze" in t or "research" in t:
        return "Analysis is comprehensive and actionable"
    if "refactor" in t or "restructure" in t:
        return "Refactoring is complete with no regression"
    if "deploy" in t:
        return "Deployment is confirmed working"
    if "debug" in t or "fix" in t:
        return "Bug is fixed and verified"
    return "Step completed successfully"


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class PlanDoReviewEngine:
    """Plan-Do-Review 自主循环引擎。"""

    MAX_STEPS = 12
    DEEP_REVIEW_INTERVAL = 3

    def __init__(self) -> None:
        self.plan = RuntimePlan()
        self._is_active = False

    def initialize(self, task: str) -> None:
        self.plan = RuntimePlan(original_task=task[:2000])
        raw_steps = decompose_task(task)
        for i, s in enumerate(raw_steps[:self.MAX_STEPS]):
            self.plan.steps.append(StepNode(
                id=s.get("id", f"step_{i+1}"),
                description=s["description"],
                success_criteria=s.get("success_criteria", "Step completed successfully"),
                depends_on=[raw_steps[j]["id"] for j in range(i) if j < len(raw_steps)],
            ))
        self._is_active = True
        self.plan.current_step_index = -1

    def start_next_step(self) -> StepNode | None:
        for i, step in enumerate(self.plan.steps):
            if step.status == StepStatus.PENDING:
                deps_met = all(
                    any(s.id == dep and s.status == StepStatus.COMPLETED for s in self.plan.steps)
                    for dep in step.depends_on
                )
                step.status = StepStatus.BLOCKED if not deps_met else StepStatus.IN_PROGRESS
                if deps_met:
                    self.plan.current_step_index = i
                    return step
        self.plan.current_step_index = -1
        return None

    def mark_step_complete(self, summary: str = "") -> None:
        step = self.plan.current_step
        if step is None:
            return
        step.status = StepStatus.COMPLETED
        step.result_summary = summary[:500]
        self.plan.completed_steps += 1

    def mark_step_failed(self, error: str = "") -> None:
        step = self.plan.current_step
        if step is None:
            return
        step.error = error[:500]
        if step.retry_count < step.max_retries:
            step.retry_count += 1
            step.status = StepStatus.IN_PROGRESS
            self.plan.retry_count += 1
        else:
            step.status = StepStatus.FAILED
            self.plan.failed_steps += 1

    def skip_current_step(self, reason: str = "") -> None:
        step = self.plan.current_step
        if step is None:
            return
        step.status = StepStatus.SKIPPED
        step.notes.append(f"Skipped: {reason[:200]}")
        self.plan.completed_steps += 1

    def record_tool_call(
        self, turn: int, tool_name: str, args: dict[str, Any],
        result: str, is_error: bool, latency_ms: float = 0.0,
    ) -> None:
        step = self.plan.current_step
        if step is None:
            return
        step.tool_calls.append(ToolCallRecord(
            turn=turn, tool_name=tool_name,
            args_summary=_summarize_args(args),
            result_summary=_truncate(result, 200) if result else "",
            is_error=is_error, latency_ms=latency_ms,
        ))
        self.plan.total_tool_calls += 1

    def lightweight_review(self) -> ReviewGrade:
        step = self.plan.current_step
        if step is None:
            return ReviewGrade.PASS
        calls = step.tool_calls
        if not calls:
            return ReviewGrade.PASS
        error_calls = [c for c in calls if c.is_error]
        if error_calls and len(error_calls) == len(calls):
            return ReviewGrade.FAIL
        if error_calls and len(error_calls) / len(calls) > 0.5:
            return ReviewGrade.NEEDS_RETRY
        tool_counts: dict[str, int] = {}
        for c in calls:
            tool_counts[c.tool_name] = tool_counts.get(c.tool_name, 0) + 1
        repeated = {t: n for t, n in tool_counts.items() if n >= 4}
        if repeated:
            step.notes.append(f"Repeated tool calls: {repeated}")
            return ReviewGrade.PASS_WITH_ISSUES
        empty_results = [
            c for c in calls
            if not c.result_summary or c.result_summary.strip() in ("", "[]", "{}", "null", "None")
        ]
        if empty_results and len(empty_results) / len(calls) > 0.4:
            return ReviewGrade.PASS_WITH_ISSUES
        return ReviewGrade.PASS

    def needs_deep_review(self) -> bool:
        if self.plan.completed_steps > 0 and self.plan.completed_steps % self.DEEP_REVIEW_INTERVAL == 0:
            self.plan.deep_reviews_done += 1
            return True
        if self.plan.failed_steps >= 2:
            recent = self.plan.steps[-2:]
            if all(s.status == StepStatus.FAILED for s in recent if s.status != StepStatus.PENDING):
                return True
        return False

    def should_plan(self, task: str, max_turns: int = 0) -> bool:
        return should_plan(task, max_turns)

    def get_context(self) -> str:
        if not self._is_active or not self.plan.steps:
            return ""
        return self.plan.to_prompt_context()

    def reset(self) -> None:
        self.plan = RuntimePlan()
        self._is_active = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    skip_keys = {"api_key", "password", "secret", "token", "key"}
    safe = {k: v for k, v in args.items() if k not in skip_keys}
    try:
        return json.dumps(safe, ensure_ascii=False)[:150]
    except (TypeError, ValueError):
        return str(safe)[:150]


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


__all__ = [
    "PlanDoReviewEngine",
    "ReviewGrade",
    "RuntimePlan",
    "StepNode",
    "StepStatus",
    "decompose_task",
    "should_plan",
]
