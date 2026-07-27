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

"""
Inspired by the Hermes Agent project (https://github.com/NousResearch/hermes-agent.git).
Thanks to Hermes Agent for the inspiration on this module.

QQ Bot inline keyboards and approval / update-prompt senders.

QQ Bot v2 supports attaching inline keyboards to outbound messages. When a
user clicks a button, the platform dispatches an INTERACTION_CREATE
gateway event containing the button's data payload. The bot must ACK the
interaction promptly via PUT /interactions/{id} or the user sees an
error indicator on the button.

This module provides:

- Keyboard dataclasses (InlineKeyboard, KeyboardButton, KeyboardRow, etc.)
  that serialize into the ``keyboard`` field of the outbound message body.
- Button builders (build_approval_keyboard, build_update_prompt_keyboard)
  that construct pre-defined keyboard layouts.
- Button-data parsers (parse_approval_button_data, parse_update_prompt_button_data)
  that decode the ``button_data`` payload from INTERACTION_CREATE events.
- ApprovalRequest dataclass + text renderer (build_approval_text)
  for rendering structured approval requests as markdown.
- ApprovalSender helper class that posts approval messages with keyboards.
- InteractionEvent dataclass + parser (parse_interaction_event)
  for decoding INTERACTION_CREATE dispatch payloads.

button_data formats::

    approve:<session_key>:<decision>      # decision = allow-once|allow-always|deny
    update_prompt:<answer>                # answer = y|n

Keyboard structure (QQ Bot v2)::

    InlineKeyboard
        └── content: KeyboardContent
            └── rows: List[KeyboardRow]
                └── buttons: List[KeyboardButton]
                    ├── id: str              — unique button identifier
                    ├── render_data: KeyboardButtonRenderData
                    │   ├── label: str       — pre-click display text
                    │   ├── visited_label: str — post-click display text
                    │   └── style: int       — 0=grey, 1=blue
                    └── action: KeyboardButtonAction
                        ├── type: int          — 1=callback, 2=link
                        ├── data: str          — button_data payload
                        ├── permission: KeyboardButtonPermission
                        └── click_limit: int  — max clicks per user (1=single-use)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── button_data prefixes + patterns ──────────────────────────────────

# Prefix used in button_data to identify approval decisions.
APPROVAL_BUTTON_PREFIX = "approve:"

# Prefix used in button_data to identify update-prompt answers.
UPDATE_PROMPT_PREFIX = "update_prompt:"

# Pattern: approve:<session_key>:<decision>
# session_key may itself contain colons (e.g. agent:main:qqbot:c2c:OPENID),
# so the session_key group is greedy but trails the decision.
# This regex captures exactly three groups: full_session_key and decision.
_APPROVAL_DATA_RE = re.compile(
    r"^approve:(.+):(allow-once|allow-always|deny)$"
)

# Pattern: update_prompt:y | update_prompt:n
# Simple two-option pattern — only accepts 'y' or 'n'.
_UPDATE_PROMPT_RE = re.compile(r"^update_prompt:(y|n)$")


# ── Keyboard dataclasses ─────────────────────────────────────────────

@dataclass
class KeyboardButtonPermission:
    """Button permission metadata.

    Controls who can click this button. QQ Bot v2 supports:
        type=0: Only the creator can click (default, rarely used)
        type=1: Specified users can click (requires user_ids list)
        type=2: All users can click (most common)

    Attributes:
        type: Permission type code. 2 = all users.
    """
    type: int = 2

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {"type": self.type}


@dataclass
class KeyboardButtonAction:
    """What happens when the button is clicked.

    Two action types supported by QQ Bot v2:
        type=1: Callback — triggers INTERACTION_CREATE event on click.
            The ``data`` field is delivered as ``button_data`` in the event.
        type=2: Link — opens a URL in the client.

    Attributes:
        type: Action type (1=Callback, 2=Link).
        data: Payload delivered in button_data when type=1. Ignored for type=2.
        permission: Who can click this button.
        click_limit: Max clicks per user (1 = single-use, button greys after click).
    """
    type: int
    data: str
    permission: KeyboardButtonPermission = field(
        default_factory=KeyboardButtonPermission
    )
    click_limit: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {
            "type": self.type,
            "data": self.data,
            "permission": self.permission.to_dict(),
            "click_limit": self.click_limit,
        }


@dataclass
class KeyboardButtonRenderData:
    """Visual rendering configuration for a button.

    Controls how the button appears before and after being clicked.

    Attributes:
        label: Text displayed before the button is clicked.
        visited_label: Text displayed after the button is clicked.
            The button stays greyed in place (not removed).
        style: Visual style. 0 = grey background, 1 = blue background.
    """
    label: str
    visited_label: str
    style: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {
            "label": self.label,
            "visited_label": self.visited_label,
            "style": self.style,
        }


@dataclass
class KeyboardButton:
    """One button in a keyboard row.

    A button has a unique ID, visual rendering config, and an action that
    defines what happens on click.

    Attributes:
        id: Unique identifier for this button within the keyboard.
        render_data: How the button looks (label, style, visited state).
        action: What happens when clicked (callback data, permissions).
        group_id: Buttons sharing the same group_id are mutually exclusive —
            clicking one greys out all other buttons in the group.
            Use "default" for independent buttons.
    """
    id: str
    render_data: KeyboardButtonRenderData
    action: KeyboardButtonAction
    group_id: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {
            "id": self.id,
            "render_data": self.render_data.to_dict(),
            "action": self.action.to_dict(),
            "group_id": self.group_id,
        }


@dataclass
class KeyboardRow:
    """A horizontal row of buttons in a keyboard.

    QQ Bot v2 keyboards are laid out as rows of buttons. Each row can
    contain up to 5 buttons.

    Attributes:
        buttons: List of buttons in this row, left to right.
    """
    buttons: List[KeyboardButton] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {"buttons": [b.to_dict() for b in self.buttons]}


@dataclass
class KeyboardContent:
    """Container for keyboard rows.

    A keyboard can have multiple rows, each rendered as a horizontal line
    of buttons.

    Attributes:
        rows: List of button rows, top to bottom.
    """
    rows: List[KeyboardRow] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {"rows": [r.to_dict() for r in self.rows]}


@dataclass
class InlineKeyboard:
    """Top-level keyboard payload — goes into ``MessageToCreate.keyboard``.

    This is the root dataclass that gets serialized and sent as the
    ``keyboard`` field in an outbound message body. The QQ Bot API
    expects exactly this structure.

    Attributes:
        content: Container for the keyboard's rows.
    """
    content: KeyboardContent = field(default_factory=KeyboardContent)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to QQ Bot API format."""
        return {"content": self.content.to_dict()}


