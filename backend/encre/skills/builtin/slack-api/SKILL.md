---
name: slack-api
description: Slack API integration with managed OAuth. Send messages, manage channels, search conversations, and interact with Slack workspaces.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Slack Api
# Slack

Access the Slack API with managed OAuth authentication. Send messages, manage channels, list users, and automate Slack workflows.

## Quick Start

**CLI:**

```bash
maton slack message send --channel C0123456789 --text 'Hello from Maton!'
```

```bash
maton api '/slack/api/chat.postMessage'
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
data = json.dumps({'channel': 'C0123456789', 'text': 'Hello from Maton!'}).encode()
req = urllib.request.Request('https://api.maton.ai/slack/api/chat.postMessage', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Base URL

```
https://api.maton.ai/slack/{method}
```

Maton proxies requests to `slack.com` and automatically injects your OAuth token.

## Installation

**NPM:**
```bash
npm install -g @maton/cli
```

**Homebrew:**
```bash
`bash brew install` maton-ai/cli/maton
```

## Authentication

**CLI:**

```bash
maton login                          # Opens browser for API key
maton login --interactive            # Skip browser, paste API key directly
maton whoami                         # Show current auth state
```

**Manual:**

1. Sign in or create an account at [maton.ai](https://maton.ai)
2. Go to [maton.ai/settings](https://maton.ai/settings)
3. Copy your API key
4. Set your API key as `MATON_API_KEY`:

```bash
export MATON_API_KEY="YOUR_API_KEY"
```

## Connection Management

Manage your Slack OAuth connections at `https://api.maton.ai`.

### List Connections

**CLI:**

```bash
maton connection list slack --status ACTIVE
```

```bash
maton api -X GET /connections -f app=slack -f status=ACTIVE
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://api.maton.ai/connections?app=slack&status=ACTIVE')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Create Connection

**CLI:**

```bash
maton connection create slack
```

```bash
maton api /connections -f app=slack
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
data = json.dumps({'app': 'slack'}).encode()
req = urllib.request.Request('https://api.maton.ai/connections', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Get Connection

**CLI:**

```bash
maton connection view {connection_id}
```

```bash
maton api /connections/{connection_id}
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://api.maton.ai/connections/{connection_id}')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

**Response:**
```json
{
  "connection": {
    "connection_id": "{connection_id}",
    "status": "ACTIVE",
    "creation_time": "2025-12-08T07:20:53.488460Z",
    "last_updated_time": "2026-01-31T20:03:32.593153Z",
    "url": "https://connect.maton.ai/?session_token=...",
    "app": "slack",
    "metadata": {}
  }
}
```

Open the returned `url` in a browser to complete OAuth authorization.

### Delete Connection

**CLI:**

```bash
maton connection delete {connection_id}
```

```bash
maton api -X DELETE /connections/{connection_id}
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://api.maton.ai/connections/{connection_id}', method='DELETE')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Specifying Connection

If you have multiple Slack connections, specify which one to use:

**CLI:**

```bash
maton slack message send --channel C0123456789 --text 'Hello!' --connection {connection_id}
```

```bash
maton api /slack/api/chat.postMessage --connection {connection_id}
```

**Python:**

```bash
python <<'EOF'
import urllib.request, os, json
data = json.dumps({'channel': 'C0123456789', 'text': 'Hello!'}).encode()
req = urllib.request.Request('https://api.maton.ai/slack/api/chat.postMessage', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Maton-Connection', '{connection_id}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

If you have multiple connections, always specify the connection to ensure requests go to the intended account.

## Security & Permissions

- Access is scoped to messages, channels, users, files, and reactions within the connected Slack account.
- **All write operations require explicit user approval.** Before executing any create, update, or delete call, confirm the target resource and intended effect with the user.

## API Reference

### Authentication

#### Auth Test

```bash
GET /slack/api/auth.test
```

Returns current user and team info.

Example:

```bash
maton slack whoami
```

---

### Messages

#### Post Message

```bash
POST /slack/api/chat.postMessage
Content-Type: application/json

{
  "channel": "C0123456789",
  "text": "Hello, world!"
}
```

Example:

```bash
maton slack message send --channel C0123456789 --text 'Hello, world!'
```

With blocks:

```bash
POST /slack/api/chat.postMessage
Content-Type: application/json

{
  "channel": "C0123456789",
  "blocks": [
    {"type": "section", "text": {"type": "mrkdwn", "text": "*Bold* and _italic_"}}
  ]
}
```

Example:

```bash
maton slack message send --channel C0123456789 --blocks '[{"type":"section","text":{"type":"mrkdwn","text":"*Bold* and _italic_"}}]'
```

#### Post /me-style Message

```bash
maton slack message me --channel C0123456789 --text 'is deploying'
```

#### Post Thread Reply

```bash
POST /slack/api/chat.postMessage
Content-Type: application/json

{
  "channel": "C0123456789",
  "thread_ts": "1234567890.123456",
  "text": "This is a reply in a thread"
}
```

Example:

```bash
maton slack message reply --channel C0123456789 --thread-ts 1234567890.123456 --text 'This is a reply in a thread'
```

#### Update Message

```bash
POST /slack/api/chat.update
Content-Type: application/json

{
  "channel": "C0123456789",
  "ts": "1234567890.123456",
  "text": "Updated message"
}
```

Example:

```bash
maton slack message update --channel C0123456789 --ts 1234567890.123456 --text 'Updated message'
```

#### Delete Message

```bash
POST /slack/api/chat.delete
Content-Type: application/json

{
  "channel": "C0123456789",
  "ts": "1234567890.123456"
}
```

Example:

```bash
maton slack message delete --channel C0123456789 --ts 1234567890.123456
```

#### Schedule Message

```bash
POST /slack/api/chat.scheduleMessage
Content-Type: application/json

{
  "channel": "C0123456789",
  "text": "Scheduled message",
  "post_at": 1734567890
}
```

Example:

```bash
maton slack schedule create --channel C0123456789 --text 'Scheduled message' --post-at 1734567890
```

#### List Scheduled Messages

```bash
GET /slack/api/chat.scheduledMessages.list
```

Example:

```bash
maton slack schedule list
```

#### Delete Scheduled Message

```bash
POST /slack/api/chat.deleteScheduledMessage
Content-Type: application/json

{
  "channel": "C0123456789",
  "scheduled_message_id": "Q1234567890"
}
```

Example:

```bash
maton slack schedule delete --channel C0123456789 --id Q1234567890
```

#### Get Permalink

```bash
GET /slack/api/chat.getPermalink?channel=C0123456789&message_ts=1234567890.123456
```

Example:

```bash
maton slack message permalink --channel C0123456789 --message-ts 1234567890.123456
```

---

### Conversations (Channels)

#### List Channels

```bash
GET /slack/api/conversations.list?

> *This skill was truncated from its original 22174 chars. For the full version, use `web_search`/`web_fetch` to find the latest documentation.*
