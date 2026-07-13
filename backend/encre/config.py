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

import contextlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from encre.crypto import decrypt, encrypt
from encre.utils.types import PermissionMode, ThinkingConfig


@dataclass
class AgentConfig:
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    model_index: int = 0
    permission_mode: PermissionMode = "bypass"
    max_turns: int = 0
    enabled_skills: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "model_index": self.model_index,
            "permission_mode": self.permission_mode,
            "max_turns": self.max_turns,
            "enabled_skills": list(self.enabled_skills),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentConfig":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            system_prompt=d.get("system_prompt", ""),
            model_index=d.get("model_index", 0),
            permission_mode=d.get("permission_mode", "bypass"),
            max_turns=d.get("max_turns", 0),
            enabled_skills=d.get("enabled_skills", []),
            enabled=d.get("enabled", True),
        )


@dataclass
class ModelConfig:
    """Configuration for a single AI model provider.

    Each entry represents one model endpoint that the user can select from
    the frontend dropdown or API.
    """
    name: str = ""
    model_id: str = ""
    backend_type: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    context_window: int = 0  # 0 = auto-detect from model/backend, >0 = explicit override
    enabled: bool = True

    def to_dict(self, encrypt_api_keys: bool = True) -> dict[str, Any]:
        encrypted_key = ""
        if self.api_key and encrypt_api_keys:
            try:
                encrypted_key = encrypt(self.api_key)
            except Exception:
                encrypted_key = self.api_key
        else:
            encrypted_key = self.api_key
        return {
            "name": self.name,
            "model_id": self.model_id,
            "backend_type": self.backend_type,
            "api_key": encrypted_key,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "context_window": self.context_window,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelConfig":
        raw_key = str(d.get("api_key", ""))
        decrypted_key = raw_key
        if raw_key and raw_key != "":
            try:
                decrypted_key = decrypt(raw_key)
            except Exception:
                decrypted_key = raw_key
        return cls(
            name=str(d.get("name", "")),
            model_id=str(d.get("model_id", "")),
            backend_type=str(d.get("backend_type", "")),
            api_key=decrypted_key,
            base_url=str(d.get("base_url", "")),
            max_tokens=int(d.get("max_tokens", 4096)),
            context_window=int(d.get("context_window", 0)),
            enabled=bool(d.get("enabled", True)),
        )

# Data directory -- all Encre data lives under this single tree.
_DATA_DIR = Path("~/.dunimd/encre").expanduser()
_DATA_DIR_ENV_VAR = "ENCRE_DATA_DIR"


def get_data_dir() -> Path:
    """Return the Encre data directory (``~/.dunimd/encre`` by default).

    Set the ``ENCRE_DATA_DIR`` environment variable to override.
    The directory is created if it does not exist.
    """
    env = os.environ.get(_DATA_DIR_ENV_VAR)
    p = Path(env).expanduser() if env else _DATA_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# Single canonical config path -- all model/provider config lives here.
def _get_config_path() -> Path:
    p = get_data_dir() / "model" / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _find_config_file(explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        return p if p.exists() else None
    p = _get_config_path()
    if p.exists():
        return p
    return None


def _load_yaml(path: str) -> dict[str, Any]:
    content: dict[str, Any] = {}
    try:
        import yaml  # type: ignore[import-untyped]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            content = data
    except ImportError:
        raise ImportError("PyYAML is required for YAML config files: pip install pyyaml") from None
    return content


def _load_toml(path: str) -> dict[str, Any]:
    content: dict[str, Any] = {}
    suffix = Path(path).suffix.lower()
    if suffix in (".toml",):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        if isinstance(data, dict):
            content = _flatten_toml(data)
    return content


def _flatten_toml(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and not any(k in full_key for k in ("backend_kwargs",)):
            result.update(_flatten_toml(value, full_key))
        else:
            result[full_key] = value
    return result




@dataclass
class SubAgentConfig:
    """Configuration for a named sub-agent that can be invoked by the main agent."""
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    hidden: bool = False
    # ``tool_policy`` constrains the tools a sub-agent may invoke.
    # ``"readonly"`` (Explore-style): read-only tools only.
    # ``"no_writes"`` (Plan-style): no write-class tools, but can
    #    ask questions / run analysis.
    # ``"all"`` (General-purpose): default, full tool access.
    tool_policy: str = "all"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "hidden": self.hidden,
            "tool_policy": self.tool_policy,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SubAgentConfig":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            system_prompt=d.get("system_prompt", ""),
            hidden=d.get("hidden", False),
            tool_policy=d.get("tool_policy", "all"),
        )


@dataclass
class EncreConfig:
    model: str = ""
    host: str = "localhost"
    port: int = 8000
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    max_turns: int = 0
    tool_result_max_chars: int = 80000
    permission_mode: PermissionMode = "bypass"
    slash_command_mode: str = ""
    sandbox_enabled: bool = True
    workspace: str = ""
    session_max_age_hours: float = 24.0
    thinking_config: ThinkingConfig | None = None
    backend_type: str = ""
    backend_kwargs: dict[str, Any] = field(default_factory=dict)
    enable_prompt_caching: bool = True
    enable_streaming_tool_execution: bool = True
    enable_multi_stage_compact: bool = False
    enable_unified_recovery: bool = False
    enable_context_collapse: bool = False
    enable_project_rules: bool = True
    enable_file_watcher: bool = False
    # Fallback model: auto-switched when the primary model fails (rate limit,
    # overload, etc.).  Empty string = no fallback.  Mirrors Claude Code's
    # fallbackModel in query.ts.
    fallback_model: str = ""
    fallback_base_url: str = ""
    fallback_api_key: str = ""
    fallback_backend_type: str = ""
    # Slot reservation: initial output token budget for the first API call
    # each turn.  Escalates to max_tokens when the model hits this limit
    # (finish_reason = "max_tokens" or "length").  0 = disabled (use max_tokens
    # directly).  Mirrors Claude Code's slot reservation in query.ts.
    default_slot_tokens: int = 0
    # Thinking prefill: inject a thinking hint to guide the model's
    # reasoning process.  Mirrors Hermes agent's thinking prefill.
    thinking_prefill_enabled: bool = False
    # Token budget: total output token budget across all turns (0 = unlimited).
    # When exhausted, the model gets one grace call to wrap up.
    # Mirrors Claude Code's token budget (+500k style).
    token_budget: int = 0
    enable_global_rules: bool = True
    checkpoint_max_count: int = 10
    telemetry_enabled: bool = True
    log_level: str = "INFO"
    models: list[ModelConfig] = field(default_factory=list)
    active_model_index: int = 0
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    enabled_skills: list[str] = field(default_factory=list)
    system_prompt: str = ""
    default_specialty: str = "general"
    language: str = "zh"
    language_preference: str = "auto"
    default_link_behavior: str = "ask"
    auto_expand: bool = True
    sub_agent_auto_open_view: bool = True
    automation_auto_open_view: bool = False
    shortcut_send_mode: str = "enter"
    startup_session_mode: str = "normal"
    startup_session_behavior: str = "new"
    agents: list[AgentConfig] = field(default_factory=list)
    active_agent_index: int = -1
    sub_agents: list[SubAgentConfig] = field(default_factory=list)
    # The tool policy currently active for *this* loop.  Set to the
    # role-template's policy (``"readonly"``, ``"no_writes"``, or
    # ``"all"``) when the loop is spawned as a sub-agent.  The
    # ``_enforce_tool_policy`` hook reads this to decide whether a
    # tool call should be blocked.  Defaults to ``"all"`` for the
    # main agent and for sub-agents that are not policy-restricted.
    current_tool_policy: str = "all"
    dangerous_command_patterns: list[str] = field(default_factory=list)
    adapter_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # OpenTelemetry / OpenInference tracing
    tracing_enabled: bool = False
    tracing_endpoint: str = ""
    tracing_service_name: str = "encre"

    # Permission override settings (like OS permissions)
    # Maps: tool_or_feature_name → "allow" | "deny" | "ask"
    # Examples:
    #   "bash" → "ask"       — ask every time bash runs
    #   "file_write" → "allow"  — always allow file writes
    #   "network" → "deny"      — block all network access
    #   "sandbox" → "allow"     — allow sandbox isolation
    # Empty = use mode-based default for that tool.
    permission_settings: dict[str, str] = field(default_factory=dict)

    def get_active_model(self) -> ModelConfig:
        if self.models and 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return ModelConfig(
            name=self.model,
            model_id=self.model,
            backend_type=self.backend_type,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
        )

    def apply_active_model(self) -> None:
        active = self.get_active_model()
        if active.name:
            self.model = active.model_id
            self.backend_type = active.backend_type
            self.api_key = active.api_key
            self.base_url = active.base_url
            self.max_tokens = active.max_tokens
            # Pass context_window through backend_kwargs so the backend
            # can honour it when computing context_window_size().
            if active.context_window > 0:
                self.backend_kwargs["context_window"] = active.context_window
            else:
                self.backend_kwargs.pop("context_window", None)

    def get_active_agent(self) -> AgentConfig | None:
        if self.agents and 0 <= self.active_agent_index < len(self.agents):
            return self.agents[self.active_agent_index]
        return None

    @classmethod
    def from_file(cls, path: str | None = None) -> "EncreConfig":
        config_dict: dict[str, Any] = {}

        found = _find_config_file(path)
        if found is None:
            found = _get_config_path()
        if found.exists():
            raw_text = found.read_text(encoding="utf-8").strip()
            if raw_text:
                decrypted = decrypt(raw_text)
                import json as _json
                config_dict = _json.loads(decrypted)

        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs: dict[str, Any] = {}
        adapter_cfgs: dict[str, dict[str, Any]] = {}
        for key, value in config_dict.items():
            if key in valid_keys:
                kwargs[key] = value
            elif key.startswith("adapter_"):
                parts = key.split("_", 2)
                if len(parts) >= 3:
                    adapter_id = parts[1]
                    field_key = parts[2]
                    adapter_cfgs.setdefault(adapter_id, {})[field_key] = value
            elif key.startswith("backend_kwargs."):
                bk_key = key.split(".", 1)[1]
                kwargs.setdefault("backend_kwargs", {})[bk_key] = value
        if adapter_cfgs:
            kwargs["adapter_configs"] = adapter_cfgs

        if kwargs.get("api_key"):
            with contextlib.suppress(Exception):
                kwargs["api_key"] = decrypt(str(kwargs["api_key"]))
            # keep as-is if decryption fails (legacy plaintext)

        if "models" in kwargs and isinstance(kwargs["models"], list):
            kwargs["models"] = [
                ModelConfig.from_dict(m) if isinstance(m, dict) else m
                for m in kwargs["models"]
            ]

        if "agents" in kwargs and isinstance(kwargs["agents"], list):
            kwargs["agents"] = [
                AgentConfig.from_dict(a) if isinstance(a, dict) else a
                for a in kwargs["agents"]
            ]

        if "sub_agents" in kwargs and isinstance(kwargs["sub_agents"], list):
            kwargs["sub_agents"] = [
                SubAgentConfig.from_dict(s) if isinstance(s, dict) else s
                for s in kwargs["sub_agents"]
            ]

        cfg = cls(**kwargs)
        if cfg.models:
            cfg.apply_active_model()
        return cfg

    @classmethod
    def from_env(cls) -> "EncreConfig":
        return cls.from_file(path=None)

    _MODEL_FLAT_FIELDS = frozenset({"model", "api_key", "base_url", "max_tokens", "backend_type"})
    _SKIP_TO_DICT = frozenset({"adapter_configs", "models", "agents", "sub_agents"})

    def to_dict(self, encrypt_api_keys: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {}
        has_models = bool(self.models)
        for field_info in self.__dataclass_fields__.values():
            if field_info.name in self._SKIP_TO_DICT or (has_models and field_info.name in self._MODEL_FLAT_FIELDS):
                continue
            elif field_info.name == "api_key":
                raw = self.api_key
                if raw and encrypt_api_keys:
                    try:
                        result["api_key"] = encrypt(raw)
                    except Exception:
                        result["api_key"] = raw
                else:
                    result["api_key"] = raw or ""
            else:
                result[field_info.name] = getattr(self, field_info.name)

        # Models, agents, sub_agents
        if self.models:
            result["models"] = [m.to_dict(encrypt_api_keys=encrypt_api_keys) if isinstance(m, ModelConfig) else m for m in self.models]
        if self.agents:
            result["agents"] = [a.to_dict() if isinstance(a, AgentConfig) else a for a in self.agents]
        if self.sub_agents:
            result["sub_agents"] = [s.to_dict() if isinstance(s, SubAgentConfig) else s for s in self.sub_agents]

        # Flatten adapter_configs -> flat adapter_* keys for frontend compatibility
        for adapter_id, fields in self.adapter_configs.items():
            for field_key, field_value in fields.items():
                result[f"adapter_{adapter_id}_{field_key}"] = field_value

        return result

    def save(self, path: str) -> None:
        data = {k: v for k, v in self.to_dict().items() if v is not None}
        import json
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        encrypted = encrypt(raw)
        p.write_text(encrypted, encoding="utf-8")
