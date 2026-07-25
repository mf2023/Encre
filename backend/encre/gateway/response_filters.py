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

"""Response filters for the gateway delivery pipeline.

Detects intentional-silence responses, partial markers, and other patterns
that should suppress or modify delivery behavior.

Aligns with Hermes ``gateway/response_filters.py``.
"""

import re

# Matches strings that are *only* a "silence" narration with optional markdown.
_SILENCE_RE = re.compile(
    r"^[\s*_~`]*\(?\s*(silent|silence|no\s+response|no\s+reply)\s*\.?\)?[\s*_~`]*$"
    r"|^[\s*_~`]*[\U0001F507\.\u2026]+[\s*_~`]*$",
    re.IGNORECASE,
)

# Partial silence marker that may appear mid-stream (strip before delivery).
_PARTIAL_SILENCE_RE = re.compile(
    r"\(silent\)|\(silence\)|\(no response\)",
    re.IGNORECASE,
)


def is_intentional_silence_response(content: str | None) -> bool:
    """Return True when the response is *only* a silence narration token.

    The model sometimes responds with "(silent)" or similar to indicate it
    chose not to reply.  These should not be delivered to the user.
    """
    if not content:
        return False
    stripped = content.strip()
    if not stripped or len(stripped) > 64:
        return False
    return bool(_SILENCE_RE.match(stripped))


def is_partial_silence_marker(text: str) -> bool:
    """Return True if the text contains a partial silence marker."""
    return bool(_PARTIAL_SILENCE_RE.search(text))


def strip_silence_markers(text: str) -> str:
    """Remove partial silence markers from text."""
    return _PARTIAL_SILENCE_RE.sub("", text).strip()
