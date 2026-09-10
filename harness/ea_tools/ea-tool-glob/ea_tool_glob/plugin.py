"""EA glob Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_glob.tool import glob_tool


def create_plugin() -> EncrePlugin:
    return _GlobPlugin()


class _GlobPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-glob",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: glob.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['glob'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [glob_tool]
