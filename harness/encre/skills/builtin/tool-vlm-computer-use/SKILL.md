---
name: tool-vlm-computer-use
description: VLM computer-use skill. goal/max_steps/template_name, vision-model-driven goal-driven automation
hidden: true
context: inline
---

## When to Use
- Goal-driven automation where a vision model figures out the steps from a high-level goal
- Open-ended GUI tasks without a fixed action sequence

## When NOT to Use
- **Deterministic step-by-step automation** -> `computer_use`/`desktop`/`browser`
- **A single known action** -> the specific tool

## Key Parameters
- `goal` (required): high-level goal description for the VLM to achieve
- `max_steps`: cap on autonomous steps
- `template_name`: optional action template

## Best Practices
- Set a sensible `max_steps` to bound autonomous execution
- Phrase `goal` clearly and concretely; the VLM drives from it

## Common Pitfalls / Anti-patterns
- **Using it for a known fixed sequence**: if you already know the steps, `computer_use`/`desktop`/`browser` are cheaper and more reliable - VLM autonomy pays a reasoning + vision cost per step
- **No step cap**: unbounded autonomy can loop or run away on a stuck goal. Always set `max_steps` to bound it
- **Vague goal**: "fix the app" gives the VLM nothing to verify against. Phrase concretely ("click login, enter user X, assert dashboard loads") so it knows when it's done
- **No verification of the end state**: the VLM reports success but may have stopped early or hit a wrong state. Check the final screenshot/result yourself before declaring done

## Pairing with Other Tools
- `computer_use`/`desktop`/`browser`: deterministic alternatives
- `image`: screenshot analysis
