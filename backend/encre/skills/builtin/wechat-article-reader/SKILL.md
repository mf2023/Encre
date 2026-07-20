---
name: wechat-article-reader
description: Export WeChat public account articles to Markdown format. Triggered when user provides a WeChat public account link (mp.weixin.qq.com) or requests to download/export/save WeChat articles. Default save to workspace source directory.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Wechat Article Reader
# WeChat Public Account Article Export Skill (WeChat-Article-Reader)

## Trigger Conditions

Trigger this skill when the following conditions are met:

- User provides a WeChat public account article link (mp.weixin.qq.com)
- User requests to "download", "export" or "save" WeChat articles
- User requests to convert WeChat articles to Markdown
- User mentions "public account articles", "WeChat articles", "download WeChat", "export public account"

**Trigger Examples:**
- "Download this article https://mp.weixin.qq.com/s/xxx"
- "Export this public account article to markdown"
- "Save WeChat article to local"
- "Help me save this WeChat article"

## How It Works

This skill uses Python scripts to perform the following operations:
1. Get WeChat article HTML page
2. Extract metadata from Open Graph meta tags (title, author, publish time)
3. Extract content from `#js_content` div
4. Convert HTML to Markdown using markdownify
5. Save as Markdown file with YAML Front Matter

## Script Directory

**Base Directory**: `~/.npm-global/lib/node_modules/Encre/skills/WeChat-article-reader`

**Script Location**: the tool

## Installation Setup

### First-time Installation

1. **Check Python Dependencies**:
```bash
python3 -c "import requests, bs4, markdownify" 2>/dev/null || echo "需要安装依赖"
```

2. **To Install Dependencies**:
```bash
pip3 install requests beautifulsoup4 lxml markdownify
```

### No Configuration Needed

This skill works out of the box, no API Key or additional configuration needed. Uses HTTP requests with browser headers to fetch WeChat articles.

## Execution Steps

When this skill is triggered, follow these steps:

### Step 1: Extract URL

Identify the WeChat article URL from the user's request. Valid URLs start with:
- `https://mp.weixin.qq.com/s/`
- `https://mp.weixin.qq.com/...`

### Step 2: Determine Output Directory

**Default output directory**: `~/.Encre/workspace-qiming/source`

Users can specify a custom output directory.

### Step 3: Run Export Script

```bash
# 如需要则创建输出目录
mkdir -p "$OUTPUT_DIR"

# 运行导出脚本
python3 ~/.npm-global/lib/node_modules/Encre/skills/WeChat-article-reader/scripts/export.py "$URL" "$OUTPUT_DIR"
```

### Step 4: Report Results

Inform the user:
- Success or failure status
- Output file path
- Article title and metadata
- Any errors or warnings

## Command Examples

```bash
# 基本导出
python3 ~/.npm-global/lib/node_modules/Encre/skills/WeChat-article-reader/scripts/export.py "https://mp.weixin.qq.com/s/xxx" ~/.Encre/workspace-qiming/source

# 指定自定义输出目录
python3 ~/.npm-global/lib/node_modules/Encre/skills/WeChat-article-reader/scripts/export.py "$URL" "/path/to/output"
```

## Output Format

The exported Markdown file contains:

```yaml
---
title: Article标题
author: 作者名称
publish_time: 发布时间
source_url: 原文链接
exported_at: 导出时间戳
description: Article描述
---

# Article标题

> 原文链接: URL

**作者**: XXX
**发布时间**: XXX

-----

Article正文内容...
```

## File Naming

Generated files follow the format: `YYYYMMDD_HHMMSS_Article.md` (article title)

Special characters in titles are cleaned to ensure file system compatibility.

## Common Issues and Limitations

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Cannot find article content" | Article requires login or has been deleted | Try opening in browser, or use browser tools |
| Connection timeout | Network issue or rate limiting | Wait and retry, check network connection |
| Encoding issue | Special characters | Script handles UTF-8 automatically |

### Known Limitations

- **Login required articles**: Some articles require WeChat login to view
- **Anti-crawling**: WeChat has anti-bot measures that may block frequent requests
- **Images**: Article images are not downloaded, only Markdown text is saved
- **Complex formatting**: May not be able to fully preserve all formatting

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| requests | >=2.31.0 | HTTP requests |
| beautifulsoup4 | >=4.12.0 | HTML parsing |
| lxml | >=4.9.0 | XML/HTML parser |
| markdownify | >=0.11.6 | HTML to Markdown |

## Error Handling

The script will:
- Print clear error messages (in Chinese)
- Exit with correct status codes
- Handle missing dependencies gracefully
- Validate URL format before processing

## Source

Based on the wechat-article-export project:
- GitHub: https://github.com/wechat-article/wechat-article-exporter
- This Skill was created by Qiming

## Open Source License

MIT License