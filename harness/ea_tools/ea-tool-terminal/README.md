# ea-tool-terminal

EA (Encre Agent) mandatory **terminal (bash)** tool plugin.

Executes shell commands (PowerShell on Windows) with timeout, output capture
and background job control. Part of the Encre mandatory core toolset —
installed and activated automatically with the host application; cannot be
uninstalled.

## Metadata

| Field | Value |
| --- | --- |
| Name | `ea-tool-terminal` |
| Version | 0.4.3 |
| Tier | `mandatory` |
| Author | Dunimd Team <dunimd@outlook.com> |
| License | Apache-2.0 |
| Provides tools | `bash` |

## Layout

```
ea_tool_terminal/
  __init__.py    # lazy create_plugin export
  plugin.py      # EncrePlugin manifest + factory
  tool.py        # terminal tool implementation (exports terminal_tool)
  skills/        # SKILL.md files auto-scanned by EncreSkillRegistry
```

The plugin is discovered by the EA directory scanner (`encre.plugins.ea_scan`) —
no registration code is needed. Drop this folder into `ea_tools/` and it works.
