---
name: tool-github
description: "Interact with the GitHub and GitLab REST APIs to manage issues, pull/merge requests, repositories, releases, gists, and CI Actions runs. Use this for any provider-level operation such as listing/creating/searching issues, opening or merging PRs, reviewing code, dispatching workflows, or browsing repo metadata. Do NOT use this for local git commands (commit, push, branch) \u9225?use the git tool instead; and avoid it for in-depth file diffs already covered by git. Tips: prefer GITHUB_TOKEN/GITLAB_TOKEN env vars over passing `token`; cap `per_page` (max 100) to keep responses small. Pitfalls: most repo-scoped actions require `repo` as owner/repo; the request times out after 60s and provider rate limits apply."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# github

Interact with the GitHub and GitLab REST APIs to manage issues, pull/merge requests, repositories, releases, gists, and CI Actions runs. Use this for any provider-level operation such as listing/creating/searching issues, opening or merging PRs, reviewing code, dispatching workflows, or browsing repo metadata. Do NOT use this for local git commands (commit, push, branch) 鈥?use the git tool instead; and avoid it for in-depth file diffs already covered by git. Tips: prefer GITHUB_TOKEN/GITLAB_TOKEN env vars over passing `token`; cap `per_page` (max 100) to keep responses small. Pitfalls: most repo-scoped actions require `repo` as owner/repo; the request times out after 60s and provider rate limits apply.
