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

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Recovery limits ───────────────────────────────────────────────────
MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
ESCALATED_MAX_TOKENS = 64_000
REACTIVE_COMPACT_MAX_RETRIES = 3

# ── Context overflow detection ────────────────────────────────────────

_CONTEXT_OVERFLOW_PATTERNS = [
    "prompt is too long",
    "context length exceeded",
    "input length exceeds",
    "input is too long",
    "max_tokens",
    "maximum context length",
    "reduce the length of the messages",
    "too many tokens",
    "413",
    "request too large",
    "payload too large",
]


def is_context_overflow(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(pattern.lower() in msg for pattern in _CONTEXT_OVERFLOW_PATTERNS)


def is_withheld_max_output_tokens(event: Any) -> bool:
    try:
        from encre.utils.types import BackendFinish
        if isinstance(event, BackendFinish):
            return event.reason in ("max_tokens", "length")
    except Exception:
        pass
    return False


def is_prompt_too_long_error(error_msg: str) -> bool:
    lower = error_msg.lower()
    return any(
        p in lower
        for p in [
            "prompt is too long",
            "context length exceeded",
            "input length exceeds",
            "input is too long",
            "maximum context length",
            "reduce the length",
            "too many tokens",
        ]
    )


def is_rate_limit_or_overload(exc: Exception) -> bool:
    msg = str(exc).lower()
    patterns = [
        "rate limit", "too many requests", "overloaded",
        "capacity", "throttl", "too many", "429",
        "503", "service unavailable", "high demand",
    ]
    return any(p in msg for p in patterns)


async def reactive_compact_with_retry(
    session: Any,
    compact_engine: Any,
    backend: Any,
    max_retries: int = REACTIVE_COMPACT_MAX_RETRIES,
    *,
    has_attempted: bool = False,
) -> bool:
    if has_attempted:
        logger.warning("[reactive] already attempted — skipping")
        return False

    for attempt in range(max_retries):
        try:
            context_msgs = session.get_context_messages()
            session.set_compact_archive(context_msgs)
            from encre.compact.engine import COMPACT_MAX_OUTPUT_TOKENS
            budget = COMPACT_MAX_OUTPUT_TOKENS // (2 ** attempt)
            compacted = await compact_engine.compact(
                context_msgs, backend=backend,
                turn_count=session.turn_count,
                system_prompt=session.messages[0].get("content", "") if session.messages else "",
                session_id=session.id or "",
            )
            if compacted is not None:
                session.replace_branch_messages(session.active_branch_id, compacted)
                logger.info(
                    "[reactive] compact succeeded attempt=%d/%d turn=%d budget=%d",
                    attempt + 1, max_retries, session.turn_count, budget,
                )
                return True
        except Exception as e:
            logger.warning(
                "[reactive] compact attempt %d/%d failed: %s",
                attempt + 1, max_retries, e,
            )
            if attempt < max_retries - 1:
                backoff = 1.0 * (2 ** attempt)
                await asyncio.sleep(backoff)

    logger.error("[reactive] all %d compact attempts failed", max_retries)
    return False


def yield_missing_tool_result_blocks(
    assistant_tool_calls: list[dict[str, Any]],
    error_message: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for tc in assistant_tool_calls:
        tc_id = tc.get("id", "") or tc.get("_client_id", "")
        if not tc_id:
            continue
        entry = {
            "role": "tool",
            "tool_call_id": tc_id,
            "name": tc.get("function", {}).get("name", tc.get("name", "")),
            "content": error_message,
            "is_error": True,
        }
        results.append(entry)
    return results


def build_max_tokens_recovery_message() -> str:
    return (
        "Output token limit hit. Resume directly — no apology, no recap of what you were doing. "
        "Pick up mid-thought if that is where the cut happened. Break remaining work into smaller pieces."
    )


def build_slot_escalation_message() -> str:
    return (
        "[Output limit reached. Please continue from where you left off. "
        "Be concise — your full output budget is now available.]"
    )


def can_fallback(config: Any) -> bool:
    return bool(
        getattr(config, "fallback_model", "")
        and getattr(config, "fallback_model", "") != getattr(config, "model", "")
    )


def build_fallback_system_message(original_model: str, fallback_model: str) -> str:
    return (
        f"Switched to {fallback_model} due to high demand for {original_model}"
    )