"""EA agent Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_agent.tool import agent_tool


def create_plugin() -> EncrePlugin:
    return _AgentPlugin()


class _AgentPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-agent",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: agent.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['agent'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [agent_tool]
