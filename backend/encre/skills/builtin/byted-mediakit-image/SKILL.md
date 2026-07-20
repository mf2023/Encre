---
name: byted-mediakit-image
version: "1.0.0"
license: "MIT"
description: "Image processing, covering image compression, image enhancement, AI processing, etc. Capabilities include: image-ocr, erase-image, remove-image-background, enhance-image, evaluate-image-quality. Triggered when users need to use MediaKit CLI capabilities in the image domain."
permissions:
  - shell
metadata:
  requires:
    bins: ["mediakit-cli"]
  cliHelp: "mediakit-cli image --help"
  product: mediakit-cli/skills
  domain: image
  capability_count: 5
---
# Image Skills

## Prerequisites

Before starting, you must read the contents of `./reference/shared.md`, which contains instructions on prerequisite checks, result processing, etc.

> All tools in this domain execute synchronously. The final result is returned directly upon successful invocation, no `query-task` polling required.

## Tool List

| Tool | Description | Parameter Declaration | Reference |
|------|------|----------|----------|
| image-ocr | Recognize printed text in images, returning editable text, text box coordinates, and confidence | `image_url:string, callback_args?:string, client_token?:string` | [reference/image-ocr.md](reference/image-ocr.md) |
| erase-image | Automatically detect and erase common icons, text, or specified regions in images, with intelligent background filling for erased areas | `image_url:string, tool_version?:string, standard_scene?:string, standard_erase_text?:string, output_format?:string, callback_args?:string, client_token?:string` | [reference/erase-image.md](reference/erase-image.md) |
| remove-image-background | Automatically identify and preserve the main subject of an image, remove the background, and generate a transparent background image | `image_url:string, scene:string, need_contour?:boolean, contour_color?:string, contour_size?:integer, need_crop_background?:boolean, output_format?:string, callback_args?:string, client_token?:string` | [reference/remove-image-background.md](reference/remove-image-background.md) |
| enhance-image | Intelligent decision-making based on image content understanding to comprehensively improve image resolution, clarity, and color performance | `image_url:string, tool_version?:string, multiple?:number, target_width?:integer, target_height?:integer, callback_args?:string, client_token?:string` | [reference/enhance-image.md](reference/enhance-image.md) |
| evaluate-image-quality | Perform subjective and objective quality and aesthetic scoring on input images | `image_url:string, tool_version?:string, standard_evaluate_items?:array<string>, callback_args?:string, client_token?:string` | [reference/evaluate-image-quality.md](reference/evaluate-image-quality.md) |
