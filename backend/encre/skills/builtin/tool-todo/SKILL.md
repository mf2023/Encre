---
name: tool-todo
description: Task tracking skill. todos/summary/reset, plan and track multi-step work in-session
hidden: true
context: inline
---

## When to Use
- Plan a multi-step task and track progress through it
- Show the user what's done / in-progress / pending
- Break complex work into visible steps before executing

## When NOT to Use
- **Single trivial step** -> just do it, no todo needed
- **Background async tasks** -> `task_create` (different mechanism)

## Key Parameters
- `todos`: list of todo items with subject/description/status
- `summary`: brief status summary
- `reset`: clear the current todo list

## Best Practices
- Create todos at the start of multi-step work; mark in_progress when starting each, completed when done
- Keep subjects short and imperative ("Fix auth bug", "Add tests")
- Update status as you go so progress stays accurate

## Common Pitfalls / Anti-patterns
- **Creating todos for trivial single steps**: overhead with no benefit
- **Forgetting to update status**: stale todos mislead; mark done as you finish
- **Too granular**: one todo per line of code is noise; group meaningfully
- **Never checking off completed steps** - stale todos accumulate and mislead on what is actually done. Mark DONE immediately after completing each step.
- **Todo instead of actual work** - writing a plan with todos and stopping there. Todos are a tracking tool, not a deliverable. Execute the work after the plan.

## Pairing with Other Tools
- Use alongside `file_edit`/`bash`/`test_run` as you execute each todo
