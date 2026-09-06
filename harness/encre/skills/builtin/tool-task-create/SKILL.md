---
name: tool-task-create
description: Async background task skill. name/description/task_type/prompt/parent_id, spawn long-running or parallel work
hidden: true
context: inline
---

## When to Use
- Spawn a background task for long-running or parallelizable work
- Fan out independent workstreams (with `agent` for delegation)
- Run something that shouldn't block the main turn

## When NOT to Use
- **Quick synchronous operation** -> just do it directly with the relevant tool
- **Track your own multi-step plan** -> `todo` (in-session checklist, not async tasks)
- **Delegate to a sub-agent** -> `agent` (task_create is the lower-level primitive)

## Key Parameters
- `name` (required): task name
- `description`: what the task does
- `task_type`: e.g. shell/agent/workflow
- `prompt`: the task's input/prompt
- `parent_id`: for nested tasks

## Best Practices
- Give tasks self-contained prompts with expected output format
- Use for genuinely independent work that can run without blocking

## Common Pitfalls / Anti-patterns
- **Spawning tasks for trivial synchronous work**: a single file read or one-line edit costs more in overhead than it saves. Just do it directly
- **Vague prompt**: a background task can't ask follow-ups, so an underspecified prompt produces a wrong or useless result. Give self-contained inputs and an expected output format
- **Forgetting to poll**: spawned tasks don't surface on their own. Check results via `task_output`/`task_list` before declaring the work done
- **Hidden dependencies between "parallel" tasks**: if task B needs task A's output, running them in parallel means B runs on stale/empty input. Sequence the dependent ones; parallelize only the independent ones

## Pairing with Other Tools
- `task_output`: retrieve a task's result
- `task_list`: see task statuses
- `task_stop`: cancel a task
