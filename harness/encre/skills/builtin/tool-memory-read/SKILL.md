---
name: tool-memory-read
description: Memory read skill. filename, load a specific memory file's content
hidden: true
context: inline
---

## When to Use
- Read a specific memory file by name
- Recall a known memory when its filename is referenced

## When NOT to Use
- **Search memories by content** -> `memory_search`
- **Read a project file** -> `file_read`

## Key Parameters
- `filename` (required): the memory file to read

## Best Practices
- Use when you know the filename; use `memory_search` when you don't
- Pair with `memory_profile` to understand the user before reading specific memories

## Common Pitfalls
- **Guessing the filename** - memory files are named by slug; guessing ("user-prefs.md") misses the real one. `memory_search` finds it by content first.
- **Reading memory as project file** - `memory_read` is for the agent's own memory store, not workspace files. For project code/data use `file_read`.
- **Reading memory that doesn't exist** - a guessed slug produces empty output, not an error. If `memory_read` returns nothing, use `memory_search` to find the right name first.
- **Forgetting frontmatter on write-back** - if you `memory_read`, edit in mind, then `memory_update`, the frontmatter (name/description/metadata) must be preserved or the memory won't resolve next load.

## Pairing with Other Tools
- `memory_search`: discover relevant memories
- `memory_update`/`memory_delete`: modify after reading
