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

"""
Base adapter framework for Encre multi-channel messaging system.

This module defines the core abstractions that all platform adapters must implement:
- MessageType: Enum for supported message content types
- MessageEvent: Normalized message envelope for incoming messages
- SendResult: Normalized result of message send operations
- BaseAdapter: Abstract base class providing gateway connectivity, session
  management, and event dispatching common to all channel adapters

Architecture:
    Each platform adapter (Feishu, Discord, Telegram, etc.) inherits from
    BaseAdapter and implements platform-specific send/receive logic. Incoming
    messages from any platform are normalized into MessageEvent instances and
    dispatched through the Encre gateway to the AI agent backend. Outgoing
    AI responses are streamed back through the gateway and translated by the
    adapter into platform-specific API calls.

Key design patterns:
    - Template Method: connect/disconnect lifecycle with platform-specific hooks
    - Adapter: unified interface across 18+ messaging platforms
    - Lazy Gateway Initialization: _ensure_gateway() prevents connection leaks
      when an adapter is instantiated but never actually used

Dependencies:
    - encre.gateway.client.GatewayClient: WebSocket client for agent communication
    - encre.utils.types.AgentEvent, TextDelta, Finish: Streaming event types
"""

import asyncio
import enum
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from encre.gateway.client import GatewayClient
from encre.utils.types import AgentEvent, Finish, TextDelta

logger = logging.getLogger("encre.adapters.base")

# Default Encre gateway WebSocket endpoint for local development.
GATEWAY_URL = "ws://127.0.0.1:18792/gateway"


class MessageType(enum.Enum):
    """Supported message content types in the Encre messaging system.

    Maps to the content_type field in platform-specific API requests.
    Adapters may or may not support all types depending on platform capabilities.
    """
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    LOCATION = "location"
    STICKER = "sticker"
    VOICE = "voice"


@dataclass
class MessageEvent:
    """Normalized incoming message envelope for cross-platform message handling.

    All platform-specific message formats are translated into this unified
    representation before being dispatched to the Encre agent backend. This
    enables the agent to process messages without knowing the originating platform.

    Attributes:
        text: The message text content. For image/video/file messages, this may
            contain a description or alt-text rather than the file content itself.
        message_type: The type of content carried by this message. Determines how
            the adapter processes and renders the message.
        message_id: Platform-unique message identifier. Used for reply chaining,
            message editing, and message deletion operations.
        chat_id: The conversation/channel/group identifier where this message was
            received. Used to route responses back to the correct recipient.
        user_id: The sender's platform-specific identifier. Enables per-user session
            management and command routing (e.g., /help @username).
        reply_to_message_id: If this message is a reply, the message_id of the
            message being replied to. Enables thread/chain tracking.
        reply_to_text: Cached text of the message being replied to, provided by
            some platforms (e.g., Telegram, Discord) in the API response. Avoids
            needing a separate API call to fetch the parent message.
        media_urls: URLs or file paths for any attached media (images, videos,
            files). Populated when message_type is IMAGE, VIDEO, or FILE.
        media_types: MIME types corresponding to entries in media_urls.
        raw: The original platform-specific message payload before normalization.
            Useful for debugging or accessing platform-specific metadata.
        timestamp: When the message was received by the Encre system.
        internal: Flag indicating this event originated from within Encre (e.g.,
            a gateway-generated heartbeat) rather than an external user. Internal
            events can be filtered out to prevent echo loops.
    """
    text: str
    message_type: MessageType = MessageType.TEXT
    message_id: str | None = None
    chat_id: str | None = None
    user_id: str | None = None
    reply_to_message_id: str | None = None
    reply_to_text: str | None = None
    media_urls: list[str] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)
    raw: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    internal: bool = False

    def is_command(self) -> bool:
        """Check if this message is a command (starts with '/').

        Returns:
            True if the message text begins with '/', False otherwise.
        """
        return self.text.startswith("/")

    def get_command(self) -> str | None:
        """Extract the command name from this message.

        Parses the first token of the message text, strips the leading '/',
        and removes any bot username suffix (e.g., '/help@mybot' -> 'help').
        This handles both direct commands (/help) and group mentions (@mybot /help).

        Returns:
            The command name without '/' or '@bot' suffix, or None if this
            is not a command message.
        """
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
        """Extract the arguments passed to the command.

        Returns everything after the command name (the first token).
        For a message like '/help some text', returns 'some text'.
        For a non-command message, returns the entire text unchanged.

        Returns:
            The command arguments string, or the full text if not a command.
        """
        if not self.is_command():
            return self.text
        parts = self.text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""


