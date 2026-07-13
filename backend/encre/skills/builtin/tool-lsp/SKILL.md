---
name: tool-lsp
description: Language server skill. goToDefinition/findReferences/hover/documentSymbol, semantic navigation vs grep
hidden: true
context: inline
---

## When to Use
- Jump to a symbol's definition (goToDefinition)
- Find all references to a symbol (findReferences)
- Hover for type/doc info (hover)
- List all symbols in a file (documentSymbol)
- Find implementations of an interface/abstract method (goToImplementation)

## When NOT to Use
- **Text/regex search** -> `grep` (lsp is semantic, grep is text)
- **Find files by name** -> `glob`
- **Read a file** -> `file_read`

## Key Parameters
- `operation` (required): one of goToDefinition, findReferences, hover, documentSymbol, goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls, workspaceSymbol
- `file_path` (required for most ops): target file
- `line` + `character` (required for position ops): 1-based line and character offset of the symbol
- `workspace`: workspace root; some servers need it
- `query`: for workspaceSymbol, partial name to search

## Best Practices
- For "where is X defined / who calls X", prefer lsp over grep (semantic, accurate)
- Use documentSymbol to map a file's structure before reading specific parts
- workspaceSymbol for project-wide symbol search by partial name
- Confirm an LSP server is configured for the file type; if absent, fall back to grep

## Common Pitfalls / Anti-patterns
- **Using grep for definitions**: grep only guesses via regex; lsp is accurate
- **Wrong line/character**: position ops need exact 1-based coordinates; off-by-one fails
- **No LSP for the language**: if no server is configured, lsp returns an error; fall back to grep
- **Ignoring documentSymbol**: reading a big file blindly when you could list symbols first wastes effort

## Pairing with Other Tools
- `grep`: fallback text search when lsp is unavailable
- `file_read`: after lsp locates a definition, read the file for full context
- `glob`: find the file first, then lsp on it
