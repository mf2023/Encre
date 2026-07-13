---
name: tool-memory-create
description: Memory create skill. filename/content, persist a memory file for cross-conversation recall
hidden: true
context: inline
---

## When to Use
- Persist a fact/preference/decision that should survive across conversations
- Store user profile info, project context, or feedback for future sessions

## When NOT to Use
- **Ephemeral in-session state** -> use `todo` or conversation context, not memory
- **Code/config** -> `file_write`
- **Read existing memory** -> `memory_read`

## Key Parameters
- `filename` (required): memory file name (kebab-case slug)
- `content` (required): the memory content

## Best Practices
- Save genuinely cross-conversation info (user role, preferences, project context), not ephemeral state
- Use clear slugs as filenames, organized by topic
- Don't duplicate; check existing memories first with `memory_search`

## Common Pitfalls / Anti-patterns
- **Saving ephemeral state**: memory is for cross-conversation recall, not current-task state. This turn's plan belongs in `todo`, not memory
- **Duplicating existing memories**: always `memory_search` first; a second memory on the same topic fragments recall
- **Vague filename**: future recall depends on a discoverable slug. Use a clear kebab-case name by topic (`user-testing-preferences`, not `note1`)
- **Saving what the repo already records**: code structure, git history, and CLAUDE.md are already discoverable. Memory is for what's *not* in the repo - save the non-obvious fact, not the derivable one

## Pairing with Other Tools
- `memory_search`: check for existing similar memories
- `memory_read`/`memory_update`/`memory_delete`: manage memories
