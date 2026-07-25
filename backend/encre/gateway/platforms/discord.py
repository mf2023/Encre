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

#
# discord.py
#
# Platform adapter for Discord in the Encre gateway framework.
# Provides the DiscordAdapter class that connects to the Discord gateway
# via WebSocket and dispatches normalized MessageEvents.
#
# Exported classes:
#   - DiscordAdapter
#
import asyncio
import logging
from typing import Any

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.discord")

try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordAdapter(BasePlatformAdapter):
    """Discord bot adapter using discord.py.

    Connects to Discord via WebSocket gateway and relays messages to the
    Encre gateway for AI processing. The adapter dispatches incoming
    :class:`MessageEvent` instances and streams responses back to
    Discord channels.

    To use:
        1. Install ``discord.py``
        2. Create a bot application at https://discord.com/developers
           and obtain its token
        3. Pass the ``token`` via PlatformConfig

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.gateway.platforms.discord import DiscordAdapter  # noqa: E402
        from encre.gateway.config import PlatformConfig, Platform  # noqa: E402

        async def main():
            config = PlatformConfig(enabled=True, token="YOUR_BOT_TOKEN")
            adapter = DiscordAdapter(config)
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    supports_code_blocks: bool = True
    max_message_length: int = 2000

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform = Platform.DISCORD,
    ) -> None:
        """Initialize the Discord adapter.

        Args:
            config: Platform configuration containing the bot token.
            platform: The Platform enum value.
        """
        super().__init__(config=config, platform=platform)
        if not DISCORD_AVAILABLE:
            raise ImportError(
                "discord.py is required. "
                "Install with: pip install discord.py"
            )
        self._token = config.token or config.extra.get("bot_token", "")
        self._discord_client: discord.Client | None = None
        self._ready = asyncio.Event()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Initialize the Discord client and connect to the gateway."""
        intents = discord.Intents.default()
        intents.message_content = True

        class _BotClient(discord.Client):
            """Internal discord.Client subclass that forwards events to the adapter."""
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
            self._discord_client = _BotClient(self)
            logger.info("[discord] Step 1: Client created")
        except Exception as e:
            logger.error("[discord] Step 1 failed: create _BotClient: %s", e)
            return False

        try:
            _t = asyncio.ensure_future(self._discord_client.start(self._token))
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

        self._running = True
        logger.info("[discord] Connected and ready")
        return True

    async def disconnect(self) -> None:
        """Disconnect the Discord client."""
        self._running = False
        self._ready.clear()
        await self._cancel_background_tasks()
        if self._discord_client:
            try:
                await self._discord_client.close()
            except Exception as e:
                logger.warning("[discord] Close error: %s", e)
            self._discord_client = None
        logger.info("[discord] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a Discord channel.

        Messages longer than 2000 characters are split into multiple
        messages (Discord's character limit).
        """
        if self._discord_client is None:
            return SendResult(success=False, error="Client not connected")
        channel = self._discord_client.get_channel(int(chat_id))
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

            return SendResult(
                success=True,
                message_id=str(first_message.id) if first_message else None,
                raw=first_message,
            )
        except Exception as e:
            logger.error("[discord] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Get information about a Discord channel."""
        return {"id": chat_id, "platform": self.name}

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to the Discord channel."""
        if self._discord_client is None:
            return
        channel = self._discord_client.get_channel(int(chat_id))
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

        # Normalize the Discord channel into the Hermes chat_type vocabulary.
        # Threads carry parent_id; DM channels are private; everything else is
        # a guild text/voice channel.  scope_id (guild) is REQUIRED for Discord
        # server isolation -- two guilds must never collide into one session.
        chan = message.channel
        parent_id = getattr(chan, "parent_id", None)
        is_thread = parent_id is not None and hasattr(chan, "parent")
        guild = getattr(message, "guild", None)
        guild_id = str(guild.id) if guild is not None else None
        if is_thread:
            chat_type = "thread"
            chat_id = str(parent_id)  # parent channel -- shared-thread key base
            thread_id = str(chan.id)
        elif hasattr(chan, "recipient") or str(getattr(chan, "type", "")) == "ChannelType.private":
            chat_type = "dm"
            chat_id = str(chan.id)
            thread_id = None
        else:
            chat_type = "group"
            chat_id = str(chan.id)
            thread_id = None

        source = SessionSource(
            platform=self.name,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=getattr(chan, "name", None),
            user_id=user_id,
            user_name=str(message.author) if message.author else None,
            thread_id=thread_id,
            scope_id=guild_id,
        )

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=message_id,
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            raw_message=message,
            source=source,
        )

        task = asyncio.create_task(self._dispatch_event(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _dispatch_event(self, event: MessageEvent) -> None:
        """Send a typing indicator, then route the event via handle_message.

        handle_message builds the session key (already populated on ``event``),
        runs the two-level guard, and dispatches to the gateway -- giving each
        Discord channel/thread/DM its own agent session.
        """
        if event.source and event.source.chat_id:
            try:
                await self.send_typing(event.source.chat_id)
            except Exception:
                pass
        await self.handle_message(event)


# ── Platform registration ─────────────────────────────────────────────────────

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return DISCORD_AVAILABLE


platform_registry.register(PlatformEntry(
    name="discord",
    label="Discord",
    platform=Platform.DISCORD,
    adapter_factory=lambda cfg: DiscordAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["DISCORD_BOT_TOKEN"],
))
