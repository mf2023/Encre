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

from typing import Any

from yim.backends.base import BaseBackend
from yim.backends.anthropic import AnthropicBackend
from yim.backends.bedrock import BedrockBackend
from yim.backends.deepseek import DeepSeekBackend
from yim.backends.failover import FailoverBackend
from yim.backends.google import GoogleBackend
from yim.backends.groq import GroqBackend
from yim.backends.local import LocalBackend
from yim.backends.ollama import OllamaBackend
from yim.backends.openai import OpenAIBackend
from yim.backends.openai_compatible import OpenAICompatibleBackend
from yim.backends.router import RouterBackend


def create_backend(type: str, **kwargs: Any) -> BaseBackend | None:
    if not type:
        return None
    backend_map: dict[str, type[BaseBackend]] = {
        "openai": OpenAIBackend,
        "anthropic": AnthropicBackend,
        "ollama": OllamaBackend,
        "deepseek": DeepSeekBackend,
        "google": GoogleBackend,
        "groq": GroqBackend,
        "local": LocalBackend,
        "bedrock": BedrockBackend,
        "openai_compatible": OpenAICompatibleBackend,
        "failover": FailoverBackend,
        "router": RouterBackend,
    }
    cls = backend_map.get(type)
    if cls is None:
        raise ValueError(f"Unknown backend type: {type}. Available: {sorted(backend_map.keys())}")
    return cls(**kwargs)
