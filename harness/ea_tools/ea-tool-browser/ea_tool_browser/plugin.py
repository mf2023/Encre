"""EA browser Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_browser.tool import browser_tool


def create_plugin() -> EncrePlugin:
    return _BrowserPlugin()


class _BrowserPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-browser",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: browser.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['browser'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [browser_tool]
