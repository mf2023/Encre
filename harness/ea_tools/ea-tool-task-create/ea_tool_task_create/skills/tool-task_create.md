---
name: tool-task_create
description: "Create a new background sub-task (bash command, delegated agent, or workflow) that runs independently and can be polled later."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# task_create

Create a new background sub-task (bash command, delegated agent, or workflow) that runs independently and can be polled later.

WHEN to use: long-running work that would block the main conversation (builds, test suites, research delegations); parallelizable sub-problems you want to fan out to sub-agents.
WHEN NOT to use: for short synchronous actions just use the relevant tool directly; for the model's own task tracking use the todo tool.
TIPS: give the task a descriptive name and prompt so a sub-agent knows exactly what to do; set parent_id when spawning from another task to keep the hierarchy navigable.
PITFALLS: returns immediately with a task ID -- you must poll with task_output or task_get to retrieve the result.
