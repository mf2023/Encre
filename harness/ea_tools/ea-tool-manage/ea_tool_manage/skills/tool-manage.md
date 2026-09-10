---
name: tool-manage
description: "God tool for dynamically managing the runtime: install new tools, register sub-agents, install skills, and connect MCP servers. All changes take effect immediately and are available on the very next turn."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# manage

God tool for dynamically managing the runtime: install new tools, register sub-agents, install skills, and connect MCP servers. All changes take effect immediately and are available on the very next turn.

WHEN to use: the built-in tools cannot satisfy a request and you need to add a capability at runtime (a custom tool, a specialized sub-agent, a reusable skill, or an MCP server exposing external tools).
WHEN NOT to use: if a built-in tool already covers the task, prefer it over installing a new one; do not use this for trivial operations that don't require new capabilities.
TIPS: keep new tool code self-contained (the `code` field is exec'd in a fresh namespace and must define an `async def execute(**kwargs)`); give agents a focused system_prompt and a narrow tool_policy to limit blast radius; verify MCP server connectivity with a trivial call right after install_mcp.
PITFALLS: install_tool runs arbitrary Python via exec -- only install code you trust; install_mcp with stdio spawns a long-lived child process, so prefer HTTP transport when available.

Actions:
  install_tool  - Create and register a brand new tool. Requires: name, description, input_schema (JSON Schema), code (Python async function body named `execute`). Optional: category, intents, always_available.
  install_agent - Register a new named sub-agent. Requires: name, description. Optional: system_prompt, tool_policy (all/readonly/no_writes).
  install_skill - Install a new skill. Requires: name, description, body (skill prompt text). Optional: aliases.
  install_mcp   - Connect a new MCP server. Requires: name, and either command (stdio) or url (HTTP). Optional: args, env, cwd, timeout.
