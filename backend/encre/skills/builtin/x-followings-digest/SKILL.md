---
name: x-followings-digest
description: Auto-fetch latest tweets from your X/Twitter followings and generate structured AI digest.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## X Followings Digest
# X Followings Digest Generator

Auto-fetch latest tweets from your followings and generate structured AI digest.

## Quick Start

### 1. Configure X Auth

```bash
export AUTH_TOKEN="your_auth_token"
export CT0="your_ct0"
```

### 2. Fetch Tweets

```bash
# Default: last 1 day
./scripts/fetch_followings_tweets.sh

# Specify count & days
./scripts/fetch_followings_tweets.sh 50 1   # 50 tweets, 1 day
./scripts/fetch_followings_tweets.sh 50 3   # 50 tweets, 3 days
./scripts/fetch_followings_tweets.sh 100 7  # 100 tweets, 7 days (weekly)
```

### 3. Generate Digest

Feed the fetched tweets to the AI using the prompt template in external documentation.

## Output Format

Digest includes (only shows categories with content):

- **🔥 Major Events** - Specific details & impact analysis
- **🚀 Product Releases** - New models, API updates, tools
- **💡 Tech Insights** - Technical solutions, optimizations
- **🔗 Resources** - Papers, OSS, tutorials, tools
- **🎁 Deals & Freebies** - Free credits, discounts, giveaways
- **📊 Signals** - Controversies, predictions, warnings

## Language Setting

When calling the AI, specify output language in the prompt:

- **Chinese Output**: Use the [Chinese] section in the prompt template
- **English Output**: Use the [EN] section in the prompt template
- **Bilingual**: Use the full prompt template, request bilingual output

## Dependencies

- `bird` CLI (X/Twitter client)
- `AUTH_TOKEN` & `CT0` from browser cookies

## Notes

- More tweets = longer processing time
- Recommended: set up cron job for daily auto-run
