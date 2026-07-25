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

"""Remote platform adapter: wraps a WS connection as a BasePlatformAdapter.

When a remote adapter connects to the WsBridgeServer, it is wrapped in a
:class:`RemotePlatformAdapter` instance which presents the standard
BasePlatformAdapter interface to the GatewayRunner.

Inbound: WS receives SUBMIT_STREAM -> builds MessageEvent -> handle_message
Outbound: send() -> sends TEXT_DELTA/FINISH frames over WS
"""

import asyncio
import json
import logging
from typing import Any

from encre.gateway.config import Platform, PlatformConfig
from encre.gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from encre.gateway.ws_bridge.protocol import GatewayMessage, GatewayOp

logger = logging.getLogger("encre.gateway.ws_bridge.remote_adapter")


class RemotePlatformAdapter(BasePlatformAdapter):
    """Wraps a remote WebSocket connection as a local BasePlatformAdapter.

    This adapter serves as a proxy for a remote adapter connected via the
    WS bridge.  The remote adapter sends SUBMIT/SUBMIT_STREAM frames, and
    this adapter translates them into MessageEvent dispatches.  Outbound
    send() calls are translated into TEXT_DELTA + FINISH frames sent back
    over the WebSocket.
    """

    supports_async_delivery: bool = True

    def __init__(
        self,
        config: PlatformConfig,
        platform: Platform,
        ws: Any,
        remote_name: str,
    ) -> None:
        super().__init__(config=config, platform=platform)
        self._ws = ws
        self._remote_name = remote_name
        self._seq = 0

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._remote_name

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Remote adapter is already connected via WS."""
        self._running = True
        return True

    async def disconnect(self) -> None:
        """Close the WS connection to the remote adapter."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send content back to the remote adapter via WS."""
        if not self._ws:
            return SendResult(success=False, error="WS disconnected")
        try:
            self._seq += 1
            msg = GatewayMessage.text_delta(content, session_id=chat_id)
            msg.seq = self._seq
            await self._ws.send(json.dumps(msg.to_dict()))
            return SendResult(success=True)
        except Exception as e:
            logger.error("[remote-adapter] %s send error: %s", self._remote_name, e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Remote adapters don't provide chat info."""
        return {"id": chat_id, "type": "remote", "adapter": self._remote_name}
