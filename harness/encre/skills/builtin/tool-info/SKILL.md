---
name: tool-info
description: Info card skill. display/content/title/type, render a self-contained HTML/CSS/JS card in chat
hidden: true
context: inline
---

## When to Use
- Render a self-contained rich information card (HTML/CSS/JS) in the chat timeline
- Show a flight card, weather widget, delivery status, stock quote, or schedule visually
- Present structured/visual results instead of plain text

## When NOT to Use
- **Plain text answers** -> just answer in text; do not wrap trivia in a card
- **Charts from data** -> `data-viz` skill / charting tools
- **Editing files** -> this tool renders content, it does not write files
- **External resources / third-party scripts** -> payloads must be self-contained; external loads are at the user's risk

## Key Parameters
- `display` (required): base (render the HTML/CSS/JS card - default), code (show raw source), split (reserved)
- `content` (required): a single self-contained HTML document or fragment, with optional inline CSS and JS
- `title`: optional card title shown above the rendered content
- `type`: html (free-form rendering) or widget (reserved for future structured templates)

## Best Practices
- Keep the payload self-contained: inline CSS and JS, no external resources
- Use `display=base` for rendered cards; use `display=code` when the user wants to see the source
- Prefer semantic HTML and scoped inline styles to avoid clashing with the host UI
- Give the card a `title` so it is identifiable in the timeline
- Return the card as the final step after the data is ready; do not render partial/empty content

## Common Pitfalls / Anti-patterns
- **Wrapping trivial text in a card** -> use a card only when visual/structured presentation adds value
- **External scripts/stylesheets** -> they may be blocked or load unreliably; inline everything
- **Forgetting `display`** -> it is required; always set it (usually `base`)
- **Over-large payloads** -> keep cards focused; huge HTML floods the timeline

## Pairing with Other Tools
- `web_fetch` / `web_search`: gather the data before rendering it in a card
- `file_read`: read source to show via `display=code`
- `data-viz`: for charts, prefer charting tools over hand-rolled HTML
