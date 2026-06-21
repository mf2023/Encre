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



"""Reusable subprocess window-suppression helpers.

Use :func:`hidden_subprocess_kwargs` to get the platform-specific kwargs
that guarantee no visible terminal window when spawning a child process.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return ``**kwargs`` that guarantee no visible terminal window.

    Windows:
      - ``creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS``
      - ``startupinfo`` with ``STARTF_USESHOWWINDOW | SW_HIDE``
        (OS-level "do not show", blocks the conhost flash on Win 11)

    Linux / macOS:
      - ``start_new_session = True`` (``setsid(2)``)
    """
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            "creationflags": 0x08000000,  # CREATE_NO_WINDOW only -- DETACHED_PROCESS blocks stdout
            "startupinfo": si,
        }
    return {
        "start_new_session": True,
    }
