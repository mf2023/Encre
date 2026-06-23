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



from typing import Any

from encre.backends.aigateway import AIGatewayBackend
from encre.backends.alibaba import AlibabaBackend
from encre.backends.anthropic import AnthropicBackend
from encre.backends.arcee import ArceeBackend
from encre.backends.base import BaseBackend
from encre.backends.bedrock import BedrockBackend
from encre.backends.deepseek import DeepSeekBackend
from encre.backends.failover import FailoverBackend
from encre.backends.github_copilot import GitHubCopilotBackend
from encre.backends.glm import GLMBackend
from encre.backends.gmi import GMIBackend
from encre.backends.google import GoogleBackend
from encre.backends.groq import GroqBackend
from encre.backends.huggingface import HuggingFaceBackend
from encre.backends.kilocode import KiloCodeBackend
from encre.backends.kimi import KimiBackend
from encre.backends.lmstudio import LMStudioBackend
from encre.backends.local import LocalBackend
from encre.backends.minimax import MiniMaxBackend
from encre.backends.novita import NovitaBackend
from encre.backends.ollama import OllamaBackend
from encre.backends.openai import OpenAIBackend
from encre.backends.openai_compatible import OpenAICompatibleBackend
from encre.backends.opencode import OpenCodeGoBackend, OpenCodeZenBackend
from encre.backends.openrouter import OpenRouterBackend
from encre.backends.retry import DEFAULT_RETRY_CONFIG, RetryConfig
from encre.backends.router import RouterBackend
from encre.backends.tencent import TencentBackend
from encre.backends.volcengine import VolcengineArkBackend
from encre.backends.xiaomi import XiaomiBackend


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_failover_backends(
    models: list[Any],
    default_api_key: str = "",
    default_base_url: str = "",
    default_model: str = "",
) -> list[tuple[str, BaseBackend]]:
    """Convert a list of model configs into ``(name, backend)`` pairs."""
    result: list[tuple[str, BaseBackend]] = []
    for m in models:
        if hasattr(m, "enabled") and not m.enabled:
            continue
        if hasattr(m, "name"):  # ModelConfig dataclass
            name = m.name or m.model_id or "unknown"
            bt = m.backend_type or "openai"
            ak = m.api_key or default_api_key
            bu = m.base_url or default_base_url
            md = m.model_id or default_model
        elif isinstance(m, dict):  # Raw dict
            name = m.get("name") or m.get("model_id", "unknown")
            bt = m.get("backend_type", "openai")
            ak = m.get("api_key", default_api_key)
            bu = m.get("base_url", default_base_url)
            md = m.get("model_id", default_model)
        else:
            continue
        be = create_backend(bt, api_key=ak, base_url=bu, model=md)
        if be is not None:
            result.append((name, be))
    return result


_FAILOVER_ACCEPTED = frozenset({"retry_config", "connection_monitor"})


def _create_failover(**kwargs: Any) -> FailoverBackend:
    """Construct a ``FailoverBackend`` from factory kwargs."""
    # Pre-instantiated backends (programmatic use).
    backends = kwargs.pop("backends", None)
    if backends is not None:
        return FailoverBackend(backends=backends, **{
            k: v for k, v in kwargs.items() if k in _FAILOVER_ACCEPTED
        })

    # Model config list (from EncreConfig.models).
    models = kwargs.pop("models", None)
    if models:
        built = _build_failover_backends(
            models,
            default_api_key=kwargs.get("api_key", ""),
            default_base_url=kwargs.get("base_url", ""),
            default_model=kwargs.get("model", ""),
        )
        if built:
            return FailoverBackend(backends=built, **{
                k: v for k, v in kwargs.items() if k in _FAILOVER_ACCEPTED
            })

    raise ValueError(
        "FailoverBackend requires either 'backends' (list of tuple) "
        "or 'models' (list of ModelConfig / dict) parameter"
    )


# ── Factory ──────────────────────────────────────────────────────────────


def create_backend(type: str, **kwargs: Any) -> BaseBackend | None:
    if not type:
        return None

    # Failover requires special handling — it needs pre-built children.
    if type == "failover":
        return _create_failover(**kwargs)

    # For non-failover types, strip meta-params that the individual
    # backend constructors do not expect.
    kwargs.pop("models", None)

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
        "openrouter": OpenRouterBackend,
        "novita": NovitaBackend,
        "aigateway": AIGatewayBackend,
        "glm": GLMBackend,
        "kimi": KimiBackend,
        "arcee": ArceeBackend,
        "gmi": GMIBackend,
        "minimax": MiniMaxBackend,
        "alibaba": AlibabaBackend,
        "kilocode": KiloCodeBackend,
        "xiaomi": XiaomiBackend,
        "tencent": TencentBackend,
        "huggingface": HuggingFaceBackend,
        "opencode-zen": OpenCodeZenBackend,
        "opencode-go": OpenCodeGoBackend,
        "lmstudio": LMStudioBackend,
        "github-copilot": GitHubCopilotBackend,
        "volcengine-ark": VolcengineArkBackend,
    }
    cls = backend_map.get(type)
    if cls is None:
        raise ValueError(f"Unknown backend type: {type}. Available: {sorted(backend_map.keys())}")
    return cls(**kwargs)
