#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Media (video/audio) processing tool (ffmpeg).

Converts, trims, extracts audio, transcribes and reports info for video and
audio files via ffmpeg.
"""

import asyncio
import json
import os
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin._encoding import decode_bytes


async def _media_execute(**kwargs: Any) -> str:
    """Media execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    file_path = kwargs.get("file_path", "")
    if not file_path:
        return "Error: 'file_path' is required."

    if action == "info":
        return await _media_info(file_path)
    elif action == "convert":
        output_path = kwargs.get("output_path", "")
        codec = kwargs.get("codec", "")
        bitrate = kwargs.get("bitrate", "")
        return await _media_convert(file_path, output_path, codec, bitrate)
    elif action == "extract_audio":
        output_path = kwargs.get("output_path", "")
        format = kwargs.get("format", "mp3")
        return await _media_extract_audio(file_path, output_path, format)
    elif action == "extract_frames":
        output_dir = kwargs.get("output_dir", "")
        fps = kwargs.get("fps", 1)
        return await _media_extract_frames(file_path, output_dir, fps)
    elif action == "compress":
        output_path = kwargs.get("output_path", "")
        quality = kwargs.get("quality", 23)
        return await _media_compress(file_path, output_path, quality)
    elif action == "trim":
        output_path = kwargs.get("output_path", "")
        start = kwargs.get("start", 0)
        duration = kwargs.get("duration", 10)
        return await _media_trim(file_path, output_path, start, duration)
    elif action == "screenshot":
        output_path = kwargs.get("output_path", "")
        time = kwargs.get("time", "00:00:01")
        return await _media_screenshot(file_path, output_path, time)
    elif action == "audio_info":
        return await _media_audio_info(file_path)
    elif action == "transcribe":
        return await _media_transcribe(file_path)
    else:
        return f"Error: Unknown action '{action}'."


def _check_ffmpeg() -> None:
    """Check ffmpeg."""
    pass


async def _run_ffmpeg(args: list[str], timeout: int = 300) -> str:
    """Run ffmpeg.

    Args:
        args: Description of the args parameter.
        timeout: Description of the timeout parameter.
    """
    try:
        from encre.tools.builtin._suppress_window import (
            hidden_subprocess_kwargs as _hidden,
        )
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_hidden(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Error: ffmpeg command timed out after {timeout}s"
        out = decode_bytes(stdout) if stdout else ""
        err = decode_bytes(stderr) if stderr else ""
        if proc.returncode != 0:
            return f"ffmpeg error (exit {proc.returncode}): {err[:500]}"
        return out or err or "(completed)"
    except FileNotFoundError:
        return "Error: ffmpeg not found in PATH. Install ffmpeg from https://ffmpeg.org/"
    except Exception as e:
        return f"Error running ffmpeg: {e}"


def _parse_ffprobe_output(text: str) -> dict[str, Any]:
    """Parse ffprobe output.

    Args:
        text: Description of the text parameter.
    """
    info: dict[str, Any] = {}
    for line in text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"')
            if key and val:
                info[key.lower().replace(" ", "_")] = val
    return info


async def _media_info(file_path: str) -> str:
    """Media info.

    Args:
        file_path: Description of the file_path parameter.
    """
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    try:
        from encre.tools.builtin._suppress_window import (
            hidden_subprocess_kwargs as _hidden,
        )
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_hidden(),
        )
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return f"Error: ffprobe failed (exit {proc.returncode}). Is ffmpeg installed?"
        data = json.loads(decode_bytes(stdout))
    except FileNotFoundError:
        return "Error: ffprobe not found. Install ffmpeg from https://ffmpeg.org/"
    except json.JSONDecodeError:
        return "Error: Could not parse media file metadata."
    except Exception as e:
        return f"Error reading media info: {e}"

    result: dict[str, Any] = {
        "file": os.path.basename(file_path),
        "size_bytes": os.path.getsize(file_path),
    }

    fmt = data.get("format", {})
    if fmt:
        result.update({
            "duration_sec": round(float(fmt.get("duration", 0)), 2),
            "bitrate_kbps": fmt.get("bit_rate", ""),
            "format_name": fmt.get("format_name", ""),
        })

    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if video_streams:
        v = video_streams[0]
        result["video"] = {
            "codec": v.get("codec_name", ""),
            "width": v.get("width", 0),
            "height": v.get("height", 0),
            "fps": eval(v.get("r_frame_rate", "0/1")) if "/" in v.get("r_frame_rate", "") else 0,
            "bitrate_kbps": v.get("bit_rate", ""),
        }

    if audio_streams:
        a = audio_streams[0]
        result["audio"] = {
            "codec": a.get("codec_name", ""),
            "sample_rate": a.get("sample_rate", ""),
            "channels": a.get("channels", 0),
            "bitrate_kbps": a.get("bit_rate", ""),
        }

    return json.dumps(result, indent=2)


