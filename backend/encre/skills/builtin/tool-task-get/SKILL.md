---
name: tool-task-get
description: Task details skill. task_id, fetch a single async task's full details
hidden: true
context: inline
---

## When to Use
- Inspect a single background task's details (config, status, prompt)
- Check one specific task by id

## When NOT to Use
- **List all tasks** -> `task_list`
- **Get output/result** -> `task_output`

## Key Parameters
- `task_id` (required): the task to inspect

## Best Practices
- Use when you know the id and want full details, not just status
- `task_list` first if you're unsure of the id

## Common Pitfalls
- **Guessing the id** - inventing a task_id instead of getting it from `task_list` returns nothing or the wrong task. Always list first when the id isn't from this session.
- **Confusing task_get with task_output** - `task_get` returns config/status; `task_output` returns the result/output. To see what the task *produced*, use `task_output`, not this.
- **Treating a fetched status as live** - the status is a snapshot at fetch time; a running task can finish or fail right after. Re-fetch before acting on a status-sensitive decision (like stopping).
- **Acting on a completed task's stale config** - a completed task's config is historical, not the current state. Don't use it to infer what's running now.

## Pairing with Other Tools
- `task_list`: discover ids
- `task_output`: get the result
