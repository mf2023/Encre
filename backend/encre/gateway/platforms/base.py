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

"""Base platform adapter interface.

All platform adapters inherit from :class:`BasePlatformAdapter` and implement
the required abstract methods.

Architecture:
    Platform adapters run in the same process as the agent.  Incoming messages
    are normalized into :class:`MessageEvent` and dispatched via
    :meth:`BasePlatformAdapter.handle_message` to the GatewayRunner, which
    routes them through the EventRouter to the AI agent.  Outgoing responses
    are delivered back through :meth:`BasePlatformAdapter.send`.

Key patterns:
    - ABC with 4 abstract methods: connect, disconnect, send, get_chat_info
    - Capability flags for platform-specific behavior (supports_code_blocks, etc.)
    - Standardized MessageEvent / SendResult dataclasses
    - handle_message dispatches to the registered _message_handler (set by GatewayRunner)
"""

import asyncio
import enum
import logging
import os
import re as _re
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from encre.gateway.config import Platform, PlatformConfig
from encre.gateway.session import SessionSource

logger = logging.getLogger("encre.gateway.platforms.base")





def _word_split(text: str, limit: int, page_offset: int) -> list[str]:
    """Split *text* on word boundaries so each piece ≤ *limit*.

    *page_offset* is the zero-based number of complete chunks already emitted
    before this function is called; it is used only for internal progress
    indicators that are stripped at the end.
    """
    # ── second resort: split on word boundaries ──
    words = text.split()
    parts: list[str] = []
    buf = ""
    for w in words:
        if len(buf) + len(w) + (1 if buf else 0) <= limit:
            buf = (buf + " " + w).strip()
            continue
        if buf:
            parts.append(buf)
            buf = w
        else:
            # Single word exceeds limit → hard-chop
            parts.append(w[:limit])
            buf = w[limit:]
    if buf:
        parts.append(buf)
    return parts


# -- Message types -------------------------------------------------------------


class MessageType(enum.Enum):
    """Supported message content types."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    LOCATION = "location"
    STICKER = "sticker"
    VOICE = "voice"
    PHOTO = "photo"
    DOCUMENT = "document"
    COMMAND = "command"


# -- MessageEvent --------------------------------------------------------------


@dataclass
class MessageEvent:
    """Normalized incoming message from a platform.

    All platform-specific message formats are translated into this unified
    representation before being dispatched to the agent backend.

    Attributes:
        text: The message text content.
        message_type: The type of content carried by this message.
        source: Structured routing origin (platform/chat_id/chat_type/user).
        raw_message: The original platform-specific message payload.
        message_id: Platform-unique message identifier.
        media_urls: URLs or file paths for attached media.
        media_types: MIME types corresponding to media_urls entries.
        reply_to_message_id: If this is a reply, the id of the parent message.
        reply_to_text: Cached text of the replied-to message.
        reply_to_author_id: Author id of the replied-to message.
        reply_to_author_name: Author name of the replied-to message.
        reply_to_is_own_message: True when replying to the bot's own message.
        auto_skill: Auto-loaded skill(s) for topic/channel bindings.
        channel_prompt: Per-channel ephemeral system prompt.
        channel_context: Channel context recovered by history backfill.
        platform_update_id: Platform-specific update identifier (e.g. Telegram update_id).
    """

    text: str
    message_type: MessageType = MessageType.TEXT
    source: SessionSource | None = None
    raw_message: Any = None
    message_id: Optional[str] = None
    platform_update_id: Optional[int] = None
    media_urls: List[str] = field(default_factory=list)
    media_types: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    reply_to_author_id: Optional[str] = None
    reply_to_author_name: Optional[str] = None
    reply_to_is_own_message: bool = False
    auto_skill: Optional[str | list[str]] = None
    channel_prompt: Optional[str] = None
    channel_context: Optional[str] = None
    timestamp: Optional[datetime] = None

    def is_command(self) -> bool:
        """Check if this message is a slash command."""
        return self.text.startswith("/")

    def get_command(self) -> str | None:
        """Extract the command name (without leading '/')."""
        if not self.is_command():
            return None
        parts = self.text.split(maxsplit=1)
        raw = parts[0][1:].lower() if parts else None
        if raw and "@" in raw:
            raw = raw.split("@", 1)[0]
        if raw and "/" in raw:
            return None
        return raw

    def get_command_args(self) -> str:
        """Extract command arguments (everything after the command token)."""
        if not self.is_command():
            return self.text
        parts = self.text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""


# -- SendResult ----------------------------------------------------------------


@dataclass
class SendResult:
    """Result of a message send operation.

    Attributes:
        success: Whether the message was sent successfully.
        message_id: Platform-specific id of the sent message.
        error: Human-readable error description if success is False.
        retryable: Whether the failure is transient and retryable.
        retry_after: Server-requested retry delay in seconds.
        error_kind: Machine-readable failure category.
        raw: Platform-specific raw response data.
    """

    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    retry_after: Optional[float] = None
    error_kind: Optional[str] = None
    raw: Any = None


# -- Error classification -------------------------------------------------------

SEND_ERROR_KINDS = frozenset({
    "too_long",
    "bad_format",
    "forbidden",
    "not_found",
    "rate_limited",
    "transient",
    "unknown",
})


def classify_send_error(exc: BaseException | None = None, error_text: str = "") -> str:
    """Map a send exception / error string to a SEND_ERROR_KINDS value."""
    parts: list[str] = []
    if error_text:
        parts.append(str(error_text))
    if exc is not None:
        parts.append(str(exc))
        parts.append(type(exc).__name__)
    blob = " ".join(parts).lower()
    if not blob.strip():
        return "unknown"
    if "message_too_long" in blob or "too long" in blob:
        return "too_long"
    if "can't parse entities" in blob or "unsupported start tag" in blob:
        return "bad_format"
    if "forbidden" in blob or "blocked" in blob or "kicked" in blob:
        return "forbidden"
    if "not found" in blob or "chat not found" in blob:
        return "not_found"
    if ("rate" in blob and "limit" in blob) or "flood" in blob or "too many requests" in blob:
        return "rate_limited"
    if "timeout" in blob or "timed out" in blob or "connection" in blob or "network" in blob:
        return "transient"
    return "unknown"


# -- ProcessingOutcome ---------------------------------------------------------


class ProcessingOutcome(enum.Enum):
    """Outcome of processing an incoming message."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


