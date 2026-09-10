---
name: tool-translate_audio
description: "Translate speech in an audio file directly into English text using the active backend's translation model (Whisper-compatible). Use this when the source audio is non-English and English output is wanted in a single step; prefer transcribe_audio when you need the original-language text. Do NOT use this for same-language transcription or for translating written text (use translation). Tips: ensure the file format is supported by the backend; output is always English regardless of the source language. Pitfalls: the active backend must implement translate_audio, otherwise the call returns an unsupported error."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# translate_audio

Translate speech in an audio file directly into English text using the active backend's translation model (Whisper-compatible). Use this when the source audio is non-English and English output is wanted in a single step; prefer transcribe_audio when you need the original-language text. Do NOT use this for same-language transcription or for translating written text (use translation). Tips: ensure the file format is supported by the backend; output is always English regardless of the source language. Pitfalls: the active backend must implement translate_audio, otherwise the call returns an unsupported error.
