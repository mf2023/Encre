# ea-tool-web-fetch

EA (Encre Agent) mandatory **web_fetch** tool plugin.

Fetches a URL and converts the response to markdown/text/html. Uses
`encre.search.manager.EncreSearchManager` internally. Part of the Encre
mandatory core toolset — installed and activated automatically with the host
application; cannot be uninstalled.

## Metadata

| Field | Value |
| --- | --- |
| Name | `ea-tool-web-fetch` |
| Version | 0.4.3 |
| Tier | `mandatory` |
| Author | Dunimd Team <dunimd@outlook.com> |
| License | Apache-2.0 |
| Provides tools | `web_fetch` |

## Layout

```
ea_tool_web_fetch/
  __init__.py    # lazy create_plugin export
  plugin.py      # EncrePlugin manifest + factory
  tool.py        # web_fetch tool implementation
  skills/        # SKILL.md files auto-scanned by EncreSkillRegistry
```

The plugin is discovered by the EA directory scanner (`encre.plugins.ea_scan`) —
no registration code is needed. Drop this folder into `ea_tools/` and it works.
