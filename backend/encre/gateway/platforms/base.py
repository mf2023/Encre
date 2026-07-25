#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

"""Base platform adapter interface.

All platform adapters inherit from :class:`BasePlatformAdapter` and implement
the required abstract methods.  This is the Encre equivalent of Hermes'
``gateway/platforms/base.py``.

Architecture:
    Platform adapters run in the same process as the agent.  Incoming messages
    are normalized into :class:`MessageEvent` and dispatched via
    :meth:`BasePlatformAdapter.handle_message` to the GatewayRunner, which
    routes them through the EventRouter to the AI agent.  Outgoing responses
    are delivered back through :meth:`BasePlatformAdapter.send`.

Key patterns:
    - ABC with 4 abstract methods: connect, disconnect, send, get_chat_info
    - Capability flags for platform-specific behavior (supports_code_blocks, etc.)
    - Standardized MessageEvent / SendResult dataclasses
    - handle_message dispatches to the registered _message_handler (set by GatewayRunner)
"""

import asyncio
import enum
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from encre.gateway.config import Platform, PlatformConfig
from encre.gateway.session import SessionSource

logger = logging.getLogger("encre.gateway.platforms.base")


# -- Message types -------------------------------------------------------------


class MessageType(enum.Enum):
    """Supported message content types."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    LOCATION = "location"
    STICKER = "sticker"
    VOICE = "voice"


# -- MessageEvent --------------------------------------------------------------


@dataclass
class MessageEvent:
    """Normalized incoming message from a platform.

    All platform-specific message formats are translated into this unified
    representation before being dispatched to the agent backend.

    Attributes:
        text: The message text content.
        message_type: The type of content carried by this message.
        source: Structured routing origin (platform/chat_id/chat_type/user).
        raw_message: The original platform-specific message payload.
        message_id: Platform-unique message identifier.
        media_urls: URLs or file paths for attached media.
        media_types: MIME types corresponding to media_urls entries.
        reply_to_message_id: If this is a reply, the id of the parent message.
        reply_to_text: Cached text of the replied-to message.
        reply_to_author_id: Author id of the replied-to message.
        reply_to_author_name: Author name of the replied-to message.
        reply_to_is_own_message: True when replying to the bot's own message.
        auto_skill: Auto-loaded skill(s) for topic/channel bindings.
        channel_prompt: Per-channel ephemeral system prompt.
        channel_context: Channel context recovered by history backfill.
        platform_update_id: Platform-specific update identifier (e.g. Telegram update_id).
    """

    text: str
    message_type: MessageType = MessageType.TEXT
    source: SessionSource | None = None
    raw_message: Any = None
    message_id: Optional[str] = None
    platform_update_id: Optional[int] = None
    media_urls: List[str] = field(default_factory=list)
    media_types: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    reply_to_author_id: Optional[str] = None
    reply_to_author_name: Optional[str] = None
    reply_to_is_own_message: bool = False
    auto_skill: Optional[str | list[str]] = None
    channel_prompt: Optional[str] = None
    channel_context: Optional[str] = None

    def is_command(self) -> bool:
        """Check if this message is a slash command."""
        return self.text.startswith("/")

    def get_command(self) -> str | None:
        """Extract the command name (without leading '/')."""
        if not self.is_command():
            return None
        parts = self.text.split(maxsplit=1)
        raw = parts[0][1:].lower() if parts else None
        if raw and "@" in raw:
            raw = raw.split("@", 1)[0]
        if raw and "/" in raw:
            return None
        return raw

    def get_command_args(self) -> str:
        """Extract command arguments (everything after the command token)."""
        if not self.is_command():
            return self.text
        parts = self.text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""


# -- SendResult ----------------------------------------------------------------


@dataclass
class SendResult:
    """Result of a message send operation.

    Attributes:
        success: Whether the message was sent successfully.
        message_id: Platform-specific id of the sent message.
        error: Human-readable error description if success is False.
        retryable: Whether the failure is transient and retryable.
        retry_after: Server-requested retry delay in seconds.
        error_kind: Machine-readable failure category.
        raw: Platform-specific raw response data.
    """

    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    retry_after: Optional[float] = None
    error_kind: Optional[str] = None
    raw: Any = None


# -- Error classification -------------------------------------------------------

SEND_ERROR_KINDS = frozenset({
    "too_long",
    "bad_format",
    "forbidden",
    "not_found",
    "rate_limited",
    "transient",
    "unknown",
})


def classify_send_error(exc: BaseException | None = None, error_text: str = "") -> str:
    """Map a send exception / error string to a SEND_ERROR_KINDS value."""
    parts: list[str] = []
    if error_text:
        parts.append(str(error_text))
    if exc is not None:
        parts.append(str(exc))
        parts.append(type(exc).__name__)
    blob = " ".join(parts).lower()
    if not blob.strip():
        return "unknown"
    if "message_too_long" in blob or "too long" in blob:
        return "too_long"
    if "can't parse entities" in blob or "unsupported start tag" in blob:
        return "bad_format"
    if "forbidden" in blob or "blocked" in blob or "kicked" in blob:
        return "forbidden"
    if "not found" in blob or "chat not found" in blob:
        return "not_found"
    if ("rate" in blob and "limit" in blob) or "flood" in blob or "too many requests" in blob:
        return "rate_limited"
    if "timeout" in blob or "timed out" in blob or "connection" in blob or "network" in blob:
        return "transient"
    return "unknown"


# -- Message handler type -------------------------------------------------------

MessageHandler = Callable[["BasePlatformAdapter", MessageEvent], Awaitable[None] | None]


# -- BasePlatformAdapter --------------------------------------------------------


class BasePlatformAdapter(ABC):
    """Base class for all platform adapters.

    Subclasses implement platform-specific logic for:
    - Connecting and authenticating
    - Receiving messages
    - Sending messages/responses
    - Handling media

    Capability flags (class-level, override in subclasses):
        supports_code_blocks: Whether the platform renders fenced code blocks.
        supports_async_delivery: Whether the adapter can deliver notifications
            after a turn ends (persistent outbound channel).
        splits_long_messages: Whether the adapter chunks long content itself.
        max_message_length: Platform's per-message size cap (0 = no limit).
        typed_command_prefix: The command prefix users type on this platform.
    """

    # -- Capability flags (override in subclasses) --
    supports_code_blocks: bool = False
    supports_async_delivery: bool = True
    splits_long_messages: bool = False
    max_message_length: int = 0
    typed_command_prefix: str = "/"

    def __init__(self, config: PlatformConfig | None = None, platform: Platform | None = None) -> None:
        self.config = config
        self.platform = platform
        self._message_handler: Optional[MessageHandler] = None
        self._authz: Any = None
        self._pairing: Any = None
        self._running = False
        self._fatal_error_code: Optional[str] = None
        self._fatal_error_message: Optional[str] = None
        self._active_sessions: dict[str, asyncio.Event] = {}
        self._pending_messages: dict[str, list[MessageEvent]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # -- Properties --

    @property
    def name(self) -> str:
        """Platform name string (e.g. 'telegram')."""
        if self.platform is not None:
            return self.platform.value
        return getattr(self, '_name', 'unknown')

    @property
    def running(self) -> bool:
        """Whether the adapter is in a running state."""
        return self._running

    @property
    def has_fatal_error(self) -> bool:
        """Whether the adapter has encountered an unrecoverable error."""
        return self._fatal_error_message is not None

    @property
    def authorization_is_upstream(self) -> bool:
        """Whether authorization is enforced upstream (e.g. by a relay connector).

        When True, the gateway skips the local 5-layer auth check for messages
        from this adapter.  Default False; relay adapters override to True.
        """
        return False

    # -- Lifecycle --

    @abstractmethod
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Connect to the platform and start receiving messages.

        Args:
            is_reconnect: True when re-establishing after a previous drop.

        Returns:
            True if connection was successful.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform and clean up resources."""
        ...

    # -- Messaging --

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to the specified chat.

        Args:
            chat_id: Target chat/channel/group identifier.
            content: The message text content.
            reply_to: Optional message_id to reply to.
            metadata: Optional platform-specific metadata (thread_id, etc.).

        Returns:
            SendResult with success/failure information.
        """
        ...

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get information about a chat/channel.

        Returns:
            Dict with at least: name, type, chat_id.
            Override in subclasses for richer platform-specific info.
        """
        return {"name": chat_id, "type": "dm"}

    # -- Optional methods (override in subclasses) --

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator.  No-op by default."""
        pass

    async def send_image(
        self, chat_id: str, image_url: str, caption: str = ""
    ) -> SendResult:
        """Send an image.  Falls back to sending URL as text."""
        text = f"{caption}\n{image_url}" if caption else image_url
        return await self.send(chat_id, text)

    async def send_document(
        self, chat_id: str, file_path: str, caption: str = ""
    ) -> SendResult:
        """Send a file/document.  Falls back to sending path as text."""
        text = f"{caption}\n[file: {file_path}]" if caption else f"[file: {file_path}]"
        return await self.send(chat_id, text)

    async def send_voice(self, chat_id: str, file_path: str) -> SendResult:
        """Send a voice message.  Falls back to send_document."""
        return await self.send_document(chat_id, file_path, caption="[voice]")

    async def edit_message(
        self, chat_id: str, message_id: str, content: str
    ) -> SendResult:
        """Edit an existing message.  Not all platforms support this.

        Default: send a new message (adapter should override for real edit).
        """
        return await self.send(chat_id, content)

    # -- Message dispatch --

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the callback that receives incoming MessageEvents.

        Set by GatewayRunner during adapter initialization.
        """
        self._message_handler = handler

    def set_authz(self, checker: Any) -> None:
        """Set the authorization checker for this adapter."""
        self._authz = checker

    def set_pairing(self, store: Any) -> None:
        """Set the pairing store for this adapter."""
        self._pairing = store

    async def handle_message(self, event: MessageEvent) -> None:
        """Dispatch an incoming message to the registered handler.

        This is the standard inbound path called by platform-specific code
        after normalizing the raw platform message into a MessageEvent.
        The GatewayRunner's handler performs authorization, session routing,
        and agent invocation.

        Processing order:
        1. Authorization check (if authz is configured)
        2. /pair command handling (if pairing is configured)
        3. Command hooks (command:<name>)
        4. Two-level concurrency guard (per session key)
        5. Dispatch to handler
        """
        # -- Authz + pairing check --
        if self._authz is not None and not self.authorization_is_upstream:
            source = event.source
            if source and source.user_id:
                # Handle /pair command
                text = (event.text or "").strip()
                if text.startswith("/pair") and self._pairing is not None:
                    parts = text.split(maxsplit=1)
                    code = parts[1].strip() if len(parts) > 1 else ""
                    chat_id = source.chat_id
                    if not code:
                        # Mint a new code
                        result = self._authz.is_authorized(source, self.name)
                        if result.authorized:
                            new_code = self._pairing.create_code()
                            await self.send(chat_id, f"Pairing code: {new_code}\nShare this with the user to pair.")
                        else:
                            await self.send(chat_id, "\u26d4 Not authorized to create pairing codes.")
                        return
                    else:
                        # Redeem a code
                        ok = self._pairing.redeem(code, source.platform, source.user_id)
                        if ok:
                            await self.send(chat_id, "\u2705 Paired successfully!")
                        else:
                            await self.send(chat_id, "\u274c Invalid or expired pairing code.")
                        return

                # Check authorization
                result = self._authz.is_authorized(source, self.name)
                if not result.authorized:
                    chat_id = source.chat_id
                    await self.send(chat_id, "\u26d4 Not authorized. Use /pair <code> to pair.")
                    return

        if self._message_handler is None:
            logger.warning("[%s] No message handler registered, dropping message", self.name)
            return

        # -- Command hook evaluation --
        text = event.text.strip() if event.text else ""
        if text.startswith("/"):
            from encre.gateway.hooks import get_hook_registry

            canonical = text.split()[0][1:].lower()  # e.g. "/go arg" -> "go"
            event_type = f"command:{canonical}"
            reg = get_hook_registry()
            ctx = {"command": canonical, "text": text, "adapter": self.name}
            if event.source:
                ctx["chat_id"] = event.source.chat_id
                ctx["user_id"] = event.source.user_id
            decisions = await reg.emit_collect(event_type, ctx)
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                decision = d.get("decision")
                if decision == "deny":
                    msg = d.get("message", "Command denied.")
                    if event.source:
                        await self.send(event.source.chat_id, msg)
                    return
                if decision == "handled":
                    return
                if decision == "rewrite":
                    new_text = d.get("text", text)
                    event = MessageEvent(
                        text=new_text,
                        message_type=event.message_type,
                        source=event.source,
                        raw_message=event.raw_message,
                        message_id=event.message_id,
                        media_urls=event.media_urls,
                        media_types=event.media_types,
                        reply_to_message_id=event.reply_to_message_id,
                        reply_to_text=event.reply_to_text,
                        reply_to_is_own_message=event.reply_to_is_own_message,
                        auto_skill=event.auto_skill,
                        channel_prompt=event.channel_prompt,
                    )
                    break
                # "allow" or unknown -> proceed

        # -- Two-level guard: queue concurrent messages for same session --
        session_key = None
        if event.source:
            from encre.gateway.session import build_session_key
            session_key = build_session_key(event.source)

        if session_key and session_key in self._active_sessions:
            # Queue the message for later processing
            self._pending_messages.setdefault(session_key, []).append(event)
            return

        # Mark session active and process
        if session_key:
            self._active_sessions[session_key] = asyncio.Event()

        try:
            result = self._message_handler(self, event)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result
        except Exception as e:
            logger.error("[%s] Message handler error: %s %s", self.name, type(e).__name__, e)
        finally:
            if session_key:
                self._active_sessions.pop(session_key, None)
                # Drain pending messages for this session
                pending = self._pending_messages.pop(session_key, [])
                for pending_event in pending:
                    self._spawn_task(
                        self.handle_message(pending_event),
                        name=f"drain-{session_key}",
                    )

    # -- Source construction --

    def build_source(
        self,
        chat_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
        chat_type: str = "dm",
        chat_name: str | None = None,
        thread_id: str | None = None,
        scope_id: str | None = None,
        user_id_alt: str | None = None,
    ) -> SessionSource:
        """Convenience method to construct a SessionSource for this adapter."""
        return SessionSource(
            platform=self.name,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=chat_name,
            user_id=user_id,
            user_name=user_name,
            thread_id=thread_id,
            scope_id=scope_id,
            user_id_alt=user_id_alt,
        )

    # -- Internal state management --

    def _mark_connected(self) -> None:
        """Mark the adapter as connected.  Clears any previous fatal error."""
        self._running = True
        self._fatal_error_code = None
        self._fatal_error_message = None
        logger.info("[%s] Connected", self.name)

    def _mark_disconnected(self) -> None:
        """Mark the adapter as disconnected."""
        self._running = False
        logger.info("[%s] Disconnected", self.name)

    def _set_fatal_error(self, code: str, message: str) -> None:
        """Record an unrecoverable error and stop the adapter."""
        self._running = False
        self._fatal_error_code = code
        self._fatal_error_message = message
        logger.error("[%s] Fatal error [%s]: %s", self.name, code, message)

    # -- Session interrupt support --

    def interrupt_session(self, session_key: str) -> bool:
        """Signal an active session to stop processing.

        Returns True if a session was interrupted, False if no active session.
        """
        event = self._active_sessions.get(session_key)
        if event is not None:
            event.set()
            return True
        return False

    def _register_active_session(self, session_key: str) -> asyncio.Event:
        """Register an active processing session (for interrupt support)."""
        event = asyncio.Event()
        self._active_sessions[session_key] = event
        return event

    def _unregister_active_session(self, session_key: str) -> None:
        """Unregister a completed processing session."""
        self._active_sessions.pop(session_key, None)

    # -- Background task management --

    def _spawn_task(self, coro, *, name: str | None = None) -> asyncio.Task:
        """Spawn a background task tracked by this adapter."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _cancel_background_tasks(self) -> None:
        """Cancel all background tasks (called during disconnect)."""
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
