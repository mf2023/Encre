---
name: tool-desktop
description: Desktop automation skill. action and many params, automate native OS UI without shell tools
hidden: true
context: inline
---

## When to Use
- Automate native desktop UI (click, type, find elements)
- Take screenshots of the desktop or an app
- Interact with OS-native controls (Windows UIA, accessibility tree)

## When NOT to Use
- **Browser automation** -> `browser`
- **Run a shell command** -> `bash`
- **Take a screenshot of a webpage** -> `browser`

## Key Parameters
- `action` (required): the desktop action (click, type, screenshot, find_element, etc.)
- `x`/`y`/`x2`/`y2`: coordinates (with `coord_space`)
- `text`/`key`/`keys`: input data
- `template`: image template for visual matching
- `confidence`: match threshold
- `name`/`control_type`: for accessibility-tree targeting
- `max_depth`/`max_nodes`: tree traversal limits

## Best Practices
- Prefer accessibility-tree targeting (`name`/`control_type`) over raw coordinates (more stable)
- Use screenshots to verify state before/after actions
- Set `confidence` for visual matching to avoid false hits

## Common Pitfalls / Anti-patterns
- **Hardcoded coordinates**: break on resolution/layout changes; prefer element-based targeting
- **No verification after action**: screenshot to confirm the action took effect
- **Deep tree traversal without limits**: can be slow; bound with max_depth/max_nodes
- **Blind wait without a timeout** - `wait` for a UI element that never appears hangs the turn. Always set a timeout on waits.
- **Screenshot blindness** - a screenshot confirms what is on screen; without it after an action, you are guessing the state. Screenshot after every destructive or navigational step.

## Pairing with Other Tools
- `browser`: web content
- `bash`: when a shell command is genuinely simpler
- `image`: analyze screenshots
