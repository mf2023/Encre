#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Gateway configuration management.

Defines the platform enumeration, per-platform configuration dataclass, and
the top-level gateway configuration container.  Supports loading from the
encrypted settings store and environment variable overrides.

Aligns with Hermes ``gateway/config.py``.
"""

import enum
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("encre.gateway.config")


# ── Platform enumeration ──────────────────────────────────────────────────────


class Platform(enum.Enum):
    """All supported messaging platforms."""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    QQ = "qqbot"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WEIXIN = "weixin"
    WECOM = "wecom"
    SLACK = "slack"
    SIGNAL = "signal"
    MATRIX = "matrix"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    HOMEASSISTANT = "homeassistant"
    MSGRAPH = "msgraph"
    SMS = "sms"
    WEBHOOK = "webhook"
    BLUEBUBBLES = "bluebubbles"
    YUANBAO = "yuanbao"
    RELAY = "relay"


# ── Per-platform configuration ────────────────────────────────────────────────


@dataclass
class PlatformConfig:
    """Configuration for a single platform adapter.

    Attributes:
        enabled: Whether this platform is active.
        token: Primary auth token (bot token, API key, etc.).
        extra: Platform-specific additional configuration (app_id, webhook_url,
            allowed_users, etc.).  Adapters read their specific fields from here.
    """

    enabled: bool = False
    token: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HomeChannel:
    """A platform's default delivery channel for cron/notification output.

    Attributes:
        chat_id: The target chat/channel/group id.
        name: Human-friendly display name (optional).
        thread_id: Thread/topic id within the chat (optional).
    """

    chat_id: str = ""
    name: str = ""
    thread_id: str | None = None


# ── Top-level gateway configuration ──────────────────────────────────────────


@dataclass
class GatewayConfig:
    """Top-level gateway configuration container.

    Holds per-platform configs and global gateway settings.
    """

    platforms: dict[Platform, PlatformConfig] = field(default_factory=dict)
    home_channels: dict[Platform, HomeChannel] = field(default_factory=dict)

    # Global gateway flags
    allow_all_users: bool = False
    require_mention: bool = False
    multiplex_profiles: bool = False

    # Streaming defaults
    streaming_edit_interval: float = 1.0
    streaming_buffer_threshold: int = 50
    streaming_cursor: str = " ..."


# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_STREAMING_EDIT_INTERVAL = 1.0
DEFAULT_STREAMING_BUFFER_THRESHOLD = 50
DEFAULT_STREAMING_CURSOR = " ..."


# ── Config loading ────────────────────────────────────────────────────────────


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce a config value to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def load_gateway_config() -> GatewayConfig:
    """Load gateway configuration from settings + environment overrides.

    Reads the encrypted settings store (via settings_manager) and overlays
    environment variables.  Environment always takes precedence.

    Returns:
        A fully resolved GatewayConfig instance.
    """
    config = GatewayConfig()

    # Load from settings store
    try:
        from encre.settings_manager import load_settings
        settings = load_settings() or {}
    except Exception:
        settings = {}

    # Global flags
    config.allow_all_users = _coerce_bool(
        os.getenv("GATEWAY_ALLOW_ALL_USERS") or settings.get("gateway_allow_all_users")
    )
    config.require_mention = _coerce_bool(
        os.getenv("GATEWAY_REQUIRE_MENTION") or settings.get("gateway_require_mention")
    )

    # Per-platform: extract from settings (adapter_<name>_* keys)
    for plat in Platform:
        name = plat.value
        prefix = f"adapter_{name}_"
        plat_settings = {
            k[len(prefix):]: v
            for k, v in settings.items()
            if k.startswith(prefix)
        }
        if not plat_settings:
            continue

        pc = PlatformConfig(
            enabled=_coerce_bool(plat_settings.pop("enabled", None)),
            token=str(plat_settings.pop("token", "") or ""),
            extra=plat_settings,
        )
        config.platforms[plat] = pc

    # Environment variable overrides for common platforms
    _apply_env_overrides(config)

    return config


def _apply_env_overrides(config: GatewayConfig) -> None:
    """Apply environment variable overrides for platform tokens.

    Mirrors Hermes' _apply_env_overrides pattern: if a platform's token env var
    is set, auto-enable and configure that platform.
    """
    _ENV_TOKEN_MAP: dict[Platform, str] = {
        Platform.TELEGRAM: "TELEGRAM_BOT_TOKEN",
        Platform.DISCORD: "DISCORD_BOT_TOKEN",
        Platform.SLACK: "SLACK_BOT_TOKEN",
        Platform.SIGNAL: "SIGNAL_CLI_PATH",
        Platform.WHATSAPP: "WHATSAPP_PHONE_NUMBER",
        Platform.MATRIX: "MATRIX_ACCESS_TOKEN",
    }

    for plat, env_var in _ENV_TOKEN_MAP.items():
        token = os.getenv(env_var, "").strip()
        if token:
            if plat not in config.platforms:
                config.platforms[plat] = PlatformConfig()
            config.platforms[plat].enabled = True
            config.platforms[plat].token = token
