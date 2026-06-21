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
Adapter manager for the Encre multi-channel messaging system.

This module provides the central lifecycle management for all platform adapters:
- Registry: Maintains a mapping of adapter names to classes (_ADAPTER_CLASSES)
- Gateway: Wraps a GatewayServer for inter-process communication between
  adapters and the agent backend
- Configuration: Applies configuration changes from the frontend, handling
  adapter start/stop/restart automatically
- Status: Provides aggregated status for all adapters for UI display

Configuration format:
    The frontend sends a flat config dict where adapter configs are prefixed
    with "adapter_<name>_" (e.g., "adapter_feishu_app_id": "xxx"). This module
    extracts nested configs, validates required fields, and applies changes.

Architecture:
    AdapterManager sits between the GatewayServer (accepting WebSocket messages
    from the frontend) and the individual adapter instances. It translates  # noqa: E402
    high-level configure/start/stop commands into adapter-level operations.

    In iClaw mode (when session_manager is provided), the GatewayServer routes
    adapter messages through an EventRouter to the appropriate agent session,
    enabling the AI agent to interact with users across all enabled platforms.
"""

import logging
from collections.abc import Callable
from typing import Any

from encre.gateway.server import GatewayServer

logger = logging.getLogger("encre.adapters.manager")

# Global registry mapping adapter name strings to their class objects.
# Populated lazily by _init_adapter_map() on first use.
_ADAPTER_CLASSES: dict[str, Any] = {}


def _init_adapter_map() -> None:
    """Lazy-initialize the adapter class registry by importing all adapters.

    This function uses a singleton pattern: once the registry is populated,
    subsequent calls return immediately without re-importing. The import
    is done inside a try/except to handle cases where optional dependencies
    (e.g., discord.py, telegram) are not installed -- in that case, the
    corresponding adapter class simply won't be in the registry.

    The registry uses each adapter's class attribute `name` as the key,
    which must match the adapter_id used in configuration.
    """
    if _ADAPTER_CLASSES:
        return
    try:
        from encre.adapters import (
            BlueBubblesAdapter,
            DingTalkAdapter,
            DiscordAdapter,
            EmailAdapter,
            FeishuAdapter,
            HomeAssistantAdapter,
            MatrixAdapter,
            MSGraphAdapter,
            QQBotAdapter,
            SignalAdapter,
            SlackAdapter,
            SmsAdapter,
            TelegramAdapter,
            WebhookAdapter,
            WeComAdapter,
            WeixinAdapter,
            WhatsAppAdapter,
            YuanbaoAdapter,
        )
        for _cls in [QQBotAdapter, TelegramAdapter, DiscordAdapter,
                     WeixinAdapter, FeishuAdapter, DingTalkAdapter,
                     SlackAdapter, SignalAdapter, MatrixAdapter,
                     SmsAdapter, WeComAdapter, WebhookAdapter,
                     WhatsAppAdapter, EmailAdapter, HomeAssistantAdapter,
                     MSGraphAdapter, YuanbaoAdapter, BlueBubblesAdapter]:
            _ADAPTER_CLASSES[_cls.name] = _cls
    except Exception as e:
        logger.warning("Failed to load adapter classes: %s", e)


def _field_key(adapter_id: str, field: str) -> str:
    """Generate a flat config key for an adapter field.

    Used to encode nested adapter configuration into a flat key-value store
    compatible with the frontend's configuration UI.

    Args:
        adapter_id: The adapter name (e.g., "feishu", "discord").
        field: The configuration field name (e.g., "app_id", "token").

    Returns:
        A flat config key like "adapter_feishu_app_id".
    """
    return f"adapter_{adapter_id}_{field}"


def _extract_adapter_config(flat_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract nested adapter configs from the flat config dict sent by the frontend.

    The frontend sends all config as a flat dict with prefixed keys (e.g.,
    "adapter_feishu_app_id": "xxx", "adapter_feishu_app_secret": "yyy").
    This function groups them back into nested dicts per adapter.

    Args:
        flat_config: The flat configuration dictionary from the frontend.

    Returns:
        Nested dict mapping adapter_id -> {field: value}.
        E.g., {"feishu": {"app_id": "xxx", "app_secret": "yyy"}, "discord": {"token": "zzz"}}

    Example:
        >>> flat = {"adapter_feishu_app_id": "123", "adapter_discord_token": "abc"}
        >>> _extract_adapter_config(flat)
        {"feishu": {"app_id": "123"}, "discord": {"token": "abc"}}
    """
    result: dict[str, dict[str, Any]] = {}
    for key, value in flat_config.items():
        if key.startswith("adapter_"):
            parts = key.split("_", 2)
            if len(parts) >= 3:
                aid = parts[1]
                fk = parts[2]
                result.setdefault(aid, {})[fk] = value
    return result


