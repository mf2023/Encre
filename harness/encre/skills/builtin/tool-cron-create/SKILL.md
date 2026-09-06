---
name: tool-cron-create
description: Scheduled task skill. cron/prompt/name/recurring, schedule recurring or one-shot prompts
hidden: true
context: inline
---

## When to Use
- Schedule a prompt to run on a recurring schedule (e.g. check the deploy every 5 minutes)
- Fire a one-shot reminder/prompt at a future time
- Run a task periodically without a live agent watching

## When NOT to Use
- **Run something once now** -> `bash` or the relevant tool directly
- **Background async task** -> `task_create` (runs once, not scheduled)
- **Poll a background shell** -> `bash_output`

## Key Parameters
- `cron` (required): standard 5-field cron expression in local time (min hour DoM month DoW)
- `prompt` (required): the prompt to enqueue when the job fires
- `name`: optional label for the job
- `recurring`: true for repeating, false for one-shot (auto-deletes after firing)

## Best Practices
- For recurring jobs, pass the same prompt each fire so the loop stays coherent
- Pick off-round minutes (e.g. `7 * * * *` not `0 * * * *`) to avoid fleet-wide synchronization
- One-shot tasks: pin the minute/hour/day/month explicitly
- Recurring jobs auto-expire after 7 days; mention this to the user

## Common Pitfalls / Anti-patterns
- **Using `0`/`30` minute marks unnecessarily**: causes fleet synchronization; pick an off-minute
- **Forgetting recurring vs one-shot**: a one-shot deletes itself; a recurring fires until deleted
- **Vague prompt**: the fired prompt should be self-contained; the loop can't ask follow-ups
- **Creating with no mechanism to delete** - if the job runs away, you need its id to delete it. Store the returned id or list it immediately after creation.
- **Not verifying the prompt fires correctly** - the first fire happens at the cron time, not immediately. If the prompt has a syntax issue, you won't know for minutes/hours. Test the command standalone first.

## Pairing with Other Tools
- `cron_list`: see scheduled jobs
- `cron_delete`: remove a job
