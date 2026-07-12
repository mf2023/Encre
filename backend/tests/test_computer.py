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

"""Tests for encre.computer.browser -- EncreBrowserSession and BrowserState."""

import time

# ===========================================================================
# BrowserState dataclass
# ===========================================================================

class TestBrowserState:
    """Tests for the BrowserState dataclass."""

    def test_default_creation(self):
        """Test: Default creation."""
        from encre.computer.browser import BrowserState
        state = BrowserState()
        # Verify: state.url == ""
        assert state.url == ""
        # Verify: state.title == ""
        assert state.title == ""
        # Verify: state.html == ""
        assert state.html == ""
        # Verify: state.text == ""
        assert state.text == ""

    def test_creation_with_values(self):
        """Test: Creation with values."""
        from encre.computer.browser import BrowserState
        state = BrowserState(
            url="https://example.com",
            title="Example Domain",
            html="<html><body>Example</body></html>",
            text="Example",
        )
        # Verify: state.url == "https://example.com"
        assert state.url == "https://example.com"
        # Verify: state.title == "Example Domain"
        assert state.title == "Example Domain"
        # Verify: state.html == "<html><body>Example</body></html>"
        assert state.html == "<html><body>Example</body></html>"
        # Verify: state.text == "Example"
        assert state.text == "Example"

    def test_is_dataclass(self):
        """Test: Is dataclass."""
        from dataclasses import is_dataclass

        from encre.computer.browser import BrowserState
        # Verify: is_dataclass(BrowserState)
        assert is_dataclass(BrowserState)

    def test_all_fields_have_defaults(self):
        """Test: All fields have defaults."""
        from encre.computer.browser import BrowserState
        state = BrowserState()
        for field_name in ["url", "title", "html", "text"]:
            # Verify: getattr(state, field_name) == ""
            assert getattr(state, field_name) == ""


# ===========================================================================
# EncreBrowserSession construction
# ===========================================================================

class TestEncreBrowserSessionConstruction:
    """Tests for EncreBrowserSession construction."""

    def test_default_construction(self):
        """Test: Default construction."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # Verify: session is not None
        assert session is not None
        # Verify: session.headless is True
        assert session.headless is True
        # Verify: session.viewport_width == 1280
        assert session.viewport_width == 1280
        # Verify: session.viewport_height == 800
        assert session.viewport_height == 800
        # Verify: session.timeout == 30000
        assert session.timeout == 30000

    def test_custom_construction(self):
        """Test: Custom construction."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession(
            headless=False,
            viewport_width=1920,
            viewport_height=1080,
            timeout=60000,
        )
        # Verify: session.headless is False
        assert session.headless is False
        # Verify: session.viewport_width == 1920
        assert session.viewport_width == 1920
        # Verify: session.viewport_height == 1080
        assert session.viewport_height == 1080
        # Verify: session.timeout == 60000
        assert session.timeout == 60000

    def test_initial_internal_state(self):
        """Test: Initial internal state."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # Verify: session._pw is None
        assert session._pw is None
        # Verify: session._browser is None
        assert session._browser is None
        # Verify: session._context is None
        assert session._context is None
        # Verify: session._page is None
        assert session._page is None

    def test_initial_browser_state_empty(self):
        """Test: Initial browser state empty."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # Verify: session._state.url == ""
        assert session._state.url == ""
        # Verify: session._state.title == ""
        assert session._state.title == ""
        # Verify: session._state.html == ""
        assert session._state.html == ""
        # Verify: session._state.text == ""
        assert session._state.text == ""

    def test_last_used_timestamp_set(self):
        """Test: Last used timestamp set."""
        from encre.computer.browser import EncreBrowserSession
        before = time.time()
        session = EncreBrowserSession()
        after = time.time()
        # Verify: before <= session._last_used <= after
        assert before <= session._last_used <= after


# ===========================================================================
# EncreBrowserSession state methods (no browser needed)
# ===========================================================================

