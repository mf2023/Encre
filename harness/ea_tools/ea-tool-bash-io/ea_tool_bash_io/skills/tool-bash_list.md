---
name: tool-bash_list
description: "List all backgrounded shells (running and exited) tracked in this session. Returns ids, commands, running flags, and exit codes. WHEN to use: before calling bash_output or bash_kill when you forgot the shell id; to check whether a background process is still running. WHEN NOT to use: for foreground commands (they return directly); for system-wide process listing (use bash with `ps` or `tasklist`). TIP: Call this first if you lost track of which background shells are active. PITFALLS: exited shells remain in the list until the session ends; shell ids are session-scoped and not portable across sessions."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# bash_list

List all backgrounded shells (running and exited) tracked in this session. Returns ids, commands, running flags, and exit codes. WHEN to use: before calling bash_output or bash_kill when you forgot the shell id; to check whether a background process is still running. WHEN NOT to use: for foreground commands (they return directly); for system-wide process listing (use bash with `ps` or `tasklist`). TIP: Call this first if you lost track of which background shells are active. PITFALLS: exited shells remain in the list until the session ends; shell ids are session-scoped and not portable across sessions.
