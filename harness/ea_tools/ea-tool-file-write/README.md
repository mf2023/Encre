# ea-tool-file-write

EA (Encre Agent) mandatory file write tool.

| Field | Value |
|-------|-------|
| Tool | `file_write` |
| Tier | `mandatory` (cannot be uninstalled) |
| Package | `ea-tool-file-write` |
| Module | `ea_tool_file_write` |
| Author | Dunimd Team <dunimd@outlook.com> |
| Version | 0.4.3 |

Creates a new file or overwrites an existing one entirely, returning a unified
diff with insertion/deletion counts.

## Layout

```
ea-tool-file-write/
  pyproject.toml
  README.md
  ea_tool_file_write/
    __init__.py
    tool.py               # file_write_tool (build_tool)
    plugin.py             # EncrePlugin manifest + create_plugin factory
    skills/
      tool-file-write.md  # Skill instructions
```
