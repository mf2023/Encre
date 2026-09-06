#!/usr/bin/env python3
# ruff: noqa: E402
# Copyright 2026 Beijing Volcano Engine Technology Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

"""Detect evolution signal candidates from user messages via Hook.

Can be used as:
1. PostToolUse hook 鈥?reads JSON from stdin, auto-records high-confidence signals
2. Library 鈥?import detect_signals() for batch detection in scan-history.py
"""

import json
import os
import re
import sys

for stream in [sys.stdout, sys.stderr, sys.stdin]:
    if stream and hasattr(stream, "reconfigure") and stream.encoding != "utf-8":
        stream.reconfigure(encoding="utf-8")

from _workspace import resolve_workspace_root

DEFAULT_DB_PATH = os.path.join(resolve_workspace_root(), "evolution-data/evolution.db")

# 鈹€鈹€ Pattern  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

PATTERNS = {
    "correction": {
        "high_confidence": [
            r"涓峓瑕佹槸]杩橻鏍蜂釜涔圿",
            r"閿欎簡",
            r"涓嶅[锛屻€傦紒\s]",
            r"搴旇[鐢ㄦ槸]",
            r"姝ｇ‘鐨刐鍋氭柟]娉?,
            r"鎴戣鐨勬槸.{1,20}涓嶆槸",
            r"鍒玔鍐嶈繖]",
            r"涓嶆槸杩欎釜鎰忔€?,
            r"浣犳悶[閿欐贩]浜?,
            r"閲峓鍋氭潵]",
        ],
        "low_confidence": [
            r"鎴戝垰[鎵嶈]鐨勬槸",
            r"鍐峓璇曡]涓€[娆￠亶]",
            r"鐪嬫竻妤?,
        ],
    },
    "negative": {
        "high_confidence": [
            r"澶猍闀跨煭鎱浜?,
            r"AI[鍛虫劅]",
            r"鏈哄櫒[鍛虫劅]",
            r"濂楄瘽",
            r"鍙堟潵浜?,
            r"璺熶笂娆′竴鏍?,
            r"涓峓鏄]鎴慬鎯宠]鐨?,
            r"搴熻瘽",
            r"娌＄敤",
        ],
        "low_confidence": [
            r"^鍞?,
            r"^绠椾簡",
            r"^琛屽惂",
            r"^鍑戝悎",
            r"emmm",
            r"鏃犺",
        ],
    },
    "positive": {
        "high_confidence": [
            r"[瀹屽お]缇庝簡?",
            r"灏盵鏄繖][杩欐牱]",
            r"鍋氬緱[濂戒笉]閿?,
            r"姣斾笂娆″ソ",
            r"nice|great|perfect",
        ],
        "low_confidence": [],
    },
    "suggestion": {
        "high_confidence": [
            r"浠ュ悗[鍙兘]浠?,
            r"涓嬫",
            r"鑳戒笉鑳?,
            r"瑕佹槸鑳?{1,30}灏卞ソ浜?,
            r"杩欑鎯呭喌搴旇",
            r"寤鸿",
            r"鏈€濂絒鑳芥槸]",
            r"甯屾湜浣?,
        ],
        "low_confidence": [
            r"鏈夋病鏈夊姙娉?,
            r"鎬庝箞鎵嶈兘",
        ],
    },
    "preference": {
        "high_confidence": [
            r"鎴慬鏇存瘮杈僝鍠滄",
            r"鎴戜範鎯?,
            r"鎴慬涓€閫歖鑸琜閮戒細]",
            r"鎴戠殑椋庢牸",
            r"[鍒笉][瑕佺敤]缁?鎴?,
            r"鐢?{1,10}鏍煎紡",
            r"[绠€璇[鐭粏][涓€鐐逛簺]",
        ],
        "low_confidence": [],
    },
    "clarification": {
        "high_confidence": [
            r"鎴慬鐨勮繖]閲孾璇寸殑鎸嘳鐨勬槸",
            r"[鎵€鍏禲璋?{1,15}[灏辨寚]鐨?鏄?,
            r"浣燵鐞嗘悶]瑙ｉ敊浜?,
            r"涓嶆槸.{1,20}鑰屾槸",
            r"鍑嗙‘[鏉ュ湴]璇?,
            r"琛ュ厖涓€涓?,
            r"鎴慬鍐嶈В]閲婁竴涓?,
        ],
        "low_confidence": [],
    },
}


def detect_signals(text):
    """瀵规枃鏈仛 pattern 鍖归厤锛岃繑鍥炲€欓€変俊鍙峰垪琛ㄣ€?""
    candidates = []
    for signal_type, patterns in PATTERNS.items():
        high_matches = []
        low_matches = []
        for pat in patterns.get("high_confidence", []):
            if re.search(pat, text, re.IGNORECASE):
                high_matches.append(pat)
        for pat in patterns.get("low_confidence", []):
            if re.search(pat, text, re.IGNORECASE):
                low_matches.append(pat)
        if high_matches or low_matches:
            confidence = "high" if high_matches else "low"
            candidates.append(
                {
                    "type": signal_type,
                    "confidence": confidence,
                    "matched_patterns": high_matches + low_matches,
                    "high_count": len(high_matches),
                    "low_count": len(low_matches),
                }
            )
    return candidates


def auto_record(db_path, signal_type, raw_text, session_id, context):
    """Write a signal directly to DB. Returns signal_id or None."""
    if not os.path.exists(db_path):
        return None
    import sqlite3

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO signals (session_id, type, severity, raw_text, context)
        VALUES (?, ?, 'medium', ?, ?)
    """,
        (session_id, signal_type, raw_text[:500], context),
    )
    conn.commit()
    signal_id = cur.lastrowid
    conn.close()
    return signal_id


def handle_hook_input():
    """浠?Hook stdin 璇诲彇 JSON锛屾彁鍙栫敤鎴锋秷鎭仛妫€娴嬨€?""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
    except (json.JSONDecodeError, IOError):
        sys.exit(0)

    messages = data.get("messages", [])
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                user_text = "\n".join(texts)
            elif isinstance(content, str):
                user_text = content
            break

    if not user_text or len(user_text) < 2:
        sys.exit(0)

    candidates = detect_signals(user_text)
    if not candidates:
        sys.exit(0)

    auto_recorded = []
    needs_confirmation = []
    db_path = DEFAULT_DB_PATH
    session_id = (data.get("session_id") or "")[:12]

    for cand in candidates:
        if cand["confidence"] == "high":
            sid = auto_record(
                db_path,
                cand["type"],
                user_text,
                session_id,
                f"auto-detected by hook, patterns: {cand['matched_patterns']}",
            )
            if sid:
                auto_recorded.append({"signal_id": sid, "type": cand["type"]})
            else:
                needs_confirmation.append(cand)
        else:
            needs_confirmation.append(cand)

    context_parts = []
    if auto_recorded:
        ids_str = ", ".join(f"#{r['signal_id']}({r['type']})" for r in auto_recorded)
        context_parts.append(
            f"[Evolution] Auto-recorded {len(auto_recorded)} signal(s): {ids_str}"
        )
    if needs_confirmation:
        types_str = ", ".join(c["type"] for c in needs_confirmation)
        context_parts.append(
            f"[Evolution] Candidate signal(s) need confirmation: {types_str}. "
            f"Consider recording via signal-record.py if appropriate."
        )

    if context_parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": " | ".join(context_parts),
            }
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    handle_hook_input()
