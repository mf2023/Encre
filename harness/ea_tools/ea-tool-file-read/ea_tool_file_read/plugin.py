"""EA File Read Plugin."""
from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_file_read.tool import file_read_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _FilereadPlugin()


class _FilereadPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-file-read",
        version="0.4.3",
        description="EA (Encre Agent) mandatory file-read tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.MANDATORY,
        tier="mandatory",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["mandatory"],
        provides_tools=["file_read"],
        activation_events=[],
        permissions=['filesystem:read'],
    )

    def get_tools(self) -> list:
        return [file_read_tool]
