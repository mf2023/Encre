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

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yim.utils.types import PermissionMode, ThinkingConfig


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
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "backend_type": self.backend_type,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelConfig":
        return cls(
            name=str(d.get("name", "")),
            model_id=str(d.get("model_id", "")),
            backend_type=str(d.get("backend_type", "")),
            api_key=str(d.get("api_key", "")),
            base_url=str(d.get("base_url", "")),
            max_tokens=int(d.get("max_tokens", 4096)),
            enabled=bool(d.get("enabled", True)),
        )

# Data directory — all Yim data lives under this single tree.
_DATA_DIR = Path("~/.dunimd/yim").expanduser()
_DATA_DIR_ENV_VAR = "YIM_DATA_DIR"


def get_data_dir() -> Path:
    """Return the Yim data directory (``~/.dunimd/yim`` by default).

    Set the ``YIM_DATA_DIR`` environment variable to override.
    The directory is created if it does not exist.
    """
    env = os.environ.get(_DATA_DIR_ENV_VAR)
    p = Path(env).expanduser() if env else _DATA_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# Single canonical config path — all model/provider config lives here.
_CONFIG_PATH = Path("~/.dunimd/yim/model/config.toml")


def _get_config_path() -> Path:
    p = _CONFIG_PATH.expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _find_config_file(explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        return p if p.exists() else None
    p = _get_config_path()
    return p if p.exists() else None


def _load_yaml(path: str) -> dict[str, Any]:
    content: dict[str, Any] = {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            content = data
    except ImportError:
        raise ImportError("PyYAML is required for YAML config files: pip install pyyaml")
    return content


def _load_toml(path: str) -> dict[str, Any]:
    content: dict[str, Any] = {}
    suffix = Path(path).suffix.lower()
    if suffix in (".toml",):
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                raise ImportError("tomli/tomllib required for TOML config: pip install tomli") from None
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
class YmiConfig:
    model: str = ""
    host: str = "localhost"
    port: int = 8000
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    max_turns: int = 25
    tool_result_max_chars: int = 80000
    permission_mode: PermissionMode = "default"
    sandbox_enabled: bool = True
    workspace: str = ""
    session_max_age_hours: float = 24.0
    thinking_config: ThinkingConfig | None = None
    backend_type: str = ""
    backend_kwargs: dict[str, Any] = field(default_factory=dict)
    enable_prompt_caching: bool = True
    checkpoint_max_count: int = 10
    telemetry_enabled: bool = True
    log_level: str = "INFO"
    models: list[ModelConfig] = field(default_factory=list)
    active_model_index: int = 0
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    enabled_skills: list[str] = field(default_factory=list)
    system_prompt: str = ""
    default_specialty: str = "general"

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

    @classmethod
    def from_file(cls, path: str | None = None) -> "YmiConfig":
        config_dict: dict[str, Any] = {}

        found = _find_config_file(path)
        if found is None:
            found = _get_config_path()
        suffix = found.suffix.lower()
        if found.exists():
            if suffix in (".yaml", ".yml"):
                config_dict = _load_yaml(str(found))
            elif suffix == ".toml":
                config_dict = _load_toml(str(found))

        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs: dict[str, Any] = {}
        for key, value in config_dict.items():
            if key in valid_keys:
                kwargs[key] = value
            elif key.startswith("backend_kwargs."):
                bk_key = key.split(".", 1)[1]
                kwargs.setdefault("backend_kwargs", {})[bk_key] = value

        if "models" in kwargs and isinstance(kwargs["models"], list):
            kwargs["models"] = [
                ModelConfig.from_dict(m) if isinstance(m, dict) else m
                for m in kwargs["models"]
            ]

        cfg = cls(**kwargs)
        if cfg.models:
            cfg.apply_active_model()
        return cfg

    @classmethod
    def from_env(cls) -> YmiConfig:
        return cls.from_file(path=None)

    _MODEL_FLAT_FIELDS = frozenset({"model", "api_key", "base_url", "max_tokens", "backend_type"})

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        has_models = bool(self.models)
        for field_info in self.__dataclass_fields__.values():  # type: ignore[attr-defined]
            if field_info.name == "models":
                result[field_info.name] = [
                    m.to_dict() if isinstance(m, ModelConfig) else m
                    for m in (self.models or [])
                ]
            elif has_models and field_info.name in self._MODEL_FLAT_FIELDS:
                continue
            else:
                result[field_info.name] = getattr(self, field_info.name)
        return result

    def save(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        data = {k: v for k, v in self.to_dict().items() if v is not None}
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
                with open(path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
            except ImportError:
                raise ImportError("PyYAML is required: pip install pyyaml")
        elif suffix in (".json",):
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif suffix == ".toml":
            try:
                import tomli_w
                with open(path, "wb") as f:
                    tomli_w.dump(data, f)
            except ImportError:
                raise ImportError("tomli-w is required: pip install tomli-w")
        else:
            raise ValueError(f"Unsupported config format: {suffix}. Use .yaml, .json, or .toml")
