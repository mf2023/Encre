---
name: tool-memory_update
description: "Replace the entire contents of an existing memory file with new content, encrypted on save. Use this to refresh or correct a memory that has grown stale. Do NOT use this to create a new memory (use memory_create) or to delete (use memory_delete); for partial edits, read first then write the merged content. Tips: preserve any YAML frontmatter so metadata stays intact. Pitfalls: the previous content is overwritten with no history retained."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# memory_update

Replace the entire contents of an existing memory file with new content, encrypted on save. Use this to refresh or correct a memory that has grown stale. Do NOT use this to create a new memory (use memory_create) or to delete (use memory_delete); for partial edits, read first then write the merged content. Tips: preserve any YAML frontmatter so metadata stays intact. Pitfalls: the previous content is overwritten with no history retained.
