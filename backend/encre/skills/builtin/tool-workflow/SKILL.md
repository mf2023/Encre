---
name: tool-workflow
description: Multi-agent workflow skill. goal, orchestrate deterministic multi-agent pipelines
hidden: true
context: inline
---

## When to Use
- Orchestrate a deterministic, multi-step pipeline across many sub-agents
- Fan out work that needs structured coordination (find -> verify -> synthesize)
- Scale beyond a single context window (migrations, broad audits)

## When NOT to Use
- **A single sub-agent task** -> `agent`
- **Sequential simple work** -> just do it; don't over-orchestrate
- **A trivial task** -> direct tools

## Key Parameters
- `goal` (required): the workflow goal; the script orchestrates sub-agents toward it

## Best Practices
- Use for genuinely large/complex work that benefits from structured fan-out
- Keep the goal clear and bounded; the workflow encodes its own phases
- Prefer this over many manual `agent` calls when the structure is deterministic

## Common Pitfalls / Anti-patterns
- **Using a workflow for trivial work**: a multi-agent pipeline has setup + coordination cost. For one or two steps, direct tools or a single `agent` are faster
- **Vague goal**: the workflow drives every agent off the goal string. Make it specific and bounded ("audit src/ for SQL injection, report findings per file") - a vague goal produces vague fan-out
- **No verification of synthesized output**: each agent "succeeded" but the merged result may contradict itself or not build. Always verify the synthesis, not just per-agent success
- **Over-orchestration**: wrapping a 3-step task in a workflow because it "feels thorough". If the structure is simple, direct tools are clearer and cheaper

## Pairing with Other Tools
- `agent`: single delegation
- `todo`: track your own steps around the workflow
