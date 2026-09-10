"""EA codebase Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_codebase.tool import codebase_context_tool, codebase_search_tool


def create_plugin() -> EncrePlugin:
    return _CodebasePlugin()


class _CodebasePlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-codebase",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: codebase_context, codebase_search.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['codebase_context', 'codebase_search'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [codebase_context_tool, codebase_search_tool]
