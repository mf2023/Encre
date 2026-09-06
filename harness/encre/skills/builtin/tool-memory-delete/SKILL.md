---
name: tool-memory-delete
description: Memory delete skill. filename, remove an outdated or wrong memory file
hidden: true
context: inline
---

## When to Use
- Remove a memory that's outdated or wrong
- Clean up memories that are no longer relevant

## When NOT to Use
- **Modify a memory** -> `memory_update`
- **Create a memory** -> `memory_create`

## Key Parameters
- `filename` (required): the memory file to delete

## Best Practices
- Confirm the filename via `memory_search`/`memory_read` before deleting
- Delete when a memory is wrong or superseded, not just stale-ish (update instead)

## Common Pitfalls / Anti-patterns
- **Deleting without confirming**: a guessed filename deletes the wrong memory. `memory_search`/`memory_read` to confirm the exact filename first
- **Deleting when update would do**: if the memory is just stale or partly wrong, `memory_update` preserves the still-correct parts. Delete only when it's wholly wrong or unwanted
- **Deleting a memory that other memories link to**: memories reference each other by `[[name]]`; deleting one leaves dangling links. Check for inbound references before deleting
- **Deletion is permanent** - there is no undo for a deleted memory file. If you are unsure whether the info is still useful, `memory_update` instead of delete.

## Pairing with Other Tools
- `memory_search`: find the filename
- `memory_read`: confirm content before delete
