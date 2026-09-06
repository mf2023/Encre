---
name: tool-task-list
description: List tasks skill. status filter, enumerate background tasks and their statuses
hidden: true
context: inline
---

## When to Use
- See all background tasks and their current status
- Find task ids before getting details/output or stopping

## When NOT to Use
- **Get one task's details** -> `task_get`
- **Get a task's result** -> `task_output`

## Key Parameters
- `status`: filter by status (e.g. running/completed/failed)

## Best Practices
- Filter by status to focus on what's relevant (e.g. only running)
- Use returned ids with `task_get`/`task_output`/`task_stop`

## Common Pitfalls
- **Acting on a stale list** - between listing and acting, a task can complete or fail. Re-list (or `task_get`) right before `task_stop` if the decision hinges on current status.
- **Treating "no tasks" as a bug** - an empty list usually means no background tasks were spawned this session, not an error. If you expected tasks, check whether `task_create`/`agent` actually ran.
- **Ignoring the status column** - listing without checking status leads to stopping a completed task or waiting on a failed one. Filter or read status before acting on any task id.
- **Listing in a tight loop** - calling `task_list` every turn when no tasks changed wastes context. Only list when you've spawned, completed, or need to check on tasks.

## Pairing with Other Tools
- `task_get`: details by id
- `task_output`: result by id
- `task_stop`: cancel by id
