"""EA cron_create Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_cron_create.tool import cron_create_tool


def create_plugin() -> EncrePlugin:
    return _CronCreatePlugin()


class _CronCreatePlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-cron-create",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: cron_create.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['cron_create'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [cron_create_tool]
