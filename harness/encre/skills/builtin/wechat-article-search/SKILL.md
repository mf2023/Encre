---
name: wechat-article-search
description: Search WeChat official account articles
metadata:
  source: clawhub
  tags: wechat-article-search
user_invocable: true
hidden: true
context: inline
---

## WeChat Article Search

### When to Use
- Search for public WeChat Official Account articles by keyword
- Find content published on WeChat's closed ecosystem

### How It Works
- Use `web_search` with `site:mp.weixin.qq.com <keyword>` to find public articles
- Append `?scene=1` to URLs to bypass some access prompts

### Common Pitfalls
- Many articles require login or follower access; only public articles are searchable
- Deleted articles may still appear in search results but return 404
