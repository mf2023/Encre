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
GitHub Copilot backend -- uses GitHub Copilot subscription via OpenAI-compatible API.

GitHub Copilot provides an OpenAI-compatible chat completion API for
subscribers.  Authentication is handled via a GitHub token (OAuth device
code flow) or a COPILOT_GITHUB_TOKEN environment variable.

Note: This backend expects a valid GitHub token.  The OAuth device code
flow must be completed externally before using this backend.

Authentication (priority order):
1. Explicit ``api_key`` parameter
2. ``COPILOT_GITHUB_TOKEN`` environment variable
3. ``GH_TOKEN`` environment variable
4. Output of ``gh auth token`` (CLI)

Base URL: https://api.githubcopilot.com (determined dynamically)
"""

import os
import subprocess
from typing import Any

from encre.backends.openai_sse import OpenAISSEBackend


class GitHubCopilotBackend(OpenAISSEBackend):
    """GitHub Copilot backend for Copilot subscribers.

    Uses GitHub Copilot's OpenAI-compatible chat API.  Authentication
    requires a GitHub token with Copilot access.
    """

    DEFAULT_BASE_URL = "https://api.githubcopilot.com"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "gpt-4o-copilot",
        **kwargs: Any,
    ) -> None:
        """Initialize the GitHub Copilot backend.

        Args:
            api_key: Explicit GitHub token. When empty, a token is resolved
                from environment variables or the ``gh`` CLI.
            base_url: API endpoint; defaults to the Copilot API URL.
            model: Default Copilot model identifier.
            **kwargs: Additional options forwarded to the parent backend.
        """
        if not base_url:
            # No explicit endpoint given: use the Copilot API URL.
            base_url = self.DEFAULT_BASE_URL
        # Resolve the GitHub token from env / CLI when not passed explicitly.
        resolved_key = api_key or self._resolve_github_token()
        super().__init__(api_key=resolved_key, base_url=base_url, model=model, **kwargs)

    @staticmethod
    def _resolve_github_token() -> str:
        """Resolve a GitHub token for Copilot authentication.

        Resolution order:
            1. ``COPILOT_GITHUB_TOKEN`` environment variable.
            2. ``GH_TOKEN`` environment variable.
            3. The output of ``gh auth token`` (GitHub CLI).

        Returns:
            The resolved token string, or an empty string if none found.
        """
        # Prefer explicit environment variables for the token.
        token = os.environ.get("COPILOT_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        # Fall back to the GitHub CLI if no env token is set.
        if not token:
            try:
                # Ask the gh CLI for the currently authenticated token.
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Strip trailing newline from the CLI output.
                    token = result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                # gh not installed / timed out / other OS error: no token.
                pass
        return token

    def context_window_size(self) -> int:
        """Return the context window size (in tokens) for Copilot models."""
        return 128000
