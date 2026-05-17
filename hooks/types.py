#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
# ...
# Licensed under the Apache License, Version 2.0.

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

HookEventType = Literal[
    "pre_tool_exec",
    "post_tool_exec",
    "on_session_start",
    "on_session_end",
    "on_turn_start",
    "on_turn_end",
    "on_error",
    "on_permission_request",
    "on_permission_response",
    "pre_compact",
    "post_compact",
    "pre_model_request",
    "post_model_response",
    "on_tool_progress",
    "on_backend_error",
    "on_rate_limit",
    "on_checkpoint",
    "pre_sub_agent",
    "post_sub_agent",
    "on_goal_progress",
    "on_telemetry",
    "pre_bash",
    "on_file_change",
]

HookResult = dict[str, Any]
HookHandler = Callable[[str, dict[str, Any], dict[str, Any] | None], Awaitable[HookResult]]


@dataclass
class HookStartedEvent:
    hook_id: str
    hook_name: str
    event_type: HookEventType
    timestamp: float = field(default_factory=__import__('time').time)


@dataclass
class HookProgressEvent:
    hook_id: str
    hook_name: str
    event_type: HookEventType
    output: str
    stdout: str = ""
    stderr: str = ""


@dataclass
class HookResponseEvent:
    hook_id: str
    hook_name: str
    event_type: HookEventType
    output: str
    exit_code: int = 0
    outcome: str = "success"
