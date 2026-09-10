"""EA device_info Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_device_info.tool import device_info_tool


def create_plugin() -> EncrePlugin:
    return _DeviceInfoPlugin()


class _DeviceInfoPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-device-info",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: device_info.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['device_info'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [device_info_tool]
