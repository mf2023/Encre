---
name: email-daily-summary
description: Automatically logs into email accounts (Gmail, Outlook, QQ Mail, etc.) and generates daily email summaries.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Email Daily Summary
# Email Daily Summary Skill

This skill helps you automatically log into your email, retrieve email content, and generate daily email summaries.

## Features

- 🔐 Supports multiple email logins (Gmail, Outlook, QQ Mail, 163 Mail, etc.)
- 📧 Automatically retrieves latest email list
- 📝 Smart email summary generation
- 🏷️ Categorized by importance/sender/subject
- 📊 Generates daily email statistics report

## Prerequisites

1. Install browser-use CLI:
```bash
uv pip install browser-use[cli]
browser-use install
```

2. Ensure you have logged into your email in the browser (using real mode reuses the login session directly)

## Usage

### Method 1: Using a Logged-In Browser (Recommended)

Using `--browser real` mode reuses your Chrome browser's logged-in email session:

```bash
# Gmail
browser-use --browser real open https://mail.google.com

# Outlook
browser-use --browser real open https://outlook.live.com

# QQ 邮箱
browser-use --browser real open https://mail.qq.com

# 163 邮箱
browser-use --browser real open https://mail.163.com
```

### Method 2: Manual Login Process

If manual login is needed, use `--headed` mode to view the operation process:

```bash
# 打开邮箱登录页面（以 Gmail 为例）
browser-use --headed open https://accounts.google.com

# 查看页面元素
browser-use state

# 输入邮箱地址（根据 state 返回的索引）
browser-use input <email_input_index> "your-email@gmail.com"
browser-use click <next_button_index>

# 输入密码
browser-use input <password_input_index> "your-password"
browser-use click <login_button_index>

# 跳转到邮箱
browser-use open https://mail.google.com
```

## Get Email List

After successful login, retrieve the email list:

```bash
# 获取当前页面状态，查看邮件列表
browser-use state

# 截图保存当前邮件列表
browser-use screenshot emails_$(date +%Y%m%d).png

# 使用 JavaScript 提取邮件信息（Gmail 示例）
browser-use eval "
  const emails = [];
  document.querySelectorAll('tr.zA').forEach((row, i) => {
    if (i < 20) {
      const sender = row.querySelector('.yX.xY span')?.innerText || '';
      const subject = row.querySelector('.y6 span')?.innerText || '';
      const snippet = row.querySelector('.y2')?.innerText || '';
      const time = row.querySelector('.xW.xY span')?.innerText || '';
      emails.push({ sender, subject, snippet, time });
    }
  });
  JSON.stringify(emails, null, 2);
"
```

## Generate Email Summary with Python

```bash
# 初始化邮件数据收集
browser-use python "
emails_data = []
summary_date = '$(date +%Y-%m-%d)'
"

# 滚动页面加载更多邮件
browser-use python "
for i in range(3):
    browser.scroll('down')
    import time
    time.sleep(1)
"

# 提取邮件数据（需要根据实际邮箱 DOM 结构调整）
browser-use python "
import json

# 获取页面 HTML 进行解析
html = browser.html

# 这里需要根据具体邮箱服务解析 HTML
# 示例：统计基本信息
print(f'=== 邮件日报 {summary_date} ===')
print(f'页面 URL: {browser.url}')
print(f'页面标题: {browser.title}')
"

# 截图保存
browser-use python "
browser.screenshot(f'email_summary_{summary_date}.png')
print(f'截图已保存: email_summary_{summary_date}.png')
"
```

## Complete Daily Email Summary Script

Create a complete summary flow:

