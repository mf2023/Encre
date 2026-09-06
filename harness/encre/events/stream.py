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

"""Typed event stream: publish/subscribe fan-out with async iteration.

:class:`EventStream` is the single contract between the agent loop and every
consumer of agent events (frontend transport, plugin taps, telemetry).  The
loop publishes :class:`~encre.utils.types.AgentEvent` items; any number of
subscribers iterate them asynchronously via :meth:`EventStream.subscribe`.

Design notes:

* **Fan-out** -- every subscriber gets its own bounded queue; a slow
  consumer never blocks the loop or other subscribers.
* **Backpressure** -- when a subscriber's queue is full the newest event is
  dropped *for that subscriber only* and a warning is logged.  The loop's
  own delivery (the async-generator bridge) is never back-pressured.
* **Lifecycle** -- :meth:`close` ends every subscription gracefully
  (pending buffered events are still delivered before iteration stops).
"""

import asyncio
from typing import AsyncIterator, Generic, TypeVar

from encre.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class _Subscription(Generic[T]):
    """A single subscriber view over an :class:`EventStream`.

    Async-iterates events from a private queue until the stream is closed
    and the queue is drained.
    """

    __slots__ = ("_queue", "_stream")

    def __init__(self, stream: "EventStream[T]") -> None:
        self._stream = stream
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(
            maxsize=stream.buffer_size,
        )

    def _deliver(self, event: T) -> bool:
        """Enqueue ``event``; return ``False`` when the queue is full."""
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            return False

    def _seal(self) -> None:
        """Enqueue the end-of-stream sentinel (drop-oldest if full)."""
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def __aiter__(self) -> "_Subscription[T]":
        return self

    async def __anext__(self) -> T:
        event = await self._queue.get()
        if event is None:
            raise StopAsyncIteration
        return event


class EventStream(Generic[T]):
    """Typed publish/subscribe event stream with async iteration.

    Args:
        name: Human-readable stream name (used in logs).
        buffer_size: Per-subscriber queue bound.  Events are dropped for a
            subscriber whose queue is full; the publisher never blocks.
    """

    def __init__(self, name: str = "events", buffer_size: int = 4096) -> None:
        self.name = name
        self.buffer_size = buffer_size
        self._subs: list[_Subscription[T]] = []
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` has been called."""
        return self._closed

    @property
    def subscriber_count(self) -> int:
        """Number of active subscriptions (diagnostics)."""
        return len(self._subs)

    def publish(self, event: T) -> bool:
        """Fan ``event`` out to every subscriber without blocking.

        Args:
            event: The typed event to broadcast.

        Returns:
            ``True`` when at least one subscriber received the event
            (or there are no subscribers at all -- publishing into the
            void is not an error); ``False`` when the stream is closed.
        """
        if self._closed:
            return False
        if not self._subs:
            return True
        delivered = 0
        for sub in list(self._subs):
            if sub._deliver(event):
                delivered += 1
            else:
                logger.warning(
                    "[event_stream:%s] subscriber queue full -- event dropped "
                    "(type=%s)",
                    self.name, type(event).__name__,
                )
        return delivered > 0 or True

    def subscribe(self) -> _Subscription[T]:
        """Open a new subscription (async iterator over events).

        Returns:
            An async iterator yielding every event published after this
            call, until :meth:`close` drains the stream.

        Raises:
            RuntimeError: When the stream is already closed.
        """
        if self._closed:
            raise RuntimeError(f"event stream '{self.name}' is closed")
        sub = _Subscription(self)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: _Subscription[T]) -> None:
        """Remove a subscription so it no longer receives events."""
        try:
            self._subs.remove(sub)
        except ValueError:
            pass

    async def close(self) -> None:
        """Close the stream and seal every active subscription.

        Buffered events remain consumable; after the buffer drains the
        async iterators raise :class:`StopAsyncIteration`.
        """
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            for sub in list(self._subs):
                sub._seal()
            self._subs.clear()
