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

import asyncio
import logging
import re
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.slack")

try:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_bolt.async_app import AsyncApp
    from slack_sdk.web.async_client import AsyncWebClient

    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    AsyncApp = Any  # type: ignore[misc,assignment]
    AsyncSocketModeHandler = Any  # type: ignore[misc,assignment]
    AsyncWebClient = Any  # type: ignore[misc,assignment]


class SlackAdapter(BaseAdapter):
    """Slack bot adapter using Socket Mode (slack-bolt).

    Connects to Slack via Socket Mode and relays messages to the
    Encre gateway for AI processing. Supports DMs and channel messages
    with thread replies.

    Requires two tokens:
      - ``bot_token`` (xoxb-...) -- for API calls (chat.postMessage, etc.)
      - ``app_token`` (xapp-...) -- for Socket Mode connection

    To use:
        1. Install ``slack-bolt`` and ``slack-sdk``
        2. Create a Slack app at https://api.slack.com/apps
        3. Enable Socket Mode and generate an App-Level Token
        4. Install the app to your workspace and get the Bot Token
        5. Pass tokens to the constructor

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.slack import SlackAdapter  # noqa: E402

        async def main():
            adapter = SlackAdapter(
                bot_token="xoxb-...",
                app_token="xapp-...",
            )
            await adapter.start()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.stop()

        asyncio.run(main())
    """

    name = "slack"

    MAX_MESSAGE_LENGTH = 39000

    def __init__(
        self,
        bot_token: str = "",
        *,
        app_token: str = "",
        signing_secret: str = "",
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
        port: int = 18796,
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not SLACK_AVAILABLE:
            raise ImportError(
                "slack-bolt and slack-sdk are required. "
                "Install with: pip install slack-bolt slack-sdk"
            )
        self._bot_token = bot_token
        self._app_token = app_token
        self._signing_secret = signing_secret
        self._port = port
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._web_client: AsyncWebClient | None = None
        self._bot_user_id: str = ""
        self._ready = asyncio.Event()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to Slack via Socket Mode."""
        try:
            self._app = AsyncApp(
                token=self._bot_token,
                signing_secret=self._signing_secret or None,
            )
            self._web_client = AsyncWebClient(token=self._bot_token)
            logger.info("[slack] Step 1: AsyncApp + AsyncWebClient created")
        except Exception as e:
            logger.error("[slack] Step 1 failed: create AsyncApp/AsyncWebClient: %s", e)
            return False

        try:
            auth_response = await self._web_client.auth_test()
            self._bot_user_id = auth_response.get("user_id", "")
            logger.info("[slack] Step 2: Auth test passed (user_id=%s)", self._bot_user_id)
        except Exception as e:
            logger.error("[slack] Step 2 failed: auth_test: %s", e)
            return False

        try:
            @self._app.event("message")
            async def handle_message_event(event: dict, _say: Any) -> None:
                await self._handle_message(event)

            @self._app.event("app_mention")
            async def handle_app_mention(event: dict, _say: Any) -> None:
                await self._handle_message(event)
            logger.info("[slack] Step 3: Event handlers registered")
        except Exception as e:
            logger.error("[slack] Step 3 failed: register handlers: %s", e)
            return False

        try:
            self._handler = AsyncSocketModeHandler(
                app=self._app,
                app_token=self._app_token,
            )
            _t = asyncio.ensure_future(self._handler.start_async())
            self._background_tasks.add(_t)
            logger.info("[slack] Step 4: SocketModeHandler start scheduled")
        except Exception as e:
            logger.error("[slack] Step 4 failed: start SocketModeHandler: %s", e)
            return False

        self._mark_connected()
        self._ready.set()
        logger.info(
            "[slack] Connected as bot user %s",
            auth_response.get("user", "unknown"),
        )
        return True

    async def disconnect(self) -> None:
        """Disconnect from Slack and close Socket Mode handler."""
        await super().disconnect()
        self._ready.clear()
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception as e:
                logger.warning("[slack] Socket Mode handler close error: %s", e)
            self._handler = None
        self._app = None
        self._web_client = None
        logger.info("[slack] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a Slack channel or DM."""
        client = self._web_client
        if client is None:
            return SendResult(success=False, error="Not connected")
        try:
            formatted = self._format_markdown(content)
            chunks = self._chunk_message(formatted)

            thread_ts: str | None = None
            if metadata:
                thread_ts = metadata.get("thread_id") or metadata.get("thread_ts")
            if not thread_ts and reply_to:
                thread_ts = reply_to

            last_result: dict[str, Any] | None = None
            for chunk in chunks:
                kwargs: dict[str, Any] = {
                    "channel": chat_id,
                    "text": chunk,
                    "mrkdwn": True,
                }
                if thread_ts:
                    kwargs["thread_ts"] = thread_ts
                result = await client.chat_postMessage(**kwargs)
                if isinstance(result, dict):
                    last_result = result

            sent_ts = ""
            if last_result:
                sent_ts = last_result.get("ts", "") or ""

            return SendResult(
                success=True,
                message_id=sent_ts,
            )
        except Exception as e:
            logger.error("[slack] Send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, _chat_id: str) -> None:
        """Send a typing indicator using Slack's assistant_threads.setStatus."""
        client = self._web_client
        if client is None:
            return
        try:
            await client.api_test()
        except Exception as e:
            logger.warning("[slack] send_typing error: %s", e)

    # ── Message Handler ────────────────────────────────────────────────────

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """Process an incoming Slack message event."""
        subtype = event.get("subtype", "")
        if subtype in {"message_changed", "message_deleted"}:
            return

        bot_id = event.get("bot_id")
        if bot_id:
            msg_user = event.get("user", "")
            if msg_user and msg_user == self._bot_user_id:
                return

        text = event.get("text", "") or ""
        channel = event.get("channel", "") or ""
        ts = event.get("ts", "") or ""
        user_id = event.get("user", "") or ""

        if not channel or not text:
            return

        channel_type = event.get("channel_type", "")
        if not channel_type and channel.startswith("D"):
            channel_type = "im"

        thread_ts = event.get("thread_ts") or ts
        is_thread_reply = bool(event.get("thread_ts")) and event.get("thread_ts") != ts

        reply_to_message_id: str | None = None
        reply_to_text: str | None = None
        if is_thread_reply and thread_ts != ts:
            reply_to_message_id = thread_ts

        msg_event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=ts,
            chat_id=channel,
            user_id=user_id,
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            raw=event,
        )

        self.dispatch_message(msg_event)

        task = asyncio.create_task(self._process_chat(channel, text))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response."""
        session_id = self.get_session(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)

    # ── Markdown Formatting ────────────────────────────────────────────────

    def _format_markdown(self, content: str) -> str:
        """Convert standard markdown to Slack mrkdwn format."""
        if not content:
            return content

        placeholders: dict[str, str] = {}
        counter = [0]

        def _ph(value: str) -> str:
            key = f"\x00SL{counter[0]}\x00"
            counter[0] += 1
            placeholders[key] = value
            return key

        text = content

        text = re.sub(
            r"(```(?:[^\n]*\n)?[\s\S]*?```)",
            lambda m: _ph(m.group(0)),
            text,
        )

        text = re.sub(r"(`[^`]+`)", lambda m: _ph(m.group(0)), text)

        def _convert_markdown_link(m: re.Match[str]) -> str:
            label = m.group(1)
            url = m.group(2).strip()
            if url.startswith("<") and url.endswith(">"):
                url = url[1:-1].strip()
            return _ph(f"<{url}|{label}>")

        text = re.sub(
            r"(?<!!)\[([^\]]+)\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)",
            _convert_markdown_link,
            text,
        )

        text = re.sub(
            r"(<(?:[@#!]|(?:https?|mailto|tel):)[^>\n]+>)",
            lambda m: _ph(m.group(1)),
            text,
        )

        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def _convert_header(m: re.Match[str]) -> str:
            inner = m.group(1).strip()
            inner = re.sub(r"\*\*(.+?)\*\*", r"\1", inner)
            return _ph(f"*{inner}*")

        text = re.sub(r"^#{1,6}\s+(.+)$", _convert_header, text, flags=re.MULTILINE)

        text = re.sub(
            r"\*\*\*(.+?)\*\*\*",
            lambda m: _ph(f"*_{m.group(1)}_*"),
            text,
        )

        text = re.sub(
            r"\*\*(.+?)\*\*",
            lambda m: _ph(f"*{m.group(1)}*"),
            text,
        )

        text = re.sub(
            r"(?<!\*)\*(\S(?:[^*\n]*?\S)?)\*(?!\*)",
            lambda m: _ph(f"_{m.group(1)}_"),
            text,
        )

        text = re.sub(
            r"~~(.+?)~~",
            lambda m: _ph(f"~{m.group(1)}~"),
            text,
        )

        for key in reversed(list(placeholders.keys())):
            text = text.replace(key, placeholders[key])

        return text

    def _chunk_message(self, content: str) -> list[str]:
        """Split long messages into chunks respecting code block boundaries."""
        if len(content) <= self.MAX_MESSAGE_LENGTH:
            return [content]

        chunks: list[str] = []
        current = ""
        in_code_block = False

        for line in content.split("\n"):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > self.MAX_MESSAGE_LENGTH and current:
                chunks.append(current)
                current = line
            else:
                current = candidate

        if current:
            chunks.append(current)

        if len(chunks) > 1 and in_code_block:
            chunks[-1] += "\n```"

        return chunks
