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

"""
Inspired by the Hermes Agent project (https://github.com/NousResearch/hermes-agent.git).
Thanks to Hermes Agent for the inspiration on this module.

QQBot shared utilities — User-Agent builder, HTTP helpers, config coercion.

This module provides three categories of helpers:

1. :func:`build_user_agent` — constructs a descriptive User-Agent string
   for QQ Bot API requests. Format: ``QQBotAdapter/<ver> (Python/<ver>; <os>; Encre/<ver>)``
2. :func:`get_api_headers` — returns standard HTTP headers dict including
   Content-Type, Accept, and dynamic User-Agent.
3. :func:`coerce_list` — normalizes config values into trimmed string lists.
   Accepts comma-separated strings, lists, tuples, sets, or single values.

Dependencies:
    - :const:`QQBOT_VERSION` from ``constants`` — adapter version string.
    - Standard library: ``platform``, ``sys``, ``importlib.metadata``.
"""

import platform
import sys
from typing import Any, Dict, List

from .constants import QQBOT_VERSION


# ---------------------------------------------------------------------------
# User-Agent
# ---------------------------------------------------------------------------

def _get_encre_version() -> str:
    """Return the encre package version, or 'dev' if unavailable.

    Uses ``importlib.metadata.version()`` which reads from the installed
    package's METADATA file. Falls back to 'dev' if the package is not
    installed or metadata is unreadable.

    Returns:
        Version string like "0.9.0" or "dev".
    """
    try:
        from importlib.metadata import version
        return version("encre")
    except Exception:
        return "dev"


def build_user_agent() -> str:
    """Build a descriptive User-Agent string.

    The User-Agent includes the QQBot adapter version, Python version,
    operating system, and Encre version. This helps the QQ Bot API
    identify and debug requests from our client.

    Format::

        QQBotAdapter/<qqbot_version> (Python/<py_version>; <os>; Encre/<encre_version>)

    Example::

        QQBotAdapter/1.1.0 (Python/3.11.15; darwin; Encre/0.9.0)

    Returns:
        Formatted User-Agent string.
    """
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = platform.system().lower()
    encre_version = _get_encre_version()
    return f"QQBotAdapter/{QQBOT_VERSION} (Python/{py_version}; {os_name}; Encre/{encre_version})"


def get_api_headers() -> Dict[str, str]:
    """Return standard HTTP headers for QQBot API requests.

    Includes Content-Type, Accept, and a dynamic User-Agent.
    The ``Accept: application/json`` header is required by q.qq.com —
    without it, the server returns a JavaScript anti-bot challenge page
    instead of the expected JSON response.

    Returns:
        Dict with keys "Content-Type", "Accept", and "User-Agent".
    """
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": build_user_agent(),
    }


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def coerce_list(value: Any) -> List[str]:
    """Coerce config values into a trimmed string list.

    Handles multiple input formats commonly found in YAML config files:

    Formats supported:
        - None → empty list []
        - Comma-separated string "a, b, c" → ["a", "b", "c"]
        - List ["a", "b"] → ["a", "b"]
        - Tuple ("a", "b") → ["a", "b"]
        - Set {"a"} → ["a"]
        - Single value 42 → ["42"]

    Trimming: all items are stripped of whitespace and empty strings
    are filtered out.

    Args:
        value: Raw config value of any type.

    Returns:
        Trimmed list of non-empty strings.

    Example::

        >>> coerce_list("a, b, c")
        ['a', 'b', 'c']
        >>> coerce_list(["a", "  ", "b"])
        ['a', 'b']
        >>> coerce_list(None)
        []
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []
