---
name: tool-bash-list
description: List background shells skill. Enumerate running background shell ids and status
hidden: true
context: inline
---

## When to Use
- See which background shells are running
- Find the id of a shell before reading its output or killing it

## When NOT to Use
- **Run a command** -> `bash`
- **Read a shell's output** -> `bash_output` (needs the id this tool provides)

## Key Parameters
- (none) lists all background shells

## Best Practices
- Call this when you've lost track of which background shells are alive
- Use the returned ids with `bash_output`/`bash_kill`

## Common Pitfalls / Anti-patterns
- **Calling bash_list repeatedly instead of polling one shell**: once you have the id, use `bash_output` directly - re-listing every turn wastes a call and the id doesn't change while the shell lives
- **Assuming a shell is still alive**: a background shell may have exited since you last listed. If `bash_output` says not found, re-list to confirm before assuming a bug
- **Losing track and spawning duplicates**: forgetting you already have a dev-server shell running and starting another -> port conflict. List first before starting a long-running process
- **Assuming bash_list shows everything** - some background processes may not appear if they were started outside the tool. Cross-check with system-level tools if something seems missing.

## Pairing with Other Tools
- `bash_output`: read output by id
- `bash_kill`: stop by id
