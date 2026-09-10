"""EA File Write Plugin."""
from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_file_write.tool import file_write_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _FileWritePlugin()


class _FileWritePlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-file-write",
        version="0.4.3",
        description="EA (Encre Agent) mandatory file-write tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.MANDATORY,
        tier="mandatory",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["mandatory"],
        provides_tools=["file_write"],
        activation_events=[],
        permissions=['filesystem:write'],
    )

    def get_tools(self) -> list:
        return [file_write_tool]
