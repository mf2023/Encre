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

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from yim.logging_config import get_logger
from yim.crypto import encrypt, decrypt

logger = get_logger("yim.telemetry")


@dataclass
class ToolCallRecord:
    tool_name: str
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)
    tokens_used: int = 0
    error_message: str = ""


@dataclass
class TurnRecord:
    turn_number: int
    event_count: int
    latency_ms: float
    compact_triggered: bool = False
    token_usage: dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class RetryRecord:
    """Record of a backend retry event."""
    attempt: int
    error_type: str  # "http_status", "exception"
    error_detail: str
    delay_s: float
    timestamp: float = field(default_factory=time.time)


class YmiTelemetry:
    def __init__(self, enabled: bool = True, session_id: str = "") -> None:
        self.enabled = enabled
        self.session_id = session_id or str(int(time.time() * 1000))
        self.tool_calls: list[ToolCallRecord] = []
        self.turns: list[TurnRecord] = []
        self.retries: list[RetryRecord] = []
        self._session_started_at: float = time.time()
        self._output_dir: str = ""

    def _ensure_output(self) -> None:
        if self._output_dir:
            return
        from yim.config import get_data_dir
        _dir = get_data_dir() / "telemetry"
        _dir.mkdir(parents=True, exist_ok=True)
        self._output_dir = str(_dir)

    def _write_jsonl(self, record: dict[str, Any]) -> None:
        if not self._output_dir:
            self._ensure_output()
        try:
            _path = os.path.join(self._output_dir, f"{self.session_id}.jsonl")
            line = json.dumps(record, ensure_ascii=False)
            try:
                encrypted_line = encrypt(line)
            except Exception:
                encrypted_line = line
            with open(_path, "a", encoding="utf-8") as f:
                f.write(encrypted_line + "\n")
        except Exception:
            pass  # never crash on telemetry write failure

    def record_tool_call(
        self,
        tool_name: str,
        latency_ms: float,
        success: bool = True,
        tokens_used: int = 0,
        error_message: str = "",
    ) -> None:
        if not self.enabled:
            return
        record = ToolCallRecord(
            tool_name=tool_name,
            latency_ms=latency_ms,
            success=success,
            tokens_used=tokens_used,
            error_message=error_message,
        )
        self.tool_calls.append(record)
        entry = {
            "event": "tool_call",
            "timestamp": record.timestamp,
            "tool_name": record.tool_name,
            "latency_ms": record.latency_ms,
            "success": record.success,
            "tokens_used": record.tokens_used,
            "error": record.error_message or None,
        }
        logger.info(json.dumps(entry, ensure_ascii=False))
        self._write_jsonl(entry)

    def record_turn(
        self,
        turn_number: int,
        event_count: int,
        latency_ms: float,
        compact_triggered: bool = False,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        if not self.enabled:
            return
        record = TurnRecord(
            turn_number=turn_number,
            event_count=event_count,
            latency_ms=latency_ms,
            compact_triggered=compact_triggered,
            token_usage=token_usage or {},
        )
        self.turns.append(record)
        entry = {
            "event": "turn",
            "timestamp": record.timestamp,
            "turn_number": record.turn_number,
            "event_count": record.event_count,
            "latency_ms": record.latency_ms,
            "compact_triggered": record.compact_triggered,
            "token_usage": record.token_usage,
        }
        logger.info(json.dumps(entry, ensure_ascii=False))
        self._write_jsonl(entry)

    def record_retry(
        self,
        attempt: int,
        error_type: str,
        error_detail: str,
        delay_s: float,
    ) -> None:
        """Record a backend retry event."""
        if not self.enabled:
            return
        record = RetryRecord(
            attempt=attempt,
            error_type=error_type,
            error_detail=error_detail,
            delay_s=delay_s,
        )
        self.retries.append(record)
        entry = {
            "event": "retry",
            "timestamp": record.timestamp,
            "attempt": record.attempt,
            "error_type": record.error_type,
            "error_detail": record.error_detail,
            "delay_s": record.delay_s,
        }
        logger.warning(json.dumps(entry, ensure_ascii=False))
        self._write_jsonl(entry)

    def get_summary(self) -> dict[str, Any]:
        total_tool_calls = len(self.tool_calls)
        successful_tool_calls = sum(1 for t in self.tool_calls if t.success)
        failed_tool_calls = total_tool_calls - successful_tool_calls
        tool_latencies = [t.latency_ms for t in self.tool_calls]
        avg_tool_latency = sum(tool_latencies) / len(tool_latencies) if tool_latencies else 0.0

        total_turns = len(self.turns)
        turn_latencies = [t.latency_ms for t in self.turns]
        avg_turn_latency = sum(turn_latencies) / len(turn_latencies) if turn_latencies else 0.0
        total_events = sum(t.event_count for t in self.turns)
        compactions = sum(1 for t in self.turns if t.compact_triggered)
        session_duration_s = time.time() - self._session_started_at

        tool_usage: dict[str, int] = {}
        for t in self.tool_calls:
            tool_usage[t.tool_name] = tool_usage.get(t.tool_name, 0) + 1

        total_retries = len(self.retries)
        retry_by_type: dict[str, int] = {}
        for r in self.retries:
            retry_by_type[r.error_detail] = retry_by_type.get(r.error_detail, 0) + 1

        return {
            "session_duration_s": session_duration_s,
            "total_turns": total_turns,
            "total_tool_calls": total_tool_calls,
            "successful_tool_calls": successful_tool_calls,
            "failed_tool_calls": failed_tool_calls,
            "avg_tool_latency_ms": round(avg_tool_latency, 2),
            "avg_turn_latency_ms": round(avg_turn_latency, 2),
            "total_events": total_events,
            "compactions": compactions,
            "tool_usage": tool_usage,
            "total_retries": total_retries,
            "retry_by_error": retry_by_type,
        }

    def flush(self) -> dict[str, Any]:
        summary = self.get_summary()
        entry = {"event": "session_summary", **summary}
        logger.info(json.dumps(entry, ensure_ascii=False))
        self._write_jsonl(entry)
        return summary

    def reset(self) -> None:
        self.tool_calls.clear()
        self.turns.clear()
        self.retries.clear()
        self._session_started_at = time.time()
