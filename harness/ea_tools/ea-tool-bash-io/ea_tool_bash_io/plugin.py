"""EA bash_io Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_bash_io.tool import bash_kill_tool, bash_list_tool, bash_output_tool


def create_plugin() -> EncrePlugin:
    return _BashIoPlugin()


class _BashIoPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-bash-io",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: bash_kill, bash_list, bash_output.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['bash_kill', 'bash_list', 'bash_output'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [bash_kill_tool, bash_list_tool, bash_output_tool]
