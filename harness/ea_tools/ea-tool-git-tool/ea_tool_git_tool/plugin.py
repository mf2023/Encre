"""EA git_tool Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_git_tool.tool import git_tool


def create_plugin() -> EncrePlugin:
    return _GitToolPlugin()


class _GitToolPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-git-tool",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: git.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['git'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [git_tool]
