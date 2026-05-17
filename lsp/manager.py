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

import asyncio
import os
from typing import Any

from yim.lsp.protocol import Diagnostic, HoverResult, LSPState, Location, Position, Range
from yim.lsp.client import YmiLSPClient


class YmiLSPManager:
    LANGUAGE_SERVERS: dict[str, list[str]] = {
        "python": ["pyright-langserver", "--stdio"],
        "typescript": ["typescript-language-server", "--stdio"],
        "javascript": ["typescript-language-server", "--stdio"],
        "rust": ["rust-analyzer"],
        "go": ["gopls"],
    }

    EXTENSION_MAP: dict[str, str] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
    }

    def __init__(self) -> None:
        self._clients: dict[str, YmiLSPClient] = {}
        self._status = LSPState(status="not_started")
        self._workspace: str = ""
        self._open_documents: dict[str, int] = {}

    async def initialize_for_workspace(self, workspace: str) -> None:
        self._workspace = workspace
        self._status = LSPState(status="pending")

        languages = self._detect_languages(workspace)
        if not languages:
            self._status = LSPState(status="success")
            return

        for lang in languages:
            client = YmiLSPClient(lang)
            self._clients[lang] = client

        results = await asyncio.gather(
            *[self._start_language_server(lang, workspace) for lang in languages],
            return_exceptions=True,
        )

        for lang, result in zip(languages, results):
            if isinstance(result, Exception):
                self._status = LSPState(status="failed", error=str(result))
                return
            self._clients[lang] = result

        self._status = LSPState(status="success")

    async def _start_language_server(self, lang: str, workspace: str) -> YmiLSPClient:
        if lang not in self.LANGUAGE_SERVERS:
            raise RuntimeError(f"No language server defined for {lang}")

        server_config = self.LANGUAGE_SERVERS[lang]
        command = server_config[0]
        args = server_config[1:]

        client = YmiLSPClient(lang)
        await client.start(command, args, workspace)
        root_uri = self._path_to_uri(workspace)
        await client.initialize(root_uri)
        return client

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        lang = self._detect_language(file_path)
        if lang is None or lang not in self._clients:
            return []

        client = self._clients[lang]
        file_uri = self._path_to_uri(file_path)

        await self._ensure_document_opened(client, file_uri, file_path)

        try:
            diagnostics_raw = await client.send_request(
                "textDocument/diagnostic",
                {
                    "textDocument": {"uri": file_uri},
                },
            )
        except Exception:
            return []

        return self._parse_diagnostics(diagnostics_raw)

    async def go_to_definition(
        self, file_path: str, line: int, char: int
    ) -> list[Location]:
        lang = self._detect_language(file_path)
        if lang is None or lang not in self._clients:
            return []

        client = self._clients[lang]
        file_uri = self._path_to_uri(file_path)

        await self._ensure_document_opened(client, file_uri, file_path)

        try:
            result = await client.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": file_uri},
                    "position": {"line": line, "character": char},
                },
            )
        except Exception:
            return []

        return self._parse_locations(result)

    async def find_references(
        self, file_path: str, line: int, char: int
    ) -> list[Location]:
        lang = self._detect_language(file_path)
        if lang is None or lang not in self._clients:
            return []

        client = self._clients[lang]
        file_uri = self._path_to_uri(file_path)

        await self._ensure_document_opened(client, file_uri, file_path)

        try:
            result = await client.send_request(
                "textDocument/references",
                {
                    "textDocument": {"uri": file_uri},
                    "position": {"line": line, "character": char},
                    "context": {"includeDeclaration": True},
                },
            )
        except Exception:
            return []

        return self._parse_locations(result)

    async def hover(
        self, file_path: str, line: int, char: int
    ) -> HoverResult | None:
        lang = self._detect_language(file_path)
        if lang is None or lang not in self._clients:
            return None

        client = self._clients[lang]
        file_uri = self._path_to_uri(file_path)

        await self._ensure_document_opened(client, file_uri, file_path)

        try:
            result = await client.send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": file_uri},
                    "position": {"line": line, "character": char},
                },
            )
        except Exception:
            return None

        return self._parse_hover(result)

    async def document_symbols(self, file_path: str) -> list[dict[str, Any]]:
        lang = self._detect_language(file_path)
        if lang is None or lang not in self._clients:
            return []

        client = self._clients[lang]
        file_uri = self._path_to_uri(file_path)

        await self._ensure_document_opened(client, file_uri, file_path)

        try:
            result = await client.send_request(
                "textDocument/documentSymbol",
                {
                    "textDocument": {"uri": file_uri},
                },
            )
        except Exception:
            return []

        if isinstance(result, list):
            return result
        return []

    async def shutdown(self) -> None:
        """Shut down all LSP clients. Deprecated: use close() instead."""
        await self.close()

    async def close(self) -> None:
        """Terminate all LSP subprocesses, close pipes, and release resources."""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
        self._status = LSPState(status="not_started")

    def _detect_languages(self, workspace: str) -> list[str]:
        languages: set[str] = set()
        for root, _dirs, files in os.walk(workspace):
            if ".git" in root or "node_modules" in root or "__pycache__" in root:
                continue
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                lang = self.EXTENSION_MAP.get(ext)
                if lang:
                    languages.add(lang)
            if len(languages) >= len(self.LANGUAGE_SERVERS):
                break
        return sorted(languages)

    def _detect_language(self, file_path: str) -> str | None:
        ext = os.path.splitext(file_path)[1].lower()
        return self.EXTENSION_MAP.get(ext)

    async def _ensure_document_opened(
        self, client: YmiLSPClient, file_uri: str, file_path: str
    ) -> None:
        if file_uri in self._open_documents:
            self._open_documents[file_uri] += 1
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = ""

        await client.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_uri,
                    "languageId": self._detect_language(file_path) or "plaintext",
                    "version": 1,
                    "text": content,
                },
            },
        )
        self._open_documents[file_uri] = 1

    def _parse_diagnostics(self, raw: Any) -> list[Diagnostic]:
        result: list[Diagnostic] = []
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return result
        for item in items:
            if not isinstance(item, dict):
                continue
            rng_data = item.get("range", {})
            start = rng_data.get("start", {})
            end = rng_data.get("end", {})
            result.append(
                Diagnostic(
                    range=Range(
                        start=Position(
                            line=start.get("line", 0),
                            character=start.get("character", 0),
                        ),
                        end=Position(
                            line=end.get("line", 0),
                            character=end.get("character", 0),
                        ),
                    ),
                    severity=item.get("severity", 1),
                    message=item.get("message", ""),
                    source=item.get("source", ""),
                )
            )
        return result

    def _parse_locations(self, raw: Any) -> list[Location]:
        result: list[Location] = []
        locations = raw if isinstance(raw, list) else raw.get("result", []) if isinstance(raw, dict) else []
        if isinstance(locations, list):
            for loc in locations:
                if isinstance(loc, dict):
                    rng_data = loc.get("range", {})
                    start = rng_data.get("start", {})
                    end = rng_data.get("end", {})
                    result.append(
                        Location(
                            uri=loc.get("uri", ""),
                            range=Range(
                                start=Position(
                                    line=start.get("line", 0),
                                    character=start.get("character", 0),
                                ),
                                end=Position(
                                    line=end.get("line", 0),
                                    character=end.get("character", 0),
                                ),
                            ),
                        )
                    )
        return result

    def _parse_hover(self, raw: Any) -> HoverResult | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None

        contents = raw.get("contents", {})
        content_str = ""
        if isinstance(contents, str):
            content_str = contents
        elif isinstance(contents, dict):
            content_str = contents.get("value", "")
            kind = contents.get("kind", "")
            if kind == "markdown" and content_str:
                content_str = content_str
        elif isinstance(contents, list):
            parts: list[str] = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", ""))
            content_str = "\n".join(parts)

        if not content_str:
            return None

        hover_range = None
        range_data = raw.get("range")
        if range_data and isinstance(range_data, dict):
            start = range_data.get("start", {})
            end = range_data.get("end", {})
            hover_range = Range(
                start=Position(
                    line=start.get("line", 0),
                    character=start.get("character", 0),
                ),
                end=Position(
                    line=end.get("line", 0),
                    character=end.get("character", 0),
                ),
            )

        return HoverResult(contents=content_str, range=hover_range)

    @staticmethod
    def _path_to_uri(file_path: str) -> str:
        absolute = os.path.abspath(file_path)
        if os.name == "nt":
            encoded = absolute.replace("\\", "/")
            return "file:///" + encoded.replace(":", "%3A")
        return "file://" + absolute
