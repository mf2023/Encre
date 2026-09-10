"""EA email Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_email.tool import email_tool


def create_plugin() -> EncrePlugin:
    return _EmailPlugin()


class _EmailPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-email",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: email.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['email'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [email_tool]
