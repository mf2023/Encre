---
name: tool-task_update
description: "Update the status and/or result/error of an existing task."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# task_update

Update the status and/or result/error of an existing task.

WHEN to use: a sub-agent or workflow has produced a result to record; a task needs to move from 'running' to 'completed' or 'failed'.
WHEN NOT to use: to stop a running task at the user's request use task_stop (it sets the cancelled state with a clear reason); to read task state use task_get/task_output.
TIPS: set 'result' when transitioning to 'completed'; set 'error' when transitioning to 'failed' so callers can diagnose the failure.
PITFALLS: this is a low-level mutation -- prefer task_stop for cancellation since it guards against double-stopping.
