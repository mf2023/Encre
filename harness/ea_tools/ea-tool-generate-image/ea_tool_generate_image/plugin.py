"""EA generate_image Plugin (system-default)."""
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from ea_tool_generate_image.tool import edit_image_tool, generate_image_tool, image_variation_tool


def create_plugin() -> EncrePlugin:
    return _GenerateImagePlugin()


class _GenerateImagePlugin(EncrePlugin):
    manifest = PluginManifest(
        name="ea-tool-generate-image",
        version="0.4.3",
        description="EA (Encre Agent) system-default tools: edit_image, generate_image, image_variation.",
        author="Dunimd Team <dunimd@outlook.com>",
        license="Apache-2.0",
        homepage="https://github.com/mf2023/Encre",
        source=PluginSource.BUNDLED,
        tier="system-default",
        dependencies=[],
        min_ea_version="0.4.3",
        tags=["system-default"],
        provides_tools=['edit_image', 'generate_image', 'image_variation'],
        activation_events=[],
        permissions=[],
    )

    def get_tools(self) -> list:
        return [edit_image_tool, generate_image_tool, image_variation_tool]
