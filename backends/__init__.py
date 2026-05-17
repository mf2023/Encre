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
Backends package — multi-provider LLM inference adapters.

This package provides a unified interface for communicating with 9 different
LLM providers, each implemented as a subclass of :class:`BaseBackend`. Every
backend normalises the provider's native streaming protocol into a common set
of :class:`BackendEvent` types so that the agent loop can consume text deltas,
tool call deltas, thinking tokens, finish signals, and error events without
caring which provider is underneath.

Provider backends (2026 lineup)
-------------------------------
+--------------------------+-----------------------------------------------+
| Backend                  | Supported models (2026)                        |
+--------------------------+-----------------------------------------------+
| :class:`OpenAIBackend`   | GPT-4.1 family, GPT-5.x, o3, o4-mini          |
| :class:`AnthropicBackend`| Claude Opus 4.6/4.7, Sonnet 4.5/4.6, Haiku 4.5|
| :class:`GoogleBackend`   | Gemini 2.5 Pro, Gemini 2.5 Flash              |
| :class:`DeepSeekBackend` | DeepSeek V4-Flash, V4-Pro                     |
| :class:`GroqBackend`     | Llama 3.3 70B, Llama 4 Scout, GPT-OSS         |
| :class:`OllamaBackend`   | Locally-hosted models via Ollama               |
| :class:`LocalBackend`    | Hugging Face transformers (CPU/GPU)            |
| :class:`BedrockBackend`  | AWS Bedrock Converse API (Claude, Llama, etc.) |
| :class:`OpenAICompatibleBackend` | Any OpenAI-compatible endpoint (vLLM, etc.) |
+--------------------------+-----------------------------------------------+

Shared infrastructure
---------------------
- :class:`OpenAISSEBackend` — base class for OpenAI-protocol backends (SSE parsing,
  tool call buffering, non-stream fallback). Used by OpenAI, DeepSeek, Groq,
  and OpenAICompatible backends.
- :func:`retry_with_backoff` — exponential-backoff retry for transient HTTP
  errors (429, 502, 503, 504, timeouts, connection errors).
- :class:`BackendRegistry` — dynamic model metadata registry with provider-level
  defaults and thread-safe registration/resolution.

Typical usage::

    from yim.backends import OpenAIBackend

    backend = OpenAIBackend(model="gpt-4.1")
    async for event in backend.chat(messages=[{"role": "user", "content": "Hello"}]):
        print(event)
"""

from yim.backends.base import BaseBackend
from yim.backends.openai_sse import OpenAISSEBackend
from yim.backends.openai import OpenAIBackend
from yim.backends.anthropic import AnthropicBackend
from yim.backends.ollama import OllamaBackend
from yim.backends.deepseek import DeepSeekBackend
from yim.backends.google import GoogleBackend
from yim.backends.groq import GroqBackend
from yim.backends.local import LocalBackend
from yim.backends.bedrock import BedrockBackend
from yim.backends.openai_compatible import OpenAICompatibleBackend
from yim.backends.failover import FailoverBackend, BackendHealth
from yim.backends.router import RouterBackend, CostTracker, TaskCategory
from yim.backends.retry import RetryConfig, retry_with_backoff, DEFAULT_RETRY_CONFIG

__all__ = [
    "BaseBackend",
    "OpenAISSEBackend",
    "OpenAIBackend",
    "AnthropicBackend",
    "OllamaBackend",
    "DeepSeekBackend",
    "GoogleBackend",
    "GroqBackend",
    "LocalBackend",
    "BedrockBackend",
    "OpenAICompatibleBackend",
    "FailoverBackend",
    "BackendHealth",
    "RouterBackend",
    "CostTracker",
    "TaskCategory",
    "RetryConfig",
    "retry_with_backoff",
    "DEFAULT_RETRY_CONFIG",
]