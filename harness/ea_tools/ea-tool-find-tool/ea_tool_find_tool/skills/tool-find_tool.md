---
name: tool-find_tool
description: "Discover and unlock specialized tools beyond the always-on basic set (file_read/write/edit, bash, grep, glob, todo). Returns matching tool cards and unlocks them for the rest of the session so they become directly callable on the next turn. WHEN to use: at the start of any task needing non-basic capabilities (e.g. database, browser, docker, web fetch, ssh, email). WHEN NOT to use: for basic file/shell operations (already always available); for listing all tools (call with a broad query instead). TIP: Describe the capability you need in natural language (e.g. \"run SQL queries\"), not a tool name. TIP: Pass 'category' to narrow the search and get more relevant hits. PITFALLS: calling find_tool repeatedly for the same capability wastes turns -- once unlocked, tools stay available for the whole session; very vague queries may return too many irrelevant matches."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# find_tool

Discover and unlock specialized tools beyond the always-on basic set (file_read/write/edit, bash, grep, glob, todo). Returns matching tool cards and unlocks them for the rest of the session so they become directly callable on the next turn. WHEN to use: at the start of any task needing non-basic capabilities (e.g. database, browser, docker, web fetch, ssh, email). WHEN NOT to use: for basic file/shell operations (already always available); for listing all tools (call with a broad query instead). TIP: Describe the capability you need in natural language (e.g. "run SQL queries"), not a tool name. TIP: Pass 'category' to narrow the search and get more relevant hits. PITFALLS: calling find_tool repeatedly for the same capability wastes turns -- once unlocked, tools stay available for the whole session; very vague queries may return too many irrelevant matches.