# -- Media tag cleanup ---------------------------------------------------------

_MEDIA_DELIVERY_EXTS: Tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".flac",
    ".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".epub",
    ".xlsx", ".xls", ".ods", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".pptx", ".ppt", ".odp", ".key",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".apk", ".ipa",
    ".html", ".htm",
)

_MEDIA_EXT_ALTERNATION = "|".join(
    sorted((e.lstrip(".") for e in _MEDIA_DELIVERY_EXTS), key=len, reverse=True)
)

MEDIA_TAG_CLEANUP_RE = _re.compile(
    r'''[`"']?MEDIA:\s*'''
    r'''(?P<path>`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|'''
    r'''(?:~/|/|[A-Za-z]:[/\\])\S+(?:[^\S\n]+\S+)*?\.(?:''' + _MEDIA_EXT_ALTERNATION + r'''))'''
    r'''(?=[\s`"',;:)\]}]|$)[`"']?''',
    _re.IGNORECASE,
)

MEDIA_EXTENSIONLESS_TAG_RE = _re.compile(
    r'''[`"']?MEDIA:\s*'''
    r'''(?P<path>`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|'''
    r'''(?:~/|/|[A-Za-z]:[/\\])[^\s\n`"']+)'''
    r'''[`"']?\s*''',
    _re.IGNORECASE,
)

_LOG_UNSAFE_CHARS = _re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029]")


def _normalize_media_tag_path(raw: str) -> str:
    path = str(raw or "").strip()
    if len(path) >= 2 and path[0] == path[-1] and path[0] in "`\"'":
        path = path[1:-1].strip()
    return path.lstrip("`\"'").rstrip("`\"',.;:)}]")


