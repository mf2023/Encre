# ea-tool-web-search

EA (Encre Agent) mandatory **web_search** tool plugin.

Web search powered by `encre.search.manager.EncreSearchManager`. Part of the
Encre mandatory core toolset — installed and activated automatically with the
host application; cannot be uninstalled.

## Metadata

| Field | Value |
| --- | --- |
| Name | `ea-tool-web-search` |
| Version | 0.4.3 |
| Tier | `mandatory` |
| Author | Dunimd Team <dunimd@outlook.com> |
| License | Apache-2.0 |
| Provides tools | `web_search` |

## Layout

```
ea_tool_web_search/
  __init__.py    # lazy create_plugin export
  plugin.py      # EncrePlugin manifest + factory
  tool.py        # web_search tool implementation
  skills/        # SKILL.md files auto-scanned by EncreSkillRegistry
```

The plugin is discovered by the EA directory scanner (`encre.plugins.ea_scan`) —
no registration code is needed. Drop this folder into `ea_tools/` and it works.
