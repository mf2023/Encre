---
name: byted-mediakit-audio
version: "1.0.0"
license: "MIT"
description: "Audio processing, covering audio processing and enhancement, content understanding, etc. Capabilities include: separate-voice, probe-audio-metadata. Triggered when users need to use MediaKit CLI capabilities in the audio domain."
permissions:
  - shell
metadata:
  requires:
    bins: ["mediakit-cli"]
  cliHelp: "mediakit-cli audio --help"
  product: mediakit-cli/skills
  domain: audio
  capability_count: 2
---
# Audio Skills

## Prerequisites

Before starting, you must read the contents of `./reference/shared.md`, which contains instructions on prerequisite checks, async task mechanisms, result queries, etc.

## Tool List

| Tool | Description | Parameter Declaration | Reference |
|------|------|----------|----------|
| separate-voice | Precisely separate vocals from background audio, outputting two independent audio track files | `video_url?:string, audio_url?:string, callback_args?:string, client_token?:string` | [reference/separate-voice.md](reference/separate-voice.md) |
| probe-audio-metadata | Get detailed metadata of specified audio, outputting container layer information and audio stream metadata | `audio_url:string, callback_args?:string, client_token?:string` | [reference/probe-audio-metadata.md](reference/probe-audio-metadata.md) |
