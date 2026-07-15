#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any

from encre.tools.base import build_tool


def _get_backend():
    from encre.tools.builtin.agent import _resolve_loop
    loop = _resolve_loop()
    if loop and loop.backend:
        return loop.backend
    return None


async def _transcribe_audio_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend is not initialized"
    if not hasattr(backend, "transcribe_audio"):
        return "Error: This backend does not support audio transcription"
    try:
        file = kwargs.get("file", "")
        language = kwargs.get("language", "")
        result = await backend.transcribe_audio(file=file, language=language or None)
        return result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        return f"Error transcribing audio: {e}"


async def _translate_audio_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend is not initialized"
    if not hasattr(backend, "translate_audio"):
        return "Error: This backend does not support audio translation"
    try:
        file = kwargs.get("file", "")
        result = await backend.translate_audio(file=file)
        return result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        return f"Error translating audio: {e}"


async def _create_embeddings_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend is not initialized"
    if not hasattr(backend, "create_embeddings"):
        return "Error: This backend does not support embeddings"
    try:
        texts = kwargs.get("input", "")
        if isinstance(texts, str):
            texts = [texts]
        result = await backend.create_embeddings(input=texts)
        data = [{"index": i, "embedding": e.embedding[:5]} for i, e in enumerate(result.data)]
        return json.dumps({"model": result.model, "count": len(data), "sample": data[:3]}, indent=2)
    except Exception as e:
        return f"Error creating embeddings: {e}"


async def _create_moderation_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend is not initialized"
    if not hasattr(backend, "create_moderation"):
        return "Error: This backend does not support moderation"
    try:
        text = kwargs.get("input", "")
        result = await backend.create_moderation(input=text)
        flagged = [r.flagged for r in result.results]
        return json.dumps({"flagged": flagged, "results": [r.to_dict() if hasattr(r, "to_dict") else r for r in result.results]}, indent=2, default=str)
    except Exception as e:
        return f"Error creating moderation: {e}"


EncreTranscribeAudioTool = build_tool(
    name="transcribe_audio",
    description="Transcribe audio to text using Whisper API or compatible",
    input_schema={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Audio file path or base64 data"},
            "language": {"type": "string", "description": "Optional language code (e.g. en, zh)"},
        },
        "required": ["file"],
    },
    execute=_transcribe_audio_execute,
    intents=["general", "data"],
    category="media",
    semantic_type="media",
    is_concurrency_safe=True,
)

EncreTranslateAudioTool = build_tool(
    name="translate_audio",
    description="Translate audio to English text using Whisper API or compatible",
    input_schema={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Audio file path or base64 data"},
        },
        "required": ["file"],
    },
    execute=_translate_audio_execute,
    intents=["general", "data"],
    category="media",
    semantic_type="media",
    is_concurrency_safe=True,
)

EncreCreateEmbeddingsTool = build_tool(
    name="create_embeddings",
    description="Create vector embeddings for text using the model's embeddings API",
    input_schema={
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Text to embed, or a JSON array of strings for batch embedding",
            },
        },
        "required": ["input"],
    },
    execute=_create_embeddings_execute,
    intents=["general", "data"],
    category="data",
    is_concurrency_safe=True,
)

EncreCreateModerationTool = build_tool(
    name="create_moderation",
    description="Check text for harmful content using the moderation API",
    input_schema={
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Text to classify"},
        },
        "required": ["input"],
    },
    execute=_create_moderation_execute,
    intents=["general", "safety"],
    category="data",
    is_concurrency_safe=True,
)

__all__ = ["EncreTranscribeAudioTool", "EncreTranslateAudioTool", "EncreCreateEmbeddingsTool", "EncreCreateModerationTool"]
