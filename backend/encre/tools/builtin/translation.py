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

"""Translation tool.

Translates text between languages (with optional language detection) via a
configured translation provider.
"""


import asyncio
import json
import os
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _translation_execute(**kwargs: Any) -> str:
    """Translation execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    text = kwargs.get("text", "")
    source_lang = kwargs.get("source_lang", "auto")
    target_lang = kwargs.get("target_lang", "en")
    file_path = kwargs.get("file_path", "")
    service = kwargs.get("service", "libre")
    engine_url = kwargs.get("engine_url", "")
    preserve_format = kwargs.get("preserve_format", False)

    loop = asyncio.get_event_loop()

    if action in ("translate", "detect"):
        if not text and not file_path:
            return "Missing required field: text or file_path"
        if file_path:
            if not os.path.exists(file_path):
                return f"File not found: {file_path}"
            text = Path(file_path).read_text(encoding="utf-8")

        def _translate() -> str:
            """Translate."""
            try:
                if service == "libre":
                    import urllib.parse
                    import urllib.request

                    api_url = (engine_url or "http://localhost:5000").rstrip("/")

                    if action == "detect":
                        payload = json.dumps({"q": text}).encode("utf-8")
                        req = urllib.request.Request(
                            f"{api_url}/detect",
                            data=payload,
                            headers={"Content-Type": "application/json"},
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            result = json.loads(resp.read().decode("utf-8"))
                        return json.dumps(result if isinstance(result, list) else [result], ensure_ascii=False, indent=2)

                    payload = json.dumps({
                        "q": text,
                        "source": source_lang,
                        "target": target_lang,
                        "format": "text" if not preserve_format else "html",
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"{api_url}/translate",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = json.loads(resp.read().decode("utf-8"))

                    output = {
                        "source_lang": result.get("detectedLanguage", {}).get("language", source_lang),
                        "target_lang": target_lang,
                        "input_text": text[:500] + ("..." if len(text) > 500 else ""),
                        "translated_text": result.get("translatedText", ""),
                    }
                    return json.dumps(output, ensure_ascii=False, indent=2)

                elif service == "google":
                    try:
                        from deep_translator import GoogleTranslator
                    except ImportError:
                        return "deep_translator library required. Install: pip install deep-translator"

                    src = source_lang if source_lang != "auto" else "auto"
                    translator = GoogleTranslator(source=src, target=target_lang)
                    if action == "detect":
                        detected = translator.detect(text)
                        return json.dumps({"language": detected}, ensure_ascii=False, indent=2)
                    translated = translator.translate(text)
                    output = {
                        "source_lang": source_lang if source_lang != "auto" else "auto",
                        "target_lang": target_lang,
                        "input_text": text[:500] + ("..." if len(text) > 500 else ""),
                        "translated_text": translated,
                    }
                    return json.dumps(output, ensure_ascii=False, indent=2)

                else:
                    return f"Unsupported service: {service}. Supported: libre, google"

            except ImportError as e:
                return f"Library not installed: {e}"
            except Exception as e:
                return f"Translation failed: {e}"

        result = await loop.run_in_executor(None, _translate)

        if file_path:
            try:
                translated = json.loads(result).get("translated_text", "")
                if translated:
                    out_path = str(Path(file_path).with_stem(Path(file_path).stem + f"_{target_lang}"))
                    Path(out_path).write_text(translated, encoding="utf-8")
                    return f"Translation saved to {out_path}\n\n{result}"
            except (json.JSONDecodeError, OSError):
                pass

        return result

    elif action == "languages":
        def _languages() -> str:
            """Languages."""
            try:
                if service == "libre":
                    import urllib.request
                    api_url = (engine_url or "http://localhost:5000").rstrip("/")
                    req = urllib.request.Request(f"{api_url}/languages")
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                    return json.dumps(result, ensure_ascii=False, indent=2)
                elif service == "google":
                    try:
                        from deep_translator import GoogleTranslator
                    except ImportError:
                        return "deep_translator library required. Install: pip install deep-translator"
                    langs = GoogleTranslator().get_supported_languages(as_dict=True)
                    return json.dumps(langs, ensure_ascii=False, indent=2)
                return f"Unsupported service: {service}"
            except Exception as e:
                return f"Failed to list languages: {e}"

        return await loop.run_in_executor(None, _languages)

    return f"Unknown action: {action}. Supported: translate, detect, languages"


EncreTranslationTool = build_tool(
    name="translation",
    description=(
        "Translate text between languages, detect the source language, or list "
        "supported languages via LibreTranslate (self-hosted) or Google Translate. "
        "Use `translate` to convert text/files, `detect` to identify a language, or "
        "`languages` to enumerate supported codes; prefer LibreTranslate for "
        "offline/private setups. "
        "Do NOT use this for speech-to-English (use translate_audio), for "
        "summarization, or for in-app i18n string catalogs. "
        "Tips: set `source_lang='auto'` for auto-detection; when translating a file, "
        "the result is written next to it with a `_<target>` suffix. "
        "Pitfalls: the `libre` service needs a reachable `engine_url` (default "
        "http://localhost:5000); the `google` service requires the deep-translator "
        "package."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["translate", "detect", "languages"],
                "description": "Translation operation: translate (convert text to target_lang), detect (identify the source language), or languages (list supported language codes).",
            },
            "text": {"type": "string", "description": "Text to translate or detect; required for translate/detect unless file_path is given."},
            "source_lang": {"type": "string", "description": "Source language code (e.g. 'en', 'zh', 'fr'); defaults to 'auto' for auto-detection."},
            "target_lang": {"type": "string", "description": "Target language code for translate; defaults to 'en'."},
            "file_path": {"type": "string", "description": "Path to a text file to translate; the translated output is saved as '<stem>_<target_lang>.<ext>'. Alternative to passing text directly."},
            "service": {
                "type": "string",
                "enum": ["libre", "google"],
                "description": "Translation backend: 'libre' (self-hosted LibreTranslate HTTP API) or 'google' (deep-translator GoogleTranslator). Defaults to 'libre'.",
            },
            "engine_url": {"type": "string", "description": "Base URL of the LibreTranslate API server; libre service only. Defaults to 'http://localhost:5000'."},
            "preserve_format": {"type": "boolean", "description": "If true, treat input as HTML and preserve markup during translation; defaults to false (plain text)."},
        },
        "required": ["action"],
    },
    execute=_translation_execute,
    intents=["general", "research", "data"],
    category="communication",
    semantic_type="transform",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_readonly=lambda _: True,
)
