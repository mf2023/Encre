---
name: pdf
description: PDF document processing - extract text, inspect metadata, render pages for visual understanding, handle large and scanned PDFs
aliases: [pdf-doc, pdf-reader]
when_to_use: ".pdf"
argument_hint: "[path to PDF file or task description]"
user_invocable: true
hidden: true
auto_activate: true
context: inline
---

## PDF Document Processing

You are processing a PDF file: **{{args}}**

### When to Use
- Extract text content from a PDF for analysis, search, or quoting
- Inspect PDF metadata (page count, title, author) before deciding how to process it
- Visually understand a PDF whose meaning depends on layout, charts, or diagrams
- Handle a scanned PDF where text extraction returns little/no content

### When NOT to Use
- **Edit a PDF** -> PDF tools here are read-only; for edits use `bash` with a library (pypdf/reportlab) or tell the user the limitation
- **Pure image OCR** -> if the file is an image, not a PDF, use the `image` tool with `action: ocr`
- **Read a single page as an image for a quick look** -> `file_read` with `as_image` on the rendered page is lighter than full extraction

### Processing Workflow
1. **Assess scale first** -> call `pdf` with `action: metadata` to learn page count and size before any heavy extraction. This prevents blowing the context budget on a 500-page document.
2. **Choose the extraction path:**
   - Need the text? -> `pdf` with `action: extract_text` (preserves reading order)
   - Need to understand layout/charts/scanned content? -> render the relevant page(s) to image and read visually (see Tool Selection)
   - Need a specific page? -> extract text first to locate it, then render only that page
3. **Handle scanned PDFs** -> if `extract_text` returns empty or garbled text, the PDF is image-based: render pages to images and OCR them with the `image` tool.
4. **Large PDFs** -> never extract the whole document. Use `metadata` to size it, then extract in page ranges or render only the pages the user asked about.
5. **Verify** -> quote page numbers back to the user so they can trust the extraction.

### Tool Selection
- `pdf` tool (registered): `action: metadata` / `extract_text` / `read` - primary path for text and metadata
- `image` tool: `action: ocr` - for scanned/image-based PDF pages rendered to images
- `file_read` with `as_image`: render a page or two for a quick visual check
- `bash` + `pypdf`/`pdfplumber`/`pdftotext`: fallback when the `pdf` tool lacks a capability (e.g. per-page text, form fields, merging)

### Best Practices
- Always call `metadata` before `extract_text` on unknown files - knowing the page count changes your strategy
- For "summarize this PDF" tasks, extract text first; only fall back to visual rendering if extraction is poor
- Keep page references in your answer (`p. 12`) so the user can verify
- When the user asks about a specific section, locate it via text search before rendering

### Common Pitfalls
- **Extracting a huge PDF wholesale** -> floods context; use `metadata` first and extract by range
- **Treating an empty `extract_text` result as "no content"** -> it usually means the PDF is scanned; switch to image rendering + OCR
- **Ignoring layout** -> tables and multi-column PDFs may extract in wrong reading order; render visually to confirm
- **Re-rendering pages already read** -> cache what you have seen; don't re-extract the same page

### Pairing with Other Tools
- `image` (ocr) - OCR scanned PDF pages
- `file_read` (as_image) - quick visual check of a page
- `grep` - search across extracted text for a specific term
- `file_write` - save extracted text or a summary to a new file
- `spreadsheet` - if the PDF contains tabular data, extract text then restructure into a sheet
