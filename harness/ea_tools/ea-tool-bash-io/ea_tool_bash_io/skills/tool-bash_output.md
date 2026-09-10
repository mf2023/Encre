---
name: tool-bash_output
description: "Read new output from a backgrounded shell started via bash with run_in_background=true. Returns only bytes accumulated since the last read for that shell id; call repeatedly to stream progress. With wait=true, blocks up to wait_seconds for new output or for the shell to exit. WHEN to use: streaming progress from long-running builds, tests, or dev servers started in the background. WHEN NOT to use: for foreground commands (they return directly); for one-shot commands (use bash without run_in_background). TIP: Use wait=true for long-running builds/tests so you do not have to poll repeatedly. PITFALLS: polling in a tight loop with wait=false returns empty and burns tokens; output is incremental -- once read, it is not returned again on the next call."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# bash_output

Read new output from a backgrounded shell started via bash with run_in_background=true. Returns only bytes accumulated since the last read for that shell id; call repeatedly to stream progress. With wait=true, blocks up to wait_seconds for new output or for the shell to exit. WHEN to use: streaming progress from long-running builds, tests, or dev servers started in the background. WHEN NOT to use: for foreground commands (they return directly); for one-shot commands (use bash without run_in_background). TIP: Use wait=true for long-running builds/tests so you do not have to poll repeatedly. PITFALLS: polling in a tight loop with wait=false returns empty and burns tokens; output is incremental -- once read, it is not returned again on the next call.
