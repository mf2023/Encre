"""EA desktop Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_desktop.tool import desktop_tool


def create_plugin() -> EncrePlugin:
    return _DesktopPlugin()


class _DesktopPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-desktop",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: desktop.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['desktop'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [desktop_tool]
