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
import json
import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None

from encre.adapters.base import BaseAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger("encre.adapters.homeassistant")

_HA_WS_RECONNECT_BACKOFF = [5, 10, 30, 60]
_HA_MAX_MESSAGE_LENGTH = 4096
_HA_DEFAULT_COOLDOWN = 30


class HomeAssistantAdapter(BaseAdapter):
    """Home Assistant WebSocket adapter.

    Connects to the HA WebSocket API for real-time event monitoring.
    State-change events are converted to :class:`MessageEvent` objects and
    forwarded to the Encre agent for processing.  Outbound messages are
    delivered as HA persistent notifications via the REST API.

    Requires ``aiohttp``::

        pip install aiohttp

    Args:
        url: Home Assistant instance URL.
        token: Long-Lived Access Token for HA authentication.
        gateway_url: Encre gateway WebSocket URL.

    Example standalone usage::

        import asyncio  # noqa: E402
        from encre.adapters.homeassistant import HomeAssistantAdapter  # noqa: E402

        async def main():
            adapter = HomeAssistantAdapter(
                url="http://homeassistant.local:8123",
                token="your_long_lived_token",
            )
            await adapter.connect()
            try:
                await asyncio.Event().wait()
            finally:
                await adapter.disconnect()

        asyncio.run(main())
    """

    name = "homeassistant"

    def __init__(
        self,
        url: str = "http://homeassistant.local:8123",
        token: str = "",
        *,
        gateway_url: str = "ws://127.0.0.1:18792/gateway",
        watch_domains: list[str] | None = None,
        watch_entities: list[str] | None = None,
        ignore_entities: list[str] | None = None,
        watch_all: bool = False,
        cooldown_seconds: int = _HA_DEFAULT_COOLDOWN,
    ) -> None:
        super().__init__(gateway_url=gateway_url, capabilities=["text"])
        self._hass_url = url.rstrip("/")
        self._hass_token = token
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._rest_session: aiohttp.ClientSession | None = None
        self._listen_task: asyncio.Task | None = None
        self._msg_id = 0

        self._watch_domains: set[str] = set(watch_domains or [])
        self._watch_entities: set[str] = set(watch_entities or [])
        self._ignore_entities: set[str] = set(ignore_entities or [])
        self._watch_all = watch_all
        self._cooldown_seconds = cooldown_seconds
        self._last_event_time: dict[str, float] = {}

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to HA WebSocket API and subscribe to state_changed events."""
        if not AIOHTTP_AVAILABLE:
            logger.warning(
                "[homeassistant] aiohttp not installed. Run: pip install aiohttp"
            )
            return False

        if not self._hass_token:
            logger.warning("[homeassistant] No HA access token configured")
            return False

        try:
            logger.info("[homeassistant] Connecting to WebSocket API")
            success = await self._ws_connect()
            if not success:
                return False

            logger.info("[homeassistant] Creating REST API session")
            self._rest_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                trust_env=True,
            )

            if not self._watch_domains and not self._watch_entities and not self._watch_all:
                logger.warning(
                    "[homeassistant] No watch_domains, watch_entities, or watch_all "
                    "configured. All state_changed events will be dropped. "
                    "Configure filters to receive events."
                )

            logger.info("[homeassistant] Starting event listener")
            self._listen_task = asyncio.create_task(self._ws_listen())
            self._mark_connected()
            logger.info(
                "[homeassistant] Connected to %s", self._hass_url
            )
            return True

        except Exception as e:
            logger.error("[homeassistant] Failed to connect: %s", e)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Home Assistant."""
        self._running = False

        if self._listen_task is not None:
            self._listen_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None

        await self._cleanup_ws()
        if self._rest_session is not None and not self._rest_session.closed:
            await self._rest_session.close()
        self._rest_session = None

        await self._client.disconnect()
        logger.info("[homeassistant] Disconnected")

    # ── WebSocket connection management ────────────────────────────────────

    async def _ws_connect(self) -> bool:
        """Establish WebSocket connection and authenticate with HA."""
        ws_url = self._hass_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/api/websocket"

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            trust_env=True,
        )
        self._ws = await self._session.ws_connect(ws_url, heartbeat=30, timeout=30)

        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_required":
            logger.error(
                "[homeassistant] Expected auth_required, got: %s", msg.get("type")
            )
            await self._cleanup_ws()
            return False

        await self._ws.send_json({
            "type": "access_token",
            "access_token": self._hass_token,
        })

        msg = await self._ws.receive_json()
        if msg.get("type") != "auth_ok":
            logger.error("[homeassistant] Auth failed: %s", msg)
            await self._cleanup_ws()
            return False

        sub_id = self._next_id()
        await self._ws.send_json({
            "id": sub_id,
            "type": "subscribe_events",
            "event_type": "state_changed",
        })

        msg = await self._ws.receive_json()
        if not msg.get("success"):
            logger.error(
                "[homeassistant] Failed to subscribe to events: %s", msg
            )
            await self._cleanup_ws()
            return False

        return True

    async def _cleanup_ws(self) -> None:
        """Close WebSocket and HTTP session."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # ── Event listener ─────────────────────────────────────────────────────

    async def _ws_listen(self) -> None:
        """Main event listener loop with automatic reconnection backoff."""
        backoff_idx = 0

        while self._running:
            try:
                await self._read_events()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[homeassistant] WebSocket error: %s", e)

            if not self._running:
                return

            delay = _HA_WS_RECONNECT_BACKOFF[
                min(backoff_idx, len(_HA_WS_RECONNECT_BACKOFF) - 1)
            ]
            logger.info("[homeassistant] Reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            backoff_idx += 1

            try:
                await self._cleanup_ws()
                success = await self._ws_connect()
                if success:
                    backoff_idx = 0
                    logger.info("[homeassistant] Reconnected")
            except Exception as e:
                logger.warning("[homeassistant] Reconnection failed: %s", e)

    async def _read_events(self) -> None:
        """Read events from the WebSocket stream until disconnected."""
        if self._ws is None or self._ws.closed:
            return
        async for ws_msg in self._ws:
            if ws_msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(ws_msg.data)
                    if data.get("type") == "event":
                        self._handle_ha_event(data.get("event", {}))
                except json.JSONDecodeError:
                    logger.debug(
                        "[homeassistant] Invalid JSON from WS: %s",
                        ws_msg.data[:200],
                    )
            elif ws_msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                break

    def _handle_ha_event(self, event: dict[str, Any]) -> None:
        """Process a single state_changed event from Home Assistant."""
        event_data = event.get("data", {})
        entity_id: str = event_data.get("entity_id", "")

        if not entity_id:
            return

        if entity_id in self._ignore_entities:
            return

        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if self._watch_domains or self._watch_entities:
            domain_match = domain in self._watch_domains if self._watch_domains else False
            entity_match = entity_id in self._watch_entities if self._watch_entities else False
            if not domain_match and not entity_match:
                return
        elif not self._watch_all:
            return

        now = time.time()
        last = self._last_event_time.get(entity_id, 0)
        if (now - last) < self._cooldown_seconds:
            return
        self._last_event_time[entity_id] = now

        old_state = event_data.get("old_state", {})
        new_state = event_data.get("new_state", {})
        message = self._format_state_change(entity_id, old_state, new_state)

        if not message:
            return

        msg_event = MessageEvent(
            text=message,
            message_type=MessageType.TEXT,
            message_id=f"ha_{entity_id}_{int(now)}",
            chat_id="ha_events",
            user_id="homeassistant",
            raw=event_data,
            timestamp=datetime.now(),
        )

        self.dispatch_message(msg_event)

    @staticmethod
    def _format_state_change(
        entity_id: str,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> str | None:
        """Convert a state_changed event into a human-readable description."""
        if not new_state:
            return None

        old_val = old_state.get("state", "unknown") if old_state else "unknown"
        new_val = new_state.get("state", "unknown")

        if old_val == new_val:
            return None

        friendly_name = new_state.get("attributes", {}).get("friendly_name", entity_id)
        domain = entity_id.split(".")[0] if "." in entity_id else ""

        if domain == "climate":
            attrs = new_state.get("attributes", {})
            temp = attrs.get("current_temperature", "?")
            target = attrs.get("temperature", "?")
            return (
                f"[Home Assistant] {friendly_name}: HVAC mode changed from "
                f"'{old_val}' to '{new_val}' (current: {temp}, target: {target})"
            )

        if domain == "sensor":
            unit = new_state.get("attributes", {}).get("unit_of_measurement", "")
            return (
                f"[Home Assistant] {friendly_name}: changed from "
                f"{old_val}{unit} to {new_val}{unit}"
            )

        if domain == "binary_sensor":
            return (
                f"[Home Assistant] {friendly_name}: "
                f"{'triggered' if new_val == 'on' else 'cleared'} "
                f"(was {'triggered' if old_val == 'on' else 'cleared'})"
            )

        if domain in {"light", "switch", "fan"}:
            return (
                f"[Home Assistant] {friendly_name}: turned "
                f"{'on' if new_val == 'on' else 'off'}"
            )

        if domain == "alarm_control_panel":
            return (
                f"[Home Assistant] {friendly_name}: alarm state changed from "
                f"'{old_val}' to '{new_val}'"
            )

        return (
            f"[Home Assistant] {friendly_name} ({entity_id}): "
            f"changed from '{old_val}' to '{new_val}'"
        )

    # ── Outbound messaging ─────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,  # noqa: ARG002
        content: str,
        *,
        reply_to: str | None = None,  # noqa: ARG002
        metadata: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> SendResult:
        """Send a notification via HA REST API (persistent_notification.create).

        Uses the REST API instead of WebSocket to avoid a race condition
        with the event listener loop that reads from the same WS connection.
        """
        url = f"{self._hass_url}/api/services/persistent_notification/create"
        headers = {
            "Authorization": f"Bearer {self._hass_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "title": "Encre Agent",
            "message": content[:_HA_MAX_MESSAGE_LENGTH],
        }

        try:
            if self._rest_session is not None:
                async with self._rest_session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 300:
                        return SendResult(
                            success=True,
                            message_id=uuid.uuid4().hex[:12],
                        )
                    body = await resp.text()
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status}: {body}",
                        retryable=resp.status >= 500,
                    )
            else:
                async with aiohttp.ClientSession(trust_env=True) as session, session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 300:
                        return SendResult(
                            success=True,
                            message_id=uuid.uuid4().hex[:12],
                        )
                    body = await resp.text()
                    return SendResult(
                        success=False,
                        error=f"HTTP {resp.status}: {body}",
                        retryable=resp.status >= 500,
                    )

        except TimeoutError:
            return SendResult(
                success=False,
                error="Timeout sending notification to HA",
                retryable=True,
            )
        except Exception as e:
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_typing(self, chat_id: str) -> None:
        pass