# ── INTERACTION_CREATE parsing ───────────────────────────────────────

def parse_approval_button_data(button_data: str) -> Optional[tuple[str, str]]:
    """Parse approval ``button_data`` into ``(session_key, decision)``.

    Extracts the session key and user decision from the button_data string
    that arrives in an INTERACTION_CREATE event. The session key routes the
    decision back to the correct pending approval.

    Args:
        button_data: Raw ``data.resolved.button_data`` from
            ``INTERACTION_CREATE`` event payload.

    Returns:
        Tuple of ``(session_key, decision)`` where decision is one of
        ``"allow-once"``, ``"allow-always"``, or ``"deny"``.
        Returns ``None`` if the button_data doesn't match the approval pattern.

    Example::

        >>> parse_approval_button_data("approve:agent:main:qqbot:c2c:abc123:allow-once")
        ("agent:main:qqbot:c2c:abc123", "allow-once")
        >>> parse_approval_button_data("update_prompt:y")
        None
    """
    m = _APPROVAL_DATA_RE.match(button_data or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def parse_update_prompt_button_data(button_data: str) -> Optional[str]:
    """Parse update-prompt ``button_data`` into ``'y'`` or ``'n'``.

    Args:
        button_data: Raw ``data.resolved.button_data`` from
            ``INTERACTION_CREATE`` event payload.

    Returns:
        ``'y'`` for yes, ``'n'`` for no. Returns ``None`` if the
        button_data doesn't match the update_prompt pattern.

    Example::

        >>> parse_update_prompt_button_data("update_prompt:y")
        'y'
        >>> parse_update_prompt_button_data("approve:...")
        None
    """
    m = _UPDATE_PROMPT_RE.match(button_data or "")
    if not m:
        return None
    return m.group(1)


# ── Keyboard builders ────────────────────────────────────────────────

def _make_callback_button(
    btn_id: str,
    label: str,
    visited_label: str,
    data: str,
    style: int,
    group_id: str,
) -> KeyboardButton:
    """Create a callback-type button with the given configuration.

    Helper function to reduce boilerplate when building approval and
    update-prompt keyboards. Creates a button with type=1 (callback),
    single-use click limit, and default all-users permission.

    Args:
        btn_id: Unique button identifier.
        label: Pre-click display text.
        visited_label: Post-click display text.
        data: Payload delivered as button_data in INTERACTION_CREATE.
        style: Visual style (0=grey, 1=blue).
        group_id: Mutual exclusion group — buttons in the same group
            grey each other out on click.

    Returns:
        Configured KeyboardButton instance.
    """
    return KeyboardButton(
        id=btn_id,
        render_data=KeyboardButtonRenderData(
            label=label,
            visited_label=visited_label,
            style=style,
        ),
        action=KeyboardButtonAction(type=1, data=data),
        group_id=group_id,
    )


def build_approval_keyboard(session_key: str, *, allow_permanent: bool = True) -> InlineKeyboard:
    """Build the approval keyboard, hiding persistent scope when unavailable.

    Creates a 3-button keyboard layout for tool-approval flows:
        [✅ 允许一次] [⭐ 始终允许] [❌ 拒绝]

    All three buttons share ``group_id='approval'`` so clicking one
    greys out the rest (mutual exclusion within the row).

    The ``button_data`` embedded in each button encodes:
        - "allow-once": Allow this specific command execution only.
        - "allow-always": Whitelist this tool permanently.
        - "deny": Reject this command.

    Args:
        session_key: Unique key that routes the decision back to the
            correct pending approval in tools.approval. Must match the
            session_key of the original approval request.
        allow_permanent: If False, omit the "always allow" button.
            Used for smart-denied scenarios where permanent whitelist
            is not appropriate.

    Returns:
        InlineKeyboard with a single row of 2-3 buttons.

    button_data format::

        approve:<session_key>:allow-once
        approve:<session_key>:allow-always
        approve:<session_key>:deny
    """
    buttons = [
        # Primary action: allow once (blue, single-use).
        _make_callback_button(
            btn_id="allow", label="✅ 允许一次", visited_label="已允许",
            data=f"{APPROVAL_BUTTON_PREFIX}{session_key}:allow-once",
            style=1, group_id="approval",
        )
    ]
    if allow_permanent:
        # Secondary action: allow always (blue, single-use).
        buttons.append(_make_callback_button(
            btn_id="always", label="⭐ 始终允许", visited_label="已始终允许",
            data=f"{APPROVAL_BUTTON_PREFIX}{session_key}:allow-always",
            style=1, group_id="approval",
        ))
    # Tertiary action: deny (grey, single-use — visually distinct).
    buttons.append(_make_callback_button(
        btn_id="deny", label="❌ 拒绝", visited_label="已拒绝",
        data=f"{APPROVAL_BUTTON_PREFIX}{session_key}:deny",
        style=0, group_id="approval",
    ))
    return InlineKeyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=buttons)]))


