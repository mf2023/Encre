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

"""Gateway runner -- unified lifecycle manager for all platform adapters.

Replaces the former AdapterManager.  Core adapters run in-process (direct
callbacks); the optional WS bridge serves remote/plugin adapters.

Message flow:
    Adapter.handle_message -> GatewayRunner._on_message
    -> AuthorizationChecker -> build_session_key -> SessionStore
    -> EventRouter.submit_stream -> GatewayStreamConsumer -> adapter.send

Aligns with Hermes ``gateway/run.py``.
"""

import asyncio
import json
import logging
import pathlib
from collections.abc import Callable
from typing import Any

from encre.config import get_data_dir
from encre.gateway.authz import AuthorizationChecker
from encre.gateway.channel_directory import ChannelDirectory
from encre.gateway.config import GatewayConfig, Platform, PlatformConfig, load_gateway_config
from encre.gateway.delivery import DeliveryRouter
from encre.gateway.hooks import GATEWAY_STARTUP, get_hook_registry
from encre.gateway.pairing import PairingStore
from encre.gateway.platform_registry import PlatformEntry, platform_registry
from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from encre.gateway.response_filters import is_intentional_silence_response
from encre.gateway.session import SessionSource, SessionStore, build_session_key
from encre.gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig
from encre.utils.types import Finish, TextDelta, ToolResult

logger = logging.getLogger("encre.gateway.run")


def _field_key(adapter_id: str, field: str) -> str:
    """Generate a flat config key for an adapter field."""
    return f"adapter_{adapter_id}_{field}"


