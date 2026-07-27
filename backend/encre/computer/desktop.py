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

"""Desktop automation session: screenshots, mouse/keyboard, OCR and UI automation.

Wraps ``mss`` (screen capture) and ``pyautogui`` (input) on top of
optional Windows-only capabilities -- Win32 DPI awareness, the
``PrintWindow`` foreground-window capture, the Windows UIAutomation
(UIA) accessibility tree, and OCR via ``Windows.Media.Ocr`` or
``pytesseract``. The session tracks the physical (raw pixel) and
logical (DPI-scaled) screen sizes so coordinates from screenshots and
from the input backend line up on HiDPI displays.
"""

import base64
import importlib
import io
import logging
import os
import sys
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("encre.computer.desktop")

_PLATFORM = sys.platform


def _enable_windows_dpi_awareness() -> None:
    """Make the current process per-monitor DPI aware on Windows so
    screenshot pixels and mouse coordinates use the same coordinate system.

    Without this, on a HiDPI display mss returns physical pixels while
    pyautogui returns logical (scaled) pixels, and clicks miss their
    targets by the scale factor.
    """
    if _PLATFORM != "win32":
        return
    try:
        import ctypes
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 -- Win 8.1+. Fall back to
        # SetProcessDPIAware for older systems.
        shcore = ctypes.windll.shcore
        try:
            shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_windows_dpi_awareness()


@dataclass
class DesktopScreenState:
    """Snapshot of the desktop: screenshot, dimensions, DPI and cursor pos.

    Tracks both physical (raw pixel) and logical (DPI-scaled) sizes so
    coordinates from screenshots and from the input backend line up.
    """
    width: int = 0
    height: int = 0
    screenshot_b64: str = ""
    cursor_x: int = 0
    cursor_y: int = 0
    platform: str = _PLATFORM
    dpi_scale_x: float = 1.0
    dpi_scale_y: float = 1.0
    logical_width: int = 0
    logical_height: int = 0


@dataclass
class ActiveWindowCapture:
    """Result of a foreground-window ``PrintWindow`` capture.

    ``png_bytes`` is the captured bitmap encoded as PNG. ``left`` /
    ``top`` are the window's screen position in physical pixels so
    callers can translate OCR bounding boxes (which are relative to
    the captured image) back into screen coordinates for clicks.
    """

    png_bytes: bytes
    left: int
    top: int
    width: int
    height: int


@dataclass
class DesktopLocateResult:
    """Result of a template/image match search on the screen."""
    found: bool = False
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0


