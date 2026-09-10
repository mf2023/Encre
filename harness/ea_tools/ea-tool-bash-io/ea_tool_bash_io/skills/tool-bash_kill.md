---
name: tool-bash_kill
description: "Stop a backgrounded shell started via bash(run_in_background=true). By default sends SIGTERM (or terminate on Windows). Pass force=true to escalate to SIGKILL / hard-terminate after a short grace period. WHEN to use: dev servers, watchers, or long-running builds that no longer need to run. WHEN NOT to use: for foreground commands (they block until done); for system services (use the service manager); for Docker containers (use docker stop). TIP: Try force=false first for a clean shutdown; escalate to force=true only if the shell ignores SIGTERM. PITFALLS: force=true skips cleanup hooks and may leave temp files behind; on Windows, child processes may survive a non-force kill."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# bash_kill

Stop a backgrounded shell started via bash(run_in_background=true). By default sends SIGTERM (or terminate on Windows). Pass force=true to escalate to SIGKILL / hard-terminate after a short grace period. WHEN to use: dev servers, watchers, or long-running builds that no longer need to run. WHEN NOT to use: for foreground commands (they block until done); for system services (use the service manager); for Docker containers (use docker stop). TIP: Try force=false first for a clean shutdown; escalate to force=true only if the shell ignores SIGTERM. PITFALLS: force=true skips cleanup hooks and may leave temp files behind; on Windows, child processes may survive a non-force kill.
