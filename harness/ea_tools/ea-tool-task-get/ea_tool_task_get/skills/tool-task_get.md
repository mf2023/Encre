---
name: tool-task_get
description: "Get the details (name, type, status, description, result, error, parent) of a single task by its ID."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# task_get

Get the details (name, type, status, description, result, error, parent) of a single task by its ID.

WHEN to use: you have a task ID from task_create or task_list and want a one-shot snapshot of its current state and any stored result/error.
WHEN NOT to use: to wait for a running task to finish, use task_output (it can block until completion); to enumerate many tasks, use task_list.
TIP: the returned 'result' field is truncated to 500 chars in this view -- use task_output for the full (up to 5000 char) payload.
