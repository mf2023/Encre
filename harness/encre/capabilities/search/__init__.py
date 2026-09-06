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

"""Search capability seam.

Consolidates every code-intelligence power under one boundary:
- :mod:`encre.capabilities.search.codebase` 鈥?AST / embedding / document
  indexes over the workspace (Rust engine calls preserved).
- :mod:`encre.capabilities.search.lsp` 鈥?language-server client/manager.

Text grep stays exposed as the ``grep`` tool and calls the Rust
``native.grep`` directly; it is the single grep entrypoint.
"""
