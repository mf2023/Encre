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

"""Legacy, rule-based context compaction strategies.

These :class:`EncreCompactStrategy` implementations predate the
model-driven :class:`~encre.compact.engine.CompactEngine` and are kept for
backward compatibility.  Each strategy exposes ``compact`` (produce a
reduced message list) and ``should_compact`` (decide whether to run).

:class:`EncreMultiStagePipeline` chains them from cheapest to most
expensive -- budget reduction -> snip -> micro compact -> semantic compact
-> context collapse -> auto (LLM) compact -- escalating only as needed and
protecting the task anchor and recent turns.
"""


from abc import ABC, abstractmethod
from typing import Any

from encre.prompts.loader import PromptLoader
from encre.utils.tokens import count_message_tokens


def _estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate full message tokens including tool_calls and block content."""
    return count_message_tokens([message])


class EncreCompactStrategy(ABC):
    """Abstract base class for all compaction strategies.

    Subclasses implement :meth:`compact` (return a reduced copy of the
    message list) and :meth:`should_compact` (decide whether compaction is
    warranted for the current token budget).
    """
    @abstractmethod
    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        ...


class EncreAlwaysCompactStrategy(EncreCompactStrategy):
    """Aggressive strategy that always keeps only the first and last turns.

    Useful as a guaranteed fallback: it never relies on token estimates,
    merely retaining the first two and last two non-system messages.
    """
    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Keep system messages plus the first and last two turns."""
        if len(messages) <= 2:
            return messages
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= 4:
            return messages
        kept = non_system[:2] + non_system[-2:]
        return system_messages + kept

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Compact once the conversation exceeds ten messages."""
        return len(messages) > 10


class EncreTokenBudgetStrategy(EncreCompactStrategy):
    """Keep messages until a fraction of the token budget is consumed."""
    def __init__(self, budget_ratio: float = 0.5) -> None:
        """Configure the fraction of the token budget to retain."""
        self._budget_ratio = budget_ratio

    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Greedily keep messages (system, then first and last turns) under budget."""
        budget = int(_max_tokens * self._budget_ratio)
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if not non_system:
            return messages

        kept: list[dict[str, Any]] = []
        token_count = 0
        for m in system_messages:
            kept.append(m)
            token_count += self._estimate_tokens(m)

        first = non_system[:2]
        for m in first:
            kept.append(m)
            token_count += self._estimate_tokens(m)

        last = non_system[-2:]
        for m in last:
            t = self._estimate_tokens(m)
            if token_count + t <= budget or m == last[-1]:
                kept.append(m)
                token_count += t

        return kept

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Compact when total tokens exceed the configured budget ratio."""
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > _max_tokens * self._budget_ratio

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        """Estimate a single message's token count."""
        return _estimate_message_tokens(message)
class EncreBudgetReductionStrategy(EncreCompactStrategy):
    """Stage 1: Cap per-message size. Always active, cheapest.
    Truncates individual messages that exceed per-message limits."""

    def __init__(self, max_chars_per_message: int = 40000) -> None:
        """Configure the maximum characters retained per message."""
        self._max_chars = max_chars_per_message

    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Truncate every message that exceeds the per-message character cap."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > self._max_chars:
                truncated = dict(msg)
                truncated["content"] = content[:self._max_chars] + "\n... [message truncated]"
                result.append(truncated)
            elif isinstance(content, list):
                # Handle array content (Anthropic format)
                truncated = dict(msg)
                new_content: list[dict[str, Any]] = []
                total_len = 0
                for block in content:
                    block_text = str(block.get("text", block.get("input", "")))
                    total_len += len(block_text)
                    if total_len <= self._max_chars:
                        new_content.append(block)
                    else:
                        break
                truncated["content"] = new_content
                result.append(truncated)
            else:
                result.append(msg)
        return result

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Trigger when any single message exceeds the per-message cap."""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > self._max_chars:
                return True
        return False


class EncreSnipStrategy(EncreCompactStrategy):
    """Stage 2: Trim older history, keeping system + N most recent turns.

    Turn count adapts to token budget so that even a conversation with very
    large tool outputs (e.g. web_search, bash) is trimmed aggressively
    rather than blowing past the context window.
    """

    def __init__(self, keep_recent_turns: int = 6) -> None:
        """Configure how many recent turns to retain when snipping."""
        self._keep_turns = keep_recent_turns
        self._min_turns = 3

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Keep system + the most recent turns that fit within 60% of budget."""
        system = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self._min_turns * 2:
            return messages

        # Adaptive: start at keep_turns, shrink if the result still exceeds budget
        for keep_turns in range(self._keep_turns, self._min_turns - 1, -1):
            kept = non_system[-(keep_turns * 2):]
            total = sum(_estimate_message_tokens(m) for m in system + kept)
            if total <= max_tokens * 0.6:
                return system + kept
        # Last resort: minimal context
        return system + non_system[-(self._min_turns * 2):]

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        """Snip only once the token budget is actually threatened (>=50%)."""
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self._min_turns * 2 + 2:
            return False
        # Only snip when the token budget is actually threatened
        total = sum(_estimate_message_tokens(m) for m in messages)
        return total > max_tokens * 0.5


