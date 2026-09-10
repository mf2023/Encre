---
name: tool-codebase_search
description: "Semantic search of the active workspace codebase by meaning rather than exact text. Uses the prepared workspace index when available and falls back to the Rust native code search engine. Prefer this over grep when you want to find relevant code by intent (e.g. \"where are passwords hashed\") instead of by literal string. TIP: Phrase the query as a natural-language question or capability, not a regex. AVOID: Using codebase_search for exact symbol/string matches -- grep is faster and exact for those."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# codebase_search

Semantic search of the active workspace codebase by meaning rather than exact text. Uses the prepared workspace index when available and falls back to the Rust native code search engine. Prefer this over grep when you want to find relevant code by intent (e.g. "where are passwords hashed") instead of by literal string. TIP: Phrase the query as a natural-language question or capability, not a regex. AVOID: Using codebase_search for exact symbol/string matches -- grep is faster and exact for those.
