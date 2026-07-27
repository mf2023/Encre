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

"""
DeepSeek backend -- V4-Flash, V4-Pro (2026 lineup).

As of May 2026, DeepSeek's model lineup has been updated:

- **DeepSeek V4-Flash**: The default chat model with 1M context window,
  384K output tokens, and aggressive cache discounts (92% off cache hits).
  Pricing: $0.14/$0.28 per 1M tokens (input/output).  Replaces the
  deprecated ``deepseek-chat`` model.

- **DeepSeek V4-Pro**: The enhanced reasoning model with 1M context window,
  384K output tokens, and 80% cache hit discount.  Pricing: $1.74/$3.48 per
  1M tokens.  Replaces the deprecated ``deepseek-reasoner`` model.

- **Legacy models**: ``deepseek-chat`` and ``deepseek-reasoner`` are
  deprecated as of July 2026.  They are kept in the registry for backward
  compatibility but map to their V4 equivalents.

Both V4 models support:
- Tool/function calling (OpenAI-compatible format)
- Thinking/reasoning tokens (emitted as ``reasoning_content`` in the API)
- Prompt caching (80-92% discount on cache hits)
- 1M token context windows
- 384K token output limits

This backend extends :class:`OpenAISSEBackend` because DeepSeek uses an
OpenAI-compatible API.  The only customisation is the extraction of
``reasoning_content`` from the response delta, which is emitted as
:class:`BackendThinking` events.
"""

from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


# Standard OpenAI message fields that DeepSeek accepts.  DeepSeek's newer
# validation rejects unknown/Encre-internal fields such as ``branch_id``,
# ``seq_in_branch``, ``id``, ``parent_id``, ``usage``, ``segments`` and
# ``reasoning_content`` on regular chat-completion requests, which causes
# multi-turn tool loops to fail after the first tool result is appended.
_ALLOWED_MSG_FIELDS: dict[str, frozenset[str]] = {
    "system": frozenset({"role", "content", "name"}),
    "user": frozenset({"role", "content", "name"}),
    "assistant": frozenset({"role", "content", "name", "tool_calls"}),
    "tool": frozenset({"role", "content", "tool_call_id"}),
}

# Fields allowed inside an OpenAI ``tool_calls`` item.
_ALLOWED_TOOL_CALL_FIELDS: frozenset[str] = frozenset({"id", "type", "function"})


# DeepSeek supports a subset of JSON Schema for tool parameters.  Keep the
# standard structural keywords and value-type keywords; drop anything that
# may have been valid in JSON Schema but is not documented/supported.
_SUPPORTED_SCHEMA_KEYWORDS: frozenset[str] = frozenset({
    "type", "properties", "required", "additionalProperties",
    "items", "enum", "anyOf", "allOf", "oneOf", "$ref", "$def",
    "description", "title", "default",
    # string
    "pattern", "format",
    # number / integer
    "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf",
})


def _coerce_content(content: Any) -> Any:
    """Return a string or list content block; replace ``None`` with ``""``."""
    if content is None:
        return ""
    if isinstance(content, list):
        return content
    return str(content)


def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip Encre-internal fields from messages before sending to DeepSeek.

    DeepSeek's chat-completion endpoint validates the message payload more
    strictly than before and rejects unknown top-level fields.  This helper
    keeps only the OpenAI-standard fields for each role and ensures that
    ``content`` is never ``None`` (``None`` is accepted by OpenAI but rejected
    by DeepSeek for assistant messages that carry ``tool_calls``).
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))
        allowed = _ALLOWED_MSG_FIELDS.get(role, _ALLOWED_MSG_FIELDS["user"])
        clean: dict[str, Any] = {k: v for k, v in msg.items() if k in allowed}
        clean["role"] = role
        clean["content"] = _coerce_content(msg.get("content"))
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                clean_tool_calls: list[dict[str, Any]] = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    clean_tc = {k: v for k, v in tc.items() if k in _ALLOWED_TOOL_CALL_FIELDS}
                    func = tc.get("function")
                    if isinstance(func, dict):
                        args = func.get("arguments")
                        if args is None:
                            args = "{}"
                        elif not isinstance(args, str):
                            args = str(args)
                        clean_tc["function"] = {
                            "name": str(func.get("name", "")),
                            "arguments": args,
                        }
                    clean_tool_calls.append(clean_tc)
                clean["tool_calls"] = clean_tool_calls
        elif role == "tool":
            clean["tool_call_id"] = str(msg.get("tool_call_id", ""))
        out.append(clean)
    return out