class EncreMicroCompactStrategy(EncreCompactStrategy):
    """Stage 3: Merge consecutive similar-role messages, trim verbose tool outputs.
    Non-destructive: only compresses redundant content."""

    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Merge consecutive user messages and trim verbose tool outputs."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Trim large tool results -- shorter cap to handle tools like web_search/web_fetch
            if role in ("tool",) or (isinstance(content, str) and len(content) > 2000):
                if isinstance(content, str):
                    trimmed = dict(msg)
                    trimmed["content"] = content[:2000] + "\n... [output truncated for space]"
                    result.append(trimmed)
                else:
                    result.append(msg)
            # Merge consecutive user messages (e.g., guidance injection)
            elif role == "user" and result and result[-1].get("role") == "user":
                prev_content = result[-1].get("content", "")
                if isinstance(prev_content, str) and isinstance(content, str):
                    result[-1]["content"] = prev_content + "\n\n" + content
                else:
                    result.append(msg)
            else:
                result.append(msg)
        return result

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Trigger when a message exceeds 2000 chars or history is very long."""
        # Check if any message has large content
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 2000:
                return True
        return len(messages) > 15


class EncreContextCollapseStrategy(EncreCompactStrategy):
    """Stage 4: Replace old tool outputs with one-line summaries.
    Preserves the fact that a tool was called but not the full output."""

    def __init__(self, collapse_before_turn: int = 5) -> None:
        """Configure how many recent turns are protected from collapsing."""
        self._collapse_before = collapse_before_turn

    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Collapse tool outputs older than the protected turn window."""
        if len(messages) <= self._collapse_before * 2:
            return messages

        result: list[dict[str, Any]] = []
        turn_count = 0
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Count turns from the end
            if role == "assistant":
                turn_count += 1

            turns_from_end = 0
            # Count remaining assistant messages
            for j in range(i, len(messages)):
                if messages[j].get("role") == "assistant":
                    turns_from_end += 1

            # Collapse old tool results
            if role in ("tool",) and turns_from_end > self._collapse_before:
                if isinstance(content, str) and len(content) > 200:
                    collapsed = dict(msg)
                    collapsed["content"] = content[:200] + " [collapsed]"
                    result.append(collapsed)
                else:
                    result.append(msg)
            else:
                result.append(msg)

        return result

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Collapse when total tokens exceed 60% of the budget."""
        if len(messages) <= self._collapse_before * 3:
            return False
        total = sum(_estimate_message_tokens(m) for m in messages)
        return total > _max_tokens * 0.6


class EncreSemanticCompactStrategy(EncreCompactStrategy):
    """Stage 5: Semantic tool output summarization and context partitioning.

    Instead of blunt truncation, intelligently summarizes tool outputs:
    - grep -> groups matches by file, shows counts + first 3 matches
    - glob -> groups files by directory
    - bash -> extracts errors and key output lines
    - file_read -> preserves function signatures only

    Also splits context into hot/warm/cold tiers for better information
    density management.
    """

    def __init__(self, max_tool_output_chars: int = 8000) -> None:
        """Wire up the shared :class:`SemanticToolOutputCompactor`."""
        from encre.compact.semantic import SemanticToolOutputCompactor
        self._compactor = SemanticToolOutputCompactor()
        self._compactor.MAX_TOOL_OUTPUT_CHARS = max_tool_output_chars

    async def compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Replace oversized tool outputs with semantic summaries."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_name = msg.get("name", "")

            if role in ("tool",) and isinstance(content, str):
                compacted = self._compactor.compact_tool_output(tool_name, content)
                if compacted != content:
                    new_msg = dict(msg)
                    new_msg["content"] = compacted
                    result.append(new_msg)
                    continue
            result.append(msg)
        return result

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        _max_tokens: int = 128000,
    ) -> bool:
        """Trigger when any tool output exceeds 8000 characters."""
        for msg in messages:
            if msg.get("role") in ("tool",):
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 8000:
                    return True
        return False


_loader = PromptLoader()


class EncreAutoCompactStrategy(EncreCompactStrategy):
    """Auto compact strategy with optional LLM summarization.

    Falls back to budget-based compaction when no backend is available.
    When a backend is provided, uses LLM summarization as the last stage.
    """

    SUMMARIZE_PROMPT = _loader.load("summarize", category="compact")

    def __init__(
        self,
        threshold_ratio: float = 0.75,
        backend: Any = None,
        summarizer_model: str = "",
    ) -> None:
        """Configure threshold ratio, optional summarisation backend/model."""
        self._threshold_ratio = threshold_ratio
        self._backend = backend
        self._summarizer_model = summarizer_model

    def set_backend(self, backend: Any) -> None:
        """Attach a backend used for LLM-based summarisation."""
        self._backend = backend

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Run budget truncation, then LLM summary if a backend is available."""
        should = await self.should_compact(messages, max_tokens)
        if not should:
            return messages

        # Stage 1: budget-based truncation (cheapest)
        budget_strategy = EncreTokenBudgetStrategy(budget_ratio=0.6)
        truncated = await budget_strategy.compact(messages, max_tokens)

        # Stage 2: LLM summarization (when backend available)
        if self._backend is not None and len(truncated) > 4:
            try:
                summary = await self._summarize(truncated)
                if summary:
                    # Keep system message + summary + last 2 messages
                    system_msgs = [m for m in truncated if m.get("role") == "system"]
                    non_system = [m for m in truncated if m.get("role") != "system"]
                    keep_last = non_system[-2:] if len(non_system) >= 2 else non_system
                    summary_msg = {"role": "user", "content": f"[Conversation summary]\n{summary}"}
                    truncated = [*system_msgs, summary_msg, *keep_last]
            except Exception:
                pass  # Summarization failed, keep truncated result

        return truncated

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """Call the backend to generate a summary of the conversation."""
        if self._backend is None:
            return ""

        conversation_text: list[str] = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                conversation_text.append(f"[{role}]: {content[:500]}")
            elif isinstance(content, list):
                # Multimodal content -- extract text parts only
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", "")[:500])
                conversation_text.append(f"[{role}]: {' '.join(parts)}")

        full_text = "\n".join(conversation_text)
        if len(full_text) < 500:
            return ""

        summary_msgs = [
            {"role": "user", "content": f"{self.SUMMARIZE_PROMPT}\n\nConversation:\n{full_text[:8000]}"},
        ]

        try:
            result_parts: list[str] = []
            async for event in self._backend.chat(
                messages=summary_msgs,
                max_tokens=512,
                temperature=0.0,
                stream=True,
                enable_caching=False,
            ):
                from encre.utils.types import BackendText
                if isinstance(event, BackendText):
                    result_parts.append(event.text)
            return "".join(result_parts).strip()
        except Exception:
            return ""

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        """Compact when total tokens exceed the configured threshold ratio."""
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > max_tokens * self._threshold_ratio

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        """Estimate a single message's token count."""
        return _estimate_message_tokens(message)
