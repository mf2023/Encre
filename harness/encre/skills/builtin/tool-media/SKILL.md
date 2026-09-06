---
name: tool-media
description: Media skill. action/file_path/output_path/codec/bitrate/format/quality/fps, process video/audio via ffmpeg without manual cli
hidden: true
context: inline
---

## When to Use
- Inspect video/audio metadata (duration, resolution, codec, bitrate)
- Convert media format/codec, compress, or trim a clip
- Extract audio from video, or extract frames as images
- Grab a screenshot at a timestamp, or transcribe speech to text

## When NOT to Use
- **A single still image** -> `image` tool
- **Live screen interaction** -> `desktop` / `computer_use` tools
- **Streaming / webcam capture** -> capture to a file first, then process here

## Key Parameters
- `action` (required): one of info, convert, extract_audio, extract_frames, compress, trim, screenshot, audio_info, transcribe
- `file_path` (required): path to the media file
- `output_path`: destination for convert/compress/trim/screenshot
- `output_dir`: directory for extract_frames
- `codec`: video codec for convert (e.g. libx264, libx265)
- `bitrate`: target bitrate (e.g. 1M, 500k)
- `format`: audio format for extract_audio (mp3, aac, wav, ogg, flac; default mp3)
- `quality`: CRF for compress (0-51, lower=better, default 23)
- `fps`: frames per second for extract_frames (default 1)
- `start`/`duration`: seconds for trim (default duration 10)
- `time`: timestamp for screenshot (e.g. 00:01:30, default 00:00:01)

## Best Practices
- Always call `info` first - duration and codec decide whether conversion is worth it
- For "understand this video", extract frames at 1fps + transcribe audio, then read samples
- Compress in the 18-23 CRF range (lower = higher quality + larger file)
- Trim by start + duration, not end timestamp; verify with `info` on the output
- Write outputs (frames, audio, transcripts) to a clear dir and list them afterward

## Common Pitfalls / Anti-patterns
- **Re-running expensive ffmpeg passes** -> run once, save outputs, read from files
- **Extreme compress quality** -> destroys the video; stay 18-28 unless size is critical
- **Missing output_path** -> convert/compress/trim/screenshot need it; omitting fails
- **1fps on a long video** -> 600 frames for 10 min; lower fps or trim first
- **Transcribing long media in one pass** -> extract audio, transcribe in segments

## Pairing with Other Tools
- `image`: process extracted frames (OCR, visual read)
- `file_write`: save a transcript or frame index
- `file_read`: read a saved transcript for follow-up
- `grep`: search within a transcript for a term or timestamp
