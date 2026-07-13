---
name: tool-codebase-search
description: Semantic codebase search skill. query/limit, natural-language search over indexed code
hidden: true
context: inline
---

## When to Use
- Natural-language search over the codebase ("where do we handle auth failures")
- Semantic search when you don't know exact symbol names or patterns
- Discover related code across the indexed workspace

## When NOT to Use
- **Exact text/regex search** -> `grep` (faster, precise)
- **Find files by name** -> `glob`
- **Symbol definition/references** -> `lsp`

## Key Parameters
- `query` (required): natural-language description of what you're looking for
- `limit`: max number of results

## Best Practices
- Phrase the query as a question or capability ("how is retry logic implemented")
- Use this for exploration when you don't know the codebase; use `grep`/`lsp` once you know the symbol

## Common Pitfalls / Anti-patterns
- **Using it for exact-string lookup**: if you know the string or symbol, `grep`/`lsp` are faster and exact. This is for semantic discovery when you don't know the name
- **Vague query**: "find code" or "show functions" returns noise. Describe the capability or behavior ("where do we handle auth token refresh")
- **Searching an unindexed workspace**: returns nothing useful if the index isn't built. Confirm the workspace is indexed first, or fall back to `grep`/`glob`
- **Trusting rank over relevance**: top results are similarity-ranked, not verified. Always `file_read` a hit before acting on it - the match may be coincidental

## Pairing with Other Tools
- `codebase_context`: get context about a specific file
- `grep`/`lsp`: precise lookups after semantic discovery
- `file_read`: read the matched files
