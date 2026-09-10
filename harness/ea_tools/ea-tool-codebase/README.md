# ea-tool-codebase

EA (Encre Agent) system-default tool package.

| Tool | Factory var | Tier |
| --- | --- | --- |
| `codebase_context` | codebase_context_tool | system-default |
| `codebase_search` | codebase_search_tool | system-default |

Auto-discovered by `encre.plugins.ea_scan` from `harness/ea_tools/`. The tool
implementations are verbatim copies of the corresponding `encre.tools.builtin`
modules, adapted only by renaming the factory variable for the plugin system.
