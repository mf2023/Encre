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

"""Screen OCR -- extract visible text with bounding boxes from the desktop.

Uses Windows.Media.Ocr on Windows 10+ (no external dependencies).
Uses Vision.framework on macOS 10.15+ (via optional pyobjc-framework-Vision).
Falls back to pytesseract (optional) for cross-platform support.
"""

import io
import logging
from typing import Any

logger = logging.getLogger("encre.computer.ocr")


def _ocr_winrt(image_bytes: bytes) -> list[dict[str, Any]] | None:
    """Windows OCR via winrt-Windows.Media.Ocr (Win 10+ built-in)."""
    try:
        from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import (
            DataWriter,
            InMemoryRandomAccessStream,
        )
    except ImportError:
        return None

    import asyncio

    async def _run() -> list[dict[str, Any]]:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            logger.warning("Windows OCR: no OCR language packs installed")
            return []

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(image_bytes)
        try:
            await writer.store_async()
        finally:
            writer.detach_stream()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        software_bitmap = await decoder.get_software_bitmap_async(
            BitmapPixelFormat.bgra8
        )

        result = await engine.recognize_async(software_bitmap)

        lines = []
        for line in result.lines:
            r = line.bounding_rect
            lines.append({
                "text": line.text,
                "x": int(r.x),
                "y": int(r.y),
                "width": int(r.width),
                "height": int(r.height),
                "center_x": int(r.x + r.width / 2),
                "center_y": int(r.y + r.height / 2),
            })
        return lines

    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(_run(), loop)
        return future.result(timeout=30)
    except RuntimeError:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning("Windows OCR failed: %s", e)
        return None


def _ocr_macos_vision(image_bytes: bytes) -> list[dict[str, Any]] | None:
    """macOS OCR via Vision.framework (macOS 10.15+ built-in).

    Requires ``pyobjc-framework-Vision``.  Install with::

        pip install pyobjc-framework-Vision

    When available this gives native-quality text recognition with no
    separate binary dependency (no Tesseract needed on macOS).
    """
    try:
        import Vision  # type: ignore
        from Foundation import NSData  # type: ignore
    except ImportError:
        return None

    try:
        ns_data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(
            Vision.VNRequestTextRecognitionLevelAccurate
        )
        request.setUsesLanguageCorrection_(False)

        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
            ns_data, None,
        )
        success, error = handler.performRequests_error_([request], None)
        if not success or error is not None:
            return None

        # Denormalise Vision coordinates (0.0-1.0, bottom-left origin)
        # into pixel coordinates (top-left origin, matching our desktop
        # tool coordinate system).
        from PIL import Image

        pil_img = Image.open(io.BytesIO(image_bytes))
        img_width, img_height = pil_img.size

        lines = []
        for observation in request.results():
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            text = candidates[0].string()
            if not text.strip():
                continue

            box = observation.boundingBox()
            x = box.origin.x * img_width
            y = (1.0 - box.origin.y - box.size.height) * img_height
            w = box.size.width * img_width
            h = box.size.height * img_height

            lines.append({
                "text": text.strip(),
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "center_x": int(x + w / 2),
                "center_y": int(y + h / 2),
            })
        return lines
    except Exception as e:
        logger.warning("macOS Vision OCR failed: %s", e)
        return None


def _ocr_pytesseract(image_bytes: bytes) -> list[dict[str, Any]] | None:
    """Fallback OCR via pytesseract (requires Tesseract installed)."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
        lines = []
        seen = set()
        for i in range(len(data["text"])):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            # Deduplicate near-identical boxes (pytesseract often emits word fragments)
            key = (x // 5, y // 5, text.lower())
            if key in seen:
                continue
            seen.add(key)
            lines.append({
                "text": text,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "center_x": x + w // 2,
                "center_y": y + h // 2,
            })
        return lines
    except Exception as e:
        logger.warning("pytesseract OCR failed: %s", e)
        return None


def ocr_image(image_bytes: bytes) -> list[dict[str, Any]]:
    """Extract visible text + bounding boxes from a PNG screenshot.

    Tries OCR backends in order:
      1. Windows.Media.Ocr (WinRT, Win 10+ built-in)
      2. Vision.framework (macOS 10.15+, optional pyobjc-framework-Vision)
      3. pytesseract (cross-platform, requires Tesseract binary)

    Returns a list of dicts::

        [
            {
                "text": "Login",
                "x": 450, "y": 300,
                "width": 100, "height": 40,
                "center_x": 500, "center_y": 320,
            },
            ...
        ]

    Returns empty list if no OCR backend is available.
    """
    result = _ocr_winrt(image_bytes)
    if result is not None:
        return result

    result = _ocr_macos_vision(image_bytes)
    if result is not None:
        return result

    result = _ocr_pytesseract(image_bytes)
    if result is not None:
        return result

    import sys
    hints = []
    if sys.platform == "win32":
        hints.append("pip install encre[windows]")
    elif sys.platform == "darwin":
        hints.append("pip install encre[macos]")
    hints.append("pip install pytesseract (requires Tesseract binary)")
    logger.warning(
        "No OCR backend available. %s",
        " | ".join(hints),
    )
    return []


__all__ = ["ocr_image"]
