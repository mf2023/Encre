"""EA File Edit Plugin."""
from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_file_edit.tool import file_edit_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _FileeditPlugin()


class _FileeditPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-file-edit",
        version="0.4.3",
        description="EA (Encre Agent) mandatory file-edit tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.MANDATORY,
        tier="mandatory",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["mandatory"],
        provides_tools=["file_edit"],
        activation_events=[],
        permissions=['filesystem:write'],
    )

    def get_tools(self) -> list:
        return [file_edit_tool]
