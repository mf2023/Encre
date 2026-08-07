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
    description=(
        "Transcribe speech in an audio file into text using the active backend's "
        "transcription model (Whisper-compatible). "
        "Use this to convert recordings, voice notes, or interviews to text; prefer "
        "it over generic OCR for spoken content. "
        "Do NOT use this for in-browser live captioning or for translating audio to "
        "English (use translate_audio instead). "
        "Tips: pass an ISO language code to improve accuracy on non-English audio; "
        "use common formats such as mp3, wav, or m4a. "
        "Pitfalls: the active backend must implement transcribe_audio, otherwise the "
        "call returns an unsupported error."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Local audio file path or base64-encoded audio data to transcribe."},
            "language": {"type": "string", "description": "ISO language code (e.g. 'en', 'zh', 'fr') to guide transcription; omit for auto-detection."},
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
    description=(
        "Translate speech in an audio file directly into English text using the "
        "active backend's translation model (Whisper-compatible). "
        "Use this when the source audio is non-English and English output is wanted "
        "in a single step; prefer transcribe_audio when you need the original-"
        "language text. "
        "Do NOT use this for same-language transcription or for translating written "
        "text (use translation). "
        "Tips: ensure the file format is supported by the backend; output is always "
        "English regardless of the source language. "
        "Pitfalls: the active backend must implement translate_audio, otherwise the "
        "call returns an unsupported error."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Local audio file path or base64-encoded audio data to translate."},
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
    description=(
        "Generate vector embeddings for text inputs using the active backend's "
        "embeddings model. "
        "Use this to power semantic search, clustering, or similarity comparisons; "
        "returns a JSON sample of the first few embedding dimensions per input. "
        "Do NOT use this for chat completions (use the chat backend) or for "
        "moderation checks (use create_moderation). "
        "Tips: pass a single string or a JSON array of strings for batch embedding; "
        "keep inputs under the model's token limit. "
        "Pitfalls: output is truncated to 5 dimensions per item for display — "
        "retrieve full vectors from the backend directly if you need them."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Text to embed, or a JSON-encoded array of strings for batch embedding.",
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
    description=(
        "Classify text against a moderation policy to flag harmful or unsafe "
        "content, returning per-category results. "
        "Use this to screen user-generated or model-generated text before display, "
        "storage, or further processing. "
        "Do NOT use this for general sentiment analysis, PII detection, or as the "
        "sole safety gate without human review. "
        "Tips: submit plain text only; inspect the 'flagged' array and per-result "
        "category scores in the JSON output. "
        "Pitfalls: the active backend must implement create_moderation; policies and "
        "categories vary by provider."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Text to classify for harmful or unsafe content."},
        },
        "required": ["input"],
    },
    execute=_create_moderation_execute,
    intents=["general", "safety"],
    category="data",
    is_concurrency_safe=True,
)

__all__ = ["EncreTranscribeAudioTool", "EncreTranslateAudioTool", "EncreCreateEmbeddingsTool", "EncreCreateModerationTool"]
