---
name: tool-find-tool
description: Tool discovery skill. query/top_k/category, find the right tool when unsure, before falling back to bash
hidden: true
context: inline
---

## When to Use
- You don't see an obvious dedicated tool for the task
- You're tempted to use bash for something that might have a dedicated tool
- Discover available MCP (`mcp__*`) tools

## When NOT to Use
- **You already know the tool** -> call it directly
- **Search code** -> `grep`
- **Find files** -> `glob`

## Key Parameters
- `query` (required): natural-language description of what you need
- `top_k`: max results to return
- `category`: restrict to a tool category

## Best Practices
- Call this BEFORE reaching for bash when you're unsure a dedicated tool exists
- Phrase the query by capability ("convert pdf to text", "query a database")

## Common Pitfalls / Anti-patterns
- **Reaching for bash without checking**: a dedicated tool likely exists for the task; discover first, bash last
- **Assuming the default set is everything**: the workspace may expose more tools or MCP (`mcp__*`) tools. Discover rather than assume
- **Vague query**: "do stuff" returns nothing useful. Describe the capability ("convert pdf to text", "query a postgres database")
- **Ignoring the result and using bash anyway**: `find_tool` returns a match but you reach for bash because it's familiar - that defeats the discovery step. Use the tool it found

## Pairing with Other Tools
- After discovery, call the found tool directly
- `bash` only as the last resort when find_tool returns nothing relevant
