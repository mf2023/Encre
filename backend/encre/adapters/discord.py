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
from typing import Any

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.discord")

try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordAdapter(BaseAdapter):
    """Discord bot adapter using discord.py.

    Connects to Discord via WebSocket gateway and relays messages to the
    Encre gateway for AI processing. The adapter dispatches incoming
    :class:`MessageEvent` instances and streams responses back to
    Discord channels.

    To use:
        1. Install ``discord.py``
        2. Create a bot application at https://discord.com/developers
           and obtain its token
        3. Pass the ``token`` to the constructor

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.discord import DiscordAdapter  # noqa: E402

        async def main():
            adapter = DiscordAdapter(token="YOUR_BOT_TOKEN")
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "discord"

    def __init__(
        self,
        token: str,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        if not DISCORD_AVAILABLE:
            raise ImportError(
                "discord.py is required. "
                "Install with: pip install discord.py"
            )
        self._token = token
        self._client: discord.Client | None = None
        self._ready = asyncio.Event()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Initialize the Discord client and connect to the gateway."""
        intents = discord.Intents.default()
        intents.message_content = True

        class _BotClient(discord.Client):
            def __init__(self, adapter: DiscordAdapter) -> None:
                super().__init__(intents=intents)
                self._adapter = adapter

            async def on_ready(self) -> None:
                logger.info(
                    "[discord] Bot logged in as %s (id=%s)",
                    self.user,
                    self.user.id if self.user else "unknown",
                )
                self._adapter._ready.set()

            async def on_message(self, message: discord.Message) -> None:
                if message.author == self.user:
                    return
                await self._adapter._handle_message(message)

        try:
            self._client = _BotClient(self)
            logger.info("[discord] Step 1: Client created")
        except Exception as e:
            logger.error("[discord] Step 1 failed: create _BotClient: %s", e)
            return False

        try:
            _t = asyncio.ensure_future(self._client.start(self._token))
            self._background_tasks.add(_t)
            logger.info("[discord] Step 2: Client start scheduled")
        except Exception as e:
            logger.error("[discord] Step 2 failed: schedule client start: %s", e)
            return False

        try:
            await self._ready.wait()
            logger.info("[discord] Step 3: Client ready")
        except Exception as e:
            logger.error("[discord] Step 3 failed: wait for ready: %s", e)
            return False

        self._mark_connected()
        logger.info("[discord] Connected and ready")
        return True

    async def disconnect(self) -> None:
        """Disconnect the Discord client and shut down the gateway."""
        await super().disconnect()
        self._ready.clear()
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning("[discord] Close error: %s", e)
            self._client = None
        logger.info("[discord] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        _metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a Discord channel.

        Messages longer than 2000 characters are split into multiple
        messages (Discord's character limit).
        """
        if self._client is None:
            return SendResult(success=False, error="Client not connected")
        channel = self._client.get_channel(int(chat_id))
        if channel is None:
            return SendResult(
                success=False,
                error=f"Channel {chat_id} not found",
                retryable=True,
            )
        try:
            limit = 2000
            if len(content) <= limit:
                kwargs: dict[str, Any] = {}
                if reply_to is not None:
                    try:
                        msg = await channel.fetch_message(int(reply_to))
                        kwargs["reference"] = msg
                    except Exception:
                        pass
                message = await channel.send(content, **kwargs)
                return SendResult(
                    success=True,
                    message_id=str(message.id),
                    raw=message,
                )

            parts = []
            for i in range(0, len(content), limit):
                parts.append(content[i : i + limit])

            continuation_ids: list[str] = []
            first_message = None
            for part in parts:
                kwargs: dict[str, Any] = {}
                if reply_to is not None and first_message is None:
                    try:
                        msg = await channel.fetch_message(int(reply_to))
                        kwargs["reference"] = msg
                    except Exception:
                        pass
                message = await channel.send(part, **kwargs)
                if first_message is None:
                    first_message = message
                continuation_ids.append(str(message.id))

            return SendResult(
                success=True,
                message_id=str(first_message.id) if first_message else None,
                raw=first_message,
                continuation_message_ids=tuple(continuation_ids),
            )
        except Exception as e:
            logger.error("[discord] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to the Discord channel."""
        if self._client is None:
            return
        channel = self._client.get_channel(int(chat_id))
        if channel is None:
            return
        try:
            async with channel.typing():
                pass
        except Exception as e:
            logger.warning("[discord] send_typing error: %s", e)

    # ── Handlers ───────────────────────────────────────────────────────────

    async def _handle_message(self, message: discord.Message) -> None:
        """Process an incoming message from Discord."""
        chat_id = str(message.channel.id)
        user_id = str(message.author.id)
        text = message.content
        message_id = str(message.id)

        reply_to_message_id: str | None = None
        reply_to_text: str | None = None
        if message.reference and message.reference.message_id:
            try:
                referenced = await message.channel.fetch_message(
                    message.reference.message_id
                )
                reply_to_message_id = str(referenced.id)
                reply_to_text = referenced.content
            except Exception:
                pass

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            raw=message,
        )

        self.dispatch_message(event)

        task = asyncio.create_task(self._process_chat(chat_id, text))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _process_chat(self, chat_id: str, content: str) -> None:
        """Submit content to the gateway and stream the response to chat.

        Uses the base class :meth:`process_with_stream` which handles
        :class:`TextDelta` streaming and final :class:`Finish` delivery.
        """
        session_id = self.get_session(chat_id)
        await self.send_typing(chat_id)
        await self.process_with_stream(content, chat_id, session_id=session_id)
