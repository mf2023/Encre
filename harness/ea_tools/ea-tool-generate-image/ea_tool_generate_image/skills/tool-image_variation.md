---
name: tool-image_variation
description: "Generate one or more alternative variations of a source image, keeping the same subject but altering details. Use this to explore creative alternatives of an existing image without a text prompt; distinct from edit_image which targets a specific region. Do NOT use this for prompt-driven generation (use generate_image) or for masked edits (use edit_image). Tips: use a PNG source with a square aspect ratio for best compatibility; request multiple variations via `n`. Pitfalls: the active backend must implement create_image_variation \u9225?not all providers support this operation."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# image_variation

Generate one or more alternative variations of a source image, keeping the same subject but altering details. Use this to explore creative alternatives of an existing image without a text prompt; distinct from edit_image which targets a specific region. Do NOT use this for prompt-driven generation (use generate_image) or for masked edits (use edit_image). Tips: use a PNG source with a square aspect ratio for best compatibility; request multiple variations via `n`. Pitfalls: the active backend must implement create_image_variation 鈥?not all providers support this operation.
