---
name: tool-memory-search
description: Memory search skill. query/top_k, find relevant memories by content
hidden: true
context: inline
---

## When to Use
- Recall relevant memories by content/topic
- Check what's already remembered before acting or creating a new memory
- Ground a response in prior context the user references

## When NOT to Use
- **Read a known memory file** -> `memory_read`
- **Search project code** -> `grep`

## Key Parameters
- `query` (required): natural-language description of what to recall
- `top_k`: max results

## Best Practices
- Search before creating to avoid duplicates
- Phrase the query by topic/role ("user preferences for testing")

## Common Pitfalls / Anti-patterns
- **Creating a memory without searching first**: you may duplicate or contradict an existing one. Always search before creating
- **Vague query**: "user stuff" returns noise. Describe the topic specifically ("user preferences for test frameworks")
- **Treating no results as "nothing remembered"**: a miss is more often a bad query than an empty store. Reformulate with synonyms before concluding nothing exists
- **Trusting stale memories as current**: a memory reflects when it was written. If it names a file/symbol/flag, verify it still applies before acting on it

## Pairing with Other Tools
- `memory_create`/`memory_read`/`memory_update`/`memory_delete`: manage memories
