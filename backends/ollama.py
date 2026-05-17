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

"""
Ollama backend — locally-hosted models via the Ollama API.

Ollama is a local model runner that supports hundreds of open-source models
including Llama 3.x, Mistral, Qwen 2.5, DeepSeek, Gemma 2, Phi-4, and many
more.  Models run locally on CPU or GPU, with no data leaving the machine.

Key characteristics:
- No API key required (runs on localhost by default)
- OpenAI-compatible API at ``http://localhost:11434/v1``
- Supports tool/function calling (model-dependent)
- Context window varies by model (typically 4K-128K)
- No built-in prompt caching or thinking support
- Free and fully offline

This backend extends :class:`OpenAISSEBackend` because Ollama provides an
OpenAI-compatible API endpoint.  The default base URL is
``http://localhost:11434/v1``.
"""

from typing import Any

from yim.backends.openai_sse import OpenAISSEBackend


class OllamaBackend(OpenAISSEBackend):
    """Ollama backend for locally-hosted open-source models.

    Connects to a local Ollama instance at ``http://localhost:11434/v1``
    (configurable via ``base_url``).  Supports any model available in the
    local Ollama library.

    This backend inherits all SSE streaming, tool calling, and error handling
    from :class:`OpenAISSEBackend` without modification, as Ollama's API is
    fully OpenAI-compatible.

    Note:
        Tool calling support depends on the specific model being used.
        Some models (e.g., Llama 3.1+ and Qwen 2.5) support native tool
        calling, while others may not.
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "llama3.2",
        **kwargs: Any,
    ) -> None:
        """Initialise the Ollama backend.

        Args:
            api_key: Not required for local Ollama (defaults to empty string).
            base_url: Custom API base URL.  Defaults to
                ``http://localhost:11434/v1``.
            model: Model name.  Defaults to ``llama3.2``.  Must be a model
                that has been pulled into the local Ollama instance.
            **kwargs: Additional arguments passed to :class:`OpenAISSEBackend`.
        """
        if not base_url:
            base_url = self.DEFAULT_BASE_URL
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)

    def context_window_size(self) -> int:
        """Return a conservative context window estimate for local models.

        Ollama models vary widely in context window size (4K-128K+).  This
        returns a conservative 8192 as a safe default.  The actual context
        window depends on the specific model loaded.
        """
        return 8192