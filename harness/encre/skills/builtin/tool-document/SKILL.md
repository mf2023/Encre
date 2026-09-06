---
name: tool-document
description: Word document skill. action/file_path/content/text/data, read/create/edit .docx without manual python-docx
hidden: true
context: inline
---

## When to Use
- Read, extract text, or inspect a Word (.docx) document
- Create a new .docx, or append text/headings/tables to an existing one
- List tables, convert .docx to .txt/.md

## When NOT to Use
- **Plain text / Markdown / code files** -> `file_read` / `file_write`
- **PDF files** -> `pdf` tool
- **Spreadsheets (.xlsx)** -> `spreadsheet` tool
- **PowerPoint (.pptx)** -> `presentation` tool

## Key Parameters
- `action` (required): one of read, extract_text, info, create, add_text, add_table, list_tables, convert
- `file_path`: path to the .docx (required except for `convert` which uses source/target)
- `content`: markdown-style content for `create` (`# heading`, `- list`)
- `text`: text/headings for `add_text` (supports `#`/`##`/`###`)
- `data`: 2D array for `add_table` (`[[header1,header2],[row1c1,row1c2]]`)
- `source`/`target`: paths for `convert` (target `.txt` or `.md`)

## Best Practices
- Run `info` or `list_tables` before editing to learn the document's structure
- Use real headings (`#`/`##`) in `create`/`add_text`, not bold text, so the outline is navigable
- Pass clean 2D arrays for `add_table`, not pre-formatted strings
- After `add_text`/`add_table`/`create`, re-read to confirm the change landed

## Common Pitfalls / Anti-patterns
- **Using `file_read` on a .docx** -> .docx is a zip archive; you must use this tool, not raw read
- **`create` when you mean `add_text`** -> `create` overwrites/starts fresh; `add_text` appends. Choose deliberately
- **Treating legacy `.doc` like `.docx`** -> convert to .docx first or use an appropriate parser
- **Plain text extraction drops tables** -> use the table-aware read path (`list_tables`) if tables matter

## Pairing with Other Tools
- `file_write`: save extracted text or a converted .md
- `pdf`: convert to PDF for distribution
- `spreadsheet`: move a document's tables into a sheet
- `grep`: search extracted text for a term
