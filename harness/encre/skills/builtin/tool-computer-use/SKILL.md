---
name: tool-computer-use
description: Computer-use skill. action/target and rich action set, model-driven OS/browser automation
hidden: true
context: inline
---

## When to Use
- Model-driven computer use (the model decides actions from screenshots)
- Multi-step GUI automation that adapts to what's on screen
- Actions spanning OS and browser that need visual reasoning

## When NOT to Use
- **Deterministic browser automation** -> `browser` (faster, no vision cost)
- **Deterministic desktop clicks** -> `desktop`
- **A single shell command** -> `bash`

## Key Parameters
- `action` (required): rich action set (click, type, scroll, screenshot, key, etc.)
- `target`/`selector`/`x`/`y`: where to act
- `text`/`key`/`keys`: input data
- `coord_space`: coordinate system
- `expect_change`/`timeout_ms`: wait-for-change controls
- `actions`/`steps`: batch action sequences
- `dry_run`: preview without executing

## Best Practices
- Use for adaptive, vision-driven flows where steps depend on screen state
- Prefer `browser`/`desktop` for deterministic flows (cheaper)
- Use `expect_change`/`timeout_ms` to wait for UI transitions

## Common Pitfalls / Anti-patterns
- **Using computer_use for a fixed click sequence**: if the steps don't depend on what's on screen, `desktop`/`browser` is cheaper and deterministic - computer_use pays a vision cost per step
- **No verification screenshots**: a click can miss or hit the wrong element. Screenshot between steps to confirm state, especially after navigation or waits
- **Acting on stale screenshots**: the screen changed since you last captured. Re-screenshot before a precise click; coordinates from an old frame miss
- **Blind retries on failure**: a click that doesn't work usually means the target moved/changed. Re-screenshot and re-locate rather than clicking the same coordinates harder
- **No expect_change on async UI**: after a click that triggers a load, acting immediately hits the old page. Set `expect_change`/`timeout_ms` to wait for the transition

## Pairing with Other Tools
- `browser`/`desktop`: deterministic alternatives
- `image`: analyze screenshots
