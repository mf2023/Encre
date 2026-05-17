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

def __getattr__(name: str):
    if name == "YmiServer":
        from yim.server.app import YmiServer as _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from yim.server.protocol import (
    ClientMessage,
    parse_client_message,
    encode_server_message,
)

__all__ = [
    "YmiServer",
    "ClientMessage",
    "parse_client_message",
    "encode_server_message",
]