async def _media_convert(file_path: str, output_path: str, codec: str, bitrate: str) -> str:
    """Media convert.

    Args:
        file_path: Description of the file_path parameter.
        output_path: Description of the output_path parameter.
        codec: Description of the codec parameter.
        bitrate: Description of the bitrate parameter.
    """
    if not output_path:
        return "Error: 'output_path' is required for convert."
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    args = ["ffmpeg", "-i", file_path]
    if codec:
        args.extend(["-c:v", codec])
    if bitrate:
        args.extend(["-b:v", bitrate])
    args.extend(["-y", output_path])
    result = await _run_ffmpeg(args)
    if "error" in result.lower():
        return result
    return f"Converted: {file_path} -> {output_path}"


async def _media_extract_audio(file_path: str, output_path: str, fmt: str) -> str:
    """Media extract audio.

    Args:
        file_path: Description of the file_path parameter.
        output_path: Description of the output_path parameter.
        fmt: Description of the fmt parameter.
    """
    if not output_path:
        base = os.path.splitext(file_path)[0]
        output_path = f"{base}.{fmt}"
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"

    codec_map = {"mp3": "libmp3lame", "aac": "aac", "wav": "pcm_s16le", "ogg": "libvorbis", "flac": "flac"}
    acodec = codec_map.get(fmt, "libmp3lame")

    args = ["ffmpeg", "-i", file_path, "-vn", "-acodec", acodec, "-y", output_path]
    result = await _run_ffmpeg(args, timeout=600)
    if "error" in result.lower():
        return result
    return f"Audio extracted: {output_path}"


async def _media_extract_frames(file_path: str, output_dir: str, fps: int) -> str:
    """Media extract frames.

    Args:
        file_path: Description of the file_path parameter.
        output_dir: Description of the output_dir parameter.
        fps: Description of the fps parameter.
    """
    if not output_dir:
        output_dir = os.path.dirname(file_path) or "."
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(file_path))[0]
    pattern = os.path.join(output_dir, f"{base}_frame_%04d.png")
    args = ["ffmpeg", "-i", file_path, "-vf", f"fps={fps}", pattern, "-y"]
    result = await _run_ffmpeg(args, timeout=600)
    if "error" in result.lower():
        return result

    frame_count = len([f for f in os.listdir(output_dir) if f.startswith(base + "_frame_")])
    return f"Extracted {frame_count} frames ({fps} fps) to {output_dir}/"


async def _media_compress(file_path: str, output_path: str, quality: int) -> str:
    """Media compress.

    Args:
        file_path: Description of the file_path parameter.
        output_path: Description of the output_path parameter.
        quality: Description of the quality parameter.
    """
    if not output_path:
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}_compressed{ext}"
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    args = ["ffmpeg", "-i", file_path, "-crf", str(quality), "-preset", "medium", "-y", output_path]
    result = await _run_ffmpeg(args, timeout=600)
    if "error" in result.lower():
        return result
    orig_size = os.path.getsize(file_path)
    new_size = os.path.getsize(output_path)
    ratio = (1 - new_size / orig_size) * 100 if orig_size else 0
    return f"Compressed: {output_path} ({ratio:.1f}% smaller, CRF={quality})"


async def _media_trim(file_path: str, output_path: str, start: int, duration: int) -> str:
    """Media trim.

    Args:
        file_path: Description of the file_path parameter.
        output_path: Description of the output_path parameter.
        start: Description of the start parameter.
        duration: Description of the duration parameter.
    """
    if not output_path:
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}_trim{ext}"
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    args = ["ffmpeg", "-i", file_path, "-ss", str(start), "-t", str(duration), "-c", "copy", "-y", output_path]
    result = await _run_ffmpeg(args)
    if "error" in result.lower():
        return result
    return f"Trimmed: {output_path} ({duration}s starting at {start}s)"


async def _media_screenshot(file_path: str, output_path: str, time: str) -> str:
    """Media screenshot.

    Args:
        file_path: Description of the file_path parameter.
        output_path: Description of the output_path parameter.
        time: Description of the time parameter.
    """
    if not output_path:
        base = os.path.splitext(file_path)[0]
        output_path = f"{base}_screenshot.png"
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    args = ["ffmpeg", "-i", file_path, "-ss", time, "-vframes", "1", "-y", output_path]
    result = await _run_ffmpeg(args)
    if "error" in result.lower():
        return result
    return f"Screenshot saved: {output_path} (at {time})"


