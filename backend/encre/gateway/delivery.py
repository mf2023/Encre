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

"""Gateway outbound delivery routing.

Aligns with Hermes' ``gateway/delivery.py``: a single router that takes a
content blob plus a list of targets and delivers to each, handling:

- **Explicit targets** -- ``"platform:chat_id"`` strings (e.g.
  ``"telegram:123456789"``), the canonical cron / ``hermes send`` form.
- **Adapter-id targets** -- bare adapter names (e.g. ``"telegram"``), delivered
  to the adapter's auto-detected push target (``default_push_chat_id``).
- **Origin fallback** -- when no targets are given, deliver back to the
  originating chat (the live-reply path).
- **Truncation** -- outputs over :data:`MAX_PLATFORM_OUTPUT` chars are saved in
  full to an audit file and the adapter receives either the full payload (when
  it advertises ``splits_long_messages``) or a truncated payload with a
  ``"... [truncated, full output saved to <path>]"`` note.

This is independent of the live chat stream (which is driven by
:meth:`BaseAdapter.handle_message`): cron outputs and explicit-target sends
flow through here and are deliberately NOT mirrored into session history (a
Hermes design choice to avoid message-alternation violations).
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from encre.config import get_data_dir

logger = logging.getLogger("encre.gateway.delivery")

# Soft cap for platform output.  Over this, the full text is saved to disk and
# the adapter receives a truncated payload + note (unless it self-chunks).
# Mirrors Hermes MAX_PLATFORM_OUTPUT.
MAX_PLATFORM_OUTPUT = 4000
# Suffix appended to truncated payloads.  Hermes uses a similar note.
_TRUNCATION_NOTE = "... [truncated, full output saved to {path}]"


@dataclass(frozen=True)
class DeliveryTarget:
    """A resolved delivery destination.

    Attributes:
        raw: The original target string (e.g. ``"telegram:123"`` or ``"telegram"``).
        platform: The adapter/platform name (e.g. ``"telegram"``).
        chat_id: The explicit chat id, or None when the target was a bare
            adapter id (resolved at send time via ``default_push_chat_id``).
    """

    raw: str
    platform: str
    chat_id: str | None = None

    @classmethod
    def parse(cls, raw: str) -> "DeliveryTarget":
        """Parse a target string into a :class:`DeliveryTarget`.

        Accepted forms:
        - ``"platform:chat_id"`` -- explicit chat.
        - ``"platform"`` -- adapter id, resolved to its push target at send.
        """
        raw = raw.strip()
        if ":" in raw:
            platform, chat_id = raw.split(":", 1)
            return cls(raw=raw, platform=platform.strip(), chat_id=chat_id.strip() or None)
        return cls(raw=raw, platform=raw, chat_id=None)


@dataclass
class DeliveryResult:
    """Per-target outcome of a :meth:`DeliveryRouter.deliver` call."""

    target: str
    success: bool
    message_id: str | None = None
    error: str | None = None
    truncated: bool = False
    saved_path: str | None = None


class DeliveryRouter:
    """Routes outbound content to one or more platform targets.

    Owned by :class:`~encre.gateway.run.GatewayRunner` (which holds the
    live adapter instances).  Callers (automation/cron push, the send engine)
    pass a content blob and a list of target strings; the router resolves each
    to a live adapter, applies truncation, and sends.
    """

    def __init__(
        self,
        adapter_manager: Any,
        *,
        max_output: int = MAX_PLATFORM_OUTPUT,
        audit_dir: str | Path | None = None,
    ) -> None:
        self._am = adapter_manager
        self._max_output = max_output
        if audit_dir is None:
            audit_dir = Path(get_data_dir()) / "delivery_audit"
        self._audit_dir = Path(audit_dir)

    # ── lookup ─────────────────────────────────────────────────────────

    def _get_adapter(self, platform: str) -> Any | None:
        instances = getattr(self._am, "_instances", {}) or {}
        adapter = instances.get(platform)
        if adapter is None:
            logger.warning("[delivery] adapter '%s' not running", platform)
        return adapter

    def _resolve_chat_id(self, adapter: Any, target: DeliveryTarget) -> str | None:
        """Resolve the chat id for a target, falling back to the adapter's
        auto-detected push target (most recent inbound chat)."""
        if target.chat_id:
            return target.chat_id
        push = getattr(adapter, "default_push_chat_id", None)
        if push is None:
            logger.warning("[delivery] target '%s' has no explicit chat_id and "
                           "adapter has no default push target", target.raw)
        return push

    # ── truncation ─────────────────────────────────────────────────────

    def _maybe_truncate(self, content: str, adapter: Any) -> tuple[str, bool, str | None]:
        """Apply truncation per the adapter's capability bits.

        Returns ``(payload, truncated, saved_path)``:
        - If the adapter self-chunks (``splits_long_messages``), the full
          content is returned unchanged.
        - Otherwise, over-cap content is saved to an audit file and a
          truncated payload + note is returned.
        - Under-cap content passes through unchanged.
        """
        if not content or len(content) <= self._max_output:
            return content, False, None
        if getattr(adapter, "splits_long_messages", False):
            # Adapter handles its own chunking -- pass the full payload.
            return content, False, None
        # Truncate + save full output to disk.
        saved = self._save_audit(content)
        note = _TRUNCATION_NOTE.format(path=saved)
        cut = self._max_output - len(note) - 1
        if cut < 0:
            cut = 0
        payload = content[:cut] + "\n" + note
        logger.info("[delivery] truncated %d -> %d chars, full saved to %s",
                    len(content), len(payload), saved)
        return payload, True, saved

    def _save_audit(self, content: str) -> str:
        """Save the full content to an audit file, return its path."""
        try:
            self._audit_dir.mkdir(parents=True, exist_ok=True)
            name = f"output_{int(time.time() * 1000)}.txt"
            path = self._audit_dir / name
            path.write_text(content, encoding="utf-8")
            return str(path)
        except Exception as e:
            logger.warning("[delivery] failed to save audit output: %s", e)
            return "<save failed>"

    # ── deliver ────────────────────────────────────────────────────────

    async def deliver(
        self,
        content: str,
        targets: list[str] | None = None,
        *,
        origin: tuple[str, str] | None = None,
    ) -> list[DeliveryResult]:
        """Deliver ``content`` to each target.

        Args:
            content: The text to deliver.
            targets: Target strings (``"platform:chat_id"`` or ``"platform"``).
                When None/empty, falls back to ``origin`` (the originating
                platform + chat id) if provided.
            origin: Optional ``(platform, chat_id)`` fallback when no explicit
                targets are given (the live-reply / cron-home case).

        Returns:
            One :class:`DeliveryResult` per target.
        """
        if not targets and origin is not None:
            plat, chat = origin
            targets = [f"{plat}:{chat}" if chat else plat]
        if not targets:
            logger.warning("[delivery] no targets and no origin -- nothing to deliver")
            return []

        results: list[DeliveryResult] = []
        for raw in targets:
            target = DeliveryTarget.parse(raw)
            adapter = self._get_adapter(target.platform)
            if adapter is None:
                results.append(DeliveryResult(target=raw, success=False,
                                               error=f"adapter '{target.platform}' not running"))
                continue
            chat_id = self._resolve_chat_id(adapter, target)
            if not chat_id:
                results.append(DeliveryResult(target=raw, success=False,
                                               error="no resolvable chat_id"))
                continue
            payload, truncated, saved = self._maybe_truncate(content, adapter)
            try:
                res = await adapter.send(chat_id, payload)
                results.append(DeliveryResult(
                    target=raw,
                    success=bool(getattr(res, "success", False)),
                    message_id=getattr(res, "message_id", None),
                    error=getattr(res, "error", None) if not getattr(res, "success", False) else None,
                    truncated=truncated,
                    saved_path=saved,
                ))
            except Exception as e:
                logger.warning("[delivery] send to '%s' failed: %s", raw, e)
                results.append(DeliveryResult(target=raw, success=False, error=str(e)))
        return results