def build_update_prompt_keyboard() -> InlineKeyboard:
    """Build a Yes/No keyboard for update confirmation prompts.

    Creates a 2-button keyboard layout:
        [✓ 确认] [✗ 取消]

    Both buttons share ``group_id='update_prompt'`` for mutual exclusion.

    Returns:
        InlineKeyboard with a single row of 2 buttons.

    button_data format::

        update_prompt:y   (for confirm)
        update_prompt:n   (for cancel)
    """
    return InlineKeyboard(
        content=KeyboardContent(
            rows=[
                KeyboardRow(buttons=[
                    # Confirm button (blue).
                    _make_callback_button(
                        btn_id="yes",
                        label="✓ 确认",
                        visited_label="已确认",
                        data=f"{UPDATE_PROMPT_PREFIX}y",
                        style=1,
                        group_id="update_prompt",
                    ),
                    # Cancel button (grey).
                    _make_callback_button(
                        btn_id="no",
                        label="✗ 取消",
                        visited_label="已取消",
                        data=f"{UPDATE_PROMPT_PREFIX}n",
                        style=0,
                        group_id="update_prompt",
                    ),
                ]),
            ]
        )
    )


# ── ApprovalRequest + text builder ───────────────────────────────────

@dataclass
class ApprovalRequest:
    """Structured approval-request display data.

    Holds all information needed to render an approval message and keyboard.
    Used by both ``build_approval_text`` (text rendering) and
    ``build_approval_keyboard`` (keyboard construction).

    Two usage modes:
        - **Exec approval**: Has ``command_preview`` and/or ``cwd`` set.
          Renders as a terminal-style approval with command preview.
        - **Plugin approval**: Has ``tool_name`` set.
          Renders as a plugin-style approval with severity indicator.

    Attributes:
        session_key: Unique key that routes the decision back to the
            waiting caller in the approval resolver.
        title: Short title displayed at the top of the message.
        description: Optional longer description providing context.
        command_preview: Command text to execute (exec approvals).
        cwd: Working directory for command execution.
        tool_name: Name of the tool requesting approval (plugin approvals).
        severity: Visual severity indicator ('critical'=red, 'info'=blue, ''=yellow).
        timeout_sec: Seconds until the approval expires and auto-denoys.
        allow_permanent: Whether to show the "allow always" button.
    """
    session_key: str
    title: str
    description: str = ""
    command_preview: str = ""
    cwd: str = ""
    tool_name: str = ""
    severity: str = ""
    timeout_sec: int = 120
    allow_permanent: bool = True


