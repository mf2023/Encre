"""EA device_battery Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_device_battery.tool import device_battery_tool


def create_plugin() -> EncrePlugin:
    return _DeviceBatteryPlugin()


class _DeviceBatteryPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-device-battery",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: device_battery.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['device_battery'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [device_battery_tool]
