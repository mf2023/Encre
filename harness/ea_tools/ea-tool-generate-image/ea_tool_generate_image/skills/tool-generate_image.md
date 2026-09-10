---
name: tool-generate_image
description: "Generate one or more images from a text prompt using the active backend's image-generation model (DALL-E-compatible). Use this to create original artwork, illustrations, or visual assets from a description; prefer it over diagram tools for photorealistic or painterly output. Do NOT use this for editing an existing image (use edit_image), for diagrams/flowcharts (use diagram), or for data charts (use chart). Tips: be specific about style, composition, and aspect ratio in the prompt; check supported `size` values for the target backend. Pitfalls: the active backend must implement generate_image, otherwise the call returns an unsupported error."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# generate_image

Generate one or more images from a text prompt using the active backend's image-generation model (DALL-E-compatible). Use this to create original artwork, illustrations, or visual assets from a description; prefer it over diagram tools for photorealistic or painterly output. Do NOT use this for editing an existing image (use edit_image), for diagrams/flowcharts (use diagram), or for data charts (use chart). Tips: be specific about style, composition, and aspect ratio in the prompt; check supported `size` values for the target backend. Pitfalls: the active backend must implement generate_image, otherwise the call returns an unsupported error.