def build_approval_text(req: ApprovalRequest) -> str:
    """Render an :class:`ApprovalRequest` into the message body (markdown).

    Dispatches to either exec-text or plugin-text renderer based on which
    fields are populated.

    Args:
        req: Structured approval request data.

    Returns:
        Markdown-formatted string to include in the outbound message.
    """
    # Exec approval: has command preview or working directory.
    if req.command_preview or req.cwd:
        return _build_exec_text(req)
    # Plugin approval: tool name or severity-based rendering.
    return _build_plugin_text(req)


def _build_exec_text(req: ApprovalRequest) -> str:
    """Render an exec-style approval request with command preview.

    Format:
        🔐 **命令执行审批**

        ```
        <command_preview>
        ```
        📁 目录: <cwd>
        📋 <title>
        📝 <description>

        ⏱️ 超时: <timeout_sec> 秒
    """
    lines: List[str] = ["🔐 **命令执行审批**", ""]
    if req.command_preview:
        # Truncate command preview to prevent excessively long messages.
        preview = req.command_preview[:300]
        lines.append(f"```\n{preview}\n```")
    if req.cwd:
        lines.append(f"📁 目录: {req.cwd}")
    if req.title and req.title != req.command_preview:
        lines.append(f"📋 {req.title}")
    if req.description:
        lines.append(f"📝 {req.description}")
    lines.append("")
    lines.append(f"⏱️ 超时: {req.timeout_sec} 秒")
    return "\n".join(lines)


