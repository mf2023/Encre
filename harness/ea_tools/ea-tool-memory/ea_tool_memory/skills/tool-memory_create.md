---
name: tool-memory_create
description: "Create a new persistent memory file that is encrypted at rest and automatically loaded into the agent's context on future runs. Use this to record durable user preferences, project context, feedback, or reference notes that should outlive the current session. Do NOT use this for ephemeral scratch data (use todo/task tools), for bulk file storage (use file_write), or to overwrite an existing memory (use memory_update instead). Tips: include YAML frontmatter (between --- lines) to set name, description, type (user/feedback/project/reference), and tags for richer retrieval. Pitfalls: filenames must use the .md extension; creating a file that already exists will overwrite it."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# memory_create

Create a new persistent memory file that is encrypted at rest and automatically loaded into the agent's context on future runs. Use this to record durable user preferences, project context, feedback, or reference notes that should outlive the current session. Do NOT use this for ephemeral scratch data (use todo/task tools), for bulk file storage (use file_write), or to overwrite an existing memory (use memory_update instead). Tips: include YAML frontmatter (between --- lines) to set name, description, type (user/feedback/project/reference), and tags for richer retrieval. Pitfalls: filenames must use the .md extension; creating a file that already exists will overwrite it.
