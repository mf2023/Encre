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
Alibaba DashScope backend -- Qwen series models (2026 lineup).

Alibaba Cloud's DashScope (Model Studio) provides access to the Qwen series
models including Qwen-Max, Qwen-Plus, Qwen-Flash, and QwQ (reasoning models).
The API is OpenAI-compatible.

Models:
- Qwen-Max series: Flagship models (qwen-max, qwen3-max)
- Qwen-Plus series: Balanced performance (qwen-plus, qwen3-plus)
- Qwen-Flash series: Fast and economical (qwen-flash, qwen3-flash)
- QwQ series: Reasoning-focused (qwq-plus)
- Qwen-Coder: Coding-optimized

Two service types:
- Standard: provider="alibaba", env=DASHSCOPE_API_KEY
- Coding Plan: provider="alibaba-coding-plan", env=DASHSCOPE_API_KEY

Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
Authentication: DASHSCOPE_API_KEY environment variable or explicit api_key.
"""

from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


class AlibabaBackend(OpenAISSEBackend):
    """Alibaba DashScope backend for the Qwen model series.

    Supports Qwen-Max, Qwen-Plus, Qwen-Flash, QwQ, and Qwen-Coder models
    via Alibaba Cloud's OpenAI-compatible API.
    """

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "qwen-plus",
        **kwargs: Any,
    ) -> None:
        """Initialize the Alibaba DashScope backend.

        Args:
            api_key: DashScope API key. Falls back to the DASHSCOPE_API_KEY
                environment variable when empty.
            base_url: API endpoint; defaults to the DashScope
                OpenAI-compatible endpoint.
            model: Default Qwen model identifier.
            **kwargs: Additional options forwarded to the parent backend.
        """
        if not base_url:
            # No explicit endpoint given: use the DashScope compatible URL.
            base_url = self.DEFAULT_BASE_URL
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _thinking_request_param(self) -> dict[str, Any] | None:
        """Qwen uses ``enable_thinking`` instead of DeepSeek's ``thinking``.

        QwQ-32B-Preview and the Qwen3 thinking variants require
        ``enable_thinking: true`` to emit ``reasoning_content``.  Regular
        Qwen-Max / Qwen-Plus / Qwen-Flash do not support a thinking
        toggle, so we omit the parameter entirely.
        """
        if self.model and (
            "qwq" in self.model.lower()
            or ("qwen3" in self.model.lower()
            and "think" in self.model.lower())
        ):
            return {"enable_thinking": True}
        return None

    def context_window_size(self) -> int:
        """Return context window for Qwen models.

        2026: Qwen3.6: 256K, Qwen-Long: 10M, Qwen3: 131K, Qwen-Max: 131K.
        """
        m = self.model.lower()
        # Qwen-Long is optimized for extremely long documents (up to 10M).
        if "qwen-long" in m or "qwenlong" in m:
            return 10_000_000
        # Qwen3.6 / Qwen-Coder generation uses a 256K window.
        if "qwen3.6" in m or "qwen3-6" in m or "qwen-coder" in m:
            return 256_000
        # Qwen3.5 / Qwen-Max / Qwen-Plus also expose 256K windows.
        if "qwen3.5" in m or "qwen-max" in m or "qwen-plus" in m:
            return 256_000
        return 256_000  # Qwen3.6 default
