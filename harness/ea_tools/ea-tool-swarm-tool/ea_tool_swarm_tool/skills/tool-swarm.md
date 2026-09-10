---
name: tool-swarm
description: "Orchestrate a complex goal as a role-specialised multi-agent swarm with built-in review and consensus."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# swarm

Orchestrate a complex goal as a role-specialised multi-agent swarm with built-in review and consensus.

WHAT: decomposes the goal into a DAG of tasks, assigns each a specialised role (architect / coder / reviewer / tester / researcher / debugger), runs tasks with dependency-aware concurrency, gates coder output through a reviewer, shares context via a blackboard, and runs a proposal-vote consensus step when two or more agents produce results.
WHEN to use: large goals that benefit from role specialisation and cross-agent verification (e.g. ship a feature end-to-end with design + impl + review + test).
WHEN NOT to use: for simpler multi-step goals without role specialisation prefer the 'workflow' tool; for independent parallel sub-tasks with no review gate use the 'agent' tool.
TIPS: state the desired end result and acceptance criteria explicitly; the planner infers roles from the goal, so a precise goal yields a cleaner task decomposition.
PITFALLS: swarms cannot be spawned from inside a sub-agent (one level of delegation only); swarms are heavier than workflows -- don't use one for a 2-step task.
IMPORTANT: The goal MUST be written in English -- all swarm participants think, reason, and respond in English for reliable state matching and output parsing.
