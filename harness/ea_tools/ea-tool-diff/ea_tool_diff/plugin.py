"""EA Diff Plugin."""
from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_diff.tool import diff_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _DiffPlugin()


class _DiffPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-diff",
        version="0.4.3",
        description="EA (Encre Agent) system-default diff tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=["diff"],
        activation_events=[],
        permissions=['filesystem:read'],
    )

    def get_tools(self) -> list:
        return [diff_tool]
