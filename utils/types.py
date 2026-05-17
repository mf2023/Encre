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

from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal, Union

FinishReason = Literal["stop", "tool_calls", "error", "max_tokens", "cancelled"]
PermissionMode = Literal["default", "accept_edits", "bypass", "dont_ask", "plan", "auto"]
PermissionBehavior = Literal["allow", "deny", "ask"]
TaskType = Literal["bash", "agent", "workflow"]
TaskStatus = Literal["pending", "running", "completed", "failed", "killed"]


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class ToolCallStart:
    name: str
    id: str


@dataclass
class ToolCallDelta:
    id: str
    key: str
    value: str


@dataclass
class ToolCallEnd:
    id: str


@dataclass
class ToolProgress:
    id: str
    tool_name: str
    status: str


@dataclass
class ToolResult:
    id: str
    content: str
    is_error: bool


@dataclass
class PermissionRequest:
    tool_name: str
    reason: str


@dataclass
class Finish:
    reason: FinishReason
    usage: dict[str, Any] | None = None
    error: str | None = None


AgentEvent = Union[TextDelta, ThinkingDelta, ToolCallStart, ToolCallDelta, ToolCallEnd, ToolProgress, ToolResult, PermissionRequest, Finish]


# ── Multimodal Content Blocks ──────────────────────────────────────


@dataclass
class TextContent:
    type: str = "text"
    text: str = ""


@dataclass
class ImageContent:
    type: str = "image"
    data: str = ""           # base64 encoded
    mime_type: str = "image/png"
    source_url: str = ""


@dataclass
class FileContent:
    type: str = "file"
    data: str = ""           # base64 encoded
    filename: str = ""
    mime_type: str = "application/octet-stream"


@dataclass
class ToolUseContent:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] | None = None


@dataclass
class ToolResultContent:
    type: str = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False


ContentBlock = Union[TextContent, ImageContent, FileContent, ToolUseContent, ToolResultContent]


@dataclass
class BackendText:
    text: str


@dataclass
class BackendThinking:
    text: str
    signature_delta: str | None = None


@dataclass
class BackendToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class BackendToolCallDelta:
    index: int
    key: str
    value: str


@dataclass
class BackendFinish:
    reason: str
    usage: dict[str, Any] | None = None


@dataclass
class BackendError:
    error: str


BackendEvent = Union[BackendText, BackendThinking, BackendToolCall, BackendToolCallDelta, BackendFinish, BackendError]


@dataclass
class PermissionAllow:
    behavior: PermissionBehavior = "allow"


@dataclass
class PermissionDeny:
    behavior: PermissionBehavior = "deny"


@dataclass
class PermissionAsk:
    behavior: PermissionBehavior = "ask"


PermissionDecision = Union[PermissionAllow, PermissionDeny, PermissionAsk]


@dataclass
class AdaptiveThinking:
    enabled: bool = True
    min_tokens: int = 1024
    max_tokens: int = 8192
    budget_ratio: float = 0.5


@dataclass
class EnabledThinking:
    enabled: bool = True
    budget_tokens: int = 4096


@dataclass
class DisabledThinking:
    enabled: bool = False


ThinkingConfig = Union[AdaptiveThinking, EnabledThinking, DisabledThinking]


def create_text_delta(text: str) -> TextDelta:
    return TextDelta(text=text)


def create_thinking_delta(text: str) -> ThinkingDelta:
    return ThinkingDelta(text=text)


def create_tool_call_start(name: str, id: str) -> ToolCallStart:
    return ToolCallStart(name=name, id=id)


def create_tool_call_delta(id: str, key: str, value: str) -> ToolCallDelta:
    return ToolCallDelta(id=id, key=key, value=value)


def create_tool_call_end(id: str) -> ToolCallEnd:
    return ToolCallEnd(id=id)


def create_tool_progress(id: str, tool_name: str, status: str) -> ToolProgress:
    return ToolProgress(id=id, tool_name=tool_name, status=status)


def create_tool_result(id: str, content: str, is_error: bool = False) -> ToolResult:
    return ToolResult(id=id, content=content, is_error=is_error)


def create_permission_request(tool_name: str, reason: str) -> PermissionRequest:
    return PermissionRequest(tool_name=tool_name, reason=reason)


def create_finish(reason: FinishReason, usage: dict[str, Any] | None = None, error: str | None = None) -> Finish:
    return Finish(reason=reason, usage=usage, error=error)


def create_backend_text(text: str) -> BackendText:
    return BackendText(text=text)


def create_backend_thinking(text: str, signature_delta: str | None = None) -> BackendThinking:
    return BackendThinking(text=text, signature_delta=signature_delta)


def create_backend_tool_call(id: str, name: str, arguments: str) -> BackendToolCall:
    return BackendToolCall(id=id, name=name, arguments=arguments)


def create_backend_tool_call_delta(index: int, key: str, value: str) -> BackendToolCallDelta:
    return BackendToolCallDelta(index=index, key=key, value=value)


def create_backend_finish(reason: str, usage: dict[str, Any] | None = None) -> BackendFinish:
    return BackendFinish(reason=reason, usage=usage)


def create_backend_error(error: str) -> BackendError:
    return BackendError(error=error)