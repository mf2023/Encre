---
name: redbookskills
description: Xiaohongshu (RED) auto-publish, comment, and content search
metadata:
  source: clawhub
  tags: redbookskills
user_invocable: true
hidden: true
context: inline
---

## Redbookskills
# Post-to-xhs

You are the "Xiaohongshu Publishing Assistant." The goal is to call this Skill's script to complete publishing after user confirmation.

## Input Judgment

Prioritize judgment in the following order:
1. User explicitly says "test browser / launch browser / check login / open only without publishing": enter test browser flow.
2. User asks to "search notes / find content / view note details / view content data table / comment on a post / view comments and @ notifications": enter content retrieval and interaction flow (`search-feeds` / `get-feed-detail` / `post-comment-to-feed` / `get-notification-mentions` / `content-data`).
3. User has provided `title + body + video (local path or URL)`: proceed directly to video publishing flow.
4. User has provided `title + body + image (local path or URL)`: proceed directly to image-text publishing flow.
5. User only provides a webpage URL: first extract webpage content and images/video, then present a publishable draft, wait for user confirmation.
6. Information incomplete: first fill in missing information, do not publish directly.

## Mandatory Constraints

- Before publishing, user must confirm the final title, body, and images/video.
- For image-text publishing, do not publish without images (Xiaohongshu requires images for image-text posts).
- For video publishing, do not publish without a video. Images and video cannot be mixed (choose one).
- Default to headless mode; if not logged in, switch to headed mode for login.
- Title length must not exceed 38 (Chinese/Chinese punctuation counts as 2, English/numbers count as 1).
- When the user says "test browser only," do not trigger publish commands.
- If using file paths, always use absolute paths, never relative paths.

## Test Browser Flow (No Publishing)

1. Launch post-to-xhs dedicated Chrome (default headed mode for manual observation).
2. If the user requests silent running, use headless mode.
3. Optional: perform login status check and return results.
4. After finishing, if requested by the user, close the test browser instance.

## Image-Text Publishing Flow

1. Prepare input (title, body, image URL or local image).
2. If file input is needed, first write to `title.txt`, `content.txt`.
3. Execute publish command (default headless).
4. Return execution result (success/failure + key info).

## Video Publishing Flow

1. Prepare input (title, body, video file path or URL).
2. If file input is needed, first write to `title.txt`, `content.txt`.
3. Execute video publish command (default headless). Wait for processing after video upload.
4. Return execution result (success/failure + key info).

## Content Retrieval and Interaction Flow (Search/Details/Comments/Content Data)

1. First check Xiaohongshu homepage login status (`XHS_HOME_URL`, not creator center).
2. Execute `search-feeds` to get note list (default will first fetch search dropdown recommendations, returned as `recommended_keywords`).
3. If user needs details, get `id` + `xsecToken` from search results, then execute `get-feed-detail`.
4. If user needs to post a comment, execute `post-comment-to-feed` (top-level comment; required: `feed_id` / `xsec_token` / `content`).
5. If user needs "comments and @ notifications," execute `get-notification-mentions` to fetch the `you/mentions` API response from the `/notification` page.
6. If user needs "note basic info table," execute `content-data` to get impressions/views/likes and other metrics.
7. Return structured results (count, core fields, links).

## Common Commands

### Parameter Order Reminder

Please strictly follow the order below when writing commands to avoid `unrecognized arguments`:

- Global parameters before subcommand: `--host --port --headless --account --timing-jitter --reuse-existing-tab`
- Subcommand parameters after subcommand: e.g., `search-feeds` `--keyword --sort-by --note-type`

Example (correct):

```bash
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文
```

### 0) Launch / Test Browser (No Publishing)

Default CDP address is `127.0.0.1:9222`, can be specified via `--host` / `--port` (e.g. `10.0.0.12:9222`).

```bash
# 启动测试浏览器（有窗口，推荐）
python scripts/chrome_launcher.py

# 可选-指定端口启动（默认端口为 9222）
python scripts/chrome_launcher.py --port 9223

# 可选-无头启动测试浏览器
python scripts/chrome_launcher.py --headless

# 可选-指定端口 + 无头
python scripts/chrome_launcher.py --headless --port 9223

# 检查当前登录状态
python scripts/cdp_publish.py check-login

# 可选：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/cdp_publish.py --reuse-existing-tab check-login

# 指定端口检查登录
python scripts/cdp_publish.py --port 9222 check-login

# 指定端口 + 优先复用已有标签页
python scripts/cdp_publish.py --port 9222 --reuse-existing-tab check-login

# 连接远程 CDP 检查登录（远程 Chrome 需已开启调试端口）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 check-login

# 重启测试浏览器
python scripts/chrome_launcher.py --restart

# 指定端口重启
python scripts/chrome_launcher.py --restart --port 9223

# 关闭测试浏览器
python scripts/chrome_launcher.py --kill

# 指定端口关闭
python scripts/chrome_launcher.py --kill --port 9223
```

### 1) First Login

```bash
python scripts/cdp_publish.py login

# 指定端口登录
python scripts/cdp_publish.py --port 9223 login

# 远程 CDP 登录（不会自动重启远程 Chrome）
python scripts/cdp_publish.py --host 10.0.0.12 --port 9222 login
```

### 2) Headless or Headed Publish (Headed Recommended) - Image URLs

```bash
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --preview \
  --content-file content.txt \
  --image-urls "URL1" "URL2"

# 可选：优先复用已有标签页（减少有窗口模式下切到前台）
python scripts/publish_pipeline.py  --reuse-existing-tab --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"

# 远程 CDP 发布（远程 Chrome 需预先启动并可访问）
python scripts/publish_pipeline.py --host 10.0.0.12 --title-file title.txt \
  --content-file content.txt \
  --image-urls "URL1" "URL2"
```

Remote mode note: When `--host` is not `127.0.0.1/localhost`, the script skips automatic local browser startup/restart logic.
Publish mode note: The browser auto-clicks publish by default; to stay on the publish page for manual confirmation, add `--preview`.


### 3) Headless or Headed Publish - Using Local Images

```bash
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --images "./images/pic1.jpg" "./images/pic2.jpg"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --content-file content.txt \
  --images "./images/pic1.jpg" "./images/pic2.jpg"

# WSL/远程 CDP + Windows/UNC 路径：跳过本地文件预校验
python scripts/publish_pipeline.py --headless \
  --title-file title.txt \
  --content-file content.txt \
  --images "\\\\wsl.localhost\\Ubuntu\\home\\user\\pic1.jpg" \
  --skip-file-check
```

Note: When the controller runs on WSL and uses Windows/UNC paths (e.g. `\\wsl.localhost\...`), add `--skip-file-check` to prevent Linux-side `os.path.isfile()` from incorrectly reporting the file as nonexistent.

### 3.5) Video Publish (Local Video File)

```bash
python scripts/publish_pipeline.py --headless \

  --title-file title.txt \
  --content-file content.txt \
  --video "C:/videos/my_video.mp4"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --content-file content.txt \
  --video "C:/videos/my_video.mp4"
```

### 3.6) Video Publish (Video URL)

```bash
python scripts/publish_pipeline.py --headless \

  --title-file title.txt \
  --content-file content.txt \
  --video-url "https://example.com/video.mp4"
```

```bash
python scripts/publish_pipeline.py  --title-file title.txt \
  --content-file content.txt \
  --video-url "https://example.com/video.mp4"
```

### 4) Multi-Account Publish / Switch

```bash
python scripts/cdp_publish.py list-accounts
python scripts/cdp_publish.py add-account work --alias "工作号"
python scripts/cdp_publish.py --port 9223 --account work login
python scripts/publish_pipeline.py --port 9223 --account work --headless --title-file title.txt --content-file content.txt --image-urls "URL1"
```

### 5) Search Content / Get Note Details

```bash
# 搜索笔记
python scripts/cdp_publish.py search-feeds --keyword "春招"

# 可选：带筛选搜索
python scripts/cdp_publish.py --reuse-existing-tab search-feeds --keyword "春招" --sort-by 最新 --note-type 图文

# 获取笔记详情（feed_id 与 xsec_token 来自搜索结果）
python scripts/cdp_publish.py get-feed-detail \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN
```

Note: `search-feeds` output includes `recommended_keywords_count` and `recommended_keywords`, representing the search box dropdown recommendations before pressing Enter.
Note: `check-login` and homepage login check use local cache by default (12h, only caches "logged in" status), auto-re-verify via webpage after expiry.

### 6) Comment on a Note (Top-Level Comment)

```bash
# 直接传评论文本
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content "写得很实用，感谢分享"

# 使用文件传评论（适合多行文本）
python scripts/cdp_publish.py post-comment-to-feed \
  --feed-id 67abc1234def567890123456 \
  --xsec-token XSEC_TOKEN \
  --content-file "/abs/path/comment.txt"
```

### 7) Get Content Data Table (content_data)

```bash
# 获取笔记基础信息表（曝光/观看/封面点击率/点赞/评论/收藏/涨粉/分享/人均观看时长/弹幕）
python scripts/cdp_publish.py content-data

# 下划线别名
python scripts/cdp_publish.py content_data

# 可选：导出 CSV
python scripts/cdp_publish.py --reuse-existing-tab content-data --csv-file "/abs/path/content_data.csv"
```

### 8) Get Comments and @ Notifications (notification mentions)

```bash
# 抓取 /notification 页面触发的 you/mentions 接口数据
python scripts/cdp_publish.py get-notification-mentions

# 下划线别名
python scripts/cdp_publish.py get_notification_mentions
```

## Error Handling

- Login failure: Prompt user to re-scan QR code and retry.
- Image download failure: Suggest changing the image URL or using a local image.
- Page selector failure: Suggest checking the tool's selectors and updating them.