async def _media_audio_info(file_path: str) -> str:
    """Media audio info.

    Args:
        file_path: Description of the file_path parameter.
    """
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    try:
        from encre.tools.builtin._suppress_window import (
            hidden_subprocess_kwargs as _hidden,
        )
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams",
            "-select_streams", "a", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_hidden(),
        )
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return "No audio streams found in file."
        data = json.loads(decode_bytes(stdout))
    except FileNotFoundError:
        return "Error: ffprobe not found. Install ffmpeg."
    except Exception as e:
        return f"Error reading audio info: {e}"

    result: dict[str, Any] = {"file": os.path.basename(file_path)}
    fmt = data.get("format", {})
    if fmt:
        result.update({
            "duration_sec": round(float(fmt.get("duration", 0)), 2),
            "bitrate_kbps": fmt.get("bit_rate", ""),
            "format_name": fmt.get("format_name", ""),
        })
    streams = data.get("streams", [])
    if streams:
        a = streams[0]
        result["audio"] = {
            "codec": a.get("codec_name", ""),
            "sample_rate": a.get("sample_rate", ""),
            "channels": a.get("channels", 0),
            "bitrate_kbps": a.get("bit_rate", ""),
        }
    return json.dumps(result, indent=2)


async def _media_transcribe(file_path: str) -> str:
    """Media transcribe.

    Args:
        file_path: Description of the file_path parameter.
    """
    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"

    try:
        import whisper
    except ImportError:
        return "Error: openai-whisper is required. Install with: pip install openai-whisper"

    try:
        model = whisper.load_model("base")
        result = model.transcribe(file_path)
        return json.dumps({
            "text": result.get("text", "").strip(),
            "language": result.get("language", ""),
            "duration_sec": round(result.get("duration", 0), 2),
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error transcribing audio: {e}"


EncreMediaTool = build_tool(
    name="media",
    description=(
        "Process audio and video files with ffmpeg, plus optional Whisper-based "
        "speech transcription. "
        "Use this for `info`/`audio_info` (metadata), `convert` (re-encode), "
        "`extract_audio` (rip a track), `extract_frames` (frames to PNG), `compress` "
        "(CRF quality control), `trim` (clip a segment), `screenshot` (capture a "
        "frame), or `transcribe` (speech to text). "
        "Do NOT use this for static image operations (use image), live streaming, or "
        "real-time capture; and prefer a dedicated ASR service for long-form audio. "
        "Tips: set `output_path` to control where artifacts land; use `quality` (CRF) "
        "and `bitrate` to balance size vs. fidelity. "
        "Pitfalls: requires ffmpeg on PATH; `transcribe` additionally requires the "
        "openai-whisper package and is much slower than ffmpeg operations."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["info", "convert", "extract_audio", "extract_frames",
                         "compress", "trim", "screenshot", "audio_info", "transcribe"],
                "description": "Media operation: info/audio_info (metadata), convert (re-encode), extract_audio (rip audio), extract_frames (frames to PNG), compress (CRF), trim (clip), screenshot (single frame), or transcribe (speech to text).",
            },
            "file_path": {
                "type": "string",
                "description": "Path to the source audio or video file to process.",
            },
            "output_path": {
                "type": "string",
                "description": "Destination path for the produced media artifact (convert, extract_audio, compress, trim, screenshot).",
            },
            "codec": {
                "type": "string",
                "description": "Target video codec for convert (e.g. libx264, libx265, libvpx).",
            },
            "bitrate": {
                "type": "string",
                "description": "Target bitrate for convert/compress (e.g. '1M', '500k').",
            },
            "format": {
                "type": "string",
                "enum": ["mp3", "aac", "wav", "ogg", "flac"],
                "description": "Audio format used by extract_audio; defaults to mp3.",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to write extracted PNG frames from extract_frames.",
            },
            "fps": {
                "type": "integer",
                "description": "Frames per second to extract via extract_frames; defaults to 1.",
            },
            "quality": {
                "type": "integer",
                "description": "CRF value for compress (0-51, lower is higher quality); defaults to 23.",
            },
            "start": {
                "type": "integer",
                "description": "Start time in seconds for trim.",
            },
            "duration": {
                "type": "integer",
                "description": "Clip length in seconds for trim; defaults to 10.",
            },
            "time": {
                "type": "string",
                "description": "Timestamp for screenshot (e.g. '00:01:30'); defaults to '00:00:01'.",
            },
        },
        "required": ["action", "file_path"],
    },
    execute=_media_execute,
    intents=["data", "general", "media", "research"],
    category="media",
    semantic_type="media",
    is_concurrency_safe=lambda data: data.get("action") in ("info", "audio_info"),
    is_destructive=lambda args: args.get("action", "") in ("convert", "extract_audio", "extract_frames", "compress", "trim", "screenshot"),
)
