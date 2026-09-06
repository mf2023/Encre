---
name: tool-pdf
description: PDF skill. action/file_path/pages, read/extract/merge PDFs without bare pdftotext
hidden: true
context: inline
---

## When to Use
- Read or extract text from a PDF
- Get PDF metadata or page count
- Work with PDF content (search, extract sections)

## When NOT to Use
- **Run bare `pdftotext`/`pdfinfo` in bash** -> use this tool
- **Read a regular text file** -> `file_read`
- **Read a scanned image PDF as image** -> `file_read` with `as_image: true`

## Key Parameters
- `action` (required): the PDF action (extract, info, etc.)
- `file_path` (required): the PDF file path
- `pages`: page range to process (e.g. "1-5")

## Best Practices
- Use `pages` to limit scope on large PDFs; don't process the whole document blindly
- For scanned/image PDFs, `file_read` with `as_image` may extract more than text extraction

## Common Pitfalls / Anti-patterns
- **Processing a huge PDF without a pages limit**: a 200-page PDF floods context and stalls. Scope with `pages` (e.g. "1-5") and iterate
- **Expecting text from a scanned PDF**: text extraction returns empty/garbage for image-only scans. Use `file_read` with `as_image: true` to read it visually
- **Off-by-one page numbers**: PDF pages are 1-indexed and the range is inclusive. "0-5" or "1-4" when you mean pages 1 to 5 returns the wrong slice
- **Assuming extraction preserves layout**: tables and columns often collapse into a single garbled stream. If structure matters, render the page as an image and read it

## Pairing with Other Tools
- `file_read`: read PDFs as images (for scanned/visual content)
- `file_write`: persist extracted text
