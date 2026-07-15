#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any

from encre.tools.base import build_tool
from encre.backends.multimodal import MultimodalMixin


def _get_backend() -> MultimodalMixin | None:
    from encre.tools.builtin.agent import _resolve_loop
    loop = _resolve_loop()
    if loop and hasattr(loop.backend, "generate_image"):
        return loop.backend
    return None


async def _generate_image_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend does not support image generation"
    try:
        prompt = kwargs.get("prompt", "")
        n = int(kwargs.get("n", 1))
        size = kwargs.get("size", "1024x1024")
        result = await backend.generate_image(prompt=prompt, n=n, size=size)
        return json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, indent=2, default=str)
    except Exception as e:
        return f"Error generating image: {e}"


async def _edit_image_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend does not support image editing"
    try:
        image = kwargs.get("image", "")
        prompt = kwargs.get("prompt", "")
        mask = kwargs.get("mask", "")
        result = await backend.edit_image(image=image, prompt=prompt, mask=mask)
        return json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, indent=2, default=str)
    except Exception as e:
        return f"Error editing image: {e}"


async def _image_variation_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None:
        return "Error: Backend does not support image variation"
    try:
        image = kwargs.get("image", "")
        n = int(kwargs.get("n", 1))
        size = kwargs.get("size", "1024x1024")
        result = await backend.create_image_variation(image=image, n=n, size=size)
        return json.dumps(result.to_dict() if hasattr(result, "to_dict") else result, indent=2, default=str)
    except Exception as e:
        return f"Error creating image variation: {e}"


EncreGenerateImageTool = build_tool(
    name="generate_image",
    description="Generate an image from a text description using DALL-E or compatible API",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Text description of the image to generate"},
            "n": {"type": "integer", "description": "Number of images to generate (default 1)", "default": 1},
            "size": {"type": "string", "description": "Image size e.g. 1024x1024", "default": "1024x1024"},
        },
        "required": ["prompt"],
    },
    execute=_generate_image_execute,
    intents=["general", "creative"],
    category="media",
    semantic_type="media",
    is_destructive=False,
    is_concurrency_safe=True,
)

EncreEditImageTool = build_tool(
    name="edit_image",
    description="Edit an image by providing a new prompt and optionally a mask",
    input_schema={
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Base64-encoded image or URL"},
            "prompt": {"type": "string", "description": "Edit description"},
            "mask": {"type": "string", "description": "Base64-encoded mask image or URL (optional)"},
        },
        "required": ["image", "prompt"],
    },
    execute=_edit_image_execute,
    intents=["general", "creative"],
    category="media",
    semantic_type="media",
    is_destructive=False,
    is_concurrency_safe=True,
)

EncreImageVariationTool = build_tool(
    name="image_variation",
    description="Create a variation of an image",
    input_schema={
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Base64-encoded image or URL"},
            "n": {"type": "integer", "description": "Number of variations (default 1)", "default": 1},
            "size": {"type": "string", "description": "Variation size e.g. 1024x1024", "default": "1024x1024"},
        },
        "required": ["image"],
    },
    execute=_image_variation_execute,
    intents=["general", "creative"],
    category="media",
    semantic_type="media",
    is_destructive=False,
    is_concurrency_safe=True,
)

__all__ = ["EncreGenerateImageTool", "EncreEditImageTool", "EncreImageVariationTool"]
