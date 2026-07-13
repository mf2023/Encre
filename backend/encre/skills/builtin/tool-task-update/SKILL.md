---
name: tool-task-update
description: Update task skill. task_id/status/result/error, change task status or record outcome
hidden: true
context: inline
---

## When to Use
- Mark a task completed/failed
- Record a task's result or error after it finishes
- Change a task's status manually

## When NOT to Use
- **Retrieve output** -> `task_output`
- **Create a task** -> `task_create`

## Key Parameters
- `task_id` (required): the task to update
- `status`: new status (e.g. completed/failed)
- `result`: the task's result on completion
- `error`: error description on failure

## Best Practices
- Update status as soon as a task finishes so `task_list` stays accurate
- Record result/error so it's retrievable

## Common Pitfalls
- **Marking completed without recording result** - setting status=completed but leaving result empty makes `task_output` return nothing; callers think the task produced nothing. Always set `result` (or `error`) with the status.
- **Overwriting a real result with a later error** - if a task produced output then hit a follow-up error, don't clobber the original result. Update status only, or append to the error field.
- **Forgetting to mark failed tasks** - leaving a dead task as "running" forever. If a task errored, set status=failed + error=... so `task_list` reflects reality.
- **Updating with a wrong task_id** - a guessed id updates the wrong task or silently creates a new entry. Confirm via `task_list`/`task_get` before updating.

## Pairing with Other Tools
- `task_create`: create the task first
- `task_list`: see current statuses
