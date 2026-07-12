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

"""Notification / webhook tool.

Sends alerts via webhooks (Slack / Discord) or desktop notifications so the
model can surface progress to the user.
"""


import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from encre.tools.base import build_tool


async def _notify_execute(**kwargs: Any) -> str:
    """Notify execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")

    if action == "webhook":
        url = kwargs.get("url", "")
        method = kwargs.get("method", "POST")
        headers = kwargs.get("headers", {})
        body = kwargs.get("body", "")
        content_type = kwargs.get("content_type", "application/json")

        if not url:
            return "Missing required field: url"

        headers = dict(headers) if isinstance(headers, dict) else {}
        if content_type and "Content-Type" not in headers:
            headers["Content-Type"] = content_type

        data = body.encode("utf-8") if body else None

        loop = asyncio.get_event_loop()

        def _send() -> str:
            """Send."""
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers=headers,
                    method=method,
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    response_body = resp.read().decode("utf-8", errors="replace")[:2000]
                    return f"Webhook sent. Status: {resp.status} {resp.reason}\nResponse: {response_body}"
            except urllib.error.HTTPError as e:
                return f"Webhook failed. Status: {e.code} {e.reason}\nBody: {e.read().decode('utf-8', errors='replace')[:1000]}"
            except Exception as e:
                return f"Webhook failed: {e}"

        return await loop.run_in_executor(None, _send)

    elif action == "slack":
        webhook_url = kwargs.get("webhook_url", "")
        message = kwargs.get("message", "")
        channel = kwargs.get("channel", "")
        username = kwargs.get("username", "Encre Bot")
        icon_emoji = kwargs.get("icon_emoji", "")

        if not webhook_url or not message:
            return "Missing required fields: webhook_url, message"

        payload: dict[str, Any] = {"text": message, "username": username}
        if channel:
            payload["channel"] = channel
        if icon_emoji:
            payload["icon_emoji"] = icon_emoji

        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        loop = asyncio.get_event_loop()

        def _send_slack() -> str:
            """Send slack."""
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=body.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        return "Slack notification sent successfully"
                    return f"Slack webhook returned status {resp.status}"
            except urllib.error.HTTPError as e:
                return f"Slack webhook failed: {e.code} {e.reason}"
            except Exception as e:
                return f"Slack webhook failed: {e}"

        return await loop.run_in_executor(None, _send_slack)

    elif action == "discord":
        webhook_url = kwargs.get("webhook_url", "")
        message = kwargs.get("message", "")
        username = kwargs.get("username", "Encre Bot")

        if not webhook_url or not message:
            return "Missing required fields: webhook_url, message"

        payload = {"content": message, "username": username}
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        loop = asyncio.get_event_loop()

        def _send_discord() -> str:
            """Send discord."""
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=body.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return f"Discord notification sent (status {resp.status})"
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")[:500]
                return f"Discord webhook failed: {e.code} {e.reason} - {body_text}"
            except Exception as e:
                return f"Discord webhook failed: {e}"

        return await loop.run_in_executor(None, _send_discord)

    elif action == "desktop":
        title = kwargs.get("title", "Encre Notification")
        message = kwargs.get("message", "")

        if not message:
            return "Missing required field: message"

        loop = asyncio.get_event_loop()

        def _notify() -> str:
            """Notify."""
            try:
                if os.name == "nt":
                    try:
                        from plyer import notification
                        notification.notify(title=title, message=message, timeout=5)
                        return f"Desktop notification sent: {title}"
                    except ImportError:
                        import ctypes
                        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)
                        return f"Desktop notification (MessageBox): {title}"
                elif os.uname().sysname == "Darwin":
                    subprocess_args = ["osascript", "-e",
                                       f'display notification "{message}" with title "{title}"']
                    import subprocess
                    subprocess.run(subprocess_args, capture_output=True, timeout=10)
                    return f"macOS notification sent: {title}"
                else:
                    try:
                        import subprocess
                        subprocess.run(
                            ["notify-send", title, message],
                            capture_output=True, timeout=10,
                        )
                        return f"Linux notification sent: {title}"
                    except FileNotFoundError:
                        return "notify-send not found. Install libnotify-bin."
            except Exception as e:
                return f"Desktop notification failed: {e}"

        return await loop.run_in_executor(None, _notify)

    return f"Unknown action: {action}. Supported: webhook, slack, discord, desktop"


EncreNotifyTool = build_tool(
    name="notify",
    description="Send notifications: webhook (HTTP POST), slack, discord, desktop (OS native toast).",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["webhook", "slack", "discord", "desktop"],
                "description": "Notification channel",
            },
            "url": {"type": "string", "description": "Webhook URL (for webhook action)"},
            "method": {"type": "string", "description": "HTTP method for webhook (default POST)"},
            "headers": {"type": "object", "description": "Custom HTTP headers for webhook"},
            "body": {"type": "string", "description": "Request body for webhook"},
            "content_type": {"type": "string", "description": "Content-Type header for webhook (default application/json)"},
            "webhook_url": {"type": "string", "description": "Slack or Discord webhook URL"},
            "message": {"type": "string", "description": "Notification message text"},
            "channel": {"type": "string", "description": "Slack channel override"},
            "username": {"type": "string", "description": "Bot username for Slack/Discord"},
            "icon_emoji": {"type": "string", "description": "Icon emoji for Slack (e.g. :robot_face:)"},
            "title": {"type": "string", "description": "Notification title (for desktop action)"},
        },
        "required": ["action", "message"],
    },
    execute=_notify_execute,
    intents=["general", "system"],
    category="communication",
    semantic_type="network",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_destructive=True,
)
