---
name: tool-memory-update
description: Memory update skill. filename/content, modify an existing memory file
hidden: true
context: inline
---

## When to Use
- Modify an existing memory (correct, refine, add to)
- Keep a memory current as facts/preferences change

## When NOT to Use
- **Create a new memory** -> `memory_create`
- **Delete a memory** -> `memory_delete`

## Key Parameters
- `filename` (required): the memory file to update
- `content` (required): the new content

## Best Practices
- Read the existing memory first (`memory_read`) to preserve what should stay
- Update when info changes, not on every turn

## Common Pitfalls / Anti-patterns
- **Overwriting without reading**: you lose existing content you should have kept. `memory_read` first, then update with the full intended content
- **Frequent trivial updates**: updating every turn churns the memory and pushes cost. Only update when info materially changes
- **Dropping the frontmatter/metadata on rewrite**: if you write a new body, preserve the `name`/`description`/`metadata` block the loader expects, or the memory may stop resolving
- **Updating a wrong filename**: a guessed slug updates the wrong file. `memory_search` to confirm the exact filename first

## Pairing with Other Tools
- `memory_read`: read before update
- `memory_create`: for new memories
