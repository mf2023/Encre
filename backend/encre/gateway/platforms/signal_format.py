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

"""Shared Signal formatting helpers.

This module centralises the conversion from Markdown-flavoured text into the
native formatting model used by the Signal messaging protocol. Signal itself
does not render Markdown; instead it relies on the ``bodyRanges`` annotation
(described by signal-cli through the ``textStyle`` / ``textStyles`` parameters)
to express inline styling such as bold, italic, strikethrough and monospace.

Keeping this logic in a single module guarantees that every outbound Signal
message — whether sent through the live Signal adapter or through a standalone
send path — emits identical ``bodyRanges`` output and therefore looks the same
in the recipient's client.

Key collaborators:
    * ``markdown_to_signal`` is the single public entry point used by callers.
    * The Signal platform adapter consumes the returned ``(text, styles)`` pair
      to populate the signal-cli request payload (``message`` plus
      ``textStyles``).
"""

import re


def markdown_to_signal(text: str) -> tuple[str, list[str]]:
    """Convert Markdown source text into plain text plus Signal style strings.

    Signal does not render Markdown in its clients. Instead it exposes inline
    styling through ``bodyRanges`` (exposed by signal-cli via the ``textStyle``
    / ``textStyles`` parameters). Each style entry uses the textual format
    ``start:length:STYLE`` where positions and lengths are measured in UTF-16
    code units — that is the unit the Signal wire protocol uses for string
    offsets, so naive Python ``len`` (which counts code points) would be wrong
    for any text containing surrogate pairs or astral-plane characters.

    The conversion performs the following logical steps:
        1. Normalise whitespace and bullet markers so the visible text reads
           naturally in a Markdown-incapable client.
        2. Detect fenced code blocks and mark them as MONOSPACE ranges.
        3. Strip Markdown heading markers and treat the heading text as BOLD.
        4. Detect inline emphasis spans (bold, italic, strikethrough, inline
           code) while preventing overlapping ranges from double-covering the
           same characters.
        5. Strip the Markdown syntax characters from the text and recompute the
           offset shifts that removal introduces.
        6. Translate every retained range into the UTF-16 ``start:length:STYLE``
           string that signal-cli expects.

    Supported styles: BOLD, ITALIC, STRIKETHROUGH, MONOSPACE.

    Args:
        text: The Markdown-flavoured source string to be converted.

    Returns:
        A tuple of ``(plain_text, style_strings)`` where ``plain_text`` is the
        Markdown-stripped message body and ``style_strings`` is the list of
        ``start:length:STYLE`` entries describing how to style it in Signal.
    """

    def _utf16_len(s: str) -> int:
        """Return the length of *s* measured in UTF-16 code units.

        The Signal protocol measures ``bodyRanges`` offsets in UTF-16 units,
        so we encode as UTF-16 (little-endian) and divide the byte length by two
        rather than counting Unicode code points directly.

        Args:
            s: The string whose UTF-16 length should be computed.

        Returns:
            The number of UTF-16 code units occupied by *s*.
        """
        return len(s.encode("utf-16-le")) // 2

    def _normalize_bullet_markers(source: str) -> str:
        """Replace Markdown bullet markers with plain Unicode bullets.

        Signal does not render Markdown list syntax, so ``- item`` and
        ``* item`` would otherwise arrive as literal Markdown markers. We
        substitute a real ``•`` bullet so the list reads naturally. Fenced code
        blocks are preserved byte-for-byte: a list-looking line inside a code
        fence is code, not prose, and must not be re-bulleted.

        Args:
            source: The text in which bullet markers should be normalised.

        Returns:
            A copy of *source* with top-level bullet markers replaced by
            Unicode bullets, leaving code fences untouched.
        """
        # Split on fenced code blocks; odd-indexed parts are the code fences.
        parts = re.split(r"(```.*?```)", source, flags=re.DOTALL)
        for idx, part in enumerate(parts):
            # Leave code fences (odd indices) completely untouched.
            if idx % 2 == 1:
                continue
            # Replace up to three leading spaces/tabs plus -, * or + with a bullet.
            parts[idx] = re.sub(r"(?m)^([ \t]{0,3})[-*+]\s+", r"\1• ", part)
        return "".join(parts)

    # Collapse runs of three or more blank lines down to a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove leading/trailing whitespace so offsets start at the body origin.
    text = text.strip()
    # Normalise bullets before any further parsing so code fences are protected.
    text = _normalize_bullet_markers(text)

    # Accumulate detected style ranges as (start, length, style) tuples.
    styles: list[tuple[int, int, str]] = []

    # --- Fenced code blocks become a single MONOSPACE range. ---
    code_block = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
    while match := code_block.search(text):
        # Keep only the inner content; discard the surrounding fence markers.
        inner = match.group(1).rstrip("\n")
        start = match.start()
        text = text[: match.start()] + inner + text[match.end() :]
        styles.append((start, len(inner), "MONOSPACE"))

    # --- Headings: drop the '#' markers, keep the text styled as BOLD. ---
    heading = re.compile(r"^#{1,6}\s+", re.MULTILINE)
    new_text = ""
    last_end = 0
    for match in heading.finditer(text):
        # Copy the text preceding this heading verbatim.
        new_text += text[last_end : match.start()]
        last_end = match.end()
        # Find the end of the heading line to isolate the heading text.
        eol = text.find("\n", match.end())
        if eol == -1:
            eol = len(text)
        heading_text = text[match.end() : eol]
        start = len(new_text)
        new_text += heading_text
        styles.append((start, len(heading_text), "BOLD"))
        last_end = eol
    new_text += text[last_end:]
    text = new_text

    # Inline emphasis patterns, ordered so that the more specific/delimited
    # forms (bold, strikethrough, inline code) are tried before the weaker
    # single-* / single-_ italic patterns.
    patterns = [
        (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), "BOLD"),
        (re.compile(r"__(.+?)__", re.DOTALL), "BOLD"),
        (re.compile(r"~~(.+?)~~", re.DOTALL), "STRIKETHROUGH"),
        (re.compile(r"`(.+?)`"), "MONOSPACE"),
        (re.compile(r"(?<!\*)\*(?!\*| )(.+?)(?<!\*)\*(?!\*)"), "ITALIC"),
        (re.compile(r"(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)"), "ITALIC"),
    ]

    # Collect every inline match, rejecting any range that overlaps a range
    # already claimed so two patterns cannot both style the same characters.
    all_matches: list[tuple[int, int, int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for pattern, style in patterns:
        for match in pattern.finditer(text):
            ms, me = match.start(), match.end()
            # Skip this match if its outer span collides with a prior match.
            if not any(ms < oe and me > os for os, oe in occupied):
                # Store the outer span plus the inner (content-only) span.
                all_matches.append((ms, me, match.start(1), match.end(1), style))
                occupied.append((ms, me))
    all_matches.sort()

    # Build the list of character spans to delete: the leading/trailing Markdown
    # syntax delimiters around each inner capture group.
    removals: list[tuple[int, int]] = []
    for ms, me, g1s, g1e, _ in all_matches:
        if g1s > ms:
            removals.append((ms, g1s - ms))
        if me > g1e:
            removals.append((g1e, me - g1e))
    removals.sort()

    def _adjust(pos: int) -> int:
        """Shift an offset by the cumulative length of deletions before it.

        As Markdown delimiters are stripped from the text, every later offset
        moves left. This helper computes the new position of *pos* after all
        earlier removals are applied.

        Args:
            pos: The original offset within the pre-stripping text.

        Returns:
            The equivalent offset within the delimiter-stripped text.
        """
        shift = 0
        for remove_pos, remove_len in removals:
            # Only removals strictly before this position affect the shift.
            if remove_pos < pos:
                shift += min(remove_len, pos - remove_pos)
            else:
                break
        return pos - shift

    # Re-base the code-block / heading ranges detected earlier onto the
    # delimiter-stripped text so they keep pointing at the right characters.
    adjusted_prior: list[tuple[int, int, str]] = []
    for start, length, style in styles:
        new_start = _adjust(start)
        new_end = _adjust(start + length)
        if new_end > new_start:
            adjusted_prior.append((new_start, new_end - new_start, style))

    # Rebuild the text without delimiters while recording the inline style
    # ranges at their post-stripping positions.
    result = ""
    last_end = 0
    inline_styles: list[tuple[int, int, str]] = []
    for ms, me, g1s, g1e, style in all_matches:
        result += text[last_end:ms]
        pos = len(result)
        inner = text[g1s:g1e]
        result += inner
        inline_styles.append((pos, len(inner), style))
        last_end = me
    result += text[last_end:]
    text = result

    # Combine the pre-stripping ranges with the inline ranges, then translate
    # each one into the UTF-16 ``start:length:STYLE`` string for signal-cli.
    styles = adjusted_prior + inline_styles

    style_strings: list[str] = []
    for cp_start, cp_len, style_type in sorted(styles):
        # Guard against out-of-bounds ranges slipping through earlier math.
        if cp_start < 0 or cp_start + cp_len > len(text):
            continue
        # Convert code-point offsets to UTF-16 code-unit offsets for the wire.
        u16_start = _utf16_len(text[:cp_start])
        u16_len = _utf16_len(text[cp_start : cp_start + cp_len])
        style_strings.append(f"{u16_start}:{u16_len}:{style_type}")

    return text, style_strings