def _extract_adapter_config(flat_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract nested adapter configs from the flat config dict."""
    result: dict[str, dict[str, Any]] = {}
    for key, value in flat_config.items():
        if key.startswith("adapter_"):
            parts = key.split("_", 2)
            if len(parts) >= 3:
                aid = parts[1]
                fk = parts[2]
                result.setdefault(aid, {})[fk] = value
    return result


class GatewayRunner:
    """Unified gateway runner managing all platform adapters.

    Core adapters run in the same process and interact with the agent via
    direct async calls through the EventRouter.  The optional WS bridge
    (started via start_ws_bridge) serves remote/plugin adapters that connect
    over WebSocket.

    Public API (for frontend/desktop GUI):
        start() / stop()
        start_adapter(name, config) / stop_adapter(name)
        apply_config(flat_config)
        get_status() -> dict
    """

    def __init__(
        self,
        session_manager=None,
        config=None,
        status_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        # EventRouter for routing messages to the agent session
        self._router = None
        if session_manager and config:
            from encre.channels.base import EventRouter
            self._router = EventRouter(session_manager, config)

        # Session store: maps session_key -> agent session_id
        self._session_store = SessionStore()

        # Authorization + DM-pairing
        self._pairing = PairingStore()
        self._authz = AuthorizationChecker(pairing=self._pairing)

        # Delivery router for outbound content
        self._delivery: DeliveryRouter | None = None

        # Channel directory
        self._channel_dir = ChannelDirectory()

        # Active adapter instances: name -> adapter
        self._instances: dict[str, BasePlatformAdapter] = {}

        # Last error per adapter
        self._last_errors: dict[str, str] = {}

        # Stored configs for adapters (enables toggle without re-sending secrets)
        self._stored_configs: dict[str, dict[str, Any]] = {}

        # Fixed session_id per adapter (all messages from same adapter share one session)
        self._adapter_sessions: dict[str, str] = {}
        self._adapter_sessions_path = pathlib.Path(get_data_dir()) / "iclaw" / "adapter_sessions.json"
        self._load_adapter_sessions()

        # Hooks registry
        self._hooks = get_hook_registry()

        # Status callback (pushes to frontend)
        self._status_callback = status_callback

        # Runtime state
        self._running = False
        self._gateway_config: GatewayConfig | None = None

        # WS bridge (optional, for remote adapters)
        self._ws_bridge = None

    # -- Properties --

    @property
    def router(self):
        """EventRouter for routing messages to the agent."""
        return self._router

    @property
    def delivery(self) -> DeliveryRouter:
        """Outbound delivery router (created on first access)."""
        if self._delivery is None:
            self._delivery = DeliveryRouter(self)
        return self._delivery

    @property
    def instances(self) -> dict[str, BasePlatformAdapter]:
        """Active adapter instances."""
        return self._instances

    # -- Lifecycle --

    async def start(self) -> None:
        """Start the gateway: load config, discover adapters, connect enabled platforms."""
        if self._running:
            return
        self._running = True

        # Discover and register all built-in platform adapters
        from encre.gateway.platforms import discover_platforms
        discover_platforms()

        # Load gateway config
        self._gateway_config = load_gateway_config()

        # Discover and load hooks
        try:
            loaded = self._hooks.discover_and_load()
            if loaded:
                logger.info("[gateway] loaded %d hook(s): %s", len(loaded), loaded)
            await self._hooks.emit(GATEWAY_STARTUP, {"adapters": list(self._instances.keys())})
        except Exception as e:
            logger.warning("[gateway] hook startup failed: %s", e)

        # Load channel directory from disk cache
        self._channel_dir.load()

        # Register relay adapter if configured
        try:
            from encre.gateway.relay import relay_is_configured, register_relay_adapter
            if relay_is_configured():
                await register_relay_adapter(self)
        except Exception as e:
            logger.warning("[gateway] relay registration failed (non-fatal): %s", e)

        logger.info("[gateway] Gateway started")

    async def stop(self) -> None:
        """Stop all adapters and the gateway."""
        await self.stop_all()
        if self._ws_bridge is not None:
            await self._ws_bridge.stop()
            self._ws_bridge = None
        if self._session_store is not None:
            self._session_store.close()
        self._running = False
        logger.info("[gateway] Gateway stopped")

    async def start_ws_bridge(self, host: str = "127.0.0.1", port: int = 18792) -> None:
        """Start the optional WS bridge for remote adapters.

        Remote adapters connect via WebSocket and are wrapped as
        RemotePlatformAdapter instances.
        """
        from encre.gateway.ws_bridge.server import WsBridgeServer
        self._ws_bridge = WsBridgeServer(
            runner=self,
            host=host,
            port=port,
        )
        await self._ws_bridge.start()
        logger.info("[gateway] WS bridge started on ws://%s:%d", host, port)

    # -- Adapter management --

    async def start_adapter(self, name: str, config: dict[str, Any]) -> bool:
        """Start a single adapter by name with the given config.

        The adapter is looked up in the platform registry, instantiated via
        its factory, and connected.

        Returns True on success.
        """
        entry = platform_registry.get(name)
        if entry is None:
            msg = f"Unknown platform: {name}"
            logger.warning(msg)
            self._last_errors[name] = msg
            return False

        # Build PlatformConfig from the provided dict
        pconfig = PlatformConfig(
            enabled=True,
            token=str(config.get("token", "") or ""),
            extra={k: v for k, v in config.items() if k not in ("enabled", "token")},
        )

        # Validate
        if entry.validate_config is not None:
            try:
                if not entry.validate_config(pconfig):
                    msg = f"Config validation failed for {name}"
                    logger.warning(msg)
                    self._last_errors[name] = msg
                    return False
            except Exception as e:
                msg = f"Config validation error: {e}"
                self._last_errors[name] = msg
                return False

        try:
            adapter = entry.adapter_factory(pconfig)
            if adapter is None:
                msg = f"Factory returned None for {name}"
                self._last_errors[name] = msg
                return False

            # Wire up the message handler
            adapter.set_message_handler(self._on_message)

            # Connect
            ok = await adapter.connect()
            if ok:
                self._instances[name] = adapter
                self._last_errors.pop(name, None)
                logger.info("[gateway] Adapter '%s' started", name)
                # Update router's connected adapters list
                if self._router:
                    self._router.set_connected_adapters(list(self._instances.keys()))
            else:
                err = getattr(adapter, "_fatal_error_message", None) or "connect() returned False"
                self._last_errors[name] = err
                logger.warning("[gateway] Adapter '%s' connect failed: %s", name, err)

            await self._notify_status()
            return ok

        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self._last_errors[name] = msg
            logger.error("[gateway] Failed to start adapter '%s': %s", name, msg)
            await self._notify_status()
            return False

    async def stop_adapter(self, name: str) -> None:
        """Stop and remove a single adapter."""
        instance = self._instances.pop(name, None)
        if instance:
            try:
                await instance.disconnect()
                logger.info("[gateway] Adapter '%s' stopped", name)
            except Exception as e:
                logger.warning("[gateway] Error stopping adapter '%s': %s", name, e)
        if self._router:
            self._router.set_connected_adapters(list(self._instances.keys()))
        await self._notify_status()

    async def stop_all(self) -> None:
        """Stop all running adapters."""
        for name in list(self._instances.keys()):
            await self.stop_adapter(name)

    async def apply_config(self, flat_config: dict[str, Any]) -> None:
        """Apply a configuration update from the frontend.

        Extracts per-adapter configs, starts/stops/restarts as needed.
        """
        nested = _extract_adapter_config(flat_config)
        for adapter_id, cfg in nested.items():
            entry = platform_registry.get(adapter_id)
            if entry is None:
                continue

            # Store config for later restarts
            stored = self._stored_configs.get(adapter_id, {})
            stored.update(cfg)
            self._stored_configs[adapter_id] = stored

            enabled = str(cfg.get("enabled", stored.get("enabled", ""))).lower() in ("true", "1", "yes")
            is_running = adapter_id in self._instances

            if enabled and not is_running:
                await self.start_adapter(adapter_id, stored)
            elif not enabled and is_running:
                await self.stop_adapter(adapter_id)
            elif enabled and is_running:
                # Restart with new config
                await self.stop_adapter(adapter_id)
                await self.start_adapter(adapter_id, stored)

    def get_status(self) -> dict[str, Any]:
        """Get aggregated status for all adapters (for UI display)."""
        adapters_list = []
        for entry in platform_registry.all_entries():
            name = entry.name
            instance = self._instances.get(name)
            if instance:
                adapters_list.append({
                    "name": name,
                    "connected": instance.running,
                    "status": "connected" if instance.running else "error",
                    "error": instance._fatal_error_message,
                    "platform": entry.label,
                })
            elif name in self._last_errors:
                adapters_list.append({
                    "name": name,
                    "connected": False,
                    "status": "error",
                    "error": self._last_errors[name],
                    "platform": entry.label,
                })
            else:
                adapters_list.append({
                    "name": name,
                    "connected": False,
                    "status": "disconnected",
                    "platform": entry.label,
                })
        return {
            "running": self._running,
            "adapters": adapters_list,
            "adapter_count": len(self._instances),
        }

    # -- Core message handling --

    async def _on_message(self, adapter: BasePlatformAdapter, event: MessageEvent) -> None:
        """Core inbound message handler.

        Called by adapters when they receive a message from a platform user.
        Performs authorization, session routing, and agent invocation.
        """
        source = event.source
        if source is None:
            # Build a minimal source from available info
            source = adapter.build_source(
                chat_id=event.message_id or "unknown",
                user_id=None,
            )

        # 1. Authorization check
        if not adapter.authorization_is_upstream and self._authz is not None:
            result = self._authz.is_authorized(source, adapter.name)
            if not result.authorized:
                logger.info("[gateway] Unauthorized message from %s/%s: %s",
                           source.platform, source.user_id, result.reason)
                # Optionally send a rejection notice
                return

        # 2. Session routing
        session_key = build_session_key(source)
        session_id = self._session_store.get_or_create(session_key)

        # 3. Route to agent via EventRouter
        if self._router is None:
            logger.warning("[gateway] No router configured, dropping message")
            return

        # 4. Stream consumer for progressive delivery
        consumer_config = StreamConsumerConfig()
        # Disable progressive editing for platforms that don't support it
        if not hasattr(adapter, "edit_message") or adapter.max_message_length == 0:
            consumer_config.buffer_only = True

        consumer = GatewayStreamConsumer(
            adapter=adapter,
            chat_id=source.chat_id,
            config=consumer_config,
            reply_to=event.message_id,
            metadata={"thread_id": source.thread_id} if source.thread_id else None,
        )

        # 5. Submit to agent and consume the stream
        try:
            async with self._router.iclaw_context():
                async for agent_event in self._router.submit_stream(
                    source.platform, event.text, session_id=session_id
                ):
                    await consumer.feed(agent_event)

            # 6. Finalize delivery
            final_text = await consumer.finalize()

            # 7. Filter silence responses
            if is_intentional_silence_response(final_text):
                logger.info("[gateway] Suppressed silence response for %s", session_key)

        except Exception as e:
            logger.error("[gateway] Message processing error: %s %s", type(e).__name__, e)
            # Try to send an error notice
            try:
                await adapter.send(source.chat_id, f"[Error: {e}]")
            except Exception:
                pass

    # -- Session management --

    async def resolve_session(self, adapter_name: str, source: SessionSource) -> str:
        """Resolve a session_id for a given source (used by WS bridge)."""
        session_key = build_session_key(source)
        return self._session_store.get_or_create(session_key)

    async def ensure_adapter_session(self, adapter_name: str) -> str:
        """Ensure a fixed session exists for an adapter (legacy compat)."""
        if adapter_name in self._adapter_sessions:
            return self._adapter_sessions[adapter_name]
        import uuid
        session_id = uuid.uuid4().hex
        self._adapter_sessions[adapter_name] = session_id
        self._save_adapter_sessions()
        return session_id

    def _load_adapter_sessions(self) -> None:
        """Load persisted adapter->session mappings."""
        if self._adapter_sessions_path.exists():
            try:
                with open(self._adapter_sessions_path, "r", encoding="utf-8") as f:
                    self._adapter_sessions = json.load(f)
            except Exception:
                self._adapter_sessions = {}

    def _save_adapter_sessions(self) -> None:
        """Persist adapter->session mappings."""
        try:
            self._adapter_sessions_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._adapter_sessions_path, "w", encoding="utf-8") as f:
                json.dump(self._adapter_sessions, f)
        except Exception as e:
            logger.warning("[gateway] Failed to save adapter sessions: %s", e)

    # -- Status notification --

    async def _notify_status(self) -> None:
        """Push status update to the frontend."""
        if self._status_callback:
            try:
                status = self.get_status()
                result = self._status_callback(status)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("[gateway] Status callback error: %s", e)
