---
name: tool-task-output
description: Task output retrieval skill. task_id/block/timeout, get a background task's result
hidden: true
context: inline
---

## When to Use
- Retrieve the result of a completed or running background task
- Wait for a task to finish and get its output

## When NOT to Use
- **List tasks** -> `task_list`
- **Get task details/config** -> `task_get`

## Key Parameters
- `task_id` (required): the task whose output to retrieve
- `block`: block until the task produces output or finishes
- `timeout`: how long to block before returning (seconds)

## Best Practices
- Use `block` with `timeout` to wait for a task to finish rather than busy-polling
- For long tasks, poll with a reasonable timeout rather than blocking indefinitely

## Common Pitfalls / Anti-patterns
- **Busy-polling without block**: calling `task_output` in a tight loop burns turns. Use `block: true` with a `timeout` to wait efficiently
- **Wrong task_id**: a mismatched id returns nothing. Confirm the id via `task_list` first
- **Blocking indefinitely with no timeout**: a hung task that never finishes stalls the turn. Always set `timeout` when blocking
- **Treating partial output as final**: a still-running task returns whatever output it has so far, not the complete result. Check the task's status (via `task_get`/`task_list`) before treating output as done

## Pairing with Other Tools
- `task_list`/`task_get`: discover the id
- `task_stop`: stop after reading if done
