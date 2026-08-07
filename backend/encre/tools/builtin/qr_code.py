#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""QR-code generator and reader.

Generates QR/barcode images from text and optionally decodes QR codes from an
image, returning the image path or scanned payload.
"""


import asyncio
import json
import os
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _qr_execute(**kwargs: Any) -> str:
    """Qr execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    data = kwargs.get("data", "")
    file_path = kwargs.get("file_path", "")
    format_type = kwargs.get("format", "png")
    size = kwargs.get("size", 10)
    border = kwargs.get("border", 4)
    fill_color = kwargs.get("fill_color", "black")
    back_color = kwargs.get("back_color", "white")
    error_correction = kwargs.get("error_correction", "M")

    loop = asyncio.get_event_loop()

    if action == "generate":
        if not data:
            return "Missing required field: data"
        if not file_path:
            file_path = f"qrcode.{format_type}"

        def _generate() -> str:
            """Generate."""
            try:
                import qrcode
            except ImportError:
                return "qrcode library required. Install: pip install qrcode[pil]"

            try:
                ec_map = {
                    "L": qrcode.constants.ERROR_CORRECT_L,
                    "M": qrcode.constants.ERROR_CORRECT_M,
                    "Q": qrcode.constants.ERROR_CORRECT_Q,
                    "H": qrcode.constants.ERROR_CORRECT_H,
                }
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=ec_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
                    box_size=size,
                    border=border,
                )
                qr.add_data(data)
                qr.make(fit=True)

                p = Path(file_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                img = qr.make_image(fill_color=fill_color, back_color=back_color)
                img.save(str(p))

                return json.dumps({
                    "file": str(p),
                    "data": data,
                    "format": format_type,
                    "size": f"{img.width}x{img.height}px",
                    "modules": qr.modules_count,
                }, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to generate QR code: {e}"

        return await loop.run_in_executor(None, _generate)

    elif action == "read":
        if not file_path:
            return "Missing required field: file_path"
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"

        def _read() -> str:
            """Read."""
            try:
                from PIL import Image
                from pyzbar.pyzbar import decode
            except ImportError:
                return "pyzbar and Pillow required. Install: pip install pyzbar pillow"

            try:
                img = Image.open(file_path)
                decoded = decode(img)
                if not decoded:
                    return "No QR code or barcode found in image"
                results = []
                for obj in decoded:
                    results.append({
                        "data": obj.data.decode("utf-8", errors="replace"),
                        "type": obj.type,
                        "rect": {
                            "left": obj.rect.left,
                            "top": obj.rect.top,
                            "width": obj.rect.width,
                            "height": obj.rect.height,
                        },
                    })
                return json.dumps(results, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to read QR code: {e}"

        return await loop.run_in_executor(None, _read)

    elif action == "generate_svg":
        if not data:
            return "Missing required field: data"
        if not file_path:
            file_path = "qrcode.svg"

        def _generate_svg() -> str:
            """Generate svg."""
            try:
                import qrcode
                import qrcode.image.svg
            except ImportError:
                return "qrcode library required. Install: pip install qrcode"

            try:
                ec_map = {
                    "L": qrcode.constants.ERROR_CORRECT_L,
                    "M": qrcode.constants.ERROR_CORRECT_M,
                    "Q": qrcode.constants.ERROR_CORRECT_Q,
                    "H": qrcode.constants.ERROR_CORRECT_H,
                }
                qr = qrcode.QRCode(
                    error_correction=ec_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
                    box_size=size,
                    border=border,
                )
                qr.add_data(data)
                qr.make(fit=True)

                factory = qrcode.image.svg.SvgPathImage
                img = qr.make_image(image_factory=factory, fill_color=fill_color, back_color=back_color)

                p = Path(file_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(p))

                return json.dumps({
                    "file": str(p),
                    "data": data,
                    "format": "svg",
                    "modules": qr.modules_count,
                }, ensure_ascii=False, indent=2)
            except Exception as e:
                return f"Failed to generate SVG QR code: {e}"

        return await loop.run_in_executor(None, _generate_svg)

    return f"Unknown action: {action}. Supported: generate, read, generate_svg"


EncreQRCodeTool = build_tool(
    name="qr_code",
    description=(
        "Generate QR codes as PNG/SVG images, or decode QR codes and barcodes from "
        "an existing image. "
        "Use `generate` for raster PNG/JPG/BMP output, `generate_svg` for scalable "
        "vector output, and `read` to extract a payload from a scanned code. "
        "Do NOT use this for general image conversion (use image), for generating "
        "data charts (use chart), or for AI image synthesis (use generate_image). "
        "Tips: raise `error_correction` (L<M<Q<H) to keep codes scannable when "
        "printed small or partially obscured; pick colors with strong contrast. "
        "Pitfalls: decoding requires pyzbar plus the system zbar library — if "
        "missing, `read` returns an install hint rather than a payload."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "read", "generate_svg"],
                "description": "QR operation: generate (raster image), generate_svg (vector SVG), or read (decode codes from an image).",
            },
            "data": {"type": "string", "description": "Text or URL payload to encode; required for generate and generate_svg, ignored for read."},
            "file_path": {"type": "string", "description": "Output path when generating, or input image path when reading; defaults to 'qrcode.<ext>' for generate and is required for read."},
            "format": {
                "type": "string",
                "enum": ["png", "jpg", "bmp"],
                "description": "Raster image format for generate; defaults to png.",
            },
            "size": {"type": "integer", "description": "Box (module) size in pixels; defaults to 10."},
            "border": {"type": "integer", "description": "Quiet-zone border width in modules; defaults to 4."},
            "fill_color": {"type": "string", "description": "Foreground (module) color; defaults to 'black'."},
            "back_color": {"type": "string", "description": "Background color; defaults to 'white'."},
            "error_correction": {
                "type": "string",
                "enum": ["L", "M", "Q", "H"],
                "description": "Error correction level: L(7%), M(15%), Q(25%), H(30%). Higher levels tolerate more damage; defaults to 'M'.",
            },
        },
        "required": ["action"],
    },
    execute=_qr_execute,
    intents=["general", "coding", "data"],
    category="media",
    semantic_type="generate",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_destructive=lambda args: args.get("action", "") in ("generate", "generate_svg"),
)
