# ea-tool-file-read

EA (Encre Agent) mandatory **file_read** tool plugin.

Reads text files, images (PNG/JPEG), and PDFs with pagination, line offsets,
and binary detection. Part of the Encre mandatory core toolset — installed and
activated automatically with the host application; cannot be uninstalled.

## Metadata

| Field | Value |
| --- | --- |
| Name | `ea-tool-file-read` |
| Version | 0.4.3 |
| Tier | `mandatory` |
| Author | Dunimd Team <dunimd@outlook.com> |
| License | Apache-2.0 |
| Provides tools | `file_read` |

## Layout

```
ea_tool_file_read/
  __init__.py    # lazy create_plugin export
  plugin.py      # EncrePlugin manifest + factory
  tool.py        # file_read tool implementation
  skills/        # SKILL.md files auto-scanned by EncreSkillRegistry
```

The plugin is discovered by the EA directory scanner (`encre.plugins.ea_scan`) —
no registration code is needed. Drop this folder into `ea_tools/` and it works.
