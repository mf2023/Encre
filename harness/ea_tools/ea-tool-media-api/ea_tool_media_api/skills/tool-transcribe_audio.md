---
name: tool-transcribe_audio
description: "Transcribe speech in an audio file into text using the active backend's transcription model (Whisper-compatible). Use this to convert recordings, voice notes, or interviews to text; prefer it over generic OCR for spoken content. Do NOT use this for in-browser live captioning or for translating audio to English (use translate_audio instead). Tips: pass an ISO language code to improve accuracy on non-English audio; use common formats such as mp3, wav, or m4a. Pitfalls: the active backend must implement transcribe_audio, otherwise the call returns an unsupported error."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# transcribe_audio

Transcribe speech in an audio file into text using the active backend's transcription model (Whisper-compatible). Use this to convert recordings, voice notes, or interviews to text; prefer it over generic OCR for spoken content. Do NOT use this for in-browser live captioning or for translating audio to English (use translate_audio instead). Tips: pass an ISO language code to improve accuracy on non-English audio; use common formats such as mp3, wav, or m4a. Pitfalls: the active backend must implement transcribe_audio, otherwise the call returns an unsupported error.