```bash
#!/bin/bash
# email_daily_summary.sh

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M:%S)
OUTPUT_DIR="./email_summaries"
mkdir -p "$OUTPUT_DIR"

echo "=========================================="
echo "📧 邮件日报生成中..."
echo "日期: $DATE $TIME"
echo "=========================================="

# 1. 打开邮箱（使用已登录的浏览器）
browser-use --browser real open https://mail.google.com

# 2. 等待页面加载
sleep 3

# 3. 获取页面状态
echo ""
echo "📋 当前邮箱状态:"
browser-use state

# 4. 截图保存邮件列表
echo ""
echo "📸 保存截图..."
browser-use screenshot "$OUTPUT_DIR/inbox_$DATE.png"

# 5. 提取邮件数据
echo ""
echo "📊 邮件统计:"
browser-use eval "
(() => {
  const unreadCount = document.querySelectorAll('.zE').length;
  const totalVisible = document.querySelectorAll('tr.zA').length;
  return JSON.stringify({
    unread: unreadCount,
    visible: totalVisible,
    timestamp: new Date().toISOString()
  });
})()
"

# 6. 关闭浏览器
echo ""
echo "✅ 完成！截图保存至: $OUTPUT_DIR/inbox_$DATE.png"
browser-use close
```

## Supported Email Services

| Email Service | Login URL | Inbox URL |
|---------|---------|-----------|
| Gmail | https://accounts.google.com | https://mail.google.com |
| Outlook | https://login.live.com | https://outlook.live.com |
| QQ Mail | https://mail.qq.com | https://mail.qq.com |
| 163 Mail | https://mail.163.com | https://mail.163.com |
| 126 Mail | https://mail.126.com | https://mail.126.com |
| WeCom Mail | https://exmail.qq.com | https://exmail.qq.com |

## Generate AI Email Summary

If an API Key is configured, you can use AI to automatically generate email summaries:

```bash
# 使用 AI 提取邮件摘要（需要 BROWSER_USE_API_KEY）
browser-use --browser real open https://mail.google.com
browser-use extract "提取前 10 封邮件的发件人、主题和摘要，按重要性排序"
```

## Scheduled Tasks

### macOS/Linux (crontab)

```bash
# 编辑 crontab
crontab -e

# 添加每日早上 9 点执行的任务
0 9 * * * /path/to/email_daily_summary.sh >> /path/to/logs/email_summary.log 2>&1
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.email.dailysummary.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.email.dailysummary</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/email_daily_summary.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/email_summary.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/email_summary_error.log</string>
</dict>
</plist>
```

Load the task:
```bash
launchctl load ~/Library/LaunchAgents/com.email.dailysummary.plist
```

## Output Example

Generated email summary report format:

```
==========================================
📧 邮件日报 - 2026-01-30
==========================================

📊 统计概览:
- 未读邮件: 12 封
- 今日新邮件: 28 封
- 重要邮件: 5 封

🔴 重要邮件:
1. [工作] 来自 boss@company.com
   主题: 项目进度汇报 - 紧急
   时间: 09:30

2. [财务] 来自 finance@bank.com
   主题: 账单提醒
   时间: 08:15

📬 今日邮件分类:
- 工作相关: 15 封
- 订阅通知: 8 封
- 社交媒体: 3 封
- 其他: 2 封

💡 建议操作:
- 回复 boss@company.com 的邮件
- 处理 3 封需要审批的邮件

==========================================
```

## Safety Tips

⚠️ **Important Safety Recommendations**:

1. **Do not store passwords in plain text in scripts**, prioritize using `--browser real` mode to reuse logged-in sessions
2. **Store sensitive information using environment variables**
3. **Periodically review authorized applications**, remove unnecessary third-party access
4. **Enable two-factor authentication** to protect email security
5. **Log files should not contain sensitive information**

## Troubleshooting

**Login failed?**
```bash
# 使用 headed 模式查看登录过程
browser-use --browser real --headed open https://mail.google.com
```

**Page elements not found?**
```bash
# 等待页面完全加载
sleep 5
browser-use state
```

**Session expired?**
```bash
# 关闭所有会话重新开始
browser-use close --all
browser-use --browser real open https://mail.google.com
```

## Cleanup

Remember to close the browser when finished:

```bash
browser-use close
```
