---
name: tool-cron_list
description: "List all currently scheduled cron jobs with their IDs, names, schedule expression, and next fire time. Use this to review active schedules, find a `job_id` for cron_delete, or verify that a cron_create call succeeded. Do NOT use this to create or cancel jobs (use cron_create/cron_delete); and avoid it as a polling loop for firing jobs. Tips: returns an empty list when no jobs are scheduled; each entry includes id, name, cron, and next_fire fields. Pitfalls: returns an empty list (not an error) when the scheduler is not available."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# cron_list

List all currently scheduled cron jobs with their IDs, names, schedule expression, and next fire time. Use this to review active schedules, find a `job_id` for cron_delete, or verify that a cron_create call succeeded. Do NOT use this to create or cancel jobs (use cron_create/cron_delete); and avoid it as a polling loop for firing jobs. Tips: returns an empty list when no jobs are scheduled; each entry includes id, name, cron, and next_fire fields. Pitfalls: returns an empty list (not an error) when the scheduler is not available.
