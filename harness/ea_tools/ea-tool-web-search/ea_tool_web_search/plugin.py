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

from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_web_search.tool import web_search_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _WebsearchPlugin()


class _WebsearchPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-web-search",
        version="0.4.3",
        description="EA (Encre Agent) mandatory web-search tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.MANDATORY,
        tier="mandatory",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["mandatory"],
        provides_tools=["web_search"],
        activation_events=[],
        permissions=['network'],
    )

    def get_tools(self) -> list:
        return [web_search_tool]