class TestEncreBrowserSessionState:
    """Tests for state methods that don't require Playwright."""

    def test_get_state_before_navigate(self):
        """Test: Get state before navigate."""
        from encre.computer.browser import EncreBrowserSession

        async def _test():
            """Helper: Test."""
            session = EncreBrowserSession()
            state = await session.get_state()
            # Verify: isinstance(state, object)
            assert isinstance(state, object)
            from encre.computer.browser import BrowserState
            # Verify: isinstance(state, BrowserState)
            assert isinstance(state, BrowserState)

        import asyncio
        asyncio.run(_test())

    def test_is_idle_fresh_session(self):
        """Test: Is idle fresh session."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # A fresh session is not idle (last_used is now)
        assert session.is_idle(max_idle_seconds=600) is False

    def test_is_idle_with_custom_threshold(self):
        """Test: Is idle with custom threshold."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # With a zero-second threshold, it should be idle immediately
        assert session.is_idle(max_idle_seconds=0) is True

    def test_save_cookies_before_browser(self):
        """Test: Save cookies before browser."""
        from encre.computer.browser import EncreBrowserSession

        async def _test():
            """Helper: Test."""
            session = EncreBrowserSession()
            cookies = await session.save_cookies()
            # Verify: cookies == []
            assert cookies == []

        import asyncio
        asyncio.run(_test())

    def test_close_before_browser(self):
        """Test: Close before browser."""
        from encre.computer.browser import EncreBrowserSession

        async def _test():
            """Helper: Test."""
            session = EncreBrowserSession()
            await session.close()
            # Verify: session._browser is None
            assert session._browser is None
            # Verify: session._pw is None
            assert session._pw is None
            # Verify: session._page is None
            assert session._page is None

        import asyncio
        asyncio.run(_test())

    def test_close_is_idempotent(self):
        """Test: Close is idempotent."""
        from encre.computer.browser import EncreBrowserSession

        async def _test():
            """Helper: Test."""
            session = EncreBrowserSession()
            await session.close()
            await session.close()
            # Should not raise

        import asyncio
        asyncio.run(_test())


# ===========================================================================
# EncreBrowserSession public API exports
# ===========================================================================

class TestBrowserPublicAPI:
    """Verify the public API matches expectations."""

    def test_public_exports(self):
        """Test: Public exports."""
        from encre.computer import BrowserState, EncreBrowserSession
        # Verify: EncreBrowserSession is not None
        assert EncreBrowserSession is not None
        # Verify: BrowserState is not None
        assert BrowserState is not None

    def test_browser_methods_exist(self):
        """Test: Browser methods exist."""
        from encre.computer.browser import EncreBrowserSession
        session = EncreBrowserSession()
        # All expected async methods should exist
        assert hasattr(session, "navigate")
        # Verify: hasattr(session, "click")
        assert hasattr(session, "click")
        # Verify: hasattr(session, "type_text")
        assert hasattr(session, "type_text")
        # Verify: hasattr(session, "screenshot")
        assert hasattr(session, "screenshot")
        # Verify: hasattr(session, "get_html")
        assert hasattr(session, "get_html")
        # Verify: hasattr(session, "get_text")
        assert hasattr(session, "get_text")
        # Verify: hasattr(session, "execute_js")
        assert hasattr(session, "execute_js")
        # Verify: hasattr(session, "get_state")
        assert hasattr(session, "get_state")
        # Verify: hasattr(session, "wait_for_selector")
        assert hasattr(session, "wait_for_selector")
        # Verify: hasattr(session, "scroll_to")
        assert hasattr(session, "scroll_to")
        # Verify: hasattr(session, "fill_form")
        assert hasattr(session, "fill_form")
        # Verify: hasattr(session, "press_key")
        assert hasattr(session, "press_key")
        # Verify: hasattr(session, "save_cookies")
        assert hasattr(session, "save_cookies")
        # Verify: hasattr(session, "load_cookies")
        assert hasattr(session, "load_cookies")
        # Verify: hasattr(session, "close")
        assert hasattr(session, "close")
        # Verify: hasattr(session, "is_idle")
        assert hasattr(session, "is_idle")
