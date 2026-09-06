---
name: tool-memory-profile
description: Memory profile skill. field/value/confidence, record structured profile facts about the user
hidden: true
context: inline
---

## When to Use
- Record a structured profile fact (user role, expertise, preferences)
- Store a confidence-tagged profile field for future personalization

## When NOT to Use
- **Free-form memory** -> `memory_create`
- **Read memories** -> `memory_read`/`memory_search`

## Key Parameters
- `field` (required): the profile field (e.g. role, expertise)
- `value` (required): the field's value
- `confidence`: how confident this fact is

## Best Practices
- Use for structured, reusable profile facts; use `memory_create` for free-form notes
- Tag confidence so future recall can weight it

## Common Pitfalls / Anti-patterns
- **Storing free-form notes as profile fields**: profile fields are structured facts (role, expertise, language). Free-form context belongs in `memory_create`
- **No confidence tag**: without `confidence`, future recall can't distinguish a firm fact from a guess. Tag uncertain facts low
- **Overwriting a profile field without checking the old value**: you may clobber a more-certain earlier value with a weaker one. Read the current value first if unsure
- **Inferring profile facts the user never stated**: recording "user is a junior dev" from one question is a guess dressed as fact. Only profile what the user told you or you verified

## Pairing with Other Tools
- `memory_search`: recall profile facts
- `memory_create`: free-form memories
