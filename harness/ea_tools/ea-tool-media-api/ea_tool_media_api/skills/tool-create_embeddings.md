---
name: tool-create_embeddings
description: "Generate vector embeddings for text inputs using the active backend's embeddings model. Use this to power semantic search, clustering, or similarity comparisons; returns a JSON sample of the first few embedding dimensions per input. Do NOT use this for chat completions (use the chat backend) or for moderation checks (use create_moderation). Tips: pass a single string or a JSON array of strings for batch embedding; keep inputs under the model's token limit. Pitfalls: output is truncated to 5 dimensions per item for display \u9225?retrieve full vectors from the backend directly if you need them."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# create_embeddings

Generate vector embeddings for text inputs using the active backend's embeddings model. Use this to power semantic search, clustering, or similarity comparisons; returns a JSON sample of the first few embedding dimensions per input. Do NOT use this for chat completions (use the chat backend) or for moderation checks (use create_moderation). Tips: pass a single string or a JSON array of strings for batch embedding; keep inputs under the model's token limit. Pitfalls: output is truncated to 5 dimensions per item for display 鈥?retrieve full vectors from the backend directly if you need them.
