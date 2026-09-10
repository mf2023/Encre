"""EA cron_list Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_cron_list.tool import cron_list_tool


def create_plugin() -> EncrePlugin:
    return _CronListPlugin()


class _CronListPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-cron-list",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: cron_list.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['cron_list'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [cron_list_tool]