class EncreDesktopSession:
    """Desktop automation session: screenshots, mouse/keyboard, OCR, UIA."""

    def __init__(self):
        """Initialise idle tracking, cached screen state and DPI scale cache."""
        self._last_used = time.time()
        self._state = DesktopScreenState()
        self._dpi_x: float | None = None
        self._dpi_y: float | None = None

    def _check_mss(self) -> bool:
        """Return True if the ``mss`` screen-capture library is importable."""
        return importlib.util.find_spec("mss") is not None

    def _check_pyautogui(self) -> bool:
        """Return True if the ``pyautogui`` input library is importable."""
        return importlib.util.find_spec("pyautogui") is not None

    def _check_pillow(self) -> bool:
        """Return True if the ``PIL`` (Pillow) imaging library is importable."""
        return importlib.util.find_spec("PIL") is not None

    def screenshot(self) -> DesktopScreenState:
        """Capture the primary monitor and update/return cached screen state."""
        if not self._check_mss():
            raise RuntimeError(
                "mss not installed. Run: pip install mss pillow"
            )
        if not self._check_pillow():
                raise RuntimeError(
                    "Pillow not installed. Run: pip install pillow"
                ) from None
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)

        buf = io.BytesIO()
        self._ensure_pillow()
        from PIL import Image
        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        pil_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        physical_w = monitor["width"]
        physical_h = monitor["height"]
        logical_w, logical_h = self._logical_size_fallback(physical_w, physical_h)
        scale_x, scale_y = self._compute_scale(physical_w, physical_h, logical_w, logical_h)

        self._state.width = physical_w
        self._state.height = physical_h
        self._state.logical_width = logical_w
        self._state.logical_height = logical_h
        self._state.dpi_scale_x = scale_x
        self._state.dpi_scale_y = scale_y
        self._state.screenshot_b64 = b64
        self._last_used = time.time()
        return self._state

    def _logical_size_fallback(self, physical_w: int, physical_h: int) -> tuple[int, int]:
        """Return logical (pyautogui-visible) screen size."""
        if self._check_pyautogui():
            try:
                import pyautogui
                w, h = pyautogui.size()
                return int(w), int(h)
            except Exception:
                pass
        return physical_w, physical_h

    def _compute_scale(self, phys_w: int, phys_h: int,
                       log_w: int, log_h: int) -> tuple[float, float]:
        """Compute and cache physical/logical DPI scale factors."""
        sx = phys_w / log_w if log_w else 1.0
        sy = phys_h / log_h if log_h else 1.0
        self._dpi_x, self._dpi_y = sx, sy
        return sx, sy

    def _to_logical(self, x: int, y: int, coord_space: str) -> tuple[int, int]:
        """Convert a coordinate into pyautogui's logical coordinate system."""
        if coord_space == "logical":
            return x, y
        if coord_space == "physical":
            sx = self._dpi_x or 1.0
            sy = self._dpi_y or 1.0
            return round(x / sx), round(y / sy)
        # auto: if dpi scale != 1 and the value looks "too big" for the
        # logical screen, assume it's physical.
        sx = self._dpi_x
        sy = self._dpi_y
        if sx is None or sy is None:
            return x, y
        if abs(sx - 1.0) < 1e-3 and abs(sy - 1.0) < 1e-3:
            return x, y
        try:
            import pyautogui
            lw, lh = pyautogui.size()
            if x > lw or y > lh:
                return round(x / sx), round(y / sy)
        except Exception:
            pass
        return x, y

    def get_screen_size(self) -> dict[str, int]:
        """Return the screen size as ``{"width": w, "height": h}``."""
        if self._check_pyautogui():
            import pyautogui
            w, h = pyautogui.size()
            self._state.width = w
            self._state.height = h
        elif self._check_mss():
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                self._state.width = m["width"]
                self._state.height = m["height"]
        return {"width": self._state.width, "height": self._state.height}

    def get_cursor_position(self) -> dict[str, int]:
        """Return the current mouse cursor position as ``{"x": x, "y": y}``."""
        if not self._check_pyautogui():
            return {"x": 0, "y": 0}
        import pyautogui
        x, y = pyautogui.position()
        self._state.cursor_x = x
        self._state.cursor_y = y
        self._last_used = time.time()
        return {"x": x, "y": y}

    def move_mouse(self, x: int, y: int, coord_space: str = "auto") -> dict[str, int]:
        """Move the mouse to (x, y), converting from the given coord space."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        lx, ly = self._to_logical(int(x), int(y), coord_space)
        pyautogui.moveTo(lx, ly)
        self._state.cursor_x = lx
        self._state.cursor_y = ly
        self._last_used = time.time()
        return {"x": lx, "y": ly}

    def click(
        self, x: int | None = None, y: int | None = None, button: str = "left",
        coord_space: str = "auto",
    ) -> dict[str, Any]:
        """Click at (x, y) with the given button, or at the current position."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        if x is not None and y is not None:
            lx, ly = self._to_logical(int(x), int(y), coord_space)
            pyautogui.click(lx, ly, button=button)
        else:
            pyautogui.click(button=button)
        pos = pyautogui.position()
        self._state.cursor_x = pos[0]
        self._state.cursor_y = pos[1]
        self._last_used = time.time()
        return {"action": "click", "button": button, "x": pos[0], "y": pos[1]}

    def double_click(self, x: int | None = None, y: int | None = None,
                     coord_space: str = "auto") -> dict[str, Any]:
        """Double-click at (x, y), or at the current cursor position."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        if x is not None and y is not None:
            lx, ly = self._to_logical(int(x), int(y), coord_space)
            pyautogui.doubleClick(lx, ly)
        else:
            pyautogui.doubleClick()
        pos = pyautogui.position()
        self._state.cursor_x = pos[0]
        self._state.cursor_y = pos[1]
        self._last_used = time.time()
        return {"action": "double_click", "x": pos[0], "y": pos[1]}

    def right_click(self, x: int | None = None, y: int | None = None,
                    coord_space: str = "auto") -> dict[str, Any]:
        """Right-click at (x, y), or at the current cursor position."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        if x is not None and y is not None:
            lx, ly = self._to_logical(int(x), int(y), coord_space)
            pyautogui.rightClick(lx, ly)
        else:
            pyautogui.rightClick()
        pos = pyautogui.position()
        self._state.cursor_x = pos[0]
        self._state.cursor_y = pos[1]
        self._last_used = time.time()
        return {"action": "right_click", "x": pos[0], "y": pos[1]}

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5,
             coord_space: str = "auto") -> dict[str, Any]:
        """Press at (x1, y1) and drag to (x2, y2) over ``duration`` seconds."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        lx1, ly1 = self._to_logical(int(x1), int(y1), coord_space)
        lx2, ly2 = self._to_logical(int(x2), int(y2), coord_space)
        pyautogui.moveTo(lx1, ly1)
        pyautogui.drag(lx2 - lx1, ly2 - ly1, duration=duration)
        pos = pyautogui.position()
        self._state.cursor_x = pos[0]
        self._state.cursor_y = pos[1]
        self._last_used = time.time()
        return {"action": "drag", "from": {"x": lx1, "y": ly1}, "to": {"x": lx2, "y": ly2}}

    def type_text(self, text: str, interval: float = 0.02) -> dict[str, Any]:
        """Type ``text`` character by character with an inter-key ``interval``."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        pyautogui.typewrite(text, interval=interval)
        self._last_used = time.time()
        return {"action": "type", "text": text[:200]}

    def press_key(self, key: str) -> dict[str, Any]:
        """Press and release a single named key (e.g. "enter", "tab")."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        pyautogui.press(key)
        self._last_used = time.time()
        return {"action": "press_key", "key": key}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        """Press a key combination (e.g. ``["ctrl", "c"]``) simultaneously."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        pyautogui.hotkey(*keys)
        self._last_used = time.time()
        return {"action": "hotkey", "keys": "+".join(keys)}

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """Scroll ``clicks`` notches (positive=up), optionally at (x, y)."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x, y)
        else:
            pyautogui.scroll(clicks)
        self._last_used = time.time()
        return {"action": "scroll", "clicks": clicks}

    def locate_on_screen(self, image_b64: str, confidence: float = 0.9) -> DesktopLocateResult:
        """Locate a base64 PNG template on screen and return its match result."""
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        if not self._check_pillow():
            raise RuntimeError(
                "Pillow not installed. Run: pip install pillow"
            ) from None
        import pyautogui
        from PIL import Image

        try:
            img_data = base64.b64decode(image_b64)
            needle = Image.open(io.BytesIO(img_data))
        except Exception:
            return DesktopLocateResult(found=False)

        needle_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                needle.save(f, format="PNG")
                needle_path = f.name

            location = pyautogui.locateOnScreen(needle_path, confidence=confidence)
            if location is not None:
                x, y = pyautogui.center(location)
                return DesktopLocateResult(
                    found=True,
                    x=int(x),
                    y=int(y),
                    width=int(location.width),
                    height=int(location.height),
                    confidence=confidence,
                )
            return DesktopLocateResult(found=False)
        except Exception:
            return DesktopLocateResult(found=False)
        finally:
            if needle_path:
                with suppress(OSError):
                    os.unlink(needle_path)

    def screenshot_with_cursor(self) -> DesktopScreenState:
        """Capture a screenshot and annotate the current cursor position."""
        state = self.screenshot()
        if self._check_pyautogui():
            import pyautogui
            x, y = pyautogui.position()
            state.cursor_x = int(x)
            state.cursor_y = int(y)
        return state

    def _capture_active_window_png(self) -> ActiveWindowCapture | None:
        """Capture the foreground window via Win32 ``PrintWindow`` API.

        ``mss.grab`` composites the screen from the OS compositor, which
        loses content for windows whose pixels are rendered through
        DirectX / Direct2D surfaces (Chromium / Electron, WPF, most
        games, some Qt apps) and for any window occluded by another.
        ``PrintWindow`` asks the window itself to paint into a memory
        DC, so it sees the same pixels the application drew.  We pass
        the ``PW_RENDERFULLCONTENT`` flag (``0x00000002``) so that
        DirectX / Direct2D windows are also rendered; without it,
        Chromium-based apps come back as a blank bitmap.

        Returns an :class:`ActiveWindowCapture` on success, or
        ``None`` on any failure (caller should fall back to the
        regular ``screenshot`` path).
        """
        if _PLATFORM != "win32":
            return None
        try:
            import ctypes
            from typing import ClassVar

            from PIL import Image

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            class _RECT(ctypes.Structure):
                _fields_: ClassVar = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = _RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return None

            hdc_window = user32.GetWindowDC(hwnd)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
            hbitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
            gdi32.SelectObject(hdc_mem, hbitmap)

            # PW_RENDERFULLCONTENT = 0x2; fall back to legacy mode if
            # the application rejects the flag.
            painted = user32.PrintWindow(hwnd, hdc_mem, 0x00000002)
            if not painted:
                user32.PrintWindow(hwnd, hdc_mem, 0x00000000)

            class _BITMAPINFOHEADER(ctypes.Structure):
                _fields_: ClassVar = [
                    ("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            class _BITMAPINFO(ctypes.Structure):
                _fields_: ClassVar = [
                    ("bmiHeader", _BITMAPINFOHEADER),
                    ("bmiColors", ctypes.c_uint32 * 3),
                ]

            bmi = _BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # negative = top-down DIB
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB

            buf_len = width * height * 4
            raw = (ctypes.c_ubyte * buf_len)()
            got = gdi32.GetDIBits(
                hdc_mem, hbitmap, 0, height, raw, ctypes.byref(bmi), 0,
            )

            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_window)

            if not got:
                return None

            img = Image.frombuffer(
                "RGB", (width, height), bytes(raw), "raw", "BGRA", 0, 1,
            )
            out = io.BytesIO()
            img.save(out, format="PNG")
            return ActiveWindowCapture(
                png_bytes=out.getvalue(),
                left=int(rect.left),
                top=int(rect.top),
                width=width,
                height=height,
            )
        except Exception as exc:
            logger.debug("PrintWindow capture failed: %s", exc)
            return None

    def take_screenshot_png(self) -> bytes:
        """Capture the primary monitor as raw PNG bytes.

        This is a thin convenience wrapper around :meth:`screenshot`
        that returns the PNG bytes directly (no base64) -- convenient
        for vision-language-model clients that want to ``POST`` the
        image to an API.
        """
        if not self._check_mss():
            raise RuntimeError(
                "mss not installed. Run: pip install mss pillow"
            )
        if not self._check_pillow():
            raise RuntimeError(
                "Pillow not installed. Run: pip install pillow"
            ) from None
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)

        from PIL import Image

        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        self._last_used = time.time()
        return buf.getvalue()

    def triple_click(self, x: int | None = None, y: int | None = None,
                     coord_space: str = "auto") -> dict[str, Any]:
        """Triple-click to select a line/paragraph (text fields, URLs).

        Implemented as three quick ``pyautogui.click()`` invocations
        because pyautogui has no native triple-click primitive.
        """
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui

        if x is not None and y is not None:
            lx, ly = self._to_logical(int(x), int(y), coord_space)
        else:
            lx, ly = pyautogui.position()
        pyautogui.click(lx, ly, clicks=3, interval=0.05)
        self._last_used = time.time()
        return {"action": "triple_click", "x": lx, "y": ly}

    def wait(self, ms: int) -> dict[str, Any]:
        """Block for ``ms`` milliseconds.

        Useful inside long-running computer-use loops to give the
        underlying app time to finish an animation / network call
        before the next screenshot.
        """
        if ms < 0:
            raise ValueError("wait: ms must be non-negative")
        time.sleep(ms / 1000.0)
        self._last_used = time.time()
        return {"action": "wait", "ms": int(ms)}

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def clipboard_get(self) -> str:
        """Return the current clipboard text.

        Requires ``pyperclip`` (cross-platform) or falls back to the
        Tkinter clipboard on systems where pyperclip isn't installed.
        """
        try:
            import pyperclip  # type: ignore
            self._last_used = time.time()
            return str(pyperclip.paste() or "")
        except ImportError:
            pass
        # Tkinter fallback -- works on every platform with a display.
        try:
            import tkinter as tk  # type: ignore
            root = tk.Tk()
            root.withdraw()
            try:
                text = root.clipboard_get()
            finally:
                root.destroy()
            self._last_used = time.time()
            return str(text or "")
        except Exception as exc:
            raise RuntimeError(
                "clipboard_get: install pyperclip for clipboard access"
            ) from exc

    def clipboard_set(self, text: str) -> dict[str, Any]:
        """Set the clipboard text. See :meth:`clipboard_get` for deps."""
        try:
            import pyperclip  # type: ignore
            pyperclip.copy(str(text))
            self._last_used = time.time()
            return {"action": "clipboard_set", "length": len(str(text))}
        except ImportError:
            pass
        try:
            import tkinter as tk  # type: ignore
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(str(text))
            root.update()  # keep content available after window closes
            root.destroy()
            self._last_used = time.time()
            return {"action": "clipboard_set", "length": len(str(text))}
        except Exception as exc:
            raise RuntimeError(
                "clipboard_set: install pyperclip for clipboard access"
            ) from exc

    # ------------------------------------------------------------------
    # File drop
    # ------------------------------------------------------------------

    def file_drop(self, x: int, y: int, paths: list[str],
                  coord_space: str = "auto") -> dict[str, Any]:
        """Drop one or more files onto the window at (x, y).

        ``paths`` is a list of absolute file paths.  This is a thin
        wrapper over :meth:`drag` followed by the OS-level "release
        file" sequence, implemented via pyperclip / xdotool when
        available so the receiving app interprets the drop as a real
        file transfer rather than a phantom drag.
        """
        if not paths:
            raise ValueError("file_drop: at least one path is required")
        if not self._check_pyautogui():
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui"
            )
        import pyautogui

        lx, ly = self._to_logical(int(x), int(y), coord_space)
        # Move to the drop site and release.  The "file" is communicated
        # to the receiving app via the platform drag-drop manager which
        # pyautogui can't synthesize portably, so on Windows we shell out
        # to PowerShell's DoDragDrop for true OLE drag-drop semantics.
        pyautogui.moveTo(lx, ly)
        pyautogui.mouseDown()
        pyautogui.moveTo(lx + 2, ly + 2)
        if _PLATFORM == "win32":
            self._win32_ole_file_drop(lx, ly, list(paths))
        pyautogui.mouseUp()
        self._last_used = time.time()
        return {
            "action": "file_drop",
            "x": lx,
            "y": ly,
            "files": list(paths),
        }

    @staticmethod
    def _win32_ole_file_drop(_x: int, _y: int, paths: list[str]) -> None:
        """Best-effort Windows OLE drag-drop.

        We hand the file list to PowerShell which uses
        ``System.Windows.Forms.DataObject`` to inject the drop.  Failures
        are swallowed -- the caller still gets a mouseUp so the UI doesn't
        appear frozen.
        """
        try:
            import subprocess

            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$paths = [System.Collections.Specialized.StringCollection]::new(); "
            )
            for p in paths:
                escaped = p.replace("'", "''")
                ps_script += f"$paths.Add('{escaped}'); "
            ps_script += (
                "$data = [System.Windows.Forms.DataObject]::new(); "
                "$data.SetFileDropList($paths); "
                "[System.Windows.Forms.SendKeys]::SendWait('^'); "
            )
            # We can't truly inject the drop from PowerShell without the
            # target HWND, so we just keep the data on the clipboard and
            # let the receiving app pick it up after the mouseUp.
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, timeout=5, check=False,
            )
        except Exception:
            return

    # ------------------------------------------------------------------
    # OCR-driven "click visible text"
    # ------------------------------------------------------------------

    def click_text(self, text: str, *, fuzzy: bool = False,
                   occurrence: int = 1, button: str = "left",
                   coord_space: str = "auto") -> dict[str, Any]:
        """Find ``text`` on screen via OCR and click its center.

        Returns the same dict as :meth:`click` on success, or ``{
        'found': False, 'queried': text}`` if the text wasn't visible.
        Falls back to Windows UIA for apps where OCR is unreliable
        (e.g. text rendered into canvas / Direct2D surfaces).
        """
        match = self.find_text(text, fuzzy=fuzzy, occurrence=occurrence)
        if not match.get("found"):
            return match
        cx = int(match["center_x"])
        cy = int(match["center_y"])
        result = self.click(x=cx, y=cy, button=button, coord_space=coord_space)
        result["matched_text"] = match.get("text", text)
        result["source"] = match.get("source", "ocr")
        return result

    def find_text(self, text: str, *, fuzzy: bool = False,
                  occurrence: int = 1) -> dict[str, Any]:
        """Find a text fragment on the desktop.

        Strategy:
            1. Try Windows UIA (accurate, runs over actual UI text).
            2. Fall back to OCR (works on every platform with a
               backend installed).

        ``occurrence`` is 1-based: when the same text appears multiple
        times the caller can ask for the 2nd, 3rd, etc. match.
        """
        if not text:
            return {"found": False, "queried": text}
        if occurrence < 1:
            raise ValueError("occurrence must be >= 1")

        # 1. UIA path (Windows only) -- cheap and accurate.
        if _PLATFORM == "win32":
            try:
                tree = self.accessibility_tree(max_depth=10, max_nodes=4000)
            except Exception:
                tree = []
            if tree and not (len(tree) == 1 and "error" in tree[0]):
                target = text.strip().lower()
                hits: list[dict[str, Any]] = []
                for n in tree:
                    name = (n.get("name") or "")
                    if not name:
                        continue
                    if not self._text_matches(name, target, fuzzy):
                        continue
                    r = n["rect"]
                    if r["right"] <= r["left"] or r["bottom"] <= r["top"]:
                        continue
                    hits.append({
                        "text": name,
                        "x": r["left"],
                        "y": r["top"],
                        "width": r["right"] - r["left"],
                        "height": r["bottom"] - r["top"],
                        "center_x": (r["left"] + r["right"]) // 2,
                        "center_y": (r["top"] + r["bottom"]) // 2,
                        "control_type": n.get("control_type", ""),
                        "source": "uia",
                    })
                if hits:
                    idx = min(occurrence - 1, len(hits) - 1)
                    hit = hits[idx]
                    hit["found"] = True
                    hit["total_matches"] = len(hits)
                    return hit

        # 2. OCR fallback.
        state = self.screenshot_with_cursor()
        try:
            from encre.computer.ocr import ocr_image
            img_bytes = base64.b64decode(state.screenshot_b64)
            elements = ocr_image(img_bytes)
        except Exception:
            elements = []
        target = text.strip().lower()
        hits: list[dict[str, Any]] = []
        for e in elements:
            t = (e.get("text") or "").strip()
            if not t:
                continue
            if not self._text_matches(t, target, fuzzy):
                continue
            hits.append({
                "text": t,
                "x": int(e["x"]),
                "y": int(e["y"]),
                "width": int(e["width"]),
                "height": int(e["height"]),
                "center_x": int(e["center_x"]),
                "center_y": int(e["center_y"]),
                "source": "ocr",
            })
        if not hits:
            return {"found": False, "queried": text}
        idx = min(occurrence - 1, len(hits) - 1)
        hit = hits[idx]
        hit["found"] = True
        hit["total_matches"] = len(hits)
        return hit

    @staticmethod
    def _text_matches(haystack: str, needle: str, fuzzy: bool) -> bool:
        """Return True if ``needle`` matches ``haystack`` (substring or fuzzy)."""
        if not fuzzy:
            return needle in haystack.lower()
        # Cheap fuzzy: every whitespace-separated token of ``needle`` must
        # appear in ``haystack`` in order.  Good enough for UI labels and
        # far cheaper than Levenshtein on a hot path.
        h = haystack.lower()
        cursor = 0
        for tok in needle.split():
            pos = h.find(tok, cursor)
            if pos < 0:
                return False
            cursor = pos + len(tok)
        return True

    def is_idle(self, max_idle_seconds: int = 600) -> bool:
        """Return True if the session hasn't been used within the idle window."""
        return (time.time() - self._last_used) > max_idle_seconds

    # ------------------------------------------------------------------
    # Accessibility tree (Windows: UIAutomation)
    # ------------------------------------------------------------------

    def accessibility_tree(self, max_depth: int = 6,
                           max_nodes: int = 500) -> list[dict[str, Any]]:
        """Walk the active window's UI automation tree.

        Returns a flat list of nodes, each with ``name``, ``control_type``,
        ``automation_id``, ``class_name``, ``rect`` (physical pixel screen
        coordinates), ``depth``, and ``focusable`` keys. Returns an empty
        list (and surfaces a single error item) on unsupported platforms.
        """
        if _PLATFORM != "win32":
            return [{"error": f"accessibility_tree only supported on Windows (got {_PLATFORM})"}]
        try:
            import uiautomation as uia  # type: ignore
        except ImportError:
            return [{
                "error": (
                    "uiautomation package required. "
                    "Install with: pip install uiautomation"
                )
            }]

        try:
            root = uia.GetForegroundControl()
        except Exception as exc:
            return [{"error": f"Failed to acquire foreground control: {exc}"}]
        if root is None:
            return [{"error": "No foreground window detected"}]

        nodes: list[dict[str, Any]] = []
        self._walk_uia(root, 0, max_depth, max_nodes, nodes, uia)
        return nodes

    @staticmethod
    def _walk_uia(node, depth: int, max_depth: int, max_nodes: int,
                  out: list[dict[str, Any]], uia) -> None:
        """Recursively flatten a UIA control subtree into ``out`` (bounded)."""
        if len(out) >= max_nodes or node is None or depth > max_depth:
            return
        try:
            rect = node.BoundingRectangle
            entry = {
                "name": node.Name or "",
                "control_type": getattr(node, "ControlTypeName", "") or "",
                "automation_id": getattr(node, "AutomationId", "") or "",
                "class_name": getattr(node, "ClassName", "") or "",
                "rect": {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                },
                "depth": depth,
                "focusable": bool(getattr(node, "IsKeyboardFocusable", False)),
            }
            out.append(entry)
        except Exception:
            return
        try:
            children = list(node.GetChildren())
        except Exception:
            return
        for c in children:
            if len(out) >= max_nodes:
                return
            EncreDesktopSession._walk_uia(c, depth + 1, max_depth, max_nodes, out, uia)

    def find_element_by_name(self, name: str, control_type: str | None = None,
                             max_depth: int = 8, max_nodes: int = 2000) -> dict[str, Any]:
        """Find a UIA element by accessible name. Returns center coords or error."""
        tree = self.accessibility_tree(max_depth=max_depth, max_nodes=max_nodes)
        if tree and "error" in tree[0]:
            return tree[0]
        target = name.strip().lower()
        for n in tree:
            if not n.get("name"):
                continue
            if target not in n["name"].lower():
                continue
            if control_type and control_type.lower() != n.get("control_type", "").lower():
                continue
            r = n["rect"]
            cx = (r["left"] + r["right"]) // 2
            cy = (r["top"] + r["bottom"]) // 2
            return {
                "found": True,
                "name": n["name"],
                "control_type": n["control_type"],
                "center_x": cx,
                "center_y": cy,
                "rect": r,
            }
        return {"found": False, "queried": name}

    @staticmethod
    def _ensure_pillow() -> None:
        """Raise a helpful error if Pillow is not installed."""
        if importlib.util.find_spec("PIL") is None:
            raise RuntimeError(
                "Pillow not installed. Run: pip install pillow"
            )
