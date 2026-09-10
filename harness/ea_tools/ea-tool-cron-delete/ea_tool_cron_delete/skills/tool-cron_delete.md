---
name: tool-cron_delete
description: "Cancel or delete a previously scheduled cron job by its ID so it stops firing. Use this when a scheduled task is no longer needed or was created by mistake. Do NOT use this to pause a job temporarily (reschedule with cron_create instead) or to inspect jobs (use cron_list). Tips: obtain the `job_id` from cron_list before deleting. Pitfalls: deletion cannot be undone \u9225?a deleted recurring job must be recreated with cron_create if needed again; deleting a non-existent job returns a 'not_found' status."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# cron_delete

Cancel or delete a previously scheduled cron job by its ID so it stops firing. Use this when a scheduled task is no longer needed or was created by mistake. Do NOT use this to pause a job temporarily (reschedule with cron_create instead) or to inspect jobs (use cron_list). Tips: obtain the `job_id` from cron_list before deleting. Pitfalls: deletion cannot be undone 鈥?a deleted recurring job must be recreated with cron_create if needed again; deleting a non-existent job returns a 'not_found' status.
