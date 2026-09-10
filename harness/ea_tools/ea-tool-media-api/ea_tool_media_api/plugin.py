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

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_media_api.tool import create_embeddings_tool, create_moderation_tool, transcribe_audio_tool, translate_audio_tool


def create_plugin() -> EncrePlugin:
    return _MediaApiPlugin()


class _MediaApiPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-media-api",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: create_embeddings, create_moderation, transcribe_audio, translate_audio.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['create_embeddings', 'create_moderation', 'transcribe_audio', 'translate_audio'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [create_embeddings_tool, create_moderation_tool, transcribe_audio_tool, translate_audio_tool]
