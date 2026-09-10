---
name: tool-memory_profile
description: "Read or update the user profile \u9225?structured observations about the user (expertise, communication style, preferences, OS, editor, etc.) stored as _profile.md inside the unified memory system."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# memory_profile

Read or update the user profile 鈥?structured observations about the user (expertise, communication style, preferences, OS, editor, etc.) stored as _profile.md inside the unified memory system.

Use this to tailor responses to the user (query) or to record a new observation (update).
Do NOT use this for free-form memories (use memory_create/update) or for one-off facts that do not belong in the profile.
Tips: query with no args to dump the whole profile; pass field+value to record an observation, optionally with a confidence score.
Pitfalls: profile fields are a fixed enumeration 鈥?see the `field` enum description for the supported set.
