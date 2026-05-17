#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

import base64
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserState:
    url: str = ""
    title: str = ""
    html: str = ""
    text: str = ""


class YmiBrowserSession:
    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        timeout: int = 30000,
    ):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout = timeout
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._state = BrowserState()
        self._last_used = time.time()

    def _check_playwright(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def _ensure_browser(self):
        if not self._check_playwright():
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height}
            )
            self._context.set_default_timeout(self.timeout)
            self._page = await self._context.new_page()
        self._last_used = time.time()

    async def navigate(self, url: str) -> BrowserState:
        await self._ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded")
        self._state.url = self._page.url
        self._state.title = await self._page.title()
        self._state.html = await self._page.content()
        try:
            self._state.text = await self._page.inner_text("body")
        except Exception:
            self._state.text = ""
        return self._state

    async def click(self, selector: str) -> bool:
        await self._ensure_browser()
        try:
            await self._page.click(selector)
            self._last_used = time.time()
            return True
        except Exception:
            return False

    async def type_text(self, selector: str, text: str) -> bool:
        await self._ensure_browser()
        try:
            await self._page.fill(selector, text)
            self._last_used = time.time()
            return True
        except Exception:
            return False

    async def screenshot(
        self, full_page: bool = False, selector: str | None = None
    ) -> str:
        await self._ensure_browser()
        if selector:
            element = await self._page.query_selector(selector)
            if element is None:
                raise ValueError(f"Element not found: {selector}")
            data = await element.screenshot(type="png")
        else:
            data = await self._page.screenshot(type="png", full_page=full_page)
        self._last_used = time.time()
        return base64.b64encode(data).decode("utf-8")

    async def get_html(self) -> str:
        await self._ensure_browser()
        self._state.html = await self._page.content()
        self._last_used = time.time()
        return self._state.html

    async def get_text(self, selector: str | None = None) -> str:
        await self._ensure_browser()
        if selector:
            element = await self._page.query_selector(selector)
            if element is None:
                raise ValueError(f"Element not found: {selector}")
            text = await element.inner_text()
        else:
            text = await self._page.inner_text("body")
        self._state.text = text
        self._last_used = time.time()
        return text

    async def execute_js(self, code: str) -> Any:
        await self._ensure_browser()
        result = await self._page.evaluate(code)
        self._last_used = time.time()
        return result

    async def get_state(self) -> BrowserState:
        if self._page is not None:
            try:
                self._state.url = self._page.url
                self._state.title = await self._page.title()
            except Exception:
                pass
        return self._state

    async def wait_for_selector(
        self, selector: str, timeout: int | None = None
    ) -> bool:
        await self._ensure_browser()
        try:
            await self._page.wait_for_selector(
                selector, timeout=timeout or self.timeout
            )
            self._last_used = time.time()
            return True
        except Exception:
            return False

    async def scroll_to(self, x: int = 0, y: int = 0) -> None:
        await self._ensure_browser()
        await self._page.evaluate(f"window.scrollTo({x}, {y})")
        self._last_used = time.time()

    async def fill_form(self, fields: dict[str, str]) -> bool:
        await self._ensure_browser()
        try:
            for selector, value in fields.items():
                await self._page.fill(selector, value)
            self._last_used = time.time()
            return True
        except Exception:
            return False

    async def press_key(self, key: str) -> None:
        await self._ensure_browser()
        await self._page.keyboard.press(key)
        self._last_used = time.time()

    async def save_cookies(self) -> list[dict]:
        if self._context is None:
            return []
        cookies = await self._context.cookies()
        return cookies

    async def load_cookies(self, cookies: list[dict]) -> None:
        await self._ensure_browser()
        await self._context.add_cookies(cookies)

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        self._page = None

    def is_idle(self, max_idle_seconds: int = 600) -> bool:
        return (time.time() - self._last_used) > max_idle_seconds
