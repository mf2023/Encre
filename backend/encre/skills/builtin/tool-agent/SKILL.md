---
name: tool-agent
description: Sub-agent delegation skill. prompt/agent_name/tasks, fan out parallel or specialized work
hidden: true
context: inline
---

## When to Use
- Delegate independent parallel workstreams you can fan out and merge
- Specialized read-only investigation across a large codebase while you do other work
- Genuinely multi-domain work where domains can be explored concurrently

## When NOT to Use
- **Single trivial task** -> just do it yourself
- **Sequential work** -> delegation adds latency and coordination overhead
- **Simple file read/grep/glob/web search** -> do it directly
- **Spawning sub-agents "to be safe"** -> verify your own work instead

## Key Parameters
- `prompt` (required): self-contained brief for the sub-agent; include expected output format
- `agent_name`: pick a specialized agent type if one fits
- `tasks`: array of parallel task specs for fan-out

## Best Practices
- Give specific, self-contained prompts with expected output format (sub-agents don't share your context)
- Prefer parallel `tasks` arrays over serial sub-agent calls
- Never spawn sub-agents from a sub-agent (one level of delegation only)

## Common Pitfalls / Anti-patterns
- **Delegating trivial work**: overhead with no gain; do it yourself
- **Vague prompt**: sub-agents can't ask you follow-ups; be specific and complete
- **Nested delegation**: sub-agents must not call `agent` again; they return to you
- **Single-step delegation** - calling `agent` for one grep or one file read instead of doing it directly. The setup cost of a sub-agent exceeds the work. Do trivial things yourself.
- **Delegating without expected output format** - the sub-agent returns whatever it pleases, and you have to parse ambiguous output. Give a schema or explicit format in the prompt.

## Pairing with Other Tools
- Use after `grep`/`glob`/`web_search` to scope the work, then delegate execution
- Merge sub-agent results yourself
