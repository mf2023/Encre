---
name: tool-cron-list
description: List cron jobs skill. Enumerate scheduled recurring and one-shot tasks
hidden: true
context: inline
---

## When to Use
- See all scheduled cron jobs (recurring and one-shot)
- Find a job_id before deleting or inspecting

## When NOT to Use
- **Create a job** -> `cron_create`
- **Delete a job** -> `cron_delete` (needs the id this returns)

## Key Parameters
- (none) lists all scheduled jobs

## Best Practices
- Call this before `cron_delete` to confirm the job_id
- Review periodically; recurring jobs auto-expire after 7 days

## Common Pitfalls
- **Deleting by a guessed job_id** - cron ids are opaque; always `cron_list` first and copy the exact id before `cron_delete`, or you may cancel the wrong job.
- **Assuming a job still exists** - a one-shot job is deleted after it fires; a recurring job auto-expires after 7 days. If `cron_list` doesn't show it, it's already gone - no need to delete.
- **Acting on a stale list** - between listing and deleting, a job can fire (one-shot) or expire. Re-list right before `cron_delete` if the id's existence matters.
- **Missing jobs that fire soon** - the list shows schedule times, not "fires next" warnings. A job due in seconds can fire before you finish acting; check the next-fire time if timing is critical.

## Pairing with Other Tools
- `cron_delete`: remove a job by id
- `cron_create`: add a new job
