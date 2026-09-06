---
name: tool-bash-kill
description: Stop background shell skill. id/force, terminate runaway background processes
hidden: true
context: inline
---

## When to Use
- Stop a background shell that's done its job or gone wrong
- Kill a runaway process started with `bash` `run_in_background: true`

## When NOT to Use
- **Read output first** -> `bash_output` (check final output before killing)
- **List shells to find the id** -> `bash_list`

## Key Parameters
- `id` (required): background shell id to terminate
- `force`: force-kill if a graceful stop doesn't work

## Best Practices
- `bash_output` to grab any remaining output before killing
- Try graceful stop first; use `force` only if it hangs

## Common Pitfalls / Anti-patterns
- **Killing before reading output**: the shell's final output is lost once killed. Always `bash_output` first if you need the result
- **Wrong id**: killing the wrong shell (e.g. a dev server you still need). Confirm the id via `bash_list` before killing
- **Jumping straight to force**: `force: true` skips graceful shutdown and may leave child processes orphaned. Try graceful first; escalate to `force` only if it hangs
- **Killing without checking what the shell is doing** - the shell may be running a build or server you still need. `bash_list` shows status; confirm before killing.

## Pairing with Other Tools
- `bash_output`: read final output before kill
- `bash_list`: confirm the id
