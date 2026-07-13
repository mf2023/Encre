---
name: tool-lint-format
description: Lint and format skill. workspace/linter/mode/paths/max_duration, check and fix style without bare bash
hidden: true
context: inline
---

## When to Use
- Lint or format code after edits (ruff, eslint, prettier, clippy)
- Check style/typing issues before committing
- Auto-fix formatting issues

## When NOT to Use
- **Run bare `ruff`/`eslint`/`prettier` in bash** -> use this tool; it integrates with the project config
- **Run tests** -> `test_run`
- **Type-check only** -> some projects use this tool's lint mode; otherwise bash for the type checker

## Key Parameters
- `workspace`: project root, defaults to current workspace
- `linter`: force a specific linter (auto-detected if omitted)
- `mode`: e.g. check (report only) vs fix (apply fixes)
- `paths`: restrict to specific files/dirs
- `max_duration`: cap runtime in seconds

## Best Practices
- After editing, run lint on the changed files (narrow `paths`) for fast feedback
- Use `mode: check` to see issues, then `mode: fix` to auto-fix where safe
- Set `max_duration` for large codebases

## Common Pitfalls / Anti-patterns
- **Running lint on the whole repo for every change**: slow; scope to changed paths
- **Using bash for lint/format**: use this tool for proper config detection and result parsing
- **Applying fixes blindly**: review what `fix` mode changes; some fixes can alter behavior
- **Auto-fixing without reviewing** - `fix: true` changes files silently; some lint fixes alter runtime behavior (e.g. changing == to is). Review the diff before committing.
- **Linting generated files** - generated code (compiled, bundled, auto-gen) fails lint for style it did not write. Exclude non-source directories.

## Pairing with Other Tools
- `file_edit`: fix lint findings, then re-lint
- `test_run`: lint + test together for full verification
