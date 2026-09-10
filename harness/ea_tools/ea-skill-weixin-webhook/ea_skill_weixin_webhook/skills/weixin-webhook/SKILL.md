---
name: weixin-webhook
description: WeCom webhook message push service
metadata:
  source: clawhub
  tags: weixin-webhook
user_invocable: true
hidden: true
context: inline
---

## Weixin Webhook
# weixin-webhook

Enterprise WeChat Webhook message sending tool, one-line command to complete notification push.

## Prerequisites: Get Webhook URL

**Before using, you need to get the Enterprise WeChat Webhook address.**

### Steps

1. Open Enterprise WeChat, enter the group chat that needs to receive messages  
2. Click the top-right "three dots" → Select "Message Push" → Add message push  
3. Copy the generated Webhook URL, format as follows:  
   `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx-xxxxx`

### Notes

- Do not share the Webhook URL with others  
- If accidentally leaked, delete the push and recreate it

---

## Quick Start

```bash
# Send text message
~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh "webhook_key" "text" "message content"

# Send Markdown message
~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh "webhook_key" "markdown" "**Important** <font color=\"warning\">Reminder</font>"

# @ specific users
~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh "key" "text" "Meeting reminder" "zhangsan,lisi" "13800001111"
```

### Parameter Description

| Position | Description |
|----------|-------------|
| 1 | webhook_key (value of key parameter in URL) |
| 2 | msgtype (text / markdown) |
| 3 | Message content |
| 4 | @ user's userid list (comma separated, optional) |
| 5 | @ user's phone number list (comma separated, optional) |

---

## Set Up Scheduled Tasks

```bash
# Send reminder daily at 14:00
Encre cron add \
  --cron "0 14 * * *" \
  --agent main \
  --message "Execute: ~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh 'your_key' 'text' '【Health Reminder】Please do Kegel exercises!' 'liujie'" \
  --name "daily_kegel" \
  --description "Daily Kegel reminder" \
  --no-deliver

# Team notification daily at 9:00
Encre cron add \
  --cron "0 9 * * *" \
  --agent main \
  --message "Execute: ~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh 'your_key' 'text' 'Morning meeting starting soon, please attend on time' '@all'" \
  --name "morning_meeting" \
  --description "Morning meeting notification" \
  --no-deliver

# Daily report reminder (Markdown format)
Encre cron add \
  --cron "0 17 * * *" \
  --agent main \
  --message "Execute: ~/.Encre/workspace/skills/weixin-webhook/send_weixin.sh 'your_key' 'markdown' '【Daily Report Reminder】Please submit daily report before 18:00.<font color=\"info\">1. Today's Achievements</font><font color=\"info\">2. Issues Encountered</font><font color=\"info\">3. Tomorrow's Plan</font>'" \
  --name "daily_report" \
  --description "Daily report reminder" \
  --no-deliver
```

## Manage Scheduled Tasks

```bash
Encre cron list                    # View all tasks
Encre cron run daily_kegel         # Manual test execution
Encre cron disable daily_kegel     # Disable task
Encre cron enable daily_kegel      # Enable task
Encre cron rm daily_kegel          # Delete task
```

---

## Message Format Examples

### Text Message

```json
{
  "msgtype": "text",
  "text": {
    "content": "Meeting reminder",
    "mentioned_list": ["zhangsan", "@all"],
    "mentioned_mobile_list": ["13800001111", "@all"]
  }
}
```

### Markdown Message

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "Real-time new <font color=\"warning\">132 cases</font>\n>Regular users:<font color=\"comment\">117 cases</font>\n>VIP users:<font color=\"comment\">15 cases</font>"
  }
}
```

---

## File Structure

```
weixin-webhook/
├── SKILL.md       # Usage guide
└── send_weixin.sh # Send script
```

## Dependencies

- `rest_client` (usually built-in with system)
