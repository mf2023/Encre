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
# telegram.py
#
# Platform adapter for Telegram in the Encre gateway framework.
# Provides the TelegramAdapter class that connects to the Telegram Bot API
# via long-polling and dispatches normalized MessageEvents to the gateway.
#
# Exported classes:
#   - TelegramAdapter
#
import asyncio
import logging
from typing import Any

from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from encre.gateway.session import SessionSource
from encre.gateway.config import Platform, PlatformConfig

logger = logging.getLogger("encre.gateway.platforms.telegram")

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


class TelegramAdapter(BasePlatformAdapter):
    """Telegram bot adapter using python-telegram-bot v20+.

    Connects to Telegram via long-polling and relays messages to the
    Encre gateway for AI processing. The adapter dispatches incoming
    :class:`MessageEvent` instances and streams responses back to
    Telegram chat.

    To use:
        1. Install ``python-telegram-bot`` (v20+)
        2. Create a bot via `@BotFather <https://t.me/BotFather>`_ and
           obtain its token
        3. Pass the ``token`` via PlatformConfig

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.gateway.platforms.telegram import TelegramAdapter  # noqa: E402
        from encre.gateway.config import PlatformConfig, Platform  # noqa: E402

        async def main():
            config = PlatformConfig(enabled=True, token="YOUR_BOT_TOKEN")
            adapter = TelegramAdapter(config)
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    @classmethod
    async def validate_config(cls, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate config.

        Args:
            config (dict[str, Any]):

        Returns:
            tuple[bool, str]
        """
        token = config.get("bot_token", "")
        if not token:
            return (False, "bot_token is required")
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as session, session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        bot_name = data.get("result", {}).get("first_name", "")
                        return (True, f"Bot '{bot_name}' authenticated successfully")
                    return (False, f"API error: {data.get('description', 'unknown')}")
                return (False, f"HTTP {resp.status}")
        except TimeoutError:
            return (False, "Connection timed out to api.telegram.org")
        except Exception as e:
            return (False, f"Connection error: {e}")

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform = Platform.TELEGRAM,
    ) -> None:
        """Initialize the Telegram adapter.

        Args:
            config: Platform configuration containing the bot token.
            platform: The Platform enum value.
        """
        super().__init__(config=config, platform=platform)
        if not TELEGRAM_AVAILABLE:
            raise ImportError(
                "python-telegram-bot is required. "
                "Install with: pip install python-telegram-bot"
            )
        self._token = config.token or config.extra.get("bot_token", "")
        self._app: Application | None = None
        self._ready = asyncio.Event()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Initialize the Telegram bot application and start polling."""
        try:
            self._app = Application.builder().token(self._token).build()
            logger.info("[telegram] Step 1: Application built")
        except Exception as e:
            logger.error("[telegram] Step 1 failed: build Application: %s", e)
            return False

        try:
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_update)
            )
            self._app.add_handler(CommandHandler("start", self._handle_start))
            self._app.add_handler(CommandHandler("help", self._handle_help))
            logger.info("[telegram] Step 2: Handlers registered")
        except Exception as e:
            logger.error("[telegram] Step 2 failed: register handlers: %s", e)
            return False

        try:
            await self._app.initialize()
            logger.info("[telegram] Step 3: Application initialized")
        except Exception as e:
            logger.error("[telegram] Step 3 failed: initialize: %s", e)
            return False

        try:
            await self._app.updater.start_polling()
            logger.info("[telegram] Step 4: Polling started")
        except Exception as e:
            logger.error("[telegram] Step 4 failed: start polling: %s", e)
            return False

        try:
            await self._app.start()
            logger.info("[telegram] Step 5: Application started")
        except Exception as e:
            logger.error("[telegram] Step 5 failed: start application: %s", e)
            return False

        self._running = True
        self._ready.set()
        bot_user = self._app.bot.username if self._app.bot else "unknown"
        logger.info("[telegram] Bot @%s connected and polling", bot_user)
        return True

    async def disconnect(self) -> None:
        """Stop polling and shut down the Telegram application."""
        self._running = False
        self._ready.clear()
        await self._cancel_background_tasks()
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("[telegram] Shutdown error: %s", e)
            self._app = None
        logger.info("[telegram] Disconnected")

    # ── Messaging ──────────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to a Telegram chat."""
        bot = self._app.bot if self._app else None
        if bot is None:
            return SendResult(success=False, error="Bot not connected")
        try:
            kwargs: dict[str, Any] = {"chat_id": chat_id, "text": content}
            if reply_to is not None:
                kwargs["reply_to_message_id"] = int(reply_to)
            message = await bot.send_message(**kwargs)
            return SendResult(
                success=True,
                message_id=str(message.message_id),
                raw=message,
            )
        except Exception as e:
            logger.error("[telegram] send error: %s", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Get information about a Telegram chat."""
        return {"id": chat_id, "platform": self.name}

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator to the chat."""
        bot = self._app.bot if self._app else None
        if bot is None:
            return
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception as e:
            logger.warning("[telegram] send_typing error: %s", e)

    # ── Handlers ───────────────────────────────────────────────────────────

    async def _handle_update(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Process an incoming text message from Telegram."""
        if not update.message or not update.message.text:
            return

        message = update.message
        chat_id = str(message.chat_id)
        user_id = str(message.from_user.id) if message.from_user else chat_id
        text = message.text
        message_id = str(message.message_id)

        reply_to_message_id: str | None = None
        reply_to_text: str | None = None
        if message.reply_to_message and message.reply_to_message.text:
            reply_to_message_id = str(message.reply_to_message.message_id)
            reply_to_text = message.reply_to_message.text

        # Normalize the Telegram chat type into the Hermes chat_type vocabulary
        # (dm / group / channel / forum) so build_session_key routes correctly.
        _chat = getattr(message, "chat", None)
        _tg_type = getattr(_chat, "type", "private") if _chat else "private"
        _chat_type_map = {"private": "dm", "group": "group", "supergroup": "group", "channel": "channel"}
        chat_type = _chat_type_map.get(_tg_type, "group")
        thread_id = None
        _thread = getattr(message, "message_thread_id", None)
        if _thread and _tg_type in ("group", "supergroup") and getattr(_chat, "is_forum", False):
            chat_type = "forum"
            thread_id = str(_thread)

        source = SessionSource(
            platform=self.name,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=getattr(_chat, "title", None) if _chat else None,
            user_id=user_id,
            user_name=getattr(getattr(message, "from_user", None), "username", None)
            or getattr(getattr(message, "from_user", None), "full_name", None),
            thread_id=thread_id,
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
        Telegram conversation its own agent session.
        """
        if event.source and event.source.chat_id:
            try:
                await self.send_typing(event.source.chat_id)
            except Exception:
                pass
        await self.handle_message(event)

    async def _handle_start(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /start command."""
        if update.message:
            await update.message.reply_text(
                "Hello! I am a Encre AI agent. "
                "Send me a message and I will respond."
            )

    async def _handle_help(
        self,
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /help command."""
        if update.message:
            await update.message.reply_text(
                "Send me any text message and I will process it using AI.\n\n"
                "Commands:\n"
                "/start - Start the bot\n"
                "/help  - Show this help message"
            )


# ── Platform registration ─────────────────────────────────────────────────────

from encre.gateway.platform_registry import platform_registry, PlatformEntry


def _check_requirements() -> bool:
    return TELEGRAM_AVAILABLE


platform_registry.register(PlatformEntry(
    name="telegram",
    label="Telegram",
    platform=Platform.TELEGRAM,
    adapter_factory=lambda cfg: TelegramAdapter(cfg),
    check_fn=_check_requirements,
    required_env=["TELEGRAM_BOT_TOKEN"],
))
