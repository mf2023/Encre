---
name: tool-memory_search
description: "Search memory files semantically and return the most relevant matches for the query. Use this when you need to recall a memory by meaning rather than by filename, e.g. 'what does the user prefer for testing?'. Do NOT use this when you already know the filename (use memory_read) or for structured user profile fields (use memory_profile). Tips: write the query as a natural-language question for best recall; raise `top_k` to broaden the result set. Pitfalls: very generic queries can surface many similar memories \u9225?narrow the wording or reduce `top_k` to focus results."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# memory_search

Search memory files semantically and return the most relevant matches for the query. Use this when you need to recall a memory by meaning rather than by filename, e.g. 'what does the user prefer for testing?'. Do NOT use this when you already know the filename (use memory_read) or for structured user profile fields (use memory_profile). Tips: write the query as a natural-language question for best recall; raise `top_k` to broaden the result set. Pitfalls: very generic queries can surface many similar memories 鈥?narrow the wording or reduce `top_k` to focus results.
