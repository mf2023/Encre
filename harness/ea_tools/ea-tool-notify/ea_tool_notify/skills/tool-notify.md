---
name: tool-notify
description: "Send a notification to the user or an external channel via webhook, Slack, Discord, or a native desktop toast."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# notify

Send a notification to the user or an external channel via webhook, Slack, Discord, or a native desktop toast.

WHEN to use: surface progress on long-running work to the user, alert a monitoring channel when a job finishes or fails, or ping a chat webhook as part of an automation.
WHEN NOT to use: to ask the user a question that needs an answer use the question tool; for in-conversation status updates just reply in the chat.
TIPS: for Slack/Discord pass the incoming-webhook URL in webhook_url; keep messages concise (chat clients truncate long text); desktop toasts work cross-platform but require OS support.
PITFALLS: webhooks that need auth must include credentials in the headers or URL; desktop notifications on Linux need libnotify-bin installed.