def _normalize_tool_schema_for_deepseek(schema: Any) -> Any:
    """Make a JSON Schema object compliant with DeepSeek's supported subset.

    DeepSeek validates tool schemas more strictly than the OpenAI default:
    top-level ``parameters`` must be an ``object`` with ``properties``,
    every property must be listed in ``required``, and
    ``additionalProperties`` must be ``False``.  Unsupported keywords such as
    ``minLength``/``maxLength``/``minItems``/``maxItems`` are stripped.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _SUPPORTED_SCHEMA_KEYWORDS:
            continue
        if key in ("properties", "items"):
            if isinstance(value, dict):
                out[key] = {k: _normalize_tool_schema_for_deepseek(v) for k, v in value.items()}
            else:
                out[key] = value
        elif key in ("anyOf", "allOf", "oneOf"):
            if isinstance(value, list):
                out[key] = [_normalize_tool_schema_for_deepseek(v) for v in value]
            else:
                out[key] = value
        else:
            out[key] = value

    if out.get("type") == "object" and "properties" in out:
        # All object properties must be required for DeepSeek.
        required = set(out.get("required", []))
        required.update(out["properties"].keys())
        out["required"] = sorted(required)
        out.setdefault("additionalProperties", False)
    return out


def _sanitize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize tool definitions for DeepSeek's stricter validation."""
    out: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            out.append(tool)
            continue
        func = tool.get("function", {})
        if not isinstance(func, dict):
            out.append(tool)
            continue
        name = str(func.get("name", ""))
        # DeepSeek allows a-z, A-Z, 0-9, underscore and hyphen, max 64 chars.
        name = name[:64]
        parameters = func.get("parameters")
        if isinstance(parameters, dict):
            parameters = _normalize_tool_schema_for_deepseek(parameters)
        else:
            parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(func.get("description", "")),
                "parameters": parameters,
            },
        })
    return out


class DeepSeekBackend(OpenAISSEBackend):
    """DeepSeek backend for the 2026 V4 model lineup.

    Supports DeepSeek V4-Flash (default) and V4-Pro via the OpenAI-compatible
    API at ``https://api.deepseek.com``.  The legacy ``deepseek-chat`` and
    ``deepseek-reasoner`` model names are automatically mapped to their V4
    equivalents because DeepSeek deprecated them in July 2026.

    The key difference from the base :class:`OpenAISSEBackend` is the
    extraction of ``reasoning_content`` from the response delta, which
    contains the model's chain-of-thought reasoning.  This is emitted as
    :class:`BackendThinking` events so the agent loop can surface them
    appropriately.

    2026 pricing summary:
        - DeepSeek V4-Flash: $0.14/$0.28 per 1M tokens (92% cache discount)
        - DeepSeek V4-Pro: $1.74/$3.48 per 1M tokens (80% cache discount)
    """

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    # Deprecated model IDs and their V4 replacements.
    _DEPRECATED_MODEL_MAP: dict[str, str] = {
        "deepseek-chat": "deepseek-v4-flash",
        "deepseek-reasoner": "deepseek-v4-pro",
    }

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "deepseek-v4-flash",
        **kwargs: Any,
    ) -> None:
        """Initialise the DeepSeek backend.

        Args:
            api_key: DeepSeek API key.
            base_url: Custom API base URL.  Defaults to
                ``https://api.deepseek.com``.
            model: Model name.  Defaults to ``deepseek-v4-flash``.  Legacy
                values ``deepseek-chat`` and ``deepseek-reasoner`` are
                automatically mapped to ``deepseek-v4-flash`` and
                ``deepseek-v4-pro`` respectively.
            **kwargs: Additional arguments passed to :class:`OpenAISSEBackend`.
        """
        if not base_url:
            base_url = self.DEFAULT_BASE_URL
        # DeepSeek deprecated deepseek-chat/reasoner in July 2026.  Map them
        # to the current V4 IDs so existing user settings keep working.
        model = self._DEPRECATED_MODEL_MAP.get(model, model)
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    # ── Overrides ─────────────────────────────────────────────────────

    def context_window_size(self) -> int:
        """Return the context window size for DeepSeek V4 models.

        Both V4-Flash and V4-Pro support 1,048,576 (1M) token context windows.
        Legacy models (deepseek-chat/reasoner) had 64K context.
        """
        return 1048576

    def supports_thinking(self) -> bool:
        """DeepSeek V4 models support reasoning/thinking tokens."""
        return True

    def supports_prompt_caching(self) -> bool:
        """DeepSeek V4 models support prompt caching (80-92% discount)."""
        return True

    # ── Multimodal/Extended API capabilities ──────────────────────
    # DeepSeek is a text-only chat API.  None of the OpenAI multimodal
    # or extended endpoints (images, audio, embeddings, moderation, files,
    # batch, fine-tuning, responses, realtime) are available.

    def supports_image_generation(self) -> bool:
        return False

    def supports_image_edit(self) -> bool:
        return False

    def supports_image_variation(self) -> bool:
        return False

    def supports_embeddings(self) -> bool:
        return False

    def supports_moderation(self) -> bool:
        return False

    def supports_files(self) -> bool:
        return False

    def supports_batch(self) -> bool:
        return False

    def supports_fine_tuning(self) -> bool:
        return False

    def supports_responses_api(self) -> bool:
        return False

    def supports_realtime(self) -> bool:
        return False

    def supports_vision_input(self) -> bool:
        return False

    def _build_request_data(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        stream: bool = True,
    ) -> dict[str, Any]:
        """Build the DeepSeek request body with sanitized messages/tools.

        DeepSeek's newer validation rejects unknown fields on messages and
        requires tool parameter schemas to be well-formed (all object
        properties required, ``additionalProperties: false``).  We sanitize
        both before delegating to the base request builder.

        DeepSeek V4 models also accept ``reasoning_effort`` (e.g. ``"high"``
        or ``"max"``) to control reasoning intensity.
        """
        data = super()._build_request_data(
            messages=_sanitize_messages(messages),
            tools=_sanitize_tools(tools) if tools else None,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )
        if getattr(self, "reasoning_effort", ""):
            data["reasoning_effort"] = self.reasoning_effort
        return data
