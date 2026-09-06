---
name: tool-question
description: User clarification skill. question/details/options/questions, ask the user when genuinely blocked
hidden: true
context: inline
---

## When to Use
- You're blocked on a decision only the user can make (genuinely ambiguous, not derivable)
- Confirm a destructive or hard-to-reverse action before proceeding
- Ask which of a few valid approaches the user prefers

## When NOT to Use
- **Derivable from context/code** -> figure it out yourself; don't punt to the user
- **Simple preference you can pick a sensible default for** -> proceed, mention it
- **Trivial clarification** -> make a reasonable choice and continue

## Key Parameters
- `question` (required): the question to ask
- `details`: extra context
- `options`: discrete choices (2-4) for the user to pick from
- `questions`: multiple questions in one call

## Best Practices
- Only ask when the answer truly blocks you and can't be derived
- Offer concrete `options` with a recommended one first
- Ask at most a few questions; batch them rather than serial single questions

## Common Pitfalls / Anti-patterns
- **Asking when you could decide**: wastes the user's time; pick a sensible default
- **Too many options or vague options**: keep to 2-4 concrete, mutually exclusive choices
- **Serial single questions**: batch related questions in one call
- **Asking what you could look up** - before asking the user anything, exhaust your tools (search, read, fetch). A question should be for what is truly private or unknowable.
- **Omitting default options** - if the user might want none of the listed choices, include "Other (custom)" so they can type a free answer instead of picking a wrong one.

## Pairing with Other Tools
- Use before destructive ops, after `grep`/`file_read` scoping confirms the ambiguity is real
