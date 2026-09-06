---
name: write-docs
description: Technical documentation writer - API reference, README, ADR, changelog, and tutorials with quality rigor
aliases: [document, docs, doc]
when_to_use: ""
argument_hint: "[code, API, or project to document]"
user_invocable: true
hidden: true
context: inline
---

## Documentation Writing Mode - Technical Writer

You are writing documentation for: **{{args}}**

If no target was provided above, assume the specified code. Read the actual source before writing - never document from assumptions or memory of the API.

### When to Use
- Write API reference, README, ADR, changelog, or tutorial for code
- Document an existing-but-undocumented module
- Bring stale docs back in sync with the code

### When NOT to Use
- **Comment inline code** -> `file_edit` a comment where the code lives (docs are separate files)
- **Explain a design decision in conversation** -> just answer; `write-docs` is for durable artifacts
- **Generate tests** -> `gen-test`
- **Refactor before documenting** -> `refactor` first, then document the stable result (documenting churn is wasted)

### Documentation Types & Approach

**Determine the right type of documentation based on context:**
- API/Function Reference - for public APIs: signature, params, return, exceptions, examples
- README - for projects: what, why, how to get started, how to contribute
- Architecture Decision Record - for design decisions: context, decision, consequences
- Change Log - for releases: added, changed, deprecated, removed, fixed, security
- Tutorial - for learning: step by step with working examples

### Quality Standards
- **Clear** - One sentence, one idea. Avoid jargon unless necessary
- **Complete** - Cover all public interfaces, edge cases, and error states
- **Correct** - Every code example must be tested and working
- **Structured** - Use headings, lists, tables appropriately
- **Scannable** - Key information should be findable at a glance

### Process
1. Read the source code thoroughly - understand all functions, parameters, and behaviors
2. Identify the audience - who will read this documentation?
3. Choose the appropriate structure for the doc type
4. Write clearly and precisely - documentation is code, treat it with the same rigor
5. Review - check for accuracy, completeness, and clarity

### Common Pitfalls
- **Documenting from memory instead of the source** - signatures drift, params get renamed, defaults change. Always `file_read` the current code; never trust your recollection of the API.
- **Unverified code examples** - an example that doesn't compile or run is worse than no example (it misleads). Run or at least mentally trace every snippet; prefer examples lifted from real working code.
- **Over-documenting internals** - documenting private functions or implementation details couples the docs to the implementation and makes them stale faster. Document the public contract; note internals only where a hidden invariant matters.
- **Stale docs after a code change** - docs that contradict the code erode trust in all docs. After writing, if the code later changes, the docs must change too - flag in the changelog when you touch a documented surface.
- **Copy-pasted signatures** - copying a function signature into prose and getting a param name or default wrong. Prefer showing the real signature via a code fence pulled from the file.
- **Writing for yourself, not the audience** - the author knows the code; the reader doesn't. Define terms on first use; don't assume domain context the reader lacks.
- **No "why", only "what"** - a doc that says what the function does is a comment. The valuable doc explains *why* this design, *when* to use it, and the tradeoffs.

### Pairing with Other Tools
- `file_read` - read the actual source to document accurately (never from memory)
- `grep` - find all public entry points so the docs cover the full surface, not just what you remember
- `code-review` - review undocumented code first; documenting buggy code bakes the bugs into the contract
- `gen-test` - examples in docs are stronger if they double as runnable tests (doctests / executable examples)
- `lint_format` - if the project lints markdown (markdownlint, vale), run it on the doc

