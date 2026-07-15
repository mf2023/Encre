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
Tencent TokenHub backend -- Hunyuan and third-party model access.

Tencent Cloud's TokenHub platform provides access to Hunyuan models and
third-party models (DeepSeek, GLM, Kimi, MiniMax, etc.) through an
OpenAI-compatible API.

Models:
- Hunyuan Hy3 (preview): Latest flagship
- Hunyuan TurboS / Turbo: Previous generation
- Third-party: DeepSeek, GLM, Kimi, MiniMax, etc.

Base URL: https://tokenhub.tencentmaas.com/v1
Authentication: TOKENHUB_API_KEY environment variable or explicit api_key.

Aliases: tencent, tokenhub, tencentmaas
"""

from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


class TencentBackend(OpenAISSEBackend):
    """Tencent TokenHub backend for Hunyuan and third-party models.

    Provides access to Tencent Cloud's LLM platform via an OpenAI-compatible
    API.  Both Hunyuan native models and third-party models are supported.
    """

    DEFAULT_BASE_URL = "https://tokenhub.tencentmaas.com/v1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "hy3-preview",
        **kwargs: Any,
    ) -> None:
        if not base_url:
            base_url = self.DEFAULT_BASE_URL
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _thinking_request_param(self) -> dict[str, Any] | None:
        """Hunyuan thinking models use ``enable_thinking`` (boolean).

        Hunyuan-T1 / hunyuan-a13b thinking variants require
        ``enable_thinking: true`` to emit ``reasoning_content``.  Regular
        Hunyuan-Pro / Standard models do not accept this parameter, so
        we only send it for thinking-capable model IDs.
        """
        if not self.thinking_enabled or not self.model:
            return None
        m = self.model.lower()
        # Heuristic: send the thinking toggle for Hunyuan reasoning
        # variants (``-think``/``-t1``/``-a13b``).  Other SKUs reject the
        # parameter, so we omit it for them.
        if "think" in m or "t1" in m or "a13b" in m:
            # Only Hunyuan reasoning-capable SKUs accept this parameter.
            return {"enable_thinking": True}
        return None

    def context_window_size(self) -> int:
        return 131072