@dataclass
class SendResult:
    """Result of an asynchronous message send operation.

    Provides a unified interface for checking the success/failure of platform-
    specific send calls and accessing platform-specific metadata.

    Attributes:
        success: Whether the message was sent successfully.
        message_id: The platform-specific ID of the sent message. Useful for
            subsequent operations like edit_message or delete_message.
        error: Human-readable error description if success is False.
        raw: Platform-specific raw response data for debugging or advanced
            integrations.
        retryable: Whether the failure was transient (network timeout, rate limit)
            and a retry might succeed. Non-retryable errors (invalid auth, etc.)
            should be set to False.
        continuation_message_ids: For streaming responses that require multiple
            message parts (e.g., Discord's 2000-char limit), IDs of messages that
            should be edited/merged with this one when the stream completes.
    """
    success: bool
    message_id: str | None = None
    error: str | None = None
    raw: Any = None
    retryable: bool = False
    continuation_message_ids: tuple = ()


class BaseAdapter(ABC):
    """Abstract base class for all channel adapters in the Encre system.

    Provides the common infrastructure that every platform adapter inherits:

    1. Gateway Connectivity: Manages a WebSocket connection (GatewayClient) to
       the Encre agent backend for submitting user messages and receiving AI
       responses. Uses lazy initialization to avoid holding connections for
       unused adapters.

    2. Session Management: Tracks user-to-session mappings (per adapter) so
       that subsequent messages from the same user continue an existing AI
       conversation rather than starting a new one.

    3. Event Dispatch: Receives MessageEvent instances from platform-specific
       listeners and routes them to the registered message handler.

    4. Streaming Response Processing: Converts streamed AgentEvents (TextDelta,
       Finish) into incremental display updates via on_text_delta() hooks and
       final message delivery via send().

    Platform-specific adapters implement:
    - connect(): Platform-specific connection logic (OAuth, WebSocket, HTTP, etc.)
    - send(): Platform-specific message delivery (API calls, HTTP POST, etc.)
    - _on_connected(): Lifecycle hook called after successful connection

    Subclass contract:
        1. Set class attribute `name` to the platform identifier (e.g., "feishu")
        2. Call super().__init__() with gateway_url and capabilities
        3. Implement abstract method send()
        4. Override connect() to establish platform connection
        5. Dispatch incoming messages via dispatch_message(MessageEvent)

    Concurrency model:
        All async methods are designed for use with asyncio. The GatewayClient
        manages its own internal event loop for WebSocket communication. Adapters
        may run background tasks (e.g., Discord listener, Telegram polling loop)
        stored in self._background_tasks.
    """
    name: str = "base"

    # HTTP User-Agent header value for platform API requests.
    _USER_AGENT = "Encre/1.0.0"

    def __init__(
        self,
        gateway_url: str = GATEWAY_URL,
        capabilities: list[str] | None = None,
    ) -> None:
        """Initialize the base adapter with gateway connectivity and session storage.

        Args:
            gateway_url: WebSocket URL of the Encre agent gateway. Defaults to
                localhost:18792/gateway for local development.
            capabilities: List of capabilities this adapter supports. Common values
                are "text", "api" (platform API for sending), "webhook" (HTTP server
                for receiving). Defaults to ["text"].
        """
        self._client = GatewayClient(
            adapter_name=self.name,
            url=gateway_url,
            capabilities=capabilities or ["text"],
        )
        # Runtime state flags
        self._running = False
        self._fatal_error_code: str | None = None
        self._fatal_error_message: str | None = None
        # Message event handler registered by the caller (usually the session manager)
        self._message_handler: Callable[[MessageEvent], Any] | None = None
        # Active session tracking (chat_id -> asyncio.Event)
        self._active_sessions: dict[str, asyncio.Event] = {}
        # Messages pending delivery during streaming
        self._pending_messages: dict[str, MessageEvent] = {}
        # User-to-AI-session mappings: user_id -> session_id
        self._user_sessions: dict[str, str] = {}
        # Gateway connection lifecycle state
        self._gateway_started = False
        self._reconnecting = False
        self._background_tasks: set[asyncio.Task[Any]] = set()
        # Most recent inbound chat_id for push notifications.  Updated by
        # dispatch_message() whenever a non-internal message arrives.
        self._last_push_chat_id: str | None = None

    async def _ensure_gateway(self) -> None:
        """Ensure GatewayClient is connected before submitting messages.

        This lazy initialization pattern prevents connection leaks: the GatewayClient
        is only started when the first message is submitted, not at adapter
        construction time. It also handles reconnection automatically.

        The method uses a polling loop (up to 15s) to wait for the WebSocket
        connection to be established. This ensures the first message is not
        silently dropped due to a race condition between connection start
        and message submission.

        Side effects:
            - Starts GatewayClient.connect() if not already started
            - Restarts GatewayClient.connect() if disconnected
            - Sets _reconnecting flag during reconnection attempts
            - Logs connection progress to the adapter's logger
        """
        if not self._gateway_started:
            # First-time lazy initialization
            self._gateway_started = True
            _t = asyncio.ensure_future(self._client.connect())
            self._background_tasks.add(_t)
            logger.info("[%s] GatewayClient lazy-started, waiting for connection...", self.name)
        elif self._client.is_connected:
            # Already connected, nothing to do
            return
        else:
            # GatewayClient was started but connection was lost -- restart it.
            # Without this, submit/submit_stream silently drops messages when
            # _connected is False (the initial connect() returns after handshake
            # and does NOT reconnect on later disconnection).
            if self._reconnecting:
                logger.info("[%s] GatewayClient reconnect already in progress, waiting...", self.name)
            else:
                self._reconnecting = True
                logger.warning("[%s] GatewayClient disconnected, reconnecting...", self.name)
                _t = asyncio.ensure_future(self._client.connect())
                self._background_tasks.add(_t)

        # Poll until connected or timeout (30 iterations * 0.5s = 15s max)
        for i in range(30):
            if self._client.is_connected:
                logger.info("[%s] GatewayClient connected (took ~%ds)", self.name, i * 0.5)
                self._reconnecting = False
                return
            await asyncio.sleep(0.5)
        # Timeout reached -- proceed anyway to allow the caller to handle the error
        self._reconnecting = False
        logger.warning("[%s] GatewayClient not connected after 15s (ws=%s running=%s), proceeding anyway",
                       self.name, self._client._ws is not None, self._client._running)

    @property
    def client(self) -> GatewayClient:
        """The underlying GatewayClient instance for direct access.

        Returns:
            The GatewayClient used for WebSocket communication with the agent.
        """
        return self._client

    @property
    def is_connected(self) -> bool:
        """Whether the adapter is currently connected to the Encre gateway.

        Returns:
            True if the WebSocket connection is active, False otherwise.
        """
        return self._client.is_connected

    @property
    def running(self) -> bool:
        """Whether the adapter is in a running state (connected or connecting).

        Unlike is_connected, this flag is set at the adapter level and may
        be True even when the gateway connection is temporarily lost (e.g.,
        during auto-reconnect).

        Returns:
            True if the adapter is active, False if stopped or disconnected.
        """
        return self._running

    @property
    def has_fatal_error(self) -> bool:
        """Whether the adapter has encountered an unrecoverable error.

        Fatal errors (e.g., invalid credentials, network unreachable) prevent
        the adapter from reconnecting. The error details are available via
        _fatal_error_code and _fatal_error_message.

        Returns:
            True if a fatal error has occurred, False otherwise.
        """
        return self._fatal_error_message is not None

    def set_message_handler(self, handler: Callable[[MessageEvent], Any]) -> None:
        """Register the callback that receives normalized MessageEvent instances.

        The handler is typically set by the session manager or event router
        that routes messages to the appropriate AI agent session.

        Args:
            handler: Async callable that accepts a MessageEvent and processes it.
        """
        self._message_handler = handler

    def _mark_connected(self) -> None:
        """Mark the adapter as connected. Clears any previous fatal error state.

        Called by platform-specific connect() implementations after the
        platform connection is established (e.g., Discord ready, webhook server
        listening).
        """
        self._running = True
        self._fatal_error_code = None
        self._fatal_error_message = None
        logger.info("[%s] Connected", self.name)

    def _mark_disconnected(self) -> None:
        """Mark the adapter as disconnected.

        Called by platform-specific disconnect() implementations before
        tearing down the platform connection.
        """
        self._running = False
        logger.info("[%s] Disconnected", self.name)

    def _set_fatal_error(self, code: str, message: str) -> None:
        """Record an unrecoverable error and stop the adapter.

        Args:
            code: Machine-readable error code (e.g., "INVALID_TOKEN").
            message: Human-readable error description.
        """
        self._running = False
        self._fatal_error_code = code
        self._fatal_error_message = message
        logger.error("[%s] Fatal error [%s]: %s", self.name, code, message)

    def get_session(self, user_id: str) -> str | None:
        """Retrieve the AI session ID associated with a user.

        Args:
            user_id: The platform-specific user identifier.

        Returns:
            The AI session ID, or None if no session exists for this user.
        """
        return self._user_sessions.get(user_id)

    def set_session(self, user_id: str, session_id: str) -> None:
        """Associate an AI session with a user.

        Args:
            user_id: The platform-specific user identifier.
            session_id: The Encre agent session ID for this conversation.
        """
        self._user_sessions[user_id] = session_id

    def clear_session(self, user_id: str) -> None:
        """Remove the AI session association for a user.

        Args:
            user_id: The platform-specific user identifier.
        """
        self._user_sessions.pop(user_id, None)

    def is_session_active(self, chat_id: str) -> bool:
        """Check if there is an active AI session for a chat/channel.

        Args:
            chat_id: The platform-specific chat/channel identifier.

        Returns:
            True if the chat_id has a registered active session event.
        """
        return chat_id in self._active_sessions

    async def submit(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Submit a text prompt to the AI agent and return the complete response.

        Ensures the gateway is connected, then forwards the prompt to the agent
        backend and waits for the full response as a single string.

        Args:
            prompt: The user's message text to send to the AI agent.
            session_id: Optional explicit AI session ID. If not provided, a new
                session is created for this conversation turn.
            system_prompt: Optional system prompt to prepend to the conversation.
                Used to configure the agent's behavior (persona, constraints, etc.).

        Returns:
            The complete AI response text.

        Note:
            For streaming responses, use submit_stream() instead. This method
            buffers the entire response in memory before returning.
        """
        await self._ensure_gateway()
        logger.info("[%s] submit prompt=%.60s session=%s system_prompt=%s",
                     self.name, prompt, session_id or "(new)", "yes" if system_prompt else "no")
        return await self._client.submit(
            prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        )

    async def submit_stream(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Submit a prompt and stream the AI response as a sequence of events.

        Yields AgentEvent instances (TextDelta, Finish, etc.) as they arrive
        from the agent backend. This enables real-time display of the AI's  # noqa: E402
        response as it is being generated.

        Args:
            prompt: The user's message text to send to the AI agent.
            session_id: Optional explicit AI session ID for continuing a conversation.
            system_prompt: Optional system prompt for this conversation turn.

        Yields:
            AgentEvent instances -- typically TextDelta (incremental text) and
            Finish (completion signal with reason/error).

        Note:
            The caller is responsible for assembling the full text from TextDelta
            events and handling the Finish event for error/success notification.
        """
        await self._ensure_gateway()
        logger.info("[%s] submit_stream prompt=%.60s session=%s",
                     self.name, prompt, session_id or "(new)")
        async for event in self._client.submit_stream(
            prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        ):
            yield event

    async def process_with_stream(
        self,
        content: str,
        chat_id: str,
        session_id: str | None = None,
    ) -> None:
        """Process an incoming message by streaming the AI response and sending it back.

        This is the main event loop handler for incoming messages. It:
        1. Submits the message content to the AI agent via submit_stream()
        2. Streams TextDelta events in real-time via on_text_delta() (for UI updates)
        3. Handles the Finish event for completion/error notification
        4. Sends the complete response back to the user via send()

        This method is typically called by platform-specific message handlers
        after receiving and parsing an incoming message event.

        Args:
            content: The message text to send to the AI agent.
            chat_id: The platform chat/channel ID to send the response to.
            session_id: Optional explicit session ID. Falls back to the user's
                stored session for this adapter if not provided.
        """
        await self._ensure_gateway()
        session_id = session_id or self.get_session(chat_id)
        logger.info("[%s] process_with_stream chat=%s session=%s content=%.60s",
                     self.name, chat_id, session_id or "(none)", content)
        full_response: list[str] = []
        async for event in self.submit_stream(content, session_id=session_id):
            if isinstance(event, TextDelta) and event.text:
                full_response.append(event.text)
                await self.on_text_delta(chat_id, event.text)
            elif isinstance(event, Finish):
                if event.error:
                    logger.error("[%s] finish with error for chat=%s: %s", self.name, chat_id, event.error)
                    await self.send(
                        chat_id,
                        f"Error: {event.error}",
                    )
                else:
                    logger.info("[%s] finish reason=%s for chat=%s", self.name, event.reason, chat_id)
        response_text = "".join(full_response)
        if response_text:
            logger.info("[%s] sending response len=%d to chat=%s", self.name, len(response_text), chat_id)
            await self.send(chat_id, response_text)
        else:
            logger.warning("[%s] empty response for chat=%s", self.name, chat_id)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Start the adapter and connect to both the platform and the Encre gateway.

        Base implementation starts the GatewayClient in the background, waits
        briefly for connection, then calls the platform-specific _on_connected()
        hook. Platform adapters may override this to add their own connection
        logic (OAuth, WebSocket handshake, HTTP server startup, etc.).

        Subclasses should:
        1. Establish the platform-specific connection
        2. Call self._mark_connected() on success
        3. Call self._set_fatal_error() on failure and return False

        Returns:
            True if the adapter is connected and ready to receive messages.
        """
        self._running = True
        self._gateway_started = True
        _t = asyncio.ensure_future(self._client.connect())
        self._background_tasks.add(_t)
        logger.info("[%s] Connecting to gateway...", self.name)
        await asyncio.sleep(0.5)
        await self._on_connected()
        return True

    async def disconnect(self) -> None:
        """Disconnect the adapter and clean up resources.

        Calls _on_disconnected() for platform-specific cleanup (closing
        WebSocket connections, stopping HTTP servers, etc.), then disconnects
        the GatewayClient. Idempotent -- safe to call multiple times.
        """
        self._running = False
        try:
            await self._on_disconnected()
        except Exception as e:
            logger.warning("[%s] on_disconnected error: %s", self.name, e)
        await self._client.disconnect()
        logger.info("[%s] Disconnected", self.name)

    @property
    def default_push_chat_id(self) -> str | None:
        """Auto-detected chat_id for push notifications.

        Returns the ``chat_id`` from the most recent non-internal inbound
        message.  This works for every adapter that receives messages -- Telegram,
        QQ Bot, Discord, Feishu, DingTalk, Matrix, etc. -- without any per-adapter
        configuration.  When no message has been received since the adapter
        started, returns ``None`` and push is skipped.
        """
        return self._last_push_chat_id

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message to the specified chat/channel on the platform.

        This is the only abstract method that must be implemented by every
        platform adapter. It handles all platform-specific details of message
        delivery including API authentication, rate limiting, chunking, and
        error handling.

        Args:
            chat_id: The platform-specific chat/channel/group identifier.
            content: The message text to send.
            reply_to: Optional message ID to reply to (threading support).
            metadata: Optional platform-specific metadata (e.g., markdown flags,
                message type indicators).

        Returns:
            SendResult with success status, message_id, and optional error info.

        Raises:
            May raise platform-specific exceptions for unrecoverable errors
            (invalid credentials, network unreachable). Transient errors should
            be returned via SendResult with retryable=True.
        """
        pass

    async def edit_message(
        self,
        _chat_id: str,
        _message_id: str,
        _content: str,
        *,
        _finalize: bool = False,
    ) -> SendResult:
        """Edit an existing message in the platform.

        Base implementation returns unsupported. Platform adapters that support
        message editing (e.g., Discord, Slack) should override this method.

        Args:
            chat_id: The chat/channel where the message was sent.
            message_id: The platform-specific ID of the message to edit.
            content: The new message content.
            finalize: If True, this is the final edit (streaming complete).
                If False, this is an intermediate update.

        Returns:
            SendResult indicating success/failure of the edit operation.
        """
        return SendResult(success=False, error="Not supported")

    async def delete_message(self, _chat_id: str, _message_id: str) -> bool:
        """Delete a message from the platform.

        Base implementation returns False. Platform adapters should override
        if they support message deletion.

        Args:
            chat_id: The chat/channel where the message was sent.
            message_id: The platform-specific ID of the message to delete.

        Returns:
            True if the message was deleted successfully, False otherwise.
        """
        return False

    async def send_typing(self, chat_id: str) -> None:  # noqa: B027
        """Send a typing indicator to the platform.

        Informs the user that the bot is generating a response. Base implementation
        is a no-op. Override in adapters that support typing indicators (e.g.,
        Telegram, WhatsApp, Slack).

        Args:
            chat_id: The chat/channel to send the typing indicator to.
        """
        pass

    async def send_image(
        self,
        _chat_id: str,
        _file_path: str,
        *,
        _caption: str | None = None,
    ) -> SendResult:
        """Send an image file to the platform.

        Base implementation returns unsupported. Override in adapters that
        support image uploads (e.g., Feishu, WeCom, Telegram).

        Args:
            chat_id: The chat/channel to send the image to.
            file_path: Local file path to the image.
            caption: Optional text to include with the image.

        Returns:
            SendResult with success status and the platform-specific message ID.
        """
        return SendResult(success=False, error="Not supported")

    async def send_document(
        self,
        _chat_id: str,
        _file_path: str,
        *,
        _caption: str | None = None,
    ) -> SendResult:
        """Send a document file to the platform.

        Base implementation returns unsupported. Override in adapters that
        support document uploads (e.g., Telegram, Feishu).

        Args:
            chat_id: The chat/channel to send the document to.
            file_path: Local file path to the document.
            caption: Optional text to include with the document.

        Returns:
            SendResult with success status and the platform-specific message ID.
        """
        return SendResult(success=False, error="Not supported")

    # ── Hooks ──────────────────────────────────────────────────────────────

    async def _on_connected(self) -> None:  # noqa: B027
        """Platform-specific hook called after successful connection.

        Called by connect() after the platform connection is established.
        Override in subclasses to perform post-connection setup (e.g.,
        start background listeners, register webhooks, send test messages).

        Default implementation is a no-op.
        """
        pass

    async def _on_disconnected(self) -> None:  # noqa: B027
        """Platform-specific hook called before disconnection.

        Called by disconnect() before tearing down the platform connection.
        Override in subclasses to perform pre-disconnection cleanup (e.g.,
        cancel background tasks, unregister webhooks).

        Default implementation is a no-op.
        """
        pass

    async def on_text_delta(self, chat_id: str, delta: str) -> None:  # noqa: B027
        """Hook called for each incremental text chunk in the AI response.

        Called by process_with_stream() as TextDelta events arrive from the
        agent. Override in subclasses that want to implement real-time UI
        updates (e.g., streaming text in the Discord UI, live preview in
        the desktop app).

        Args:
            chat_id: The chat/channel receiving the streamed response.
            delta: The text chunk that was just generated.
        """
        pass

    def dispatch_message(self, event: MessageEvent) -> None:
        """Dispatch a MessageEvent to the registered message handler.

        This is the entry point for incoming messages from the platform.
        Platform-specific listeners should parse the raw platform message
        into a MessageEvent and call this method to route it to the agent.

        Args:
            event: The normalized message event to dispatch.

        Note:
            This method is synchronous to avoid event loop issues. The handler
            itself should be an async callable that is executed via asyncio.create_task()
            if necessary.
        """
        # Track the most recent non-internal chat_id so automation push
        # can deliver results back to where the bot is active.
        if not event.internal and event.chat_id:
            self._last_push_chat_id = event.chat_id
        if self._message_handler:
            self._message_handler(event)

    @staticmethod
    def build_user_agent() -> str:
        """Build the User-Agent header value for HTTP requests to platform APIs.

        Returns:
            The standard User-Agent string: "Encre/1.0.0"
        """
        return "Encre/1.0.0"

    @staticmethod
    def resolve_proxy_url(env_var: str | None = None) -> str | None:
        """Resolve a proxy URL from environment variables.

        Checks the provided environment variable first, then falls back to
        standard proxy environment variables in order of precedence:
        HTTPS_PROXY > https_proxy > ALL_PROXY > all_proxy > HTTP_PROXY > http_proxy.

        This matches the behavior of common HTTP clients and allows users to
        configure proxies globally without per-adapter settings.

        Args:
            env_var: Optional specific environment variable name to check first.

        Returns:
            The resolved proxy URL, or None if no proxy is configured.
        """
        if env_var:
            val = os.environ.get(env_var)
            if val:
                return val
        return (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("ALL_PROXY")
            or os.environ.get("ALL_PROXY")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )

    @classmethod
    async def validate_config(cls, _config: dict[str, Any]) -> tuple[bool, str]:
        """Validate that the adapter configuration is complete and correct.

        Base implementation always returns success. Platform adapters should
        override this to perform real validation (e.g., checking required fields,
        verifying credentials with the platform API).

        Args:
            config: Dictionary of adapter configuration parameters as received
                from the frontend or config file.  # noqa: E402

        Returns:
            Tuple of (is_valid, message). If is_valid is False, message
            describes the validation error.
        """
        return (True, "")
