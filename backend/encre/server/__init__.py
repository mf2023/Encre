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

"""Encre server package.

This package is the backend entry point for the Encre agent.  It exposes the
high-level :class:`EncreServer` class (defined in :mod:`encre.server.app`) and
the WebSocket protocol types (:mod:`encre.server.protocol`) used to exchange
messages between the desktop client and the agent runtime.

The package aggregates:
    * :mod:`encre.server.app`   -- the :class:`EncreServer` orchestrator.
    * :mod:`encre.server.ws`    -- the per-connection WebSocket message handler.
    * :mod:`encre.server.session_manager` -- in-memory + on-disk session store.
    * :mod:`encre.server.admin`  -- lightweight HTTP admin endpoints.
    * :mod:`encre.server.protocol` -- typed client/server message definitions.
    * :mod:`encre.server.service` -- background daemon wrapper.
"""


def __getattr__(name: str):
    if name == "EncreServer":
        from encre.server.app import EncreServer
        return EncreServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from encre.server.protocol import (
    ClientMessage,
    encode_server_message,
    parse_client_message,
)

__all__ = [
    "ClientMessage",
    "EncreServer",
    "encode_server_message",
    "parse_client_message",
]
