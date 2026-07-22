from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReviewSuggestion:
    """A single suggestion from a background review pass."""

    kind: str  # "memory" | "skill" | "strategy" | "reflection"
    summary: str
    detail: str = ""
    timestamp: float = field(default_factory=time.time)


class BackgroundReviewer:
    """Periodically forks a lightweight sub-agent to review the session and
    suggest memory/skill/strategy updates.

    Unlike ``EncreReflexLoop`` (heuristic, no LLM), this runs an actual
    sub-agent with a review prompt, producing richer insights at the cost
    of one extra API call.

    Runs after every ``review_interval`` turns (default 5).  The review
    sub-agent receives the last N turns of conversation and tool outcomes
    and returns structured suggestions.
    """

    def __init__(
        self,
        review_interval: int = 5,
        max_review_turns: int = 10,
        enabled: bool = True,
    ) -> None:
        self.review_interval = review_interval
        self.max_review_turns = max_review_turns
        self.enabled = enabled
        self._turn_count: int = 0
        self._suggestions: list[ReviewSuggestion] = []
        self._review_task: asyncio.Task[Any] | None = None

    async def on_turn_end(
        self,
        loop: Any,
        suggestions_callback: Callable[[list[ReviewSuggestion]], None] | None = None,
    ) -> None:
        """Called after each turn.  Triggers a background review every
        ``review_interval`` turns.

        ``loop`` is the active ``EncreLoop`` — used to fork a sub-agent
        for the review.
        """
        if not self.enabled:
            return
        self._turn_count += 1
        if self._turn_count % self.review_interval != 0:
            return
        if self._review_task is not None and not self._review_task.done():
            return

        self._review_task = asyncio.create_task(
            self._run_review(loop, suggestions_callback)
        )

    async def _run_review(
        self,
        loop: Any,
        suggestions_callback: Callable[[list[ReviewSuggestion]], None] | None = None,
    ) -> None:
        """Fork a sub-agent with a review prompt.

        The review prompt includes the last N turns of conversation and
        asks the sub-agent to suggest memory entries, skill definitions,
        or strategy adjustments.
        """
        try:
            messages = getattr(loop.session, "messages", [])
            recent = messages[-self.max_review_turns * 4:] if messages else []
            if not recent:
                return

            turns_text = _format_recent_turns(recent)

            review_prompt = (
                "You are a review agent. Analyze the recent conversation turns below "
                "and suggest improvements in these categories:\n"
                "1. MEMORY: facts, preferences, or patterns worth remembering\n"
                "2. SKILL: reusable tool workflows or patterns\n"
                "3. STRATEGY: parameter choices or tool selection improvements\n"
                "4. REFLECTION: self-correction notes\n\n"
                f"Recent conversation:\n{turns_text}\n\n"
                "Return structured suggestions, one per line, prefixed with "
                "[MEMORY], [SKILL], [STRATEGY], or [REFLECTION]."
            )

            sub_result = await loop._run_sub_agent(
                prompt=review_prompt,
                system_prompt="You are a review sub-agent. Be concise and specific.",
                max_turns=2,
                tool_policy="readonly",
            )
            content = sub_result.get("content", "") if isinstance(sub_result, dict) else ""
            suggestions = _parse_suggestions(content)
            self._suggestions.extend(suggestions)
            if suggestions_callback:
                suggestions_callback(suggestions)
        except Exception:
            pass


def _format_recent_turns(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages[-40:]:
        role = m.get("role", "?")
        content = str(m.get("content", "") or "")
        if len(content) > 500:
            content = content[:500] + "..."
        tool_calls = m.get("tool_calls")
        if tool_calls:
            names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
            lines.append(f"[{role}] tool_calls: {', '.join(names)}")
        elif content.strip():
            lines.append(f"[{role}] {content.strip()[:200]}")
    return "\n".join(lines[-30:])


def _parse_suggestions(text: str) -> list[ReviewSuggestion]:
    suggestions: list[ReviewSuggestion] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for kind, label in [("memory", "MEMORY"), ("skill", "SKILL"),
                            ("strategy", "STRATEGY"), ("reflection", "REFLECTION")]:
            if f"[{label}]" in line.upper():
                summary = line.split("]", 1)[-1].strip().strip(":").strip()
                suggestions.append(ReviewSuggestion(kind=kind, summary=summary))
                break
    return suggestions
