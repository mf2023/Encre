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

"""Gateway streaming consumer -- bridges agent events to platform delivery.

The agent produces a stream of events (TextDelta, ToolResult, Finish) via
EventRouter.submit_stream().  GatewayStreamConsumer:
  1. Receives events via feed()
  2. Buffers text deltas
  3. Rate-limits platform edits (progressive message editing)
  4. Finalizes the complete response via the adapter's send/edit methods

Aligns with Hermes ``gateway/stream_consumer.py``.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from encre.gateway.config import (
    DEFAULT_STREAMING_BUFFER_THRESHOLD,
    DEFAULT_STREAMING_CURSOR,
    DEFAULT_STREAMING_EDIT_INTERVAL,
)
from encre.gateway.platforms.base import BasePlatformAdapter, SendResult
from encre.gateway.stream_events import (
    Commentary,
    GatewayNotice,
    MessageChunk,
    MessageStop,
    StreamEvent,
    ToolCallChunk,
    ToolCallFinished,
)
from encre.utils.types import AgentEvent, Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.stream_consumer")


@dataclass
class StreamConsumerConfig:
    """Runtime config for a single stream consumer instance."""

    edit_interval: float = DEFAULT_STREAMING_EDIT_INTERVAL
    buffer_threshold: int = DEFAULT_STREAMING_BUFFER_THRESHOLD
    cursor: str = DEFAULT_STREAMING_CURSOR
    # When True, only buffer text without progressive editing (used for
    # platforms that don't support message editing).
    buffer_only: bool = False


class GatewayStreamConsumer:
    """Bridges agent stream events to platform-specific progressive delivery.

    Usage:
        consumer = GatewayStreamConsumer(adapter, chat_id, config)
        async for event in router.submit_stream(...):
            await consumer.feed(event)
        result = await consumer.finalize()
    """

    def __init__(
        self,
        adapter: BasePlatformAdapter,
        chat_id: str,
        config: Optional[StreamConsumerConfig] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self._adapter = adapter
        self._chat_id = chat_id
        self._config = config or StreamConsumerConfig()
        self._reply_to = reply_to
        self._metadata = metadata

        # Accumulated full response text
        self._buffer: list[str] = []
        # The message_id of the "preview" message being progressively edited
        self._preview_message_id: Optional[str] = None
        # Last time we pushed an edit to the platform
        self._last_edit_time: float = 0.0
        # Whether the stream has been finalized
        self._finalized = False
        # Complete response (set after finalize)
        self._final_text: str = ""

    @property
    def accumulated_text(self) -> str:
        """The full text accumulated so far."""
        return "".join(self._buffer)

    async def feed(self, event: AgentEvent) -> None:
        """Feed an agent event into the consumer.

        Handles TextDelta (progressive text), ToolResult (tool output indicator),
        and Finish (finalization trigger).
        """
        if self._finalized:
            return

        if isinstance(event, TextDelta) and event.text:
            self._buffer.append(event.text)
            await self._maybe_progressive_edit()

        elif isinstance(event, ToolResult):
            # Tool results are informational; we don't display them in the
            # streaming preview (they're part of the agent's internal state).
            pass

        elif isinstance(event, Finish):
            # Finish is handled by finalize(); just record any error.
            if event.error:
                logger.warning(
                    "[stream-consumer] finish with error: %s", event.error
                )

    async def feed_stream_event(self, event: StreamEvent) -> None:
        """Feed a typed StreamEvent (alternative to raw AgentEvent)."""
        if self._finalized:
            return

        if isinstance(event, MessageChunk):
            self._buffer.append(event.text)
            await self._maybe_progressive_edit()

        elif isinstance(event, Commentary):
            # Commentary is a complete intermediate message -- send it as-is
            await self._adapter.send(self._chat_id, event.text, metadata=self._metadata)

        elif isinstance(event, ToolCallChunk):
            # Optionally show tool progress (platform-dependent)
            pass

        elif isinstance(event, MessageStop):
            if event.final:
                await self.finalize()

    async def finalize(self) -> str:
        """Finalize the stream: deliver the complete response.

        If progressive editing was used, performs a final edit to remove the
        cursor and deliver the complete text.  If buffer_only mode, sends the
        complete message.

        Returns:
            The complete response text.
        """
        if self._finalized:
            return self._final_text

        self._finalized = True
        self._final_text = self.accumulated_text

        if not self._final_text.strip():
            return self._final_text

        if self._config.buffer_only or self._preview_message_id is None:
            # No progressive editing was done; send the complete message
            await self._adapter.send(
                self._chat_id,
                self._final_text,
                reply_to=self._reply_to,
                metadata=self._metadata,
            )
        else:
            # Final edit to remove cursor and show complete text
            await self._adapter.edit_message(
                self._chat_id, self._preview_message_id, self._final_text
            )

        return self._final_text

    async def _maybe_progressive_edit(self) -> None:
        """Check if we should push a progressive edit to the platform."""
        if self._config.buffer_only:
            return

        now = time.time()
        elapsed = now - self._last_edit_time
        text_so_far = self.accumulated_text

        # Only edit if enough time has passed AND enough new text accumulated
        if elapsed < self._config.edit_interval:
            return
        if len(text_so_far) < self._config.buffer_threshold and self._preview_message_id is not None:
            return

        preview_text = text_so_far + self._config.cursor
        self._last_edit_time = now

        if self._preview_message_id is None:
            # First progressive message: send a new message
            result = await self._adapter.send(
                self._chat_id,
                preview_text,
                reply_to=self._reply_to,
                metadata=self._metadata,
            )
            if result.success and result.message_id:
                self._preview_message_id = result.message_id
        else:
            # Subsequent: edit the existing preview message
            await self._adapter.edit_message(
                self._chat_id, self._preview_message_id, preview_text
            )
