"""EA find_tool Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_find_tool.tool import find_tool_tool


def create_plugin() -> EncrePlugin:
    return _FindToolPlugin()


class _FindToolPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-find-tool",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: find_tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['find_tool'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [find_tool_tool]
