"""EA wechat-pay skill plugin."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource


def create_plugin() -> EncrePlugin:
    return _SkillPlugin()


class _SkillPlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-skill-wechat-pay",
        version="0.4.3",
        description="EA (Encre Agent) system-default skill: wechat-pay.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default", "skill"],
        provides_skills=["wechat-pay"],
        activation_events=[],
        permissions=[],
    )
