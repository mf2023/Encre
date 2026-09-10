# ea-tool-file-edit

EA (Encre Agent) mandatory **file_edit** tool plugin.

Performs exact string replacement edits in files (create / edit / rename /
delete paths). Part of the Encre mandatory core toolset — installed and
activated automatically with the host application; cannot be uninstalled.

## Metadata

| Field | Value |
| --- | --- |
| Name | `ea-tool-file-edit` |
| Version | 0.4.3 |
| Tier | `mandatory` |
| Author | Dunimd Team <dunimd@outlook.com> |
| License | Apache-2.0 |
| Provides tools | `file_edit` |

## Layout

```
ea_tool_file_edit/
  __init__.py    # lazy create_plugin export
  plugin.py      # EncrePlugin manifest + factory
  tool.py        # file_edit tool implementation
  skills/        # SKILL.md files auto-scanned by EncreSkillRegistry
```

The plugin is discovered by the EA directory scanner (`encre.plugins.ea_scan`) —
no registration code is needed. Drop this folder into `ea_tools/` and it works.