def _build_plugin_text(req: ApprovalRequest) -> str:
    """Render a plugin-style approval request with severity indicator.

    Format:
        <icon> **审批请求**

        📋 <title>
        📝 <description>
        🔧 工具: <tool_name>

        ⏱️ 超时: <timeout_sec> 秒

    Icon mapping:
        severity='critical' → 🔴 red
        severity='info'     → 🔵 blue
        otherwise           → 🟡 yellow
    """
    # Select icon color based on severity level.
    icon = (
        "🔴" if req.severity == "critical"
        else "🔵" if req.severity == "info"
        else "🟡"
    )
    lines: List[str] = [f"{icon} **审批请求**", ""]
    lines.append(f"📋 {req.title}")
    if req.description:
        lines.append(f"📝 {req.description}")
    if req.tool_name:
        lines.append(f"🔧 工具: {req.tool_name}")
    lines.append("")
    lines.append(f"⏱️ 超时: {req.timeout_sec} 秒")
    return "\n".join(lines)


# ── ApprovalSender ───────────────────────────────────────────────────

PostMessageFn = Callable[..., Awaitable[Dict[str, Any]]]
"""Signature of an async POST to ``/v2/{users|groups}/{id}/messages``.

Implementations accept a body dict and return the raw API response.
Used to decouple ApprovalSender from the adapter for testability.
"""


class ApprovalSender:
    """Send an approval-request message with an inline keyboard.

    Decoupled from the adapter via callables so it can be unit-tested in
    isolation. Pass the adapter's ``_send_message_with_keyboard`` helper
    (or any equivalent) as ``post_message``.

    Usage::

        sender = ApprovalSender(post_c2c, post_group, log_tag="QQBot")
        success = await sender.send("c2c", openid, approval_req, msg_id)

    Attributes:
        _post_c2c: Coroutine for posting to C2C chats.
        _post_group: Coroutine for posting to group chats.
        _log_tag: Log prefix for all log messages.
    """

    def __init__(
        self,
        post_c2c: PostMessageFn,
        post_group: PostMessageFn,
        log_tag: str = "QQBot",
    ) -> None:
        """Initialize with C2C and group posting callables.

        Args:
            post_c2c: Async callable to post a message to a C2C chat.
                Signature: (chat_id, text, reply_to_msg_id, keyboard) -> response.
            post_group: Async callable to post a message to a group chat.
                Same signature as post_c2c.
            log_tag: Log prefix for debug/info/error messages.
        """
        self._post_c2c = post_c2c
        self._post_group = post_group
        self._log_tag = log_tag

    async def send(
        self,
        chat_type: str,
        chat_id: str,
        req: ApprovalRequest,
        msg_id: Optional[str] = None,
    ) -> bool:
        """Send an approval message to *chat_id*.

        Builds the approval text and keyboard, then posts to the appropriate
        chat endpoint (C2C or group) based on chat_type.

        Args:
            chat_type: ``'c2c'`` for private chat or ``'group'`` for group chat.
            chat_id: User openid (c2c) or group_openid (group).
            req: Structured approval request with title, description, etc.
            msg_id: Reply-to message id (required for passive/c2c messages
                where the bot hasn't initiated the conversation).

        Returns:
            ``True`` if the message was sent successfully, ``False`` on failure
            or unsupported chat_type.
        """
        # Build the approval text and keyboard from the request.
        text = build_approval_text(req)
        keyboard = build_approval_keyboard(req.session_key)

        logger.info(
            "[%s] Sending approval request to %s:%s (session=%.20s…)",
            self._log_tag, chat_type, chat_id, req.session_key,
        )

        try:
            # Route to the correct posting function based on chat type.
            if chat_type == "c2c":
                await self._post_c2c(chat_id, text, msg_id, keyboard)
            elif chat_type == "group":
                await self._post_group(chat_id, text, msg_id, keyboard)
            else:
                # Guild channels don't support inline keyboards.
                logger.warning(
                    "[%s] Approval: unsupported chat_type %r",
                    self._log_tag, chat_type,
                )
                return False
            logger.info(
                "[%s] Approval message sent to %s:%s",
                self._log_tag, chat_type, chat_id,
            )
            return True
        except Exception as exc:
            logger.error(
                "[%s] Failed to send approval message to %s:%s: %s",
                self._log_tag, chat_type, chat_id, exc,
            )
            return False


# ── INTERACTION_CREATE event shape ───────────────────────────────────

