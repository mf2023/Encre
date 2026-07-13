---
name: tool-apply-patch
description: Structured patch skill. patch/root/dry_run, multi-file diffs, when to use vs file_edit/file_write
hidden: true
context: inline
---

## When to Use
- Apply a structured diff across one or more files
- Multi-file changes expressed as a single patch
- Apply a standard unified diff

## When NOT to Use
- **Single small edit in one file** -> `file_edit` (simpler)
- **Whole-file rewrite** -> `file_write`
- **Create a new file** -> `file_write`

## Key Parameters
- `patch` (required): the diff/patch content in unified diff format
- `root`: repo root the patch paths are relative to
- `dry_run`: preview the patch result without writing

## Best Practices
- Use `dry_run` first to verify the patch applies cleanly
- Ensure patch context lines match the file exactly (whitespace included)
- For cross-file changes, one apply_patch is cleaner than many file_edit calls

## Common Pitfalls / Anti-patterns
- **Context lines mismatch**: the patch won't apply if surrounding context doesn't match exactly
- **Using apply_patch for a tiny single edit**: `file_edit` is simpler for one spot
- **Skipping dry_run**: a malformed patch can partially apply; preview first
- **Wrong root**: paths must be relative to `root`; mismatched root fails

## Pairing with Other Tools
- `file_edit`: single small edits
- `file_write`: whole-file replacement
- `git`: after applying, commit the change
- `test_run`/`lint_format`: verify after applying
