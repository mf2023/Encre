---
name: tool-memory_read
description: "Read a memory file by filename, returning the full decrypted content including any YAML frontmatter. Use this when you already know the memory filename and want its full contents loaded into context. Do NOT use this to discover memories by meaning (use memory_search) or to inspect the user profile (use memory_profile). Tips: pair with memory_search to first locate the relevant filename. Pitfalls: returns an error if the filename does not exist."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# memory_read

Read a memory file by filename, returning the full decrypted content including any YAML frontmatter. Use this when you already know the memory filename and want its full contents loaded into context. Do NOT use this to discover memories by meaning (use memory_search) or to inspect the user profile (use memory_profile). Tips: pair with memory_search to first locate the relevant filename. Pitfalls: returns an error if the filename does not exist.
