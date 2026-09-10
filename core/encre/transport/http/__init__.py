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

"""Encre transport layer: HTTP stacks for the server's own endpoints.

    * :mod:`encre.transport.http.channel`    -- :class:`HTTPChannel`, the
      REST / NDJSON channel for headless clients.
    * :mod:`encre.transport.http.openai_api` -- the OpenAI-compatible API
      server platform adapter.  It self-registers into the gateway platform
      registry (platform name ``"api_server"``) when imported by
      :func:`encre.gateway.platforms.discover_platforms`; it is imported by
      module path and therefore deliberately NOT imported here, so pulling
      in :class:`HTTPChannel` does not require ``aiohttp``.
"""

from encre.transport.http.channel import HTTPChannel

__all__ = [
    "HTTPChannel",
]
