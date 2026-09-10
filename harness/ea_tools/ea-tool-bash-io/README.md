# ea-tool-bash-io

EA (Encre Agent) system-default tool package.

| Tool | Factory var | Tier |
| --- | --- | --- |
| `bash_kill` | bash_kill_tool | system-default |
| `bash_list` | bash_list_tool | system-default |
| `bash_output` | bash_output_tool | system-default |

Auto-discovered by `encre.plugins.ea_scan` from `harness/ea_tools/`. The tool
implementations are verbatim copies of the corresponding `encre.tools.builtin`
modules, adapted only by renaming the factory variable for the plugin system.
