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
GLM (Zhipu AI) backend -- GLM-4.5, GLM-4.6, GLM-4.7 (2026 lineup).

Zhipu AI's GLM series models are among the leading Chinese LLMs, offering
strong reasoning, coding, and multilingual capabilities.  The API is
OpenAI-compatible and supports thinking/reasoning tokens.

Models:
- GLM-4.5: Balanced general-purpose model
- GLM-4.6: Enhanced reasoning with tool calling
- GLM-4.7: Latest flagship with extended context

Base URL: https://open.bigmodel.cn/api/paas/v4
Authentication: GLM_API_KEY environment variable or explicit api_key.
"""

from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


class GLMBackend(OpenAISSEBackend):
    """GLM (Zhipu AI) backend for the GLM-4.x model series.

    Supports GLM-4.5, GLM-4.6, and GLM-4.7 via Zhipu AI's OpenAI-compatible
    API.  Thinking/reasoning tokens are extracted from ``reasoning_content``.
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "glm-4.7",
        **kwargs: Any,
    ) -> None:
        if not base_url:
            base_url = self.DEFAULT_BASE_URL
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def _thinking_request_param(self) -> dict[str, Any] | None:
        """GLM-4.6 / GLM-4.7 use the DeepSeek-style ``thinking`` envelope.

        Zhipu AI's GLM-4.6 and later reasoning models accept the same
        ``{"thinking": {"type": "enabled"}}`` parameter as DeepSeek.  Older
        GLM-4 / GLM-3 models do not advertise a thinking toggle, so we
        only emit the parameter for models that look reasoning-capable.
        """
        if not self.model:
            return {"thinking": {"type": "enabled"}}
        m = self.model.lower()
        # GLM-4.5+ and GLM-5.x are reasoning-capable.
        if "glm-4.5" in m or "glm-4.6" in m or "glm-4.7" in m or "glm-5" in m:
            return {"thinking": {"type": "enabled"}}
        return None

    def context_window_size(self) -> int:
        """Return context window for GLM models.

        2026: GLM-5.x: 200K, GLM-4.x: 128K.
        """
        m = self.model.lower()
        if "glm-5" in m or "glm5" in m:
            return 200_000
        return 131_072
