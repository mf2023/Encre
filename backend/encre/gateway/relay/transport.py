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

"""Relay transport interface.

A :class:`RelayTransport` Protocol describing the contract between
:class:`~encre.gateway.relay.adapter.RelayAdapter` and a concrete transport
(the production :class:`~encre.gateway.relay.ws_transport.WebSocketRelayTransport`,
or a test double).  The transport carries **normalized event/action dicts**,
not raw bytes -- the connector already verified the platform signature at the
edge and stripped credentials, so the gateway re-processes a sanitized event.
"""

from typing import Any, Callable, Protocol, runtime_checkable

from encre.gateway.relay.descriptor import CapabilityDescriptor


@runtime_checkable
class RelayTransport(Protocol):
    """The transport surface a :class:`RelayAdapter` depends on.

    The gateway dials **out** to the connector's ``/relay`` endpoint, receives a
    :class:`CapabilityDescriptor` at handshake, then exchanges normalized
    ``MessageEvent`` envelopes (inbound) and action dicts (outbound) over a
    per-turn bidirectional connection.
    """

    async def connect(self) -> bool:
        """Open the transport and perform the handshake.

        Returns True on success.  A 4401 close after a prior successful
        handshake must be surfaced via :attr:`was_revoked` (terminal), not a
        retryable failure.
        """
        ...

    async def disconnect(self) -> None:
        """Close the transport cleanly."""
        ...

    async def handshake(self) -> CapabilityDescriptor:
        """Return the capability descriptor negotiated at connect time.

        Raises if the handshake has not completed.
        """
        ...

    def set_inbound_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register the callback for connector->gateway ``inbound`` frames.

        The handler receives the normalized ``MessageEvent`` dict.
        """
        ...

    def set_passthrough_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register the callback for ``passthrough_forward`` frames (Class-2/3
        webhooks like Discord interactions / Twilio).

        The handler receives the decoded :class:`PassthroughForward` dict
        (``{platform, botId, method, path, headers, bodyB64}``).
        """
        ...

    async def send_outbound(self, action: dict[str, Any], *, platform: str | None = None) -> dict[str, Any]:
        """Send an outbound action (``send`` / ``edit`` / ``typing``) and await
        the connector's ``outbound_result``.

        Returns the result dict (``{success, message_id?, error?}``).
        """
        ...

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        """Proxy a ``get_chat_info`` call to the connector.

        Returns at least ``{name, type}``.
        """
        ...

    async def send_interrupt(self, session_key: str, reason: str | None = None) -> None:
        """Egress a mid-turn ``/stop`` (``interrupt`` frame) for a session."""
        ...

    async def go_idle(self, timeout_s: float = 10.0) -> bool:
        """Scale-to-zero primitive: emit ``going_idle`` and await
        ``going_idle_ack``.  Returns True on ack, False on timeout.
        """
        ...

    async def send_follow_up(self, action: dict[str, Any], *, platform: str | None = None) -> dict[str, Any]:
        """Send a token-less ``follow_up`` action (A2 shared-identity capability).

        The gateway names the **session** it is already in plus the capability
        ``kind`` (e.g. ``discord.interaction_token``) -- never a token.  The
        connector resolves the real value from its vault.
        """
        ...

    @property
    def was_revoked(self) -> bool:
        """True once the connector closed the socket with 4401 AFTER a prior
        successful handshake (a terminal revocation -- do not reconnect).
        """
        ...
