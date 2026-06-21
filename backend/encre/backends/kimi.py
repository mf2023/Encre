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
Kimi / Moonshot backend -- Kimi-K2, Kimi-K2.5, Kimi-K2.6 (2026 lineup).

Moonshot AI's Kimi series models offer strong long-context reasoning and
coding capabilities.  The API is OpenAI-compatible.

Models:
- Kimi K2: Base reasoning model
- Kimi K2.5: Enhanced version with tool calling
- Kimi K2.6: Latest with extended capabilities

Two endpoints:
- Global: https://api.moonshot.cn/v1  (KIMI_API_KEY)
- China:  https://api.moonshot.cn/v1  (KIMI_CN_API_KEY, alias kimi-cn)

Base URL: https://api.moonshot.cn/v1
Authentication: KIMI_API_KEY environment variable or explicit api_key.
"""

from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


class KimiBackend(OpenAISSEBackend):
    """Kimi (Moonshot) backend for the Kimi K2 model series.

    Supports Kimi K2, K2.5, and K2.6 via Moonshot AI's OpenAI-compatible API.
    """

    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "kimi-k2.6",
        **kwargs: Any,
    ) -> None:
        if not base_url:
            base_url = self.DEFAULT_BASE_URL
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _thinking_request_param(self) -> dict[str, Any] | None:
        """Return the provider-specific parameter that enables thinking.

        Moonshot AI's thinking model lineup uses three parameter shapes
        depending on the model generation:

        * ``kimi-k2.7-code`` (and ``kimi-k2.7-code-highspeed``): always
          thinks, and the official docs explicitly forbid sending any
          ``thinking`` parameter (``type: "disabled"`` is rejected).  We
          therefore return ``None`` to skip it entirely.

        * ``kimi-k2.6``: general-purpose thinking model; defaults to
          thinking on.  Accepts ``thinking.type`` (``"enabled"`` /
          ``"disabled"``) and ``thinking.keep`` (``"all"`` for Preserved
          Thinking).

        * ``kimi-k2.5``: legacy thinking model; defaults to thinking on
          and accepts ``thinking.type``.  Does not support
          ``thinking.keep`` (Preserved Thinking).

        Some third-party proxies (e.g. OpenRouter, Apiyi) translate to
        ``enable_thinking: true`` automatically, but Moonshot's native
        endpoint uses the DeepSeek-style ``thinking.type`` envelope.
        """
        if not self.model:
            return None
        m = self.model.lower()
        # kimi-k2.7-code always thinks; sending the param is rejected.
        if "k2.7-code" in m or "k2-7-code" in m:
            return None
        # kimi-k2.5 / k2.6 / k2-thinking all accept the DeepSeek shape.
        if "k2.5" in m or "k2.6" in m or "k2-thinking" in m or "k2.7" in m:
            return {"thinking": {"type": "enabled"}}
        return None

    def context_window_size(self) -> int:
        return 262144
