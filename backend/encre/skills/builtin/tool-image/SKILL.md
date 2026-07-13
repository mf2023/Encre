---
name: tool-image
description: Image processing skill. action/file_path/options, analyze/convert images without bare imagemagick
hidden: true
context: inline
---

## When to Use
- Analyze or inspect an image (dimensions, format, content)
- Convert or transform images (resize, format conversion)
- Extract metadata from images

## When NOT to Use
- **Run bare `identify`/`convert`/`tesseract` in bash** -> use this tool
- **Read an image to understand it visually** -> `file_read` with `as_image: true`
- **Take a screenshot** -> `desktop` or `browser`

## Key Parameters
- `action` (required): the image action (analyze, convert, extract, etc.)
- `file_path` (required): the image file
- `options`: action-specific options (size, format, etc.)

## Best Practices
- For visual understanding, `file_read` as_image is often better than metadata analysis
- Use this tool for transformations (resize, convert) and metadata extraction

## Common Pitfalls / Anti-patterns
- **Using bash imagemagick/tesseract**: this tool integrates parsing and safety; bare CLI in bash bypasses it and is brittle across installs
- **Analyzing metadata when you need to see the image**: dimensions/format tell you nothing about content. Use `file_read` with `as_image: true` to actually look at it
- **Converting in place without a copy**: overwriting the source destroys the original. Write to a new path unless you explicitly mean to replace
- **OCR on a low-res image**: tesseract on a small or noisy image returns garbage. Upscale / threshold first, or visually read it via `file_read` as_image

## Pairing with Other Tools
- `file_read`: view an image visually (as_image)
- `desktop`/`browser`: take screenshots
