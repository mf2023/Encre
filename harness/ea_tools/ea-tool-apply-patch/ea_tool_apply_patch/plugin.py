"""EA Apply Patch Plugin."""
from pathlib import Path

from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_apply_patch.tool import apply_patch_tool

_PLUGIN_DIR = Path(__file__).resolve().parent


def create_plugin() -> EncrePlugin:
    return _ApplyPatchPlugin()


class _ApplyPatchPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-apply-patch",
        version="0.4.3",
        description="EA (Encre Agent) system-default apply-patch tool.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=["apply_patch"],
        activation_events=[],
        permissions=['filesystem:write'],
    )

    def get_tools(self) -> list:
        return [apply_patch_tool]
