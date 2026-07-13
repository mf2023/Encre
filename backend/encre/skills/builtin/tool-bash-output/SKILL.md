---
name: tool-bash-output
description: Background shell output retrieval skill. Read output of run_in_background shells, id/wait params
hidden: true
context: inline
---

## When to Use
- Retrieve output from a shell started with `bash` `run_in_background: true`
- Poll a long-running command's progress
- Check whether a background command finished

## When NOT to Use
- **Run a quick foreground command** -> `bash` directly (synchronous)
- **List background shells** -> `bash_list`
- **Kill a background shell** -> `bash_kill`

## Key Parameters
- `id` (required): background shell id (from the bash call that started it)
- `wait`: block until the shell produces new output or finishes
- `wait_seconds`: how long to wait for new output before returning

## Best Practices
- Use `wait` with `wait_seconds` to avoid busy-polling; the tool returns when output arrives or the timeout hits
- For dev servers / watchers, poll periodically to check for errors in output

## Common Pitfalls / Anti-patterns
- **Busy-polling without wait**: burns turns; use `wait` + `wait_seconds`
- **Wrong id**: the id comes from the bash call that started the background shell; mismatched id returns nothing
- **Expecting full output every time**: output is incremental; prior output may already have been consumed
- **Expecting output from a shell that is still running** - a long-running process may not have produced complete output yet. Combine with `bash_list` to check the shell is done before reading.
- **Reading the wrong shell output** - if you spawned multiple background shells, the ids are easy to cross. `bash_list` to confirm the id before reading output.

## Pairing with Other Tools
- `bash`: start the background shell first
- `bash_list`: discover shell ids
- `bash_kill`: stop a runaway background shell
