---
name: tool-codebase-context
description: Codebase file context skill. file_path, get indexed context/dependencies for a specific file
hidden: true
context: inline
---

## When to Use
- Get structural context about a specific file (symbols, dependencies, related files)
- Understand a file's role before editing it
- Find what depends on or is depended on by a file

## When NOT to Use
- **Search across the codebase** -> `codebase_search`
- **Read the file's content** -> `file_read`
- **Symbol navigation** -> `lsp`

## Key Parameters
- `file_path` (required): the file to get context for

## Best Practices
- Call before editing an unfamiliar file to understand its place in the codebase
- Pair with `file_read` for content and this for structure/relationships

## Common Pitfalls / Anti-patterns
- **Using it to read content**: this returns structural context (symbols, deps, related files), not the file's source. Use `file_read` for the actual content
- **File not indexed**: if the workspace isn't indexed yet, context comes back empty or stale. Index first, or fall back to `file_read` + `grep`
- **Treating stale context as current**: the index lags behind recent edits. If the context contradicts what `file_read` shows, trust the file content and let the index catch up
- **Context is not verification** - the context tells you about structure, not correctness. Always `file_read` before editing; context can be stale or incomplete.

## Pairing with Other Tools
- `file_read`: actual content
- `codebase_search`: broader discovery
- `lsp`: symbol-level navigation
