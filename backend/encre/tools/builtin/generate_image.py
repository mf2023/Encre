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
    description=(
        "Generate one or more images from a text prompt using the active backend's "
        "image-generation model (DALL-E-compatible). "
        "Use this to create original artwork, illustrations, or visual assets from a "
        "description; prefer it over diagram tools for photorealistic or painterly "
        "output. "
        "Do NOT use this for editing an existing image (use edit_image), for "
        "diagrams/flowcharts (use diagram), or for data charts (use chart). "
        "Tips: be specific about style, composition, and aspect ratio in the prompt; "
        "check supported `size` values for the target backend. "
        "Pitfalls: the active backend must implement generate_image, otherwise the "
        "call returns an unsupported error."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Text description of the image to generate; include style, subject, composition, and mood for best results."},
            "n": {"type": "integer", "description": "Number of images to generate; defaults to 1.", "default": 1},
            "size": {"type": "string", "description": "Image dimensions as 'WxH' (e.g. '1024x1024'); valid sizes depend on the backend. Defaults to '1024x1024'.", "default": "1024x1024"},
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
    description=(
        "Edit an existing image with a text prompt, optionally constrained to the "
        "area revealed by a mask. "
        "Use this to inpaint part of an image while preserving the rest, rather than "
        "regenerating from scratch. "
        "Do NOT use this for full-image regeneration (use generate_image) or for "
        "creative variations of the whole image (use image_variation). "
        "Tips: provide a mask where fully transparent pixels mark the editable "
        "region; describe the desired result, not the original. "
        "Pitfalls: the active backend must implement edit_image and accept the "
        "supplied image/mask encoding."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Source image as a base64-encoded string or a URL."},
            "prompt": {"type": "string", "description": "Description of the edit to apply."},
            "mask": {"type": "string", "description": "Mask image as a base64-encoded string or URL; transparent pixels indicate the region to edit."},
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
    description=(
        "Generate one or more alternative variations of a source image, keeping the "
        "same subject but altering details. "
        "Use this to explore creative alternatives of an existing image without a "
        "text prompt; distinct from edit_image which targets a specific region. "
        "Do NOT use this for prompt-driven generation (use generate_image) or for "
        "masked edits (use edit_image). "
        "Tips: use a PNG source with a square aspect ratio for best compatibility; "
        "request multiple variations via `n`. "
        "Pitfalls: the active backend must implement create_image_variation — not "
        "all providers support this operation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Source image as a base64-encoded string or a URL."},
            "n": {"type": "integer", "description": "Number of variations to generate; defaults to 1.", "default": 1},
            "size": {"type": "string", "description": "Output dimensions as 'WxH' (e.g. '1024x1024'); defaults to '1024x1024'.", "default": "1024x1024"},
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
