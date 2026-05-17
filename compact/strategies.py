#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

from abc import ABC, abstractmethod
from typing import Any

from yim.utils.tokens import estimate_tokens


class YmiCompactStrategy(ABC):
    @abstractmethod
    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        ...


class YmiAlwaysCompactStrategy(YmiCompactStrategy):
    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
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
        max_tokens: int = 128000,
    ) -> bool:
        return len(messages) > 10


class YmiTokenBudgetStrategy(YmiCompactStrategy):
    def __init__(self, budget_ratio: float = 0.5) -> None:
        self._budget_ratio = budget_ratio

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        budget = int(max_tokens * self._budget_ratio)
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
        max_tokens: int = 128000,
    ) -> bool:
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > max_tokens * self._budget_ratio

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        content = message.get("content", "")
        if isinstance(content, str):
            return estimate_tokens(content)
        return 0
class YmiBudgetReductionStrategy(YmiCompactStrategy):
    """Stage 1: Cap per-message size. Always active, cheapest.
    Truncates individual messages that exceed per-message limits."""

    def __init__(self, max_chars_per_message: int = 40000) -> None:
        self._max_chars = max_chars_per_message

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
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
        max_tokens: int = 128000,
    ) -> bool:
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > self._max_chars:
                return True
        return False


class YmiSnipStrategy(YmiCompactStrategy):
    """Stage 2: Trim older history, keeping system + N most recent turns.
    Each turn = user + assistant (+ optional tool result)."""

    def __init__(self, keep_recent_turns: int = 8) -> None:
        self._keep_turns = keep_recent_turns

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        system = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self._keep_turns * 2:
            return messages
        # Keep system + last N*2 non-system messages
        kept = non_system[-(self._keep_turns * 2):]
        return system + kept

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        return len(messages) > self._keep_turns * 2 + 4


class YmiMicroCompactStrategy(YmiCompactStrategy):
    """Stage 3: Merge consecutive similar-role messages, trim verbose tool outputs.
    Non-destructive: only compresses redundant content."""

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Trim large tool results
            if role in ("tool",) or (isinstance(content, str) and len(content) > 3000):
                if isinstance(content, str):
                    trimmed = dict(msg)
                    trimmed["content"] = content[:3000] + "\n... [output truncated for space]"
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
        max_tokens: int = 128000,
    ) -> bool:
        # Check if any message has large content
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 3000:
                return True
        return len(messages) > 20


class YmiContextCollapseStrategy(YmiCompactStrategy):
    """Stage 4: Replace old tool outputs with one-line summaries.
    Preserves the fact that a tool was called but not the full output."""

    def __init__(self, collapse_before_turn: int = 5) -> None:
        self._collapse_before = collapse_before_turn

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
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
        max_tokens: int = 128000,
    ) -> bool:
        return len(messages) > self._collapse_before * 3


class YmiSemanticCompactStrategy(YmiCompactStrategy):
    """Stage 5: Semantic tool output summarization and context partitioning.

    Instead of blunt truncation, intelligently summarizes tool outputs:
    - grep → groups matches by file, shows counts + first 3 matches
    - glob → groups files by directory
    - bash → extracts errors and key output lines
    - file_read → preserves function signatures only

    Also splits context into hot/warm/cold tiers for better information
    density management.
    """

    def __init__(self, max_tool_output_chars: int = 8000) -> None:
        from yim.compact.semantic import SemanticToolOutputCompactor
        self._compactor = SemanticToolOutputCompactor()
        self._compactor.MAX_TOOL_OUTPUT_CHARS = max_tool_output_chars

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
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
        max_tokens: int = 128000,
    ) -> bool:
        for msg in messages:
            if msg.get("role") in ("tool",):
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 8000:
                    return True
        return False


class YmiAutoCompactStrategy(YmiCompactStrategy):
    """Auto compact strategy with optional LLM summarization.

    Falls back to budget-based compaction when no backend is available.
    When a backend is provided, uses LLM summarization as the last stage.
    """

    SUMMARIZE_PROMPT = (
        "Summarize the conversation above, preserving all key technical details, "
        "decisions made, code changes discussed, errors encountered, and pending tasks. "
        "Keep file paths, function names, and version numbers intact. "
        "Output only the structured summary, no preamble."
    )

    def __init__(
        self,
        threshold_ratio: float = 0.75,
        backend: Any = None,
        summarizer_model: str = "",
    ) -> None:
        self._threshold_ratio = threshold_ratio
        self._backend = backend
        self._summarizer_model = summarizer_model

    def set_backend(self, backend: Any) -> None:
        self._backend = backend

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        should = await self.should_compact(messages, max_tokens)
        if not should:
            return messages

        # Stage 1: budget-based truncation (cheapest)
        budget_strategy = YmiTokenBudgetStrategy(budget_ratio=0.6)
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
                    truncated = system_msgs + [summary_msg] + keep_last
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
                # Multimodal content — extract text parts only
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
                from yim.utils.types import BackendText
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
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > max_tokens * self._threshold_ratio

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        content = message.get("content", "")
        if isinstance(content, str):
            return estimate_tokens(content)
        return 0
class YmiMultiStagePipeline(YmiCompactStrategy):
    """6-stage compaction pipeline — cheapest first, only escalates when needed.

    Stages (in order):
      1. Budget Reduction — cap per-message size (always)
      2. Snip — trim oldest history beyond N turns
      3. MicroCompact — merge similar messages, trim verbose tool outputs
      4. Semantic Compact — intelligent tool output summarization
      5. Context Collapse — summarize old tool outputs to one-liners
      6. Auto Compact — full model-generated summary (last resort)

    Architecture: budget → snip → micro → semantic → collapse → auto-compact
    """

    def __init__(
        self,
        context_threshold: float = 0.92,
        keep_recent_turns: int = 8,
        collapse_before_turn: int = 5,
    ) -> None:
        self._context_threshold = context_threshold
        self._stages: list[YmiCompactStrategy] = [
            YmiBudgetReductionStrategy(),
            YmiSnipStrategy(keep_recent_turns=keep_recent_turns),
            YmiMicroCompactStrategy(),
            YmiSemanticCompactStrategy(),
            YmiContextCollapseStrategy(collapse_before_turn=collapse_before_turn),
            YmiAutoCompactStrategy(threshold_ratio=0.75),
        ]

    async def compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        current = messages
        for stage in self._stages:
            if await stage.should_compact(current, max_tokens):
                current = await stage.compact(current, max_tokens)
            if not await self._is_over_threshold(current, max_tokens):
                break
        return current

    async def should_compact(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 128000,
    ) -> bool:
        return await self._is_over_threshold(messages, max_tokens)

    async def _is_over_threshold(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> bool:
        total = sum(self._estimate_tokens(m) for m in messages)
        return total > max_tokens * self._context_threshold

    @staticmethod
    def _estimate_tokens(message: dict[str, Any]) -> int:
        content = message.get("content", "")
        if isinstance(content, str):
            return estimate_tokens(content)
        return 0