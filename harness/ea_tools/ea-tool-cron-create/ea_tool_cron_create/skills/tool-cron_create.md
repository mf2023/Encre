---
name: tool-cron_create
description: "Schedule a prompt to run automatically on a recurring cron schedule. Use this for reminders, periodic reports, polling, or any task that must fire unattended at fixed times. Do NOT use this for one-shot delayed tasks if a deferred-task tool is available, for sub-minute scheduling, or for jobs requiring prior conversation context. Tips: use a standard 5-field cron expression in local time, e.g. '0 9 * * *' (daily 9am) or '*/5 * * * *' (every 5 min). Pitfalls: the agent has no prior context at fire time \u9225?include all needed details in the prompt; if the scheduler is not running, the job is validated but not activated."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# cron_create

Schedule a prompt to run automatically on a recurring cron schedule. Use this for reminders, periodic reports, polling, or any task that must fire unattended at fixed times. Do NOT use this for one-shot delayed tasks if a deferred-task tool is available, for sub-minute scheduling, or for jobs requiring prior conversation context. Tips: use a standard 5-field cron expression in local time, e.g. '0 9 * * *' (daily 9am) or '*/5 * * * *' (every 5 min). Pitfalls: the agent has no prior context at fire time 鈥?include all needed details in the prompt; if the scheduler is not running, the job is validated but not activated.
