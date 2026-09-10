"""EA device_display Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_device_display.tool import device_display_tool


def create_plugin() -> EncrePlugin:
    return _DeviceDisplayPlugin()


class _DeviceDisplayPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-device-display",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: device_display.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['device_display'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [device_display_tool]
