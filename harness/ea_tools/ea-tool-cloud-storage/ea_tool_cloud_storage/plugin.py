"""EA cloud_storage Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_cloud_storage.tool import cloud_storage_tool


def create_plugin() -> EncrePlugin:
    return _CloudStoragePlugin()


class _CloudStoragePlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-cloud-storage",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: cloud_storage.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['cloud_storage'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [cloud_storage_tool]
