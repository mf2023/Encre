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
Adapter package -- exports all platform adapter classes for convenient importing.

Public API:
    - BaseAdapter: Abstract base class for all adapters
    - AdapterManager: Central lifecycle manager for all adapters
    - 18 platform-specific adapter classes (see __all__ below)

Usage:
    from encre.adapters import FeishuAdapter, AdapterManager  # noqa: E402
    manager = AdapterManager()
    adapter = FeishuAdapter(app_id="...", app_secret="...")
    await manager.start_adapter("feishu", config)
"""

from encre.adapters.base import BaseAdapter
from encre.adapters.bluebubbles import BlueBubblesAdapter
from encre.adapters.dingtalk import DingTalkAdapter
from encre.adapters.discord import DiscordAdapter
from encre.adapters.email import EmailAdapter
from encre.adapters.feishu import FeishuAdapter
from encre.adapters.homeassistant import HomeAssistantAdapter
from encre.adapters.manager import AdapterManager
from encre.adapters.matrix import MatrixAdapter
from encre.adapters.msgraph import MSGraphAdapter
from encre.adapters.qqbot import QQBotAdapter
from encre.adapters.signal import SignalAdapter
from encre.adapters.slack import SlackAdapter
from encre.adapters.sms import SmsAdapter
from encre.adapters.telegram import TelegramAdapter
from encre.adapters.webhook import WebhookAdapter
from encre.adapters.wecom import WeComAdapter
from encre.adapters.weixin import WeixinAdapter
from encre.adapters.whatsapp import WhatsAppAdapter
from encre.adapters.yuanbao import YuanbaoAdapter

__all__ = [
    "BaseAdapter",
    "BlueBubblesAdapter",
    "DingTalkAdapter",
    "DiscordAdapter",
    "EmailAdapter",
    "FeishuAdapter",
    "HomeAssistantAdapter",
    "MSGraphAdapter",
    "MatrixAdapter",
    "QQBotAdapter",
    "SignalAdapter",
    "SlackAdapter",
    "SmsAdapter",
    "TelegramAdapter",
    "WeComAdapter",
    "WebhookAdapter",
    "WeixinAdapter",
    "WhatsAppAdapter",
    "YuanbaoAdapter",
]
