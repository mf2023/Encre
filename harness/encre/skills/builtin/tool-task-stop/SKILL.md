---
name: tool-task-stop
description: Stop task skill. task_id, cancel a running background task
hidden: true
context: inline
---

## When to Use
- Cancel a running background task that's no longer needed or stuck
- Abort a task gone wrong

## When NOT to Use
- **Get its output first** -> `task_output` (grab result before stopping)
- **Just list tasks** -> `task_list`

## Key Parameters
- `task_id` (required): the task to stop

## Best Practices
- `task_output` to retrieve any useful result before stopping
- Stop tasks that are stuck or redundant to free resources

## Common Pitfalls / Anti-patterns
- **Stopping before reading output**: the task's result is lost once stopped. `task_output` first if you need anything it produced
- **Wrong id**: stopping the wrong task kills a job you still need. Confirm via `task_list` first
- **Stopping a task that's about to finish**: if it's nearly done, waiting beats killing and re-running. Check status first; only stop if stuck or truly unneeded
- **Stop does not clean sub-processes** - stopping a task kills the task record, but sub-processes it spawned may continue running. Track and clean up child processes separately.

## Pairing with Other Tools
- `task_output`: read result before stop
- `task_list`: confirm id