class AdapterManager:
    """Central lifecycle manager for all platform channel adapters.

    Responsibilities:
    1. Gateway Management: Creates and controls the GatewayServer that accepts
       WebSocket connections from the frontend.
    2. Adapter Registry: Maintains a mapping of adapter names to class objects
       and active instance objects.
    3. Configuration: Parses flat config from the frontend, validates required
       fields, and applies changes by starting/stopping/restarting adapters.
    4. Status Aggregation: Provides a consolidated status dict for all adapters
       for UI display and health monitoring.
    5. iClaw Mode: When session_manager is provided, configures an EventRouter
       to route incoming adapter messages to the correct AI agent session.

    Configuration flow:
        Frontend sends flat config -> _extract_adapter_config() groups by adapter
        -> _is_configured() validates required fields -> start_adapter() creates
        and connects the adapter instance -> _notify_status() pushes status update

    Concurrency:
        All public methods are async and designed to be called from the asyncio
        event loop. The adapter instances themselves manage their own background
        tasks (e.g., WebSocket listeners, HTTP servers).
    """

    def __init__(
        self,
        gateway_host: str = "127.0.0.1",
        gateway_port: int = 18792,
        status_callback: Callable[[dict[str, Any]], None] | None = None,
        session_manager=None,
        config=None,
    ) -> None:
        """Initialize the adapter manager.

        Args:
            gateway_host: Host address for the GatewayServer WebSocket.
            gateway_port: Port for the GatewayServer WebSocket.
            status_callback: Async callable invoked with status dict whenever
                adapter status changes (e.g., connected, disconnected, error).
                Used to push real-time updates to the frontend UI.
            session_manager: Optional session manager for iClaw mode. When provided,
                an EventRouter is created to route adapter messages to agent sessions.
            config: Optional configuration dict used alongside session_manager
                to create the EventRouter.
        """
        _init_adapter_map()
        # EventRouter for routing messages through SessionManager (iClaw mode)
        self._router = None
        if session_manager and config:
            from encre.channels.base import EventRouter
            self._router = EventRouter(session_manager, config)
        # GatewayServer accepts WebSocket connections from the frontend
        self._gateway = GatewayServer(
            engine=self,  # self._router is checked by GatewayServer
            host=gateway_host,
            port=gateway_port,
            max_connections=32,
        )
        # Active adapter instances: adapter_id -> adapter_instance
        self._instances: dict[str, Any] = {}
        # Last error per adapter: adapter_id -> error_message
        self._last_errors: dict[str, str] = {}
        # Stored credentials for adapters (allows enable toggle without re-sending secrets)
        self._stored_configs: dict[str, dict[str, Any]] = {}
        # Fixed session_id per adapter -- all messages from the same adapter share one session
        self._adapter_sessions: dict[str, str] = {}
        self._status_callback = status_callback
        self._running = False

    @property
    def gateway(self) -> GatewayServer:
        """The underlying GatewayServer instance.

        Returns:
            The GatewayServer for WebSocket communication with the frontend.
        """
        return self._gateway

    @property
    def router(self):
        """EventRouter for routing messages through SessionManager (iClaw mode).

        Returns:
            The EventRouter instance, or None if iClaw mode is not enabled.
        """
        return self._router

    async def start_gateway(self) -> None:
        """Start the GatewayServer to accept WebSocket connections from the frontend.

        Idempotent -- calling multiple times is safe. Also starts all enabled
        adapters that were configured before gateway startup.
        """
        if self._running:
            return
        self._running = True
        await self._gateway.start()
        logger.info("Adapter gateway started")

    async def stop_gateway(self) -> None:
        """Stop the GatewayServer and all running adapters.

        First stops all adapter instances, then stops the gateway server.
        This is the opposite of start_gateway() and performs a clean shutdown.
        """
        await self.stop_all()
        await self._gateway.stop()
        self._running = False
        logger.info("Adapter gateway stopped")

    async def start_adapter(self, adapter_id: str, config: dict[str, Any]) -> bool:
        """Start a single adapter instance with the given configuration.

        Looks up the adapter class by name, constructs an instance with the
        provided config, and calls its connect() method. On success, stores
        the instance for later management. On failure, records the error.

        Args:
            adapter_id: The adapter name (e.g., "feishu", "discord"). Must
                match the `name` class attribute of a registered adapter.
            config: Configuration dictionary with adapter-specific parameters
                (credentials, ports, etc.). The "enabled" field is ignored.

        Returns:
            True if the adapter started successfully, False on failure.
            Errors are logged and stored in _last_errors.
        """
        cls = _ADAPTER_CLASSES.get(adapter_id)
        if cls is None:
            msg = f"Unknown adapter: {adapter_id}"
            logger.warning(msg)
            self._last_errors[adapter_id] = msg
            return False

        # Build constructor kwargs from config, excluding the "enabled" field
        kwargs = {}
        for k, v in config.items():
            if k != "enabled":
                kwargs[k] = v

        try:
            instance = cls(**kwargs)
            ok = await instance.connect()
            if ok:
                self._instances[adapter_id] = instance
                self._last_errors.pop(adapter_id, None)
                logger.info("Adapter '%s' started successfully", adapter_id)
            else:
                err = getattr(instance, "_fatal_error_message", None) or "connect() returned False"
                self._last_errors[adapter_id] = err
                logger.warning("Adapter '%s' connect failed: %s", adapter_id, err)
            await self._notify_status()
            return ok
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self._last_errors[adapter_id] = msg
            logger.error("Failed to start adapter '%s': %s", adapter_id, msg)
            await self._notify_status()
            return False

    async def stop_adapter(self, adapter_id: str) -> None:
        """Stop and remove a single adapter instance.

        Calls the adapter's disconnect() method to perform a clean shutdown
        of platform connections and background tasks.

        Args:
            adapter_id: The adapter name to stop.
        """
        instance = self._instances.pop(adapter_id, None)
        if instance:
            try:
                await instance.disconnect()
                logger.info("Adapter '%s' stopped", adapter_id)
            except Exception as e:
                logger.warning("Error stopping adapter '%s': %s", adapter_id, e)
        await self._notify_status()

    async def start_all(self, adapter_configs: dict[str, dict[str, Any]]) -> None:
        """Start all enabled and fully configured adapters at once.

        Iterates through the config dict and starts each adapter whose
        "enabled" field is True and all required configuration fields are present.

        Args:
            adapter_configs: Dict mapping adapter_id -> config dict.
        """
        for adapter_id, cfg in adapter_configs.items():
            if cfg.get("enabled") and self._is_configured(adapter_id, cfg):
                await self.start_adapter(adapter_id, cfg)

    async def stop_all(self) -> None:
        """Stop all currently running adapters.

        Iterates through all active adapter instances and calls disconnect()
        on each. This is used during shutdown and before applying new config.
        """
        ids = list(self._instances.keys())
        for aid in ids:
            await self.stop_adapter(aid)

    async def apply_config(self, flat_config: dict[str, Any]) -> None:
        """Apply a configuration update received from the frontend.

        This is the main configuration entry point. It:
        1. Extracts nested adapter configs from the flat format
        2. For each adapter, determines if it should be started, stopped, or restarted
        3. Stores credentials internally so they persist across config updates
        4. Auto-enables adapters when credentials are provided (saving = starting)

        The auto-enable logic means users don't need to manually toggle the
        "enabled" switch after saving credentials -- the save action implies start.

        Args:
            flat_config: The flat configuration dictionary from the frontend
                with keys like "adapter_feishu_app_id", "adapter_discord_token", etc.
        """
        nested = _extract_adapter_config(flat_config)
        for adapter_id, cfg in nested.items():
            cls = _ADAPTER_CLASSES.get(adapter_id)
            if cls is None:
                continue

            enabled = cfg.get("enabled", False)
            is_running = adapter_id in self._instances

            # Check if credentials are present in the current message
            has_credentials = self._is_configured(adapter_id, cfg)
            if has_credentials:
                # Store credentials for later use (e.g., enable toggle without re-sending)
                # Merge with existing stored config so non-credential fields like
                # push_chat_id are not lost when a partial config arrives (e.g. test flow).
                merged = self._stored_configs.get(adapter_id, {})
                merged.update({k: v for k, v in cfg.items() if k != "enabled"})
                self._stored_configs[adapter_id] = merged

            # If no credentials in message but enabled, try stored config
            if not has_credentials and enabled:
                stored = self._stored_configs.get(adapter_id)
                if stored:
                    cfg.update(stored)
                    has_credentials = True

            # Auto-enable when credentials are saved -- saving implies start
            if has_credentials and not enabled:
                enabled = True

            if enabled and has_credentials:
                if is_running:
                    # Restart if config changed
                    await self.stop_adapter(adapter_id)
                await self.start_adapter(adapter_id, cfg)
            elif not enabled and is_running:
                await self.stop_adapter(adapter_id)

    def _is_configured(self, adapter_id: str, cfg: dict[str, Any]) -> bool:
        """Check if an adapter has all required configuration fields filled.

        Uses introspection of the adapter class's __init__ signature to
        determine which parameters are required (no default value), then
        checks that each required field is present and non-empty in the config.

        Args:
            adapter_id: The adapter name to check.
            cfg: Configuration dict for this adapter.

        Returns:
            True if all required fields are present and non-empty, False otherwise.
        """
        cls = _ADAPTER_CLASSES.get(adapter_id)
        if cls is None:
            return False
        # Get constructor params (skip self, gateway_url)
        import inspect
        sig = inspect.signature(cls.__init__)
        required = [
            p.name for p in sig.parameters.values()
            if p.name != "self" and p.name != "gateway_url"
            and p.default is inspect.Parameter.empty
        ]
        if not required:
            return True
        return all(cfg.get(r) for r in required)

    def get_status(self) -> dict[str, Any]:
        """Get aggregated status for all adapters for UI display.

        Builds a status dict containing gateway state and per-adapter status
        (connected/running/error). This is the primary data source for the
        frontend's adapter management UI.

        Returns:
            Dict with keys:
            - running: Whether the gateway is running
            - gateway: GatewayServer status dict
            - adapters: List of per-adapter status dicts with name, connected,
              running, and error fields.
        """
        gw_status = self._gateway.get_status()
        adapter_list = []
        for adapter_id, _cls in _ADAPTER_CLASSES.items():
            connected = adapter_id in self._instances
            self._instances.get(adapter_id)
            error = self._last_errors.get(adapter_id)
            adapter_list.append({
                "name": adapter_id,
                "connected": connected,
                "running": connected,
                "error": error,
            })
        return {
            "running": self._running,
            "gateway": gw_status,
            "adapters": adapter_list,
        }

    async def _notify_status(self) -> None:
        """Push current status to the registered callback.

        Invoked after any adapter state change (start/stop/error).
        The callback is typically set by the server to push real-time
        status updates to the frontend via WebSocket.
        """
        if self._status_callback:
            try:
                await self._status_callback(self.get_status())
            except Exception as e:
                logger.warning("Status callback error: %s", e)

    async def ensure_adapter_session(self, adapter_name: str) -> str | None:
        """Get or create a fixed session_id for the given adapter.

        Returns the session_id string, or None if session_manager is not available.
        """
        if adapter_name in self._adapter_sessions:
            return self._adapter_sessions[adapter_name]
        if not self._router or not self._router.session_manager:
            return None
        info = self._router.session_manager.create_session(
            config=self._router._default_config
        )
        self._adapter_sessions[adapter_name] = info.session_id
        logger.info("[adapter-manager] created fixed session %s for adapter %s",
                     info.session_id, adapter_name)
        return info.session_id
