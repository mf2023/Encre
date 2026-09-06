---
name: tool-git
description: Git operations skill. command/repo_path/args, when to use git tool vs bash, destructive-op caution
hidden: true
context: inline
---

## When to Use
- Version-control operations: status, diff, log, add, commit, branch
- Inspect history: blame, log, show
- Stage and commit changes

## When NOT to Use
- **Run arbitrary shell git** -> use this tool, not `bash` with git commands
- **Search code content** -> `grep`
- **Find changed files** -> this tool's `status`/`diff`, not bash
- **Edit files** -> `file_edit`/`file_write`

## Key Parameters
- `command` (required): git subcommand, e.g. `status`, `diff`, `log`, `add`, `commit`, `branch`, `checkout`
- `repo_path`: repository path, defaults to workspace root
- `args`: subcommand arguments/options, e.g. `["--oneline", "-10"]` for log

## Best Practices
- Before destructive ops (reset/checkout/clean), inspect `status` and `diff` first
- Commit with a clear message; stage specific files rather than blanket `add -A`
- For understanding history use `log --oneline -N` then `show <sha>`

## Common Pitfalls / Anti-patterns
- **Hard reset / force push / clean without checking**: destructive, can lose work; inspect first
- **Blanket `git add -A`**: may stage unintended files (secrets, build artifacts); stage specific files
- **Committing secrets**: if a filename looks innocuous but holds secrets, check content before committing
- **Using bash for git**: use this tool; it integrates with permission/safety checks

## Pairing with Other Tools
- `file_edit`/`file_write`: make changes, then git to commit
- `apply_patch`: structured patches, then git to commit
- `grep`/`glob`: inspect files before staging
