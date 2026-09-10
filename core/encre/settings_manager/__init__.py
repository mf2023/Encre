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

"""Flat runtime overlay for general (UI) settings.

This module used to own a second configuration file -- the top-level
``settings.json`` -- that duplicated ten keys already held by
:class:`~encre.config.EncreConfig` (and mirrored every ``adapter_*``
credential on top).  Both stores were written on every ``configure`` call,
with this one winning at runtime, so a value could silently disagree with
itself.

It is now a thin facade over :mod:`encre.config_store`, and the data lives
in ``<data_dir>/config/ui.json`` -- one home per key.  Callers and their
``dict`` contract are unchanged.
"""

import json
from typing import Any

from encre import config_store

#: Keys with overlay semantics: the settings panel can change them at
#: runtime and they take precedence over the value that was persisted in the
#: configuration files.  Sourced from the store so the two cannot drift.
_GENERAL_SETTINGS_KEYS = config_store.UI_SETTING_KEYS


def load_settings() -> dict[str, Any]:
    """Return the flat settings view.

    Same shape as the old top-level ``settings.json``: the overlay keys plus
    the adapter credentials and ``permission_settings`` that legacy callers
    (the gateway) expect.  Those last two are *borrowed* from their own
    group files -- see :func:`encre.config_store.overlay_view`.
    """
    return config_store.overlay_view()


def save_settings(settings: dict[str, Any]) -> None:
    """Persist the flat overlay, leaving borrowed keys to their owners."""
    config_store.save_overlay(settings)


def is_general_setting(key: str) -> bool:
    return key in _GENERAL_SETTINGS_KEYS


def load_custom_slash_commands() -> list[dict]:
    """Load custom slash commands from settings."""
    try:
        settings = load_settings()
        raw = settings.get("custom_slash_commands", "[]")
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def save_custom_slash_commands(commands: list[dict]) -> None:
    """Save custom slash commands into settings."""
    try:
        settings = load_settings()
        settings["custom_slash_commands"] = json.dumps(commands, ensure_ascii=False)
        save_settings(settings)
    except Exception:
        pass
