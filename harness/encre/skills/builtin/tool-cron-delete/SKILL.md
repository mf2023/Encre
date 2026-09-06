---
name: tool-cron-delete
description: Remove cron job skill. job_id, cancel a scheduled recurring or one-shot task
hidden: true
context: inline
---

## When to Use
- Cancel a scheduled job that's no longer needed
- Stop a recurring task from firing again

## When NOT to Use
- **List jobs first** -> `cron_list` (to find the job_id)
- **Create a job** -> `cron_create`

## Key Parameters
- `job_id` (required): id of the cron job to delete (from `cron_create` or `cron_list`)

## Best Practices
- `cron_list` to confirm the job_id before deleting
- Delete jobs you no longer need to keep the schedule clean

## Common Pitfalls
- **Deleting without confirming** - calling `cron_delete` with an id you remembered rather than one from `cron_list` risks canceling the wrong recurring job. List first.
- **Deleting a one-shot that already fired** - one-shot jobs are removed after firing, so the id may already be gone. If `cron_list` doesn't show it, there's nothing to delete.
- **Deleting instead of fixing the schedule** - if the job fires at the wrong time, deleting and recreating loses history. Consider whether `cron_delete` + `cron_create` is needed, or the job just needs adjusting.
- **Canceling a job someone else depends on** - a recurring job may back another workflow. Confirm it's truly unwanted before deleting, not just mis-timed.

## Pairing with Other Tools
- `cron_list`: discover job_ids
- `cron_create`: schedule a replacement if needed
