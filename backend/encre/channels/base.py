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

"""Encre agent channels: base abstractions.

Defines :class:`Channel` (the abstract transport interface every connection
surface implements) and :class:`EventRouter` (the concurrency-safe bridge
between channels, the SessionManager and the agent runtime).  The router
exposes :meth:`EventRouter.submit` / :meth:`EventRouter.submit_stream`,
which channels call to run prompts, and guarantees each connection gets an
isolated session with its own conversation history.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar

from encre.prompts.loader import PromptLoader
from encre.utils.types import (
    AgentEvent,
    Finish,
    TextDelta,
    ToolResult,
)

if TYPE_CHECKING:
    from encre.config import EncreConfig
    from encre.server.session_manager import SessionManager

logger = logging.getLogger("encre.channels")

_prompt_loader = PromptLoader()


class Channel(ABC):
    """Abstract transport surface for the agent runtime.

    Subclasses bind a concrete client/adapter to the shared
    :class:`EventRouter`.  Each channel is responsible for spawning its
    listening loop in :meth:`start` and tearing it down in :meth:`stop`.
    """

    name: ClassVar[str]

    @abstractmethod
    async def start(self, router: EventRouter) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...


class EventRouter:
    """Multi-session event router backed by SessionManager.

    Each channel connection gets its own isolated agent session with
    independent conversation history. Concurrency is controlled by the
    SessionManager's semaphore.

    Callers **must** wrap ``submit_stream`` (and any session lookups) in a
    :meth:`iclaw_context` block to ensure the shared SessionManager is
    switched to the iClaw sessions directory::

        async with router.iclaw_context():
            info = router.session_manager.try_resume_most_recent(...)
            async for event in router.submit_stream(...):
                ...

    The router can optionally hold a reference to connected adapter names,
    set via :meth:`set_connected_adapters`, so the AI knows which IM
    platforms are active when operating in iClaw mode.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        default_config: EncreConfig | None = None,
    ) -> None:
        if default_config is None:
            from encre.config import EncreConfig
            default_config = EncreConfig()
        self._manager = session_manager
        self._default_config = default_config
        self._running = True
        self._active_streams: dict[str, asyncio.Task[None]] = {}
        self._iclaw_lock = asyncio.Lock()
        self._connected_adapters: list[str] = []

    @property
    def session_manager(self) -> SessionManager:
        return self._manager

    def set_connected_adapters(self, names: list[str]) -> None:
        """Update the list of connected adapter names (set by GatewayServer)."""
        self._connected_adapters = names

    @asynccontextmanager
    async def iclaw_context(self) -> AsyncIterator[None]:
        """Context manager: acquire iClaw lock to serialize concurrent iClaw operations.

        Sessions are saved to the main sessions directory -- the same place desktop
        client sessions live -- so the frontend sees all conversations regardless of
        source (adapter, iClaw desktop, or normal desktop).
        """
        async with self._iclaw_lock:
            yield

    async def submit(
        self,
        channel_name: str,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Submit a prompt and collect the full text response (non-streaming).

        **Must** be called inside an ``iclaw_context()`` block.
        """
        parts: list[str] = []
        async for event in self.submit_stream(
            channel_name, prompt,
            session_id=session_id,
            system_prompt=system_prompt,
        ):
            if isinstance(event, TextDelta) and event.text:
                parts.append(event.text)
        return "".join(parts)

    async def submit_stream(
        self,
        channel_name: str,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Submit a prompt and stream AgentEvent results.

        **Must** be called inside an ``iclaw_context()`` block so the
        SessionManager is switched to the iClaw sessions directory.
        """
        logger.info("[router] submit_stream channel=%s session_id=%s prompt=%.60s system_prompt=%s",
                     channel_name, session_id or "(new)", prompt,
                     "yes" if system_prompt else "no")

        # Acquire or create session
        if session_id:
            info = self._manager.load_or_create_session(
                session_id, config=replace(self._default_config)
            )
        else:
            info = self._manager.create_session(config=replace(self._default_config))
            session_id = info.session_id

        # Tag session with the originating channel so the session list
        # can display a mode badge (normal / iClaw / qqbot / telegram ...).
        info.agent.session.metadata["channel"] = channel_name
        info.metadata["channel"] = channel_name

        self._last_session_id = session_id
        self._manager.touch(session_id)
        logger.info("[router] session %s ready (running=%s)", session_id, info.is_running)

        if info.is_running:
            yield Finish(reason="busy", error="Session already running")
            return

        acquired = await self._manager.acquire_slot()
        if not acquired:
            logger.warning("[router] slot acquire failed for %s", session_id)
            yield Finish(reason="capacity", error="Server at capacity, try later")
            return

        info.is_running = True
        stream_key = f"{channel_name}:{session_id}"

        # Add user message to session history before running
        info.agent.add_message("user", prompt)

        # Build channel context as custom_instructions (not system_prompt) so that
        # the prompt builder still runs and produces the full system prompt with
        # identity, safety, permissions, tools, etc.
        # Always load the iClaw identity prompt -- EventRouter operates exclusively
        # in iClaw mode (wrapped in iclaw_context()), whether called from the
        # desktop client (channel="iclaw") or from an adapter (QQ, Telegram, etc.).
        custom_instructions = _prompt_loader.load("iclaw_mode")

        # Append connected-adapters info so the agent knows what IM platforms are active
        _connected = self._connected_adapters
        if _connected:
            adapter_list = "\n".join(f"- {name}" for name in _connected)
            custom_instructions += "\n\n" + _prompt_loader.load_with_context(
                "connected_adapters", adapter_list=adapter_list,
            )

        # Append channel-specific platform hints from prompt files
        if channel_name != "iclaw":
            try:
                hint = _prompt_loader.load(f"platform_{channel_name}")
                logger.info("[router] set rich platform context for %s", channel_name)
            except FileNotFoundError:
                hint = _prompt_loader.load_with_context(
                    "platform_default", channel=channel_name,
                )
                logger.info("[router] set generic channel context for %s", channel_name)
            custom_instructions += "\n\n" + hint

        logger.info("[router] starting agent.run for %s", session_id)

        # Fire lifecycle hooks (aligns with Hermes' gateway hook points).
        # session:start fires once per new conversation; agent:start/agent:end
        # bracket the agent run; agent:step fires on each tool result.  Hook
        # failures are logged and swallowed inside emit(), so a misbehaving hook
        # never aborts the run.
        hooks = None
        try:
            from encre.gateway.hooks import get_hook_registry, SESSION_START, AGENT_START, AGENT_STEP, AGENT_END
            hooks = get_hook_registry()
        except Exception:
            hooks = None
        is_new_session = not bool(getattr(info, "_hook_session_started", False))
        if hooks is not None and is_new_session:
            try:
                await hooks.emit(SESSION_START, {"session_id": session_id, "channel": channel_name})
            except Exception:
                pass
            info._hook_session_started = True  # type: ignore[attr-defined]

        if hooks is not None:
            try:
                await hooks.emit(AGENT_START, {
                    "session_id": session_id,
                    "channel": channel_name,
                    "message": prompt[:500],
                })
            except Exception:
                pass

        _last_response_text = ""
        try:
            async for event in info.agent.run(
                prompt=prompt,
                system_prompt=system_prompt,
                custom_instructions=custom_instructions,
            ):
                # Accumulate the assistant response for the agent:end hook.
                if isinstance(event, TextDelta) and event.text:
                    _last_response_text += event.text
                # agent:step -- approximate Hermes' per-tool-iteration point by
                # firing on each ToolResult (a tool call completing).
                if hooks is not None and isinstance(event, ToolResult) and event.id:
                    try:
                        await hooks.emit(AGENT_STEP, {
                            "session_id": session_id,
                            "tool_id": event.id,
                        })
                    except Exception:
                        pass
                yield event
        except asyncio.CancelledError:
            logger.info("[router] session %s cancelled", session_id)
            yield Finish(reason="cancelled")
        except Exception as e:
            logger.error("[router] run error [%s] session=%s: %s %s",
                         channel_name, session_id, type(e).__name__, e)
            yield Finish(reason="error", error=str(e))
        finally:
            info.is_running = False
            self._manager.release_slot()
            self._manager._save_session(info)
            self._manager.notify_session_completed()
            self._active_streams.pop(stream_key, None)
            if hooks is not None:
                try:
                    await hooks.emit(AGENT_END, {
                        "session_id": session_id,
                        "channel": channel_name,
                        "response": _last_response_text,
                    })
                except Exception:
                    pass
            logger.info("[router] session %s done and saved", session_id)

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a running session by id. Returns True if a session was found."""
        info = self._manager.get_session(session_id)
        if info is None or not info.is_running:
            return False
        if info.agent_task and not info.agent_task.done():
            info.agent.loop.cancel()
            info.agent_task.cancel()
        info.is_running = False
        self._manager.release_slot()
        return True

    def get_session_ids(self) -> list[str]:
        """Return all active session IDs."""
        return [
            s["session_id"]
            for s in self._manager.list_sessions()
        ]

    async def shutdown(self) -> None:
        self._running = False
        for sid in list(self._active_streams.keys()):
            self.cancel_session(sid.split(":", 1)[1] if ":" in sid else sid)
        self._active_streams.clear()
