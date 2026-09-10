---
name: tool-translation
description: "Translate text between languages, detect the source language, or list supported languages via LibreTranslate (self-hosted) or Google Translate. Use `translate` to convert text/files, `detect` to identify a language, or `languages` to enumerate supported codes; prefer LibreTranslate for offline/private setups. Do NOT use this for speech-to-English (use translate_audio), for summarization, or for in-app i18n string catalogs. Tips: set `source_lang='auto'` for auto-detection; when translating a file, the result is written next to it with a `_<target>` suffix. Pitfalls: the `libre` service needs a reachable `engine_url` (default http://localhost:5000); the `google` service requires the deep-translator package."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# translation

Translate text between languages, detect the source language, or list supported languages via LibreTranslate (self-hosted) or Google Translate. Use `translate` to convert text/files, `detect` to identify a language, or `languages` to enumerate supported codes; prefer LibreTranslate for offline/private setups. Do NOT use this for speech-to-English (use translate_audio), for summarization, or for in-app i18n string catalogs. Tips: set `source_lang='auto'` for auto-detection; when translating a file, the result is written next to it with a `_<target>` suffix. Pitfalls: the `libre` service needs a reachable `engine_url` (default http://localhost:5000); the `google` service requires the deep-translator package.
