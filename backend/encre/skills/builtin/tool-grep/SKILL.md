---
name: tool-grep
description: Ripgrep content search skill. When to use grep, parameter tips, multiline pitfalls, pairing with glob/lsp
hidden: true
context: inline
---

## When to Use
- Find code/text by pattern: function definitions, call sites, string literals, error messages
- Search across many files for where a symbol appears
- Count matches (count) or list matching files (files_with_matches)

## When NOT to Use
- **Find files by name** -> use `glob` (grep searches content, not filenames)
- **Jump to definition / references** -> use `lsp` (semantic, more accurate than regex)
- **Read content of a single known file** -> use `file_read`, not grep
- **Run shell grep/rg** -> forbidden, use this tool

## Key Parameters
- `pattern` (required): ripgrep regex. Write literals directly; escape special chars (`{}` `[]` `()`), e.g. to find `interface{}` write `interface\{\}`
- `path`: search root, default `.` (current workspace). Narrow it to speed up
- `glob`: filter by filename, e.g. `"*.py"`, `"**/*.ts"`. Finer than `path`
- `type`: filter by language, e.g. `py`/`js`/`rust` (semantic equivalent of glob)
- `output_mode`:
  - `content` (default): show matching lines + line numbers
  - `files_with_matches`: only list files with hits (quick "which files")
  - `count`: hits per file (assess coverage)
- `-A`/`-B`/`-C`: context lines around matches (use `-C 3` to see code context)
- `-n`: show line numbers (default true, for locating)
- `multiline: true`: let `.` match newlines so patterns span lines. **Default false**; multi-line structures (e.g. `struct\s*\{[^}]*\}`) require this
- `head_limit`: cap output lines; probe with a small value on large searches first

## Best Practices
- Start with `output_mode: files_with_matches` to locate files, then `-C 3` for content
- If a search returns nothing, swap synonyms: class name / method name / abbreviation / full name
- On large repos narrow with `type` or `glob` before searching, avoid full scans
- Definition patterns: `pattern="def my_func"` / `class MyService` / `fn my_func`

## Common Pitfalls / Anti-patterns
- **Unescaped brackets**: `pattern="foo()"` treats `()` as a regex group; for literal parens write `foo\(\)`
- **Forgot multiline for cross-line**: default single-line mode, `.*` won't cross `\n`; multi-line structures fail without `multiline: true`
- **Using grep to find files**: `glob` finds files, grep searches file content
- **Grepping for definitions instead of lsp**: "where is X defined / who calls it" -> use `lsp`; grep only guesses via regex
- **Hardcoding a single known file as path**: just `file_read` it, grepping one file is wasteful
- **Full-repo scan without narrowing**: slow and noisy; narrow with glob/type first

## Pairing with Other Tools
- **glob**: glob to locate files, then grep for content; or grep `files_with_matches` then targeted reads
- **lsp**: definition/reference queries go to lsp; grep is the fallback text search
- **file_read**: after grep locates a line number, use file_read to see full context
