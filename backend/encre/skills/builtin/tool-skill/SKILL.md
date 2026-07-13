---
name: tool-skill
description: Skill activation tool. name/args, activate a domain skill (travel-flights, pdf, data-viz) by name to inject its guidance
hidden: true
context: inline
---

## When to Use
- Activate a domain skill whose purpose matches the user's request (e.g. `travel-flights` for flight search, `pdf` for PDF processing, `data-viz` for charting)
- Bring a skill's detailed guidance into the conversation when you decide it fits - no need to wait for the user to type `/name`
- Resolve a skill by its alias when you only remember the short name

## When NOT to Use
- **Discovering tools** (not skills) -> `find_tool`
- **Activating a skill the user already typed as `/name`** -> the system auto-activates it; do not double-activate
- **Browsing the skill catalogue** -> read the **Skills** section of the system prompt; do not call this tool just to list names

## Key Parameters
- `name` (required): skill name (e.g. `travel-flights`, `pdf`) or an alias from the catalogue
- `args`: optional argument string forwarded to the skill (e.g. the user's request context)

## Best Practices
- Pick the skill whose purpose matches the request - consult the **Skills** catalogue for exact names and purposes
- Activate proactively when the request clearly fits a skill (e.g. "find me flights" -> `travel-flights`), rather than answering from scratch
- Aliases work: `flights` resolves to `travel-flights`; you do not need the exact name
- Activate once; the guidance persists into subsequent turns - do not re-activate the same skill each turn

## Common Pitfalls / Anti-patterns
- **Guessing a name not in the catalogue** -> returns an error; check the catalogue for exact names/aliases first
- **Re-activating every turn** -> the skill body is cached after the first activation; extra calls are wasted
- **Activating a skill that does not fit** -> pick by purpose match, not by name familiarity
- **Calling this just to list skills** -> read the catalogue in the system prompt instead

## Pairing with Other Tools
- `find_tool`: discover tools (capabilities), while this activates skills (domain guidance)
- `web_search` / `web_fetch`: the activated skill typically directs you to these for data
- `info`: render the skill's results as a rich card
