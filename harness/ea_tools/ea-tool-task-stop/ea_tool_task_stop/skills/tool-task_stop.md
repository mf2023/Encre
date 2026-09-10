---
name: tool-task_stop
description: "Stop a running background task by marking it cancelled."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# task_stop

Stop a running background task by marking it cancelled.

WHEN to use: the user asks to stop/cancel a task, a task is stuck or no longer needed, or you started work that became irrelevant.
WHEN NOT to use: to record a normal completion use task_update with status='completed'; to peek at progress without stopping use task_output with block=false.
TIPS: stopping is idempotent -- already-completed or already-cancelled tasks return a friendly 'already ...' message instead of an error.
