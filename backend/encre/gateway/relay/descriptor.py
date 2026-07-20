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

"""Relay capability descriptor (handshake payload).

Aligns with Hermes' ``gateway/relay/descriptor.py``.  The descriptor is the
immutable capability profile the connector returns at handshake: it tells the
gateway how to render/stream/truncate for the fronted platform without the
gateway knowing which concrete platform it is.  A single ``RelayAdapter``
instance can therefore front Discord, Telegram, Matrix, ... driven only by
the descriptor.

The descriptor is frozen so it cannot mutate after handshake -- the adapter
advertises a fixed capability profile for the life of the connection.
``contract_version`` (currently :data:`CONTRACT_VERSION`) is carried in the
descriptor; the gateway ignores unknown fields (forward-compat) and fills
missing optional fields from defaults.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any

# Relay connector contract version.  Experimental -- additive-only within a
# version; a breaking change requires a coordinated update of both repos and
# a version bump.  Mirrors Hermes CONTRACT_VERSION.
CONTRACT_VERSION = 1

# When max_message_length is 0 / absent, treat it as this default (mirrors
# Hermes' from_platform_entry behaviour and the connector's own default).
DEFAULT_MAX_MESSAGE_LENGTH = 4096


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Immutable capability profile negotiated at relay handshake.

    All required fields are populated by the connector; the gateway configures
    its adapter (char limit, length unit, draft/edit/thread/markdown
    capabilities) from this descriptor.  Optional fields default sensibly.
    """

    contract_version: int
    platform: str
    label: str
    max_message_length: int
    supports_draft_streaming: bool
    supports_edit: bool
    supports_threads: bool
    markdown_dialect: str  # "plain" | "markdown_v2" | "discord" | ...
    len_unit: str  # "chars" | "utf16"
    emoji: str = "\U0001f50c"  # 🔌 default (matches PlatformEntry default)
    platform_hint: str = ""
    pii_safe: bool = False

    def to_json(self) -> str:
        """Serialize to a compact, stable JSON string for the handshake frame.

        Keys are sorted for a stable wire representation (mirrors Hermes
        ``to_json``: ``json.dumps(asdict(self), sort_keys=True, ...)``).
        """
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict (for embedding in a larger frame)."""
        return asdict(self)

    @classmethod
    def from_json(cls, raw: str) -> "CapabilityDescriptor":
        """Reconstruct from a JSON string; unknown keys ignored (forward-compat)."""
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapabilityDescriptor":
        """Reconstruct from a dict; unknown keys ignored, missing optionals defaulted.

        Mirrors Hermes ``from_json``: forward-compatible -- a connector that
        adds a new optional field does not break an older gateway.  Required
        fields that are absent raise ``TypeError`` (deliberate: a handshake
        missing a required field is a contract violation, not a graceful-degrade
        case).
        """
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        # max_message_length == 0 -> default (mirrors from_platform_entry).
        if filtered.get("max_message_length") == 0:
            filtered["max_message_length"] = DEFAULT_MAX_MESSAGE_LENGTH
        return cls(**filtered)
