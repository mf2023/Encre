"""EA device_sensor Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_device_sensor.tool import device_sensor_tool


def create_plugin() -> EncrePlugin:
    return _DeviceSensorPlugin()


class _DeviceSensorPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-device-sensor",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: device_sensor.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['device_sensor'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [device_sensor_tool]
