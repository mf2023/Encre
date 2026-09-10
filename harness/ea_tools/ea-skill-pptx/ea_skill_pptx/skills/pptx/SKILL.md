---
name: pptx
description: PowerPoint (.pptx) processing - read, extract text, inspect slides, create presentations, add slides, list slide structure
aliases: [powerpoint, slides]
when_to_use: ".pptx .ppt"
argument_hint: "[path to .pptx file or task description]"
user_invocable: true
hidden: true
auto_activate: true
context: inline
---

## PowerPoint (.pptx) Processing

You are processing a PowerPoint file: **{{args}}**

### When to Use
- Read or extract text from a `.pptx` (slide titles, bullet content, notes)
- Inspect slide structure (`list_slides`) before editing
- Create a new presentation from a title + slide list
- Add a slide to an existing deck
- Summarize or analyze the content of a slide deck

### When NOT to Use
- **Generate a slide deck image / visual mockup** -> use `image` or a rendering tool; `.pptx` editing is structural, not visual design
- **Word documents** -> use the `docx` skill
- **Spreadsheets** -> use the `spreadsheet` tool / `xlsx` skill
- **One-off text extraction** -> if you only need the text, extract it once; do not over-engineer with slide editing

### Processing Workflow
1. **Survey the deck** -> run `list_slides` (or an info/read pass) to get the slide count and titles before editing or summarizing.
2. **Choose the operation:**
   - Read content -> extract text (titles + bullets + notes)
   - Get structure -> `list_slides`
   - Create new -> build from a title + structured slides list
   - Append a slide -> `add_slide` with a slide type and content
3. **For "summarize this deck"** -> extract text from all slides, then summarize; do not summarize slide-by-slide in isolation.
4. **Verify edits** -> after `add_slide`, re-list slides to confirm the new slide is present and in the right position.
5. **Visual review** -> if layout matters, render the deck to images and look at the slides you changed.

### Tool Selection
- `presentation` tool (registered): `action: read` / `extract_text` / `info` / `create` / `add_slide` / `list_slides` - primary path for PowerPoint files
- `bash` + `python-pptx`: fallback only if the `presentation` tool is unavailable; it wraps the same library
- `file_read`: not useful for readable text; `.pptx` is a zip - use a pptx library
- `image` tool: convert/render slides to images for visual review after edits

### Best Practices
- When creating, pass a structured slides list (title + bullets per slide) rather than one giant content blob
- Use the right slide type: title slide, content slide, section header - do not make everything a blank slide
- Keep bullets concise; if a slide needs a table or chart, note it explicitly rather than cramming text
- After structural edits, re-list slides to confirm order and count

### Common Pitfalls
- **Using `file_read` on a `.pptx`** -> it is a zip; you will not see readable text - use a pptx library via `bash` or the `presentation` tool
- **Creating a deck with a single content blob** -> yields one overcrowded slide; structure into title + bullets per slide
- **Ignoring slide order** -> `add_slide` appends; if position matters, verify and reorder explicitly
- **Treating notes as slide content** -> speaker notes are separate from on-slide text; extract them deliberately if needed

### Pairing with Other Tools
- `bash` (python-pptx) - read/create/edit/list
- `image` - render slides to images for visual review
- `file_write` - save extracted text or a Markdown outline of the deck
- `pdf` - convert the deck to PDF for distribution
- `docx` - move slide content into a Word document when a deck should become a report
