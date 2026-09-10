"""EA device_network Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_device_network.tool import device_network_tool


def create_plugin() -> EncrePlugin:
    return _DeviceNetworkPlugin()


class _DeviceNetworkPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-device-network",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: device_network.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['device_network'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [device_network_tool]