def _path_lacks_deliverable_extension(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return not suffix or suffix not in _MEDIA_DELIVERY_EXTS


def _log_safe_path(path: str) -> str:
    return _LOG_UNSAFE_CHARS.sub("?", str(path))[:200]


def _mask_protected_spans(content: str) -> str:
    """Replace content inside fenced code blocks, inline code spans,
    and blockquotes with spaces to prevent MEDIA: false positives."""
    chars = list(content)
    spans: list = []
    for m in _re.finditer(r'```[^\n]*\n.*?```', content, _re.DOTALL):
        spans.append((m.start(), m.end()))
    for m in _re.finditer(r'`[^`\n]+`', content):
        start = m.start()
        prefix = content[max(0, start - 20):start]
        if _re.search(r'MEDIA:\s*$', prefix):
            continue
        spans.append((start, m.end()))
    for m in _re.finditer(r'^>.*$', content, _re.MULTILINE):
        spans.append((m.start(), m.end()))
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != '\n':
                chars[i] = ' '
    return ''.join(chars)


def _mask_json_string_media(content: str) -> str:
    """Blank out MEDIA: tags inside JSON string values."""
    if '"' not in content or "MEDIA:" not in content:
        return content
    chars = list(content)
    for m in _re.finditer(r'(?<=[:,{\[])\s*"((?:[^"\\\n]|\\.)*)"', content):
        seg = m.group(1)
        if _re.search(r'MEDIA:\s*(?:~/|/|[A-Za-z]:[/\\])', seg):
            for i in range(m.start(1), m.end(1)):
                if chars[i] != '\n':
                    chars[i] = ' '
    return ''.join(chars)


def validate_media_delivery_path(path: str) -> str | None:
    """Return a safe absolute file path for native media delivery, else None.

    Checks: file exists on disk, expands ~, resolves symlinks, blocks
    system/credential paths (*/etc, */proc, ~/.ssh, ~/.aws, etc.).
    """
    if not path:
        return None
    candidate = str(path).strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "`\"'":
        candidate = candidate[1:-1].strip()
    candidate = candidate.lstrip("`\"'").rstrip("`\"',.;:)}]")
    if not candidate:
        return None
    try:
        expanded = Path(os.path.expanduser(candidate))
    except (OSError, RuntimeError, ValueError):
        return None
    if not expanded.is_absolute():
        return None
    try:
        resolved = expanded.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if not resolved.is_file():
        return None
    # Deny-list: system paths and credential directories
    _DENIED_PREFIXES = ("/etc", "/proc", "/sys", "/dev", "/boot", "/var/log", "/var/lib")
    _DENIED_HOME_SUBDIRS = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config")
    try:
        resolved_str = str(resolved)
        for denied in _DENIED_PREFIXES:
            if resolved_str.startswith(denied):
                return None
        home = os.path.expanduser("~")
        if resolved_str.startswith(home):
            rel = resolved_str[len(home):].strip("/\\")
            for sub in _DENIED_HOME_SUBDIRS:
                if rel == sub or rel.startswith(sub + "/") or rel.startswith(sub + "\\"):
                    return None
    except (OSError, RuntimeError, ValueError):
        return None
    return str(resolved)


def merge_pending_message_event(
    existing: "MessageEvent | None",
    new_event: "MessageEvent",
) -> "MessageEvent":
    """Merge a pending message event into an existing one."""
    if existing is None:
        return new_event
    existing.text = (existing.text or "") + "\n" + (new_event.text or "")
    if new_event.media_urls:
        existing.media_urls = (existing.media_urls or []) + new_event.media_urls
        existing.media_types = (existing.media_types or []) + new_event.media_types
    return existing


def is_network_accessible(host: str) -> bool:
    """Return True if host would expose the server beyond loopback."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_loopback:
            return False
        if getattr(addr, "ipv4_mapped", None) and addr.ipv4_mapped.is_loopback:
            return False
        return True
    except ValueError:
        pass
    try:
        import socket
        results = socket.getaddrinfo(host, 80, socket.AF_INET)
        for _, _, _, _, (ip, _) in results:
            if not is_network_accessible(ip):
                return False
        return True
    except Exception:
        return False


def validate_media_delivery_path(path: str) -> str | None:
    """Validate and return a safe absolute file path, or None."""
    if not path:
        return None
    from pathlib import Path
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        if resolved.is_file():
            return str(resolved)
    except (OSError, RuntimeError, ValueError):
        pass
    return None


# -- Media type constants ---------------------------------------

SUPPORTED_VIDEO_TYPES: tuple[str, ...] = (
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv", ".wmv",
    ".3gp", ".ogv", ".ts", ".mts", ".m2ts", ".divx", ".asf", ".rm",
    ".rmvb", ".vob", ".mpg", ".mpeg", ".f4v", ".h264", ".h265", ".hevc",
)

SUPPORTED_DOCUMENT_TYPES: tuple[str, ...] = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
    ".csv", ".json", ".xml", ".yaml", ".yml", ".md", ".rst", ".log",
    ".py", ".js", ".ts", ".html", ".css", ".sh", ".bat", ".ps1",
    ".zip", ".tar", ".gz", ".7z", ".rar",
)

SUPPORTED_IMAGE_DOCUMENT_TYPES: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".tiff", ".tif", ".heic", ".heif", ".avif",
)

_TEXT_INJECT_EXTENSIONS: tuple[str, ...] = (
    ".txt", ".md", ".rst", ".json", ".xml", ".yaml", ".yml", ".csv",
    ".log", ".py", ".js", ".ts", ".html", ".css", ".sh", ".bat",
    ".ini", ".cfg", ".conf", ".toml",
)


# -- Proxy resolution -----------------------------------------------------------

_RESOLVE_PROXY_CACHE: dict[str, str | None] = {}


def resolve_proxy_url(platform_env_var: str = "", *, target_hosts: list[str] | None = None) -> str | None:
    """Resolve a proxy URL from environment variables.

    Checks (in order): ``{platform}_PROXY``, ``WSS_PROXY``, ``HTTPS_PROXY``,
    ``https_proxy``, ``ALL_PROXY``.  Returns ``None`` when no proxy is configured.
    """
    import os
    candidates = []
    if platform_env_var:
        candidates.append(platform_env_var)
    candidates.extend(["WSS_PROXY", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"])
    for var in candidates:
        val = os.environ.get(var)
        if val:
            val = val.strip()
            if val:
                _RESOLVE_PROXY_CACHE[var] = val
                return val
    return None


# -- Media cache helpers ---------------------------------------


def cache_image_from_bytes(data: bytes, ext: str = ".png") -> str:
    """Cache image bytes to a temp file and return the path."""
    from encre.gateway.platforms.helpers import cache_media_from_bytes
    return cache_media_from_bytes(data, ext, prefix="image")


def cache_audio_from_bytes(data: bytes, ext: str = ".ogg") -> str:
    """Cache audio bytes to a temp file and return the path."""
    from encre.gateway.platforms.helpers import cache_media_from_bytes
    return cache_media_from_bytes(data, ext, prefix="audio")


def cache_video_from_bytes(data: bytes, ext: str = ".mp4") -> str:
    """Cache video bytes to a temp file and return the path."""
    from encre.gateway.platforms.helpers import cache_media_from_bytes
    return cache_media_from_bytes(data, ext, prefix="video")


def cache_document_from_bytes(data: bytes, filename: str = "document.bin") -> str:
    """Cache document bytes to a temp file and return the path."""
    import os
    ext = os.path.splitext(filename)[1] or ".bin"
    from encre.gateway.platforms.helpers import cache_media_from_bytes
    return cache_media_from_bytes(data, ext, prefix="doc")


def cache_media_bytes(data: bytes, *, filename: str = "", mime_type: str = "", default_kind: str = "media") -> str:
    """Cache media bytes and return the path (generic dispatcher)."""
    import os
    ext = os.path.splitext(filename)[1] or ""
    from encre.gateway.platforms.helpers import cache_media_from_bytes
    return cache_media_from_bytes(data, ext, prefix=default_kind)


def resolve_channel_prompt(config: Any, platform: str, chat_id: str) -> str:
    """Resolve the per-channel ephemeral prompt for a given chat."""
    return ""


def cache_image_from_url(url: str, ext: str = ".png") -> str | None:
    """Download image from URL and cache to a temp file."""
    from encre.gateway.platforms.helpers import cache_media_from_url
    return cache_media_from_url(url, ext)


def cache_audio_from_url(url: str, ext: str = ".ogg") -> str | None:
    """Download audio from URL and cache to a temp file."""
    from encre.gateway.platforms.helpers import cache_media_from_url
    return cache_media_from_url(url, ext)


def _prefix_within_utf16_limit(text: str, limit: int) -> str:
    """Truncate text to stay within a UTF-16 code unit limit."""
    if limit <= 0:
        return ""
    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 <= limit:
        return text
    # Binary search for the truncation point
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("utf-16-le")) // 2 <= limit:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def utf16_len(text: str) -> int:
    """Count UTF-16 code units (Telegram's length unit)."""
    return len(text.encode("utf-16-le")) // 2


def validate_inbound_media_size(size_bytes: int, max_bytes: int = 128 * 1024 * 1024) -> bool:
    """Validate that a media file size is within the allowed limit."""
    return 0 < size_bytes <= max_bytes


def env_int(name: str, default: int) -> int:
    """Read an integer from an environment variable."""
    import os
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    """Read a float from an environment variable."""
    import os
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean from an environment variable."""
    import os
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "y")


# -- Message handler type -------------------------------------------------------

MessageHandler = Callable[["BasePlatformAdapter", MessageEvent], Awaitable[None] | None]


# -- BasePlatformAdapter --------------------------------------------------------


class BasePlatformAdapter(ABC):
    """Base class for all platform adapters.

    Subclasses implement platform-specific logic for:
    - Connecting and authenticating
    - Receiving messages
    - Sending messages/responses
    - Handling media

    Capability flags (class-level, override in subclasses):
        supports_code_blocks: Whether the platform renders fenced code blocks.
        supports_async_delivery: Whether the adapter can deliver notifications
            after a turn ends (persistent outbound channel).
        splits_long_messages: Whether the adapter chunks long content itself.
        max_message_length: Platform's per-message size cap (0 = no limit).
        typed_command_prefix: The command prefix users type on this platform.
    """

    # -- Capability flags (override in subclasses) --
    supports_code_blocks: bool = False
    supports_async_delivery: bool = True
    splits_long_messages: bool = False
    max_message_length: int = 0
    typed_command_prefix: str = "/"

    def __init__(self, config: PlatformConfig | None = None, platform: Platform | None = None) -> None:
        self.config = config
        self.platform = platform
        self._message_handler: Optional[MessageHandler] = None
        self._fatal_error_handler: Optional[Callable[["BasePlatformAdapter"], Awaitable[None] | None]] = None
        self._session_store: Any = None
        self._authz: Any = None
        self._pairing: Any = None
        self._running = False
        self._fatal_error_code: Optional[str] = None
        self._fatal_error_message: Optional[str] = None
        self._fatal_error_retryable: bool = True
        self._active_sessions: dict[str, asyncio.Event] = {}
        self._pending_messages: dict[str, list[MessageEvent]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        # -- Properties --

    @property
    def name(self) -> str:
        """Platform name string (e.g. 'telegram')."""
        if self.platform is not None:
            return self.platform.value
        return getattr(self, '_name', 'unknown')

    @property
    def running(self) -> bool:
        """Whether the adapter is in a running state."""
        return self._running

    @property
    def has_fatal_error(self) -> bool:
        """Whether the adapter has encountered an unrecoverable error."""
        return self._fatal_error_message is not None

    @property
    def authorization_is_upstream(self) -> bool:
        """Whether authorization is enforced upstream (e.g. by a relay connector).

        When True, the gateway skips the local 5-layer auth check for messages
        from this adapter.  Default False; relay adapters override to True.
        """
        return False

    @property
    def fatal_error_retryable(self) -> bool:
        """Whether the last fatal error is retryable (adapter can reconnect)."""
        return self._fatal_error_retryable

    @staticmethod
    def truncate_message(content: str, max_length: int) -> list[str]:
        """Split content into chunks no longer than *max_length* characters.

        Splits on sentence boundaries (``.?!``) first, then on word boundaries,
        and finally by exact length as a last resort.  Each chunk beyond the
        first gets a ``(N/M)`` page indicator appended.
        """
        if not content or max_length <= 0:
            return [content] if content else []

        if len(content) <= max_length:
            return [content]

        # ── first pass: split on sentence boundaries ──
        raw = _re.split(r"(?<=[.?!])\s+", content)
        chunks: list[str] = []
        buf = ""  # uncommitted sentences accumulating toward the limit

        for sentence in raw:
            if len(buf) + len(sentence) <= max_length:
                buf = (buf + " " + sentence).strip()
                continue
            if buf:
                chunks.append(buf)
                buf = sentence
            else:
                # Single sentence exceeds max_length → word-split it inline
                for sub in _word_split(sentence, max_length, 0):
                    chunks.append(sub)
                buf = ""

        if buf:
            chunks.append(buf)

        # ── second pass: re-chunk any oversized remainder ──
        final: list[str] = []
        page = 0
        for c in chunks:
            if len(c) <= max_length:
                final.append(c)
                page += 1
                continue
            for sub in _word_split(c, max_length, page):
                final.append(sub)
                page += 1

        # ── third pass: add page indicators ──
        total = len(final)
        if total > 1:
            final = [
                f"{c} ({i + 1}/{total})" if i > 0 else c
                for i, c in enumerate(final)
            ]

        return final

    @staticmethod
    def extract_media(content: str) -> Tuple[List[Tuple[str, bool]], str]:
        """Extract MEDIA:<path> tags and [[audio_as_voice]] directives.

        Returns:
            Tuple of (list of (path, is_voice) pairs, cleaned text).
        """
        media = []
        cleaned = content
        has_voice_tag = "[[audio_as_voice]]" in content
        cleaned = cleaned.replace("[[audio_as_voice]]", "")
        cleaned = cleaned.replace("[[as_document]]", "")

        scan_content = _mask_protected_spans(content)
        scan_content = _mask_json_string_media(scan_content)

        for match in MEDIA_TAG_CLEANUP_RE.finditer(scan_content):
            path = _normalize_media_tag_path(match.group("path"))
            if path:
                try:
                    media.append((os.path.expanduser(path), has_voice_tag))
                except (OSError, RuntimeError, ValueError):
                    continue

        seen_paths = {p for p, _ in media}
        for match in MEDIA_EXTENSIONLESS_TAG_RE.finditer(scan_content):
            path = _normalize_media_tag_path(match.group("path"))
            if not path or not _path_lacks_deliverable_extension(path):
                continue
            safe = validate_media_delivery_path(path)
            if safe and safe not in seen_paths:
                media.append((safe, has_voice_tag))
                seen_paths.add(safe)

        if media:
            masked_cleaned = _mask_protected_spans(cleaned)
            masked_cleaned = _mask_json_string_media(masked_cleaned)
            spans = [m.span() for m in MEDIA_TAG_CLEANUP_RE.finditer(masked_cleaned)]
            for match in MEDIA_EXTENSIONLESS_TAG_RE.finditer(masked_cleaned):
                path = _normalize_media_tag_path(match.group("path"))
                if not path or not _path_lacks_deliverable_extension(path):
                    continue
                if validate_media_delivery_path(path):
                    spans.append(match.span())
            if spans:
                chars = list(cleaned)
                for start, end in sorted(spans, reverse=True):
                    del chars[start:end]
                cleaned = "".join(chars)
                cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return media, cleaned

    @staticmethod
    def filter_media_delivery_paths(media_files) -> List[Tuple[str, bool]]:
        """Drop unsafe MEDIA paths and normalize accepted paths."""
        safe_media: List[Tuple[str, bool]] = []
        for media_path, is_voice in media_files or []:
            safe_path = validate_media_delivery_path(str(media_path))
            if safe_path:
                safe_media.append((safe_path, bool(is_voice)))
            else:
                logger.warning("Skipping unsafe MEDIA path: %s", _log_safe_path(str(media_path)))
        return safe_media

    @staticmethod
    def filter_local_delivery_paths(file_paths) -> List[str]:
        """Drop unsafe bare local file paths and normalize accepted paths."""
        safe_paths: List[str] = []
        for file_path in file_paths or []:
            safe_path = validate_media_delivery_path(str(file_path))
            if safe_path:
                safe_paths.append(safe_path)
            else:
                logger.warning("Skipping unsafe local file path: %s", _log_safe_path(str(file_path)))
        return safe_paths

    @staticmethod
    def extract_images(content: str) -> Tuple[List[Tuple[str, str]], str]:
        """Extract image URLs from markdown and HTML image tags.

        Returns:
            Tuple of (list of (url, alt_text) pairs, cleaned content).
        """
        images = []
        cleaned = content
        md_pattern = r'!\[([^\]]*)\]\((https?://[^\s\)]+)\)'
        for match in _re.finditer(md_pattern, content):
            alt_text = match.group(1)
            url = match.group(2)
            if any(url.lower().endswith(ext) or ext in url.lower() for ext in
                   ['.png', '.jpg', '.jpeg', '.gif', '.webp', 'fal.media', 'fal-cdn', 'replicate.delivery']):
                images.append((url, alt_text))
        html_pattern = r'<img\s+src=["\']?(https?://[^\s"\'<>]+)["\']?\s*/?>\s*(?:</img>)?'
        for match in _re.finditer(html_pattern, content):
            images.append((match.group(1), ""))
        if images:
            extracted_urls = {url for url, _ in images}
            def _remove_if_extracted(m):
                url = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
                return '' if url in extracted_urls else m.group(0)
            cleaned = _re.sub(md_pattern, _remove_if_extracted, cleaned)
            cleaned = _re.sub(html_pattern, _remove_if_extracted, cleaned)
            cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return images, cleaned

    @staticmethod
    def extract_local_files(content: str) -> Tuple[List[str], str]:
        """Detect bare local file paths for native delivery.

        Returns:
            Tuple of (list of expanded file paths, cleaned text).
        """
        ext_part = '|'.join(e.lstrip('.') for e in _MEDIA_DELIVERY_EXTS)
        path_re = _re.compile(
            r'(?<![/:\w.])(?:~/|/|[A-Za-z]:[/\\])(?:[\w.\-]+[/\\])*[\w.\-]+\.(?:' + ext_part + r')\b',
            _re.IGNORECASE,
        )
        code_spans = []
        for m in _re.finditer(r'```[^\n]*\n.*?```', content, _re.DOTALL):
            code_spans.append((m.start(), m.end()))
        for m in _re.finditer(r'`[^`\n]+`', content):
            code_spans.append((m.start(), m.end()))
        def _in_code(pos: int) -> bool:
            return any(s <= pos < e for s, e in code_spans)
        found: list = []
        for match in path_re.finditer(content):
            if _in_code(match.start()):
                continue
            raw = match.group(0)
            expanded = os.path.expanduser(raw)
            if os.path.isfile(expanded):
                found.append((raw, expanded))
        seen: set = set()
        unique: list = []
        for raw, expanded in found:
            if expanded not in seen:
                seen.add(expanded)
                unique.append((raw, expanded))
        paths = [expanded for _, expanded in unique]
        cleaned = content
        if unique:
            for raw, _exp in unique:
                cleaned = cleaned.replace(raw, '')
            cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return paths, cleaned

    # -- Lifecycle --

    @abstractmethod
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Connect to the platform and start receiving messages.

        Args:
            is_reconnect: True when re-establishing after a previous drop.

        Returns:
            True if connection was successful.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform and clean up resources."""
        ...

    # -- Messaging --

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to the specified chat.

        Args:
            chat_id: Target chat/channel/group identifier.
            content: The message text content.
            reply_to: Optional message_id to reply to.
            metadata: Optional platform-specific metadata (thread_id, etc.).

        Returns:
            SendResult with success/failure information.
        """
        ...

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get information about a chat/channel.

        Returns:
            Dict with at least: name, type, chat_id.
            Override in subclasses for richer platform-specific info.
        """
        return {"name": chat_id, "type": "dm"}

    # -- Optional methods (override in subclasses) --

    async def send_typing(self, chat_id: str) -> None:
        """Send a typing indicator.  No-op by default."""
        pass

    async def send_image(
        self, chat_id: str, image_url: str, caption: str = ""
    ) -> SendResult:
        """Send an image.  Falls back to sending URL as text."""
        text = f"{caption}\n{image_url}" if caption else image_url
        return await self.send(chat_id, text)

    async def send_document(
        self, chat_id: str, file_path: str, caption: str = ""
    ) -> SendResult:
        """Send a file/document.  Falls back to sending path as text."""
        text = f"{caption}\n[file: {file_path}]" if caption else f"[file: {file_path}]"
        return await self.send(chat_id, text)

    async def send_voice(self, chat_id: str, file_path: str) -> SendResult:
        """Send a voice message.  Falls back to send_document."""
        return await self.send_document(chat_id, file_path, caption="[voice]")

    async def edit_message(
        self, chat_id: str, message_id: str, content: str
    ) -> SendResult:
        """Edit an existing message.  Not all platforms support this.

        Default: send a new message (adapter should override for real edit).
        """
        return await self.send(chat_id, content)

    # -- Message dispatch --

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the callback that receives incoming MessageEvents.

        Set by GatewayRunner during adapter initialization.
        """
        self._message_handler = handler

    def set_fatal_error_handler(
        self, handler: Callable[["BasePlatformAdapter"], Awaitable[None] | None]
    ) -> None:
        """Register the callback invoked when a fatal error occurs.

        Set by GatewayRunner; the handler typically logs the error and
        triggers reconnection logic.
        """
        self._fatal_error_handler = handler

    def set_session_store(self, store: Any) -> None:
        """Set the session store for this adapter.

        Gives the adapter access to session routing for topic recovery,
        session key lookups, etc.
        """
        self._session_store = store

    def set_authz(self, checker: Any) -> None:
        """Set the authorization checker for this adapter."""
        self._authz = checker

    def set_pairing(self, store: Any) -> None:
        """Set the pairing store for this adapter."""
        self._pairing = store

    async def handle_message(self, event: MessageEvent) -> None:
        """Dispatch an incoming message to the registered handler.

        This is the standard inbound path called by platform-specific code
        after normalizing the raw platform message into a MessageEvent.
        The GatewayRunner's handler performs authorization, session routing,
        and agent invocation.

        Processing order:
        1. Authorization check (if authz is configured)
        2. /pair command handling (if pairing is configured)
        3. Command hooks (command:<name>)
        4. Two-level concurrency guard (per session key)
        5. Dispatch to handler
        """
        # -- Authz + pairing check --
        if self._authz is not None and not self.authorization_is_upstream:
            source = event.source
            if source and source.user_id:
                # Handle /pair command
                text = (event.text or "").strip()
                if text.startswith("/pair") and self._pairing is not None:
                    parts = text.split(maxsplit=1)
                    code = parts[1].strip() if len(parts) > 1 else ""
                    chat_id = source.chat_id
                    if not code:
                        # Mint a new code
                        result = self._authz.is_authorized(source, self.name)
                        if result.authorized:
                            new_code = self._pairing.create_code()
                            await self.send(chat_id, f"Pairing code: {new_code}\nShare this with the user to pair.")
                        else:
                            await self.send(chat_id, "⛔ Not authorized to create pairing codes.")
                        return
                    else:
                        # Redeem a code
                        ok = self._pairing.redeem(code, source.platform, source.user_id)
                        if ok:
                            await self.send(chat_id, "✅ Paired successfully!")
                        else:
                            await self.send(chat_id, "❌ Invalid or expired pairing code.")
                        return

                # Check authorization
                result = self._authz.is_authorized(source, self.name)
                if not result.authorized:
                    chat_id = source.chat_id
                    logger.info("[%s] Unauthorized message from %s/%s: %s",
                               self.name, source.platform, source.user_id, result.reason)
                    await self.send(chat_id, "⛔ Not authorized. Use /pair <code> to pair.")
                    return
            elif source:
                # Source exists but no user_id - log and allow (some platforms may not provide user_id)
                logger.warning("[%s] Message from %s has no user_id, skipping auth check",
                              self.name, source.chat_id)

        if self._message_handler is None:
            logger.error("[%s] No message handler registered, dropping message from %s",
                        self.name, event.source.chat_id if event.source else "unknown")
            # Try to inform the user
            if event.source and event.source.chat_id:
                try:
                    await self.send(
                        event.source.chat_id,
                        "⚠️ Gateway error: Message handler not registered. Please contact administrator."
                    )
                except Exception as send_err:
                    logger.warning("[%s] Failed to send handler error notice: %s", self.name, send_err)
            return

        # -- Command hook evaluation --
        text = event.text.strip() if event.text else ""
        if text.startswith("/"):
            from encre.gateway.hooks import get_hook_registry

            canonical = text.split()[0][1:].lower()  # e.g. "/go arg" -> "go"
            event_type = f"command:{canonical}"
            reg = get_hook_registry()
            ctx = {"command": canonical, "text": text, "adapter": self.name}
            if event.source:
                ctx["chat_id"] = event.source.chat_id
                ctx["user_id"] = event.source.user_id
            decisions = await reg.emit_collect(event_type, ctx)
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                decision = d.get("decision")
                if decision == "deny":
                    msg = d.get("message", "Command denied.")
                    if event.source:
                        await self.send(event.source.chat_id, msg)
                    return
                if decision == "handled":
                    return
                if decision == "rewrite":
                    new_text = d.get("text", text)
                    event = MessageEvent(
                        text=new_text,
                        message_type=event.message_type,
                        source=event.source,
                        raw_message=event.raw_message,
                        message_id=event.message_id,
                        media_urls=event.media_urls,
                        media_types=event.media_types,
                        reply_to_message_id=event.reply_to_message_id,
                        reply_to_text=event.reply_to_text,
                        reply_to_is_own_message=event.reply_to_is_own_message,
                        auto_skill=event.auto_skill,
                        channel_prompt=event.channel_prompt,
                    )
                    break
                # "allow" or unknown -> proceed

        # -- Two-level guard: queue concurrent messages for same session --
        session_key = None
        if event.source:
            from encre.gateway.session import build_session_key
            session_key = build_session_key(event.source)

        if session_key and session_key in self._active_sessions:
            # Queue the message for later processing
            self._pending_messages.setdefault(session_key, []).append(event)
            return

        # Mark session active and process
        if session_key:
            self._active_sessions[session_key] = asyncio.Event()

        try:
            result = self._message_handler(self, event)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result
        except Exception as e:
            logger.error("[%s] Message handler error: %s %s", self.name, type(e).__name__, e)
        finally:
            if session_key:
                self._active_sessions.pop(session_key, None)
                # Drain pending messages for this session
                pending = self._pending_messages.pop(session_key, [])
                for pending_event in pending:
                    self._spawn_task(
                        self.handle_message(pending_event),
                        name=f"drain-{session_key}",
                    )

    # -- Source construction --

    def build_source(
        self,
        chat_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
        chat_type: str = "dm",
        chat_name: str | None = None,
        thread_id: str | None = None,
        scope_id: str | None = None,
        user_id_alt: str | None = None,
        is_bot: bool = False,
        **kwargs,
    ) -> SessionSource:
        """Convenience method to construct a SessionSource for this adapter."""
        return SessionSource(
            platform=self.name,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=chat_name,
            user_id=user_id,
            user_name=user_name,
            thread_id=thread_id,
            scope_id=scope_id,
            user_id_alt=user_id_alt,
            is_bot=is_bot,
        )

    # -- Internal state management --

    def _mark_connected(self) -> None:
        """Mark the adapter as connected.  Clears any previous fatal error."""
        self._running = True
        self._fatal_error_code = None
        self._fatal_error_message = None
        self._fatal_error_retryable = True
        logger.info("[%s] Connected", self.name)

    def _mark_disconnected(self) -> None:
        """Mark the adapter as disconnected.

        Does NOT clear fatal error state if one exists.
        behavior) so that the error is still visible to the UI.
        """
        self._running = False
        if self.has_fatal_error:
            return
        logger.info("[%s] Disconnected", self.name)

    def _set_fatal_error(
        self, code: str, message: str, *, retryable: bool = True
    ) -> None:
        """Record an unrecoverable error and stop the adapter.

        Args:
            code: Machine-readable error code.
            message: Human-readable error description.
            retryable: Whether the adapter can attempt reconnection.
        """
        self._running = False
        self._fatal_error_code = code
        self._fatal_error_message = message
        self._fatal_error_retryable = retryable
        logger.error("[%s] Fatal error [%s]: %s", self.name, code, message)
        self._spawn_task(self._notify_fatal_error(), name=f"notify-fatal-{self.name}")

    async def _notify_fatal_error(self) -> None:
        """Notify the registered fatal error handler, if any."""
        if self._fatal_error_handler is not None:
            try:
                result = self._fatal_error_handler(self)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    await result
            except Exception as e:
                logger.error("[%s] Fatal error handler raised: %s", self.name, e)

    # -- Session interrupt support --

    def interrupt_session(self, session_key: str) -> bool:
        """Signal an active session to stop processing.

        Returns True if a session was interrupted, False if no active session.
        """
        event = self._active_sessions.get(session_key)
        if event is not None:
            event.set()
            return True
        return False

    def _register_active_session(self, session_key: str) -> asyncio.Event:
        """Register an active processing session (for interrupt support)."""
        event = asyncio.Event()
        self._active_sessions[session_key] = event
        return event

    def _unregister_active_session(self, session_key: str) -> None:
        """Unregister a completed processing session."""
        self._active_sessions.pop(session_key, None)

    # -- Background task management --

    def _spawn_task(self, coro, *, name: str | None = None) -> asyncio.Task:
        """Spawn a background task tracked by this adapter."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _cancel_background_tasks(self) -> None:
        """Cancel all background tasks (called during disconnect)."""
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()


# -- Proxy helpers -------------------------------------------


def is_host_excluded_by_no_proxy(host: str) -> bool:
    """Check if a host should bypass the proxy based on NO_PROXY env var."""
    import os
    no_proxy = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
    if not no_proxy:
        return False
    for entry in no_proxy.split(","):
        entry = entry.strip()
        if entry:
            if entry.startswith("."):
                if host.endswith(entry) or host == entry[1:]:
                    return True
            elif entry == "*":
                return True
            elif entry == host:
                return True
    return False


def proxy_kwargs_for_aiohttp(proxy_url: str | None = None) -> dict:
    """Build aiohttp-compatible proxy kwargs from a proxy URL."""
    url = proxy_url or resolve_proxy_url()
    if not url:
        return {}
    return {"proxy": url}


def safe_url_for_log(url: str) -> str:
    """Redact sensitive parts of a URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            return urlunparse(parsed._replace(netloc=f"{parsed.username}:****@{parsed.hostname}"))
        if parsed.username or parsed.hostname:
            return urlunparse(parsed._replace(netloc=f"{parsed.hostname}"))
        return url
    except Exception:
        return "<invalid url>"


def _ssrf_redirect_guard(url: str) -> str:
    """Validate a redirect URL against SSRF protection."""
    from encre.ssrf import EncreSSRFGuard
    if EncreSSRFGuard().validate_url(url):
        return url
    return ""