class EncreMultiStagePipeline(EncreCompactStrategy):
    """6-stage compaction pipeline -- cheapest first, only escalates when needed.

    Stages (in order):
      1. Budget Reduction -- cap per-message size (always)
      2. Snip -- trim oldest history beyond N turns
      3. MicroCompact -- merge similar messages, trim verbose tool outputs
      4. Semantic Compact -- intelligent tool output summarization
      5. Context Collapse -- summarize old tool outputs to one-liners
      6. Auto Compact -- full model-generated summary (last resort)

    Architecture: budget -> snip -> micro -> semantic -> collapse -> auto-compact
    """

    def __init__(
        self,
        context_threshold: float = 0.20,
        keep_recent_turns: int = 6,
        collapse_before_turn: int = 4,
        max_messages: int = 15,
    ) -> None:
        """Build the ordered list of compaction stages."""
        self._context_threshold = context_threshold
        self._max_messages = max_messages
        self._stages: list[EncreCompactStrategy] = [
            EncreBudgetReductionStrategy(),
            EncreSnipStrategy(keep_recent_turns=keep_recent_turns),
            EncreMicroCompactStrategy(),
            EncreSemanticCompactStrategy(),
            EncreContextCollapseStrategy(collapse_before_turn=collapse_before_turn),
            EncreAutoCompactStrategy(threshold_ratio=0.75),
        ]

    @staticmethod
    def _sanitize_sequence(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fix message sequences broken by compaction.

        Compaction strategies snip by message count, which can split tool_call
        groups -- an assistant message with N tool_calls must be followed by
        exactly N tool results. If any are missing, most backends (OpenAI,
        DeepSeek, Anthropic) reject the request with a 400 error.

        Also handles leading/trailing orphaned messages.
        """
        if not messages:
            return messages

        # Phase 1: strip leading/trailing orphans -- must loop because popping
        # an assistant(tool_calls) can expose new leading tool messages.
        while True:
            while messages and messages[0].get("role") == "tool":
                messages.pop(0)
            if not messages:
                break
            if messages[0].get("role") == "assistant" and messages[0].get("tool_calls"):
                messages.pop(0)
                continue  # Recheck for newly exposed leading tools
            break
        while messages and messages[-1].get("role") == "tool":
            messages.pop()

        # Phase 2: ensure every assistant with tool_calls has ALL its tool results
        result: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "")
            tool_calls = msg.get("tool_calls")

            if role == "assistant" and tool_calls:
                # Collect expected tool_call_ids
                expected_ids: set[str] = set()
                for tc in tool_calls:
                    tid = tc.get("id", "") if isinstance(tc, dict) else ""
                    if tid:
                        expected_ids.add(tid)

                # Look ahead for following tool results
                j = i + 1
                found_ids: set[str] = set()
                tool_results: list[dict[str, Any]] = []
                while j < len(messages) and messages[j].get("role") == "tool":
                    tid = messages[j].get("tool_call_id", "")
                    if tid:
                        found_ids.add(tid)
                        tool_results.append(messages[j])
                    j += 1

                # Keep only if ALL expected tool results are present
                if expected_ids and expected_ids.issubset(found_ids):
                    result.append(msg)
                    result.extend(tool_results)
                    i = j
                    continue
                # Missing tool results -> drop this assistant + partial tool results
                i = j
                continue

            result.append(msg)
            i += 1

        return result

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Run all stages (multi-pass) then sanitise and anchor-protect."""
        current = messages
        # Multi-pass: run the full pipeline up to 3 times so that
        # information-dense outputs (web_search results, large diffs)
        # get multiple rounds of reduction until they stabilise.
        for _round in range(3):
            changed = False
            for stage in self._stages:
                if await stage.should_compact(current, max_tokens):
                    prev = current
                    current = await stage.compact(current, max_tokens)
                    if current != prev:
                        changed = True
                if not await self._is_over_threshold(current, max_tokens):
                    break
            if not changed or not await self._is_over_threshold(current, max_tokens):
                break

        # ── Anchor-point protection ───────────────────────────────────
        # The first user message is the TASK -- it must never be lost.
        # The last assistant + tool results are the CURRENT STATE --
        # the model needs them to continue.  We splice both into the
        # compacted result if any stage removed them.
        current = self._sanitize_sequence(current)
        current = self._anchor_protect(current, messages)
        return current

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        """Compact when message count or token total crosses the threshold."""
        if len(messages) > self._max_messages:
            return True
        return await self._is_over_threshold(messages, max_tokens)

    async def _is_over_threshold(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> bool:
        """Return True while total tokens exceed the context threshold."""
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > max_tokens * self._context_threshold

    def _anchor_protect(
        self,
        compacted: list[dict[str, Any]],
        original: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Ensure the first user message and last 2 turns survive.

        The first user message IS the task definition -- lose it and the
        model forgets why it's working.  The last two turns carry the
        immediate context the model needs to reason forward.  Any
        compaction stage that removed these is overridden.
        """
        # Find anchor messages by scanning original
        first_user = None
        for m in original:
            if m.get("role") == "user":
                first_user = m
                break

        # Find last 2 user messages and their follow-ups
        user_idxs = [i for i, m in enumerate(original) if m.get("role") == "user"]
        user_idxs[-1] if user_idxs else -1
        penultimate_user_idx = user_idxs[-2] if len(user_idxs) >= 2 else -1
        recent_original = original[penultimate_user_idx:] if penultimate_user_idx >= 0 else []

        # Check what survived compaction
        compacted_ids = {m.get("id", "") for m in compacted if m.get("id")}
        [m.get("role") for m in compacted]

        # Ensure first user is present
        if first_user is not None and first_user.get("id", "") not in compacted_ids:
            compacted = [first_user, *compacted]
            compacted_ids.add(first_user.get("id", ""))

        # Ensure recent messages (last 2 turns) are present
        for m in recent_original:
            if m.get("id", "") and m.get("id") not in compacted_ids:
                compacted.append(m)
                compacted_ids.add(m.get("id", ""))

        # Deduplicate by id while preserving order
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for m in compacted:
            mid = m.get("id", "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            deduped.append(m)

        # Sanitize: run _sanitize_sequence to fix any broken tool_call groups
        return self._sanitize_sequence(deduped)

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        """Estimate a single message's token count."""
        return _estimate_message_tokens(message)