@dataclass
class InteractionEvent:
    """Parsed ``INTERACTION_CREATE`` event payload.

    Contains all fields extracted from an INTERACTION_CREATE gateway event.
    The adapter's ``_on_interaction`` method parses the raw payload into
    this dataclass, then calls the registered interaction callback.

    Reference: https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html

    Attributes:
        id: Interaction event id — required for the ``PUT /interactions/{id}`` ACK.
        type: Event type code (``11`` = message button interaction).
        chat_type: Numeric chat type (``0`` = guild, ``1`` = group, ``2`` = c2c).
        scene: Human-readable chat type ('guild', 'group', 'c2c').
        group_openid: Group identifier (for group interactions).
        group_member_openid: Member who clicked the button (for group interactions).
        user_openid: User identifier (for c2c interactions).
        channel_id: Channel identifier (for guild interactions).
        guild_id: Guild/server identifier (for guild interactions).
        button_data: Parsed button payload (e.g. "approve:session:allow-once").
        button_id: The clicked button's ID.
        resolver_user_id: User who resolved the interaction (fallback field).
    """
    id: str = ""
    """Interaction event id — required for the ``PUT /interactions/{id}`` ACK."""

    type: int = 0
    """Event type code (``11`` = message button)."""

    chat_type: int = 0
    """``0`` = guild, ``1`` = group, ``2`` = c2c."""

    scene: str = ""
    """``'guild'`` | ``'group'`` | ``'c2c'`` — human-readable scene."""

    group_openid: str = ""
    group_member_openid: str = ""
    user_openid: str = ""
    channel_id: str = ""
    guild_id: str = ""

    button_data: str = ""
    button_id: str = ""
    resolver_user_id: str = ""

    @property
    def operator_openid(self) -> str:
        """Best available operator openid (group → member; c2c → user).

        Priority order:
            1. group_member_openid (group button click)
            2. user_openid (c2c button click)
            3. resolver_user_id (fallback from resolved.user_id)

        Returns:
            The openid of the user who clicked the button, or empty string
            if none of the fields are populated.
        """
        return (
            self.group_member_openid
            or self.user_openid
            or self.resolver_user_id
        )


def parse_interaction_event(raw: Dict[str, Any]) -> InteractionEvent:
    """Parse a raw ``INTERACTION_CREATE`` dispatch payload (``d``).

    Extracts and normalizes fields from the nested QQ Bot API event structure
    into a flat InteractionEvent dataclass. Handles missing fields gracefully
    by defaulting to empty strings or zeros.

    The raw payload structure::

        {
            "id": "...",
            "chat_type": 2,           # 0=guild, 1=group, 2=c2c
            "group_openid": "...",
            "group_member_openid": "...",
            "user_openid": "...",
            "channel_id": "...",
            "guild_id": "...",
            "data": {
                "type": 11,
                "resolved": {
                    "button_data": "approve:session:allow-once",
                    "button_id": "allow",
                    "user_id": "..."
                }
            }
        }

    Args:
        raw: The ``d`` field from an INTERACTION_CREATE dispatch payload.

    Returns:
        Parsed InteractionEvent with all fields normalized.
    """
    data_raw = raw.get("data") or {}
    resolved = data_raw.get("resolved") or {}
    scene_code = int(raw.get("chat_type", 0) or 0)
    # Map numeric scene code to human-readable string.
    scene = {0: "guild", 1: "group", 2: "c2c"}.get(scene_code, "")
    return InteractionEvent(
        id=str(raw.get("id", "")),
        type=int(data_raw.get("type", 0) or 0),
        chat_type=scene_code,
        scene=scene,
        group_openid=str(raw.get("group_openid", "")),
        group_member_openid=str(raw.get("group_member_openid", "")),
        user_openid=str(raw.get("user_openid", "")),
        channel_id=str(raw.get("channel_id", "")),
        guild_id=str(raw.get("guild_id", "")),
        button_data=str(resolved.get("button_data", "")),
        button_id=str(resolved.get("button_id", "")),
        resolver_user_id=str(resolved.get("user_id", "")),
    )
