---
name: tool-glob
description: File-by-pattern finding skill. pattern/path, find files by name not content, pair with grep/file_read
hidden: true
context: inline
---

## When to Use
- Find files by name pattern: `**/*.py`, `src/**/*.ts`, `*.config.js`
- Locate files before reading or searching their content
- Enumerate a project's structure by extension

## When NOT to Use
- **Search file contents** -> `grep` (glob finds filenames, grep searches content)
- **Read a known file** -> `file_read`
- **Find a symbol's definition** -> `lsp`

## Key Parameters
- `pattern` (required): glob pattern. `*` matches within a single segment, `**` matches any depth (e.g. `src/**/*.ts`)
- `path`: search root, defaults to workspace root

## Best Practices
- Use `**` for recursive depth: `**/*.py` finds Python files at any level
- Combine with grep: glob to find files, then grep to search their content
- Narrow `path` to a subdirectory when you know the area, to reduce noise

## Common Pitfalls / Anti-patterns
- **Using glob to search content**: glob matches filenames only; content search is grep's job
- **Pattern too broad**: `*` at root matches everything; scope with a directory or extension
- **Forgetting `**` for recursion**: `*.py` only matches the top level; use `**/*.py` for all levels
- **Using glob for a single known file** - if you know the exact path, `file_read` it directly instead of globbing.
- **Cross-platform path separators** - glob patterns with backslashes work differently on Windows vs POSIX. Use forward slashes in patterns for portability.

## Pairing with Other Tools
- `grep`: glob to find files, then grep to search inside them
- `file_read`: glob to find the path, then read
- `lsp`: after locating files, lsp for semantic navigation
