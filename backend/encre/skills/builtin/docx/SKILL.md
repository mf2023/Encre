---
name: docx
description: Word document (.docx) processing - read, extract text, create, edit (add text/tables), convert, and inspect .docx files
aliases: [word, word-doc]
when_to_use: ".docx .doc"
argument_hint: "[path to .docx file or task description]"
user_invocable: true
hidden: true
auto_activate: true
context: inline
---

## Word Document (.docx) Processing

You are processing a Word document: **{{args}}**

### When to Use
- Read or extract text from a `.docx` file (paragraphs, headings, tables)
- Inspect a `.docx`'s structure (heading outline, table list) before editing
- Create a new Word document from content
- Add text or a table to an existing `.docx`
- Convert a `.docx` to another format (e.g. PDF, Markdown)

### When NOT to Use
- **Plain text / Markdown / code files** -> use `file_read` directly; do not invoke Word tooling
- **PDF files** -> use the `pdf` skill
- **Spreadsheets** -> use the `spreadsheet` tool / `xlsx` skill
- **Editing a single line** -> if the doc is plain text, `file_edit` is far simpler than a docx library

### Processing Workflow
1. **Understand the document first** -> run an info/read pass to get the heading outline and table list before making changes. This avoids blind edits.
2. **Choose the operation:**
   - Read content -> extract text (paragraphs + tables)
   - Get structure -> list headings / `list_tables`
   - Create new -> build from a title + content
   - Append content -> `add_text` or `add_table` (preserves existing content)
   - Convert -> `convert` source to target format
3. **Verify edits** -> after `add_text`/`add_table`, re-read the document to confirm the change landed where expected.
4. **Large documents** -> extract text in sections rather than dumping everything; summarize as you go.

### Tool Selection
- `document` tool (registered): `action: read` / `extract_text` / `info` / `create` / `add_text` / `add_table` / `list_tables` / `convert` - primary path for Word documents
- `bash` + `python-docx`: fallback only if the `document` tool is unavailable; it wraps the same library so capabilities match
- `file_read`: only useful for a quick raw-byte check; `.docx` is a zip, so plain `file_read` will not show readable text
- `file_write`: for saving extracted text or a Markdown version of the document

### Best Practices
- Preserve structure: when creating, use real headings (`Heading 1/2`) not just bold text, so the outline is navigable
- When adding tables, pass clean row data (list of lists); do not embed pre-formatted strings
- After any edit, re-read to confirm; docx edits can silently land in the wrong section
- For conversion to Markdown, extract text + table structure, then write out with `file_write`

### Common Pitfalls
- **Using `file_read` on a `.docx` and concluding it is unreadable** -> `.docx` is a zip archive; you must use a docx library (python-docx) via `bash` or the `document` tool
- **Overwriting instead of appending** -> `add_text` appends; recreating the file with `create` destroys existing content - choose deliberately
- **Treating old `.doc` (binary) like `.docx`** -> legacy `.doc` is a different format; convert it to `.docx` first or use an appropriate parser
- **Losing tables** -> plain text extraction may drop table structure; use the table-aware read path and re-emit as a table

### Pairing with Other Tools
- `bash` (python-docx) - read/create/edit/convert
- `file_write` - save extracted text or a converted Markdown/PDF
- `pdf` - if the end goal is a PDF, convert then hand off
- `spreadsheet` - if the document's tables are the real focus, move them into a spreadsheet
- `grep` - search across extracted text for a term
