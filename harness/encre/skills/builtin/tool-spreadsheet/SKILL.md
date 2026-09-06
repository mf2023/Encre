---
name: tool-spreadsheet
description: Spreadsheet skill. action/file_path/sheet_name/data/range, read/write Excel/CSV without awk
hidden: true
context: inline
---

## When to Use
- Read or write spreadsheet files (Excel .xlsx, CSV)
- Work with tabular data in sheet form
- Update a specific sheet/range

## When NOT to Use
- **Parse CSV with awk/sed in bash** -> use this tool
- **Query a database** -> `database`
- **Read a plain text file** -> `file_read`

## Key Parameters
- `action` (required): the spreadsheet action (read, write, append, etc.)
- `file_path` (required): the spreadsheet file
- `sheet_name`: target sheet
- `data`: data to write
- `range`: cell range to read/write

## Best Practices
- Specify `sheet_name` when the workbook has multiple sheets
- Use `range` to scope reads/writes rather than whole-sheet operations

## Common Pitfalls / Anti-patterns
- **Whole-sheet operations when a range suffices**: reading an entire sheet is slow and floods context with irrelevant rows. Scope with `range`
- **Using awk/sed for CSV**: this tool parses quoted fields, escaping, and types correctly; awk/sed break on commas inside quoted strings
- **Wrong sheet in a multi-sheet workbook**: omitting `sheet_name` hits the default/first sheet, which may not be the one you mean. Name it explicitly
- **Writing without backing up**: a write overwrites cells in place. If the data matters, read the current value first or write to a new sheet/file

## Pairing with Other Tools
- `database`: if the data lives in a DB
- `file_write`: for non-spreadsheet files
