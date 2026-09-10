---
name: tool-create_moderation
description: "Classify text against a moderation policy to flag harmful or unsafe content, returning per-category results. Use this to screen user-generated or model-generated text before display, storage, or further processing. Do NOT use this for general sentiment analysis, PII detection, or as the sole safety gate without human review. Tips: submit plain text only; inspect the 'flagged' array and per-result category scores in the JSON output. Pitfalls: the active backend must implement create_moderation; policies and categories vary by provider."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# create_moderation

Classify text against a moderation policy to flag harmful or unsafe content, returning per-category results. Use this to screen user-generated or model-generated text before display, storage, or further processing. Do NOT use this for general sentiment analysis, PII detection, or as the sole safety gate without human review. Tips: submit plain text only; inspect the 'flagged' array and per-result category scores in the JSON output. Pitfalls: the active backend must implement create_moderation; policies and categories vary by provider.
