#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""End-to-end test: adapter -> gateway client -> server -> EventRouter -> back.

Simulates the full QQ/Telegram message flow:
1. Adapter receives a message and calls handle_message (or process_with_stream)
2. GatewayClient sends SUBMIT_STREAM frame (with or without source)
3. GatewayServer._handle_submit_stream resolves session and calls EventRouter
4. EventRouter runs a fake agent (no real LLM) and yields events
5. Events flow back to the adapter via GatewayClient
6. Adapter.process_with_stream sends the final response via adapter.send()

This catches any "message processed but no response sent back" bugs.
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest

from encre.adapters.base import BaseAdapter, MessageEvent, SendResult, SessionSource
from encre.config import EncreConfig
from encre.gateway.client import GatewayClient
from encre.gateway.server import GatewayServer
from encre.gateway.session import SessionStore
from encre.server.session_manager import SessionManager
from encre.utils.types import Finish, TextDelta


# ── Stub adapter that records sends ────────────────────────────────────


class _StubAdapter(BaseAdapter):
    """Adapter that records every send() call."""

    name = "test"

    def __init__(self, gateway_url="ws://127.0.0.1:18799/gateway"):
        super().__init__(gateway_url=gateway_url)
        self.sent: list[tuple[str, str]] = []

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        self.sent.append((chat_id, content))
        return SendResult(success=True, message_id="m1")


# ── Fake agent that yields canned events ───────────────────────────────


class _FakeAgent:
    """Minimal agent mock that covers every attribute/method EventRouter
    accesses on EncreAgent.  No real LLM is called."""

    def __init__(self, response_text: str = "Hello from agent"):
        self._text = response_text

    class _FakeSession:
        metadata = {"channel": "test"}

    session = _FakeSession()
    telemetry = type("obj", (object,), {"session_id": "test"})()
    loop = type("obj", (object,), {"cancel": lambda: None})()

    def add_message(self, role: str, content: str) -> None:
        pass

    async def run(self, *, prompt, system_prompt=None, custom_instructions=None):
        yield TextDelta(text=self._text)
        yield Finish(reason="done")


# ── End-to-end test ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_path_no_source_returns_response():
    """QQ-style legacy path: process_with_stream without source.
    The adapter should receive the response and call send()."""
    import os

    # Pick a unique port to avoid conflicts.
    port = 18799

    # 1. Set up the server side.
    sm = SessionManager()
    config = EncreConfig()
    from encre.channels.base import EventRouter

    router = EventRouter(sm, config)
    store = SessionStore(db_path=Path("/tmp/encre_test_routing.db"))

    # Override adapter session creation to use the fake agent.
    original_create = sm.create_session

    def fake_create(*a, **kw):
        info = original_create(*a, **kw)
        info.agent = _FakeAgent("Hello from agent")
        return info

    sm.create_session = fake_create

    class _Engine:
        _router = router
        _session_store = store

        async def ensure_adapter_session(self, name):
            info = sm.create_session(config=config)
            return info.session_id

    engine = _Engine()

    # 2. Start the gateway server.
    gw = GatewayServer(engine=engine, host="127.0.0.1", port=port)
    await gw.start()

    # 3. Create the adapter and connect its client.
    adapter = _StubAdapter(gateway_url=f"ws://127.0.0.1:{port}/gateway")
    await adapter._client.connect()
    await asyncio.sleep(0.5)  # let the handshake complete

    # 4. Simulate QQ-style: process_with_stream without source.
    await adapter.process_with_stream("hello", "chat-1", session_id=None)

    # 5. Verify the adapter received the response.
    assert len(adapter.sent) >= 1, f"Expected response sent, got {adapter.sent}"
    chat_id, text = adapter.sent[0]
    assert chat_id == "chat-1"
    assert "Hello from agent" in text

    # Cleanup.
    await adapter.disconnect()
    await gw.stop()
    store.close()


