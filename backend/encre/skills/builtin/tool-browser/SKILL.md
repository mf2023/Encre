---
name: tool-browser
description: Browser automation skill. action/url/selector and many action params, automate web without curl
hidden: true
context: inline
---

## When to Use
- Browser automation: navigate, click, fill forms, extract content
- Interact with pages that need JavaScript rendering
- Screenshot or scrape dynamic content

## When NOT to Use
- **Fetch a static URL's content** -> `web_fetch` (lighter, no browser overhead)
- **Call a REST/GraphQL API** -> `rest_client`
- **Desktop automation outside the browser** -> `desktop`

## Key Parameters
- `action` (required): the browser action (navigate, click, fill, screenshot, extract, etc.)
- `url`: for navigate actions
- `selector`: CSS/XPath selector to target an element
- `text`/`value`/`key`/`keys`: input data for fill/press actions
- `timeout`: per-action timeout
- `full_page`: screenshot scope
- `fields`: form field batch
- Many action-specific params (x/y coords, accept/prompt_text for dialogs, etc.)

## Best Practices
- Prefer `web_fetch` for static content; use browser only when JS rendering or interaction is needed
- Use specific selectors; prefer id/role over brittle CSS paths
- Set a `timeout` for slow pages

## Common Pitfalls / Anti-patterns
- **Using browser for a simple fetch**: `web_fetch` is faster and lighter
- **Brittle selectors**: deep CSS paths break on layout changes; prefer stable selectors
- **No timeout on slow pages**: hangs the turn
- **Not waiting for page load** - clicking a link then immediately reading the page gets the old page. Add a wait step (sleep/screenshot) after navigation.
- **Assuming selectors work in iframes** - most `browser` selectors operate on the main page, not iframes. Switch context or use a different approach for nested frames.

## Pairing with Other Tools
- `web_fetch`: static content
- `rest_client`: API calls
- `desktop`: non-browser UI automation
