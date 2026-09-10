# ea-tool-memory

EA (Encre Agent) system-default tool package.

| Tool | Factory var | Tier |
| --- | --- | --- |
| `memory_create` | memory_create_tool | system-default |
| `memory_delete` | memory_delete_tool | system-default |
| `memory_profile` | memory_profile_tool | system-default |
| `memory_read` | memory_read_tool | system-default |
| `memory_search` | memory_search_tool | system-default |
| `memory_update` | memory_update_tool | system-default |

Auto-discovered by `encre.plugins.ea_scan` from `harness/ea_tools/`. The tool
implementations are verbatim copies of the corresponding `encre.tools.builtin`
modules, adapted only by renaming the factory variable for the plugin system.