@pytest.mark.asyncio
async def test_handle_message_no_handler_fallback_returns_response():
    """handle_message without _message_handler set: falls back to
    process_with_stream with source. The adapter should still get the response."""
    import os
    from pathlib import Path

    port = 18798
    sm = SessionManager()
    config = EncreConfig()
    from encre.channels.base import EventRouter

    router = EventRouter(sm, config)
    store = SessionStore(db_path=Path("/tmp/encre_test_routing2.db"))

    original_create = sm.create_session

    def fake_create(*a, **kw):
        info = original_create(*a, **kw)
        info.agent = _FakeAgent("Response from handle_message")
        return info

    sm.create_session = fake_create

    class _Engine:
        _router = router
        _session_store = store

        async def resolve_session(self, conn, source):
            def _create():
                info = sm.create_session(config=config)
                info.metadata["source"] = source.to_dict()
                info.metadata["channel"] = source.platform
                try:
                    info.agent.session.metadata["channel"] = source.platform
                except Exception:
                    pass
                return info.session_id

            return store.get_or_create(source, _create)

    engine = _Engine()

    gw = GatewayServer(engine=engine, host="127.0.0.1", port=port)
    await gw.start()

    adapter = _StubAdapter(gateway_url=f"ws://127.0.0.1:{port}/gateway")
    await adapter._client.connect()
    await asyncio.sleep(0.5)

    # handle_message without _message_handler -> fallback to process_with_stream with source.
    event = MessageEvent(
        text="hello from handle_message",
        chat_id="chat-2",
        source=SessionSource(platform="test", chat_id="chat-2", chat_type="dm", user_id="u1"),
    )
    await adapter.handle_message(event)

    assert len(adapter.sent) >= 1, f"Expected response sent, got {adapter.sent}"
    chat_id, text = adapter.sent[0]
    assert chat_id == "chat-2"
    assert "Response from handle_message" in text

    await adapter.disconnect()
    await gw.stop()
    store.close()


@pytest.mark.asyncio
async def test_handle_message_with_handler_returns_response():
    """handle_message with _message_handler set: the handler should be called
    and the response should be sent through the normal flow."""
    port = 18797
    sm = SessionManager()
    config = EncreConfig()
    from encre.channels.base import EventRouter

    router = EventRouter(sm, config)
    store = SessionStore(db_path=Path("/tmp/encre_test_routing3.db"))

    original_create = sm.create_session

    def fake_create(*a, **kw):
        info = original_create(*a, **kw)
        info.agent = _FakeAgent("Handler response")
        return info

    sm.create_session = fake_create

    class _Engine:
        _router = router
        _session_store = store

        async def resolve_session(self, conn, source):
            def _create():
                info = sm.create_session(config=config)
                info.metadata["source"] = source.to_dict()
                info.metadata["channel"] = source.platform
                try:
                    info.agent.session.metadata["channel"] = source.platform
                except Exception:
                    pass
                return info.session_id

            return store.get_or_create(source, _create)

    engine = _Engine()

    gw = GatewayServer(engine=engine, host="127.0.0.1", port=port)
    await gw.start()

    adapter = _StubAdapter(gateway_url=f"ws://127.0.0.1:{port}/gateway")
    await adapter._client.connect()
    await asyncio.sleep(0.5)

    # Set a message handler that runs the normal flow.
    handler_called = False

    async def handler(event):
        nonlocal handler_called
        handler_called = True
        # Delegate to process_with_stream (the normal adapter-driven path).
        await adapter.process_with_stream(event.text, event.chat_id or "", source=event.source)

    adapter.set_message_handler(handler)

    event = MessageEvent(
        text="hello with handler",
        chat_id="chat-3",
        source=SessionSource(platform="test", chat_id="chat-3", chat_type="dm", user_id="u1"),
    )
    await adapter.handle_message(event)

    assert handler_called, "handler was not called"
    assert len(adapter.sent) >= 1, f"Expected response sent, got {adapter.sent}"
    chat_id, text = adapter.sent[0]
    assert chat_id == "chat-3"
    assert "Handler response" in text

    await adapter.disconnect()
    await gw.stop()
    store.close()