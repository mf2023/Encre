---
name: tool-edit_image
description: "Edit an existing image with a text prompt, optionally constrained to the area revealed by a mask. Use this to inpaint part of an image while preserving the rest, rather than regenerating from scratch. Do NOT use this for full-image regeneration (use generate_image) or for creative variations of the whole image (use image_variation). Tips: provide a mask where fully transparent pixels mark the editable region; describe the desired result, not the original. Pitfalls: the active backend must implement edit_image and accept the supplied image/mask encoding."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# edit_image

Edit an existing image with a text prompt, optionally constrained to the area revealed by a mask. Use this to inpaint part of an image while preserving the rest, rather than regenerating from scratch. Do NOT use this for full-image regeneration (use generate_image) or for creative variations of the whole image (use image_variation). Tips: provide a mask where fully transparent pixels mark the editable region; describe the desired result, not the original. Pitfalls: the active backend must implement edit_image and accept the supplied image/mask encoding.
