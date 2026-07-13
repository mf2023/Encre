---
name: tool-presentation
description: PowerPoint skill. action/file_path/title/slides/slide_type/content, read/create/edit .pptx without manual python-pptx
hidden: true
context: inline
---

## When to Use
- Read, extract text, or inspect a PowerPoint (.pptx) deck
- Create a new presentation from a title + slides list
- Add a slide to an existing deck, or list slides

## When NOT to Use
- **Visual slide design / pixel editing** -> this tool is structural; use image tools for visuals
- **Word documents (.docx)** -> `document` tool
- **Spreadsheets (.xlsx)** -> `spreadsheet` tool
- **One-off text extraction** -> extract once; do not over-engineer with slide edits

## Key Parameters
- `action` (required): one of read, extract_text, info, create, add_slide, list_slides
- `file_path`: path to the .pptx (required except for `create`)
- `title`: presentation title for `create` (also used as default filename)
- `slides`: list of slide definitions for `create` (strings or `{title, content}` dicts)
- `slide_type`: layout for `add_slide` - blank, title, content, two_content, section_header
- `content`: slide content for `add_slide` (first line = title, rest = body)

## Best Practices
- Run `list_slides` before editing to see slide count, titles, and layouts
- Pass a structured `slides` list (title + bullets per slide), not one giant content blob
- Match the slide_type to intent: title slide for the cover, section_header for dividers
- After `add_slide`, re-list slides to confirm order and position

## Common Pitfalls / Anti-patterns
- **Using `file_read` on a .pptx** -> it is a zip archive; use this tool
- **Creating a deck with a single content blob** -> yields one overcrowded slide; structure per slide
- **Assuming slide position** -> `add_slide` appends; verify order explicitly if position matters
- **Confusing speaker notes with on-slide text** -> notes are separate; extract them deliberately if needed

## Pairing with Other Tools
- `image`: render slides to images for visual review
- `file_write`: save extracted text or a Markdown outline
- `pdf`: convert the deck to PDF for distribution
- `document`: turn slide content into a Word report
