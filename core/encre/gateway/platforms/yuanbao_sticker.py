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

"""
Yuanbao sticker (TIMFaceElem) support.

Ported from yuanbao-openclaw-plugin/src/sticker/.

TIMFaceElem wire format:
    {
        "msg_type": "TIMFaceElem",
        "msg_content": {
            "index": 0,          # always 0 per Yuanbao convention
            "data": "<json>",    # serialised sticker metadata
        }
    }

The `data` field carries a JSON string with the sticker's metadata so the
receiver can look up the correct asset in the emoji pack.
"""

import json
import random
import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Sticker catalogue ?ported from builtin-stickers.json
# Key   : canonical name (Chinese)
# Value : {sticker_id, package_id, name, description, width, height, formats}
# ---------------------------------------------------------------------------
STICKER_MAP: dict[str, dict] = {
    "充?": {
        "sticker_id": "278", "package_id": "1003", "name": "充?",
        "description": "666 厉 ??绝了 好强 awesome",
        "width": 128, "height": 128, "formats": "png",
    },
    "我想?": {
        "sticker_id": "262", "package_id": "1003", "name": "我想?",
        "description": "想开 佛系 释 顿悟 看淡?无所?",
        "width": 128, "height": 128, "formats": "png",
    },
    "害羞": {
        "sticker_id": "130", "package_id": "1003", "name": "害羞",
        "description": "腼腆 不好意?脸红 娇羞 羞涩 捂脸",
        "width": 128, "height": 128, "formats": "png",
    },
    "比心": {
        "sticker_id": "252", "package_id": "1003", "name": "比心",
        "description": "笔芯 爱你 爱心手势 love heart 喜?",
        "width": 128, "height": 128, "formats": "png",
    },
    "委屈": {
        "sticker_id": "125", "package_id": "1003", "name": "委屈",
        "description": "难过 想哭 叜巴?瘘 受伤 ?",
        "width": 128, "height": 128, "formats": "png",
    },
    "亲亲": {
        "sticker_id": "146", "package_id": "1003", "name": "亲亲",
        "description": "么么 mua 亲一?kiss 飞吻 ?",
        "width": 128, "height": 128, "formats": "png",
    },
    "131": {
        "sticker_id": "131", "package_id": "1003", "name": "131",
        "description": "?墨镜 cool 高冷 有型 swagger",
        "width": 128, "height": 128, "formats": "png",
    },
    "145": {
        "sticker_id": "145", "package_id": "1003", "name": "145",
        "description": "睡 ?zzZ 打盹 躺平 休眠 sleepy",
        "width": 128, "height": 128, "formats": "png",
    },
    "发呆": {
        "sticker_id": "152", "package_id": "1003", "name": "发呆",
        "description": "?愣住 放空 呆滞 出 脑子空白",
        "width": 128, "height": 128, "formats": "png",
    },
    "157": {
        "sticker_id": "157", "package_id": "1003", "name": "157",
        "description": "卖萌 求饶 委屈巴巴 弱小 拜托 眼巴?",
        "width": 128, "height": 128, "formats": "png",
    },
    "摊手": {
        "sticker_id": "200", "package_id": "1003", "name": "摊手",
        "description": "无 没办?耸肩 随便 那咋?whatever",
        "width": 128, "height": 128, "formats": "png",
    },
    "头大": {
        "sticker_id": "213", "package_id": "1003", "name": "头大",
        "description": "头疼 烦恼 郁闷 难搞 崩溃 囹",
        "width": 128, "height": 128, "formats": "png",
    },
    "256": {
        "sticker_id": "256", "package_id": "1003", "name": "256",
        "description": "害?惊恐 震惊 吓一?恐??",
        "width": 128, "height": 128, "formats": "png",
    },
    "吐": {
        "sticker_id": "203", "package_id": "1003", "name": "吐",
        "description": "无 崩溃 袛 内伤 口 ?",
        "width": 128, "height": 128, "formats": "png",
    },
    "185": {
        "sticker_id": "185", "package_id": "1003", "name": "185",
        "description": "傲娇 生气 不满 撇嘴 不理 赌气",
        "width": 128, "height": 128, "formats": "png",
    },
    "嘿嘿": {
        "sticker_id": "220", "package_id": "1003", "name": "嘿嘿",
        "description": "坏笑 猥琐?偷笑 憨笑 得意 你懂?",
        "width": 128, "height": 128, "formats": "png",
    },
    "头": {
        "sticker_id": "218", "package_id": "1003", "name": "头",
        "description": "程序?加班 焦虑 没头?秃了 肝爆",
        "width": 128, "height": 128, "formats": "png",
    },
    "暗中观察": {
        "sticker_id": "221", "package_id": "1003", "name": "暗中观察",
        "description": "窥屏 潜水 偷偷?角落 围 屏住呼吸",
        "width": 128, "height": 128, "formats": "png",
    },
    "我酸?": {
        "sticker_id": "224", "package_id": "1003", "name": "我酸?",
        "description": "嫉 柠?羡慕 吃柠?眼红 恰柠?",
        "width": 128, "height": 128, "formats": "png",
    },
    "打call": {
        "sticker_id": "246", "package_id": "1003", "name": "打call",
        "description": "应援 加油 攌 喝彩 助威 call",
        "width": 128, "height": 128, "formats": "png",
    },
    "庆": {
        "sticker_id": "251", "package_id": "1003", "name": "庆",
        "description": "祝贺 ??party 胜利 干杯",
        "width": 128, "height": 128, "formats": "png",
    },
    "奋斗": {
        "sticker_id": "151", "package_id": "1003", "name": "奋斗",
        "description": "劊 加油 拼搏 ?干劲 卷起?",
        "width": 128, "height": 128, "formats": "png",
    },
    "惊": {
        "sticker_id": "143", "package_id": "1003", "name": "惊",
        "description": "震惊 ?不敢相信 OMG 居然 这么离谱",
        "width": 128, "height": 128, "formats": "png",
    },
    "疑问": {
        "sticker_id": "144", "package_id": "1003", "name": "疑问",
        "description": "闏 不懂 ?为什?啥情?懵问",
        "width": 128, "height": 128, "formats": "png",
    },
    "仔细分析": {
        "sticker_id": "248", "package_id": "1003", "name": "仔细分析",
        "description": "思?推敲 认真 研究 琢磨 让我想想",
        "width": 128, "height": 128, "formats": "png",
    },
    "撅嘴": {
        "sticker_id": "184", "package_id": "1003", "name": "撅嘴",
        "description": "嘟嘴 卖萌 不高?撒娇 嘴翘",
        "width": 128, "height": 128, "formats": "png",
    },
    "199": {
        "sticker_id": "199", "package_id": "1003", "name": "199",
        "description": "大哭 伤心 破防 感动?泵满面 呜呜",
        "width": 128, "height": 128, "formats": "png",
    },
    "尊嘟假嘟": {
        "sticker_id": "276", "package_id": "1003", "name": "尊嘟假嘟",
        "description": "真的假的 真假 又?你骗?昸?",
        "width": 128, "height": 128, "formats": "png",
    },
    "略略?": {
        "sticker_id": "113", "package_id": "1003", "name": "略略?",
        "description": "调皮 吐舌 不服 ?气?鬼脸",
        "width": 128, "height": 128, "formats": "png",
    },
    "180": {
        "sticker_id": "180", "package_id": "1003", "name": "180",
        "description": "想睡 ?打哈?睁不?好困?sleepy",
        "width": 128, "height": 128, "formats": "png",
    },
    "折磨": {
        "sticker_id": "181", "package_id": "1003", "name": "折磨",
        "description": "难受 痛苦 煎熬 蚌埠住了 受不?要命",
        "width": 128, "height": 128, "formats": "png",
    },
    "抠鼻": {
        "sticker_id": "182", "package_id": "1003", "name": "抠鼻",
        "description": "不屑 无聊 淡定 无所?鄙 挖鼻",
        "width": 128, "height": 128, "formats": "png",
    },
    "鼓掌": {
        "sticker_id": "183", "package_id": "1003", "name": "鼓掌",
        "description": "拍手 句 赞同 666 喝彩 掌声",
        "width": 128, "height": 128, "formats": "png",
    },
    "斜眼?": {
        "sticker_id": "204", "package_id": "1003", "name": "斜眼?",
        "description": "滑稽 坏笑 doge 意味深长 阴阳怰 嘿嘿?",
        "width": 128, "height": 128, "formats": "png",
    },
    "辣眼?": {
        "sticker_id": "216", "package_id": "1003", "name": "辣眼?",
        "description": "看不下去 cringe 毁三?夸?瞎了",
        "width": 128, "height": 128, "formats": "png",
    },
    "哦哟": {
        "sticker_id": "217", "package_id": "1003", "name": "哦哟",
        "description": "惊 起哄 哇哦 有戏 不简??",
        "width": 128, "height": 128, "formats": "png",
    },
    "吃瓜": {
        "sticker_id": "222", "package_id": "1003", "name": "吃瓜",
        "description": "围 看戏 免 跺 看热?板凳",
        "width": 128, "height": 128, "formats": "png",
    },
    "狗头": {
        "sticker_id": "225", "package_id": "1003", "name": "狗头",
        "description": "doge 保命 玩笑 滑稽 反 懂的都懂",
        "width": 128, "height": 128, "formats": "png",
    },
    "敤": {
        "sticker_id": "227", "package_id": "1003", "name": "敤",
        "description": "salute 尊重 收到 遵命 致敬 报告",
        "width": 128, "height": 128, "formats": "png",
    },
    "231": {
        "sticker_id": "231", "package_id": "1003", "name": "231",
        "description": "知道?明白 敷 ?这样?收到",
        "width": 128, "height": 128, "formats": "png",
    },
    "拿到红包": {
        "sticker_id": "236", "package_id": "1003", "name": "拿到红包",
        "description": "红包 谢谢老板 发财 ?抢到?欧气",
        "width": 128, "height": 128, "formats": "png",
    },
    "牛吖": {
        "sticker_id": "239", "package_id": "1003", "name": "牛吖",
        "description": "?厉 ?666 佩服 大佬",
        "width": 128, "height": 128, "formats": "png",
    },
    "贴贴": {
        "sticker_id": "272", "package_id": "1003", "name": "贴贴",
        "description": "抱抱 亲昵 蹹 亲密 靠靠 撒娇?",
        "width": 128, "height": 128, "formats": "png",
    },
    "爱心": {
        "sticker_id": "138", "package_id": "1003", "name": "爱心",
        "description": "?love 喜?红心 示爱 么么?",
        "width": 128, "height": 128, "formats": "png",
    },
    "晚安": {
        "sticker_id": "170", "package_id": "1003", "name": "晚安",
        "description": "好梦 睡了 night 早点休息 安啦 moon",
        "width": 128, "height": 128, "formats": "png",
    },
    "夘": {
        "sticker_id": "176", "package_id": "1003", "name": "夘",
        "description": "晴天 早上?阳光 morning 好天??",
        "width": 128, "height": 128, "formats": "png",
    },
    "柠": {
        "sticker_id": "266", "package_id": "1003", "name": "柠",
        "description": "?嫉 柠?羡慕 我酸 恰柠?",
        "width": 128, "height": 128, "formats": "png",
    },
    "大冤?": {
        "sticker_id": "267", "package_id": "1003", "name": "大冤?",
        "description": "倒霉 吃亏 臘 好心没好?背锅 工具?",
        "width": 128, "height": 128, "formats": "png",
    },
    "吐了": {
        "sticker_id": "132", "package_id": "1003", "name": "吐了",
        "description": "恶心 yue 受不?嫌弃 想吐 生理不?",
        "width": 128, "height": 128, "formats": "png",
    },
    "134": {
        "sticker_id": "134", "package_id": "1003", "name": "134",
        "description": "生气 愤?灤 暴躁 气炸 ?",
        "width": 128, "height": 128, "formats": "png",
    },
    "玑": {
        "sticker_id": "165", "package_id": "1003", "name": "玑",
        "description": "?示爱 表白 浼 送你?情人?",
        "width": 128, "height": 128, "formats": "png",
    },
    "凋谢": {
        "sticker_id": "119", "package_id": "1003", "name": "凋谢",
        "description": "花谢 失恋 难过 析 心 凉了",
        "width": 128, "height": 128, "formats": "png",
    },
    "点赞": {
        "sticker_id": "159", "package_id": "1003", "name": "点赞",
        "description": "?认同 好 good like 大拇??",
        "width": 128, "height": 128, "formats": "png",
    },
    "握手": {
        "sticker_id": "164", "package_id": "1003", "name": "握手",
        "description": "合作 你好 商务 hello deal 成交 友好",
        "width": 128, "height": 128, "formats": "png",
    },
    "抱拳": {
        "sticker_id": "163", "package_id": "1003", "name": "抱拳",
        "description": "谢谢 失敬 江湖 承 拜托 有礼",
        "width": 128, "height": 128, "formats": "png",
    },
    "ok": {
        "sticker_id": "169", "package_id": "1003", "name": "ok",
        "description": "好的 收到 没问?okay ?叻 懂了",
        "width": 128, "height": 128, "formats": "png",
    },
    "拳头": {
        "sticker_id": "174", "package_id": "1003", "name": "拳头",
        "description": "加油 ??fight 力量 击拳 硰",
        "width": 128, "height": 128, "formats": "png",
    },
    "鞂": {
        "sticker_id": "191", "package_id": "1003", "name": "鞂",
        "description": "过年 喜庆 爆 春节 噼里啕 ?",
        "width": 128, "height": 128, "formats": "png",
    },
    "烟花": {
        "sticker_id": "258", "package_id": "1003", "name": "烟花",
        "description": "庆典 漂亮 新年 ?绽放 节日忹",
        "width": 128, "height": 128, "formats": "png",
    },
}

def get_sticker_by_name(name: str) -> Optional[dict]:
    """
    按名称查找贴纸，攌模糊匹配?

    匹配优先级：
      1. 完全相等（name?
      2. name 包含查词（前缀/子串?
      3. description 包含查词（同义词搜紼
      4. 通用模糊评分（与 sticker-search 同算法），命不返回得分高的?

    返回 sticker dict，找不到返回 None?
    """
    if not name:
        return None

    query = name.strip()

    if query in STICKER_MAP:
        return STICKER_MAP[query]

    for key, sticker in STICKER_MAP.items():
        if query in key or key in query:
            return sticker

    for sticker in STICKER_MAP.values():
        desc = sticker.get("description", "")
        if query in desc:
            return sticker

    matches = search_stickers(query, limit=1)
    return matches[0] if matches else None


def get_random_sticker(category: str = None) -> dict:
    """
    随机返回临纸?

    若指?category，则?description 丐有关键词的贴纸里随机取?
    category ?None 时从全表随机?
    """
    if category:
        candidates = [
            s for s in STICKER_MAP.values()
            if category in s.get("description", "") or category in s.get("name", "")
        ]
        if candidates:
            return random.choice(candidates)
    return random.choice(list(STICKER_MAP.values()))


def get_sticker_by_id(sticker_id: str) -> Optional[dict]:
    """按 sticker_id 精确查找贴纸。"""
    if not sticker_id:
        return None
    sid = str(sticker_id).strip()
    for sticker in STICKER_MAP.values():
        if sticker.get("sticker_id") == sid:
            return sticker
    return None


# ---------------------------------------------------------------------------
# 模糊搜索（?chatbot-web yuanbao-openclaw-plugin/sticker-cache.ts.searchStickers?
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\s\u3000\-_·.,，??？\"“?‘?\\]+")


def _normalize_text(raw: str) -> str:
    return unicodedata.normalize("NFKC", str(raw or "")).strip().lower()


def _compact_text(raw: str) -> str:
    return _PUNCT_RE.sub("", _normalize_text(raw))


def _multiset_char_hit_ratio(needle: str, haystack: str) -> float:
    if not needle:
        return 0.0
    bag: dict[str, int] = {}
    for ch in haystack:
        bag[ch] = bag.get(ch, 0) + 1
    hits = 0
    for ch in needle:
        n = bag.get(ch, 0)
        if n > 0:
            hits += 1
            bag[ch] = n - 1
    return hits / len(needle)


def _bigram_jaccard(a: str, b: str) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    A = {a[i:i + 2] for i in range(len(a) - 1)}
    B = {b[i:i + 2] for i in range(len(b) - 1)}
    inter = len(A & B)
    union = len(A) + len(B) - inter
    return inter / union if union else 0.0


def _longest_subsequence_ratio(needle: str, haystack: str) -> float:
    if not needle:
        return 0.0
    j = 0
    for ch in haystack:
        if j >= len(needle):
            break
        if ch == needle[j]:
            j += 1
    return j / len(needle)


def _score_field(haystack: str, query: str) -> float:
    hay = _normalize_text(haystack)
    q = _normalize_text(query)
    if not hay or not q:
        return 0.0
    hay_c = _compact_text(haystack)
    q_c = _compact_text(query)
    best = 0.0
    if hay == q:
        best = max(best, 100.0)
    if q in hay:
        best = max(best, 92 + min(6, len(q)))
    if len(q) >= 2 and hay.startswith(q):
        best = max(best, 88.0)
    if q_c and q_c in hay_c:
        best = max(best, 86.0)
    best = max(best, _multiset_char_hit_ratio(q_c, hay_c) * 62)
    best = max(best, _bigram_jaccard(q_c, hay_c) * 58)
    best = max(best, _longest_subsequence_ratio(q_c, hay_c) * 52)
    if len(q) == 1 and q in hay:
        best = max(best, 68.0)
    return best


def search_stickers(query: str, limit: int = 10) -> list[dict]:
    """
    在内罴纸表丌模糊匹配排序返回?N 条结果?

    评分综合 name/description 字的子串字符重集覆盖、bigram Jaccard、子序列比例?
    name 权重略高?description（?.88）空 query 时按字典顺序返回?N 条?
    """
    safe_limit = max(1, min(500, int(limit) if limit else 10))
    if not query or not _normalize_text(query):
        return list(STICKER_MAP.values())[:safe_limit]

    scored: list[tuple[float, dict]] = []
    for sticker in STICKER_MAP.values():
        name_s = _score_field(sticker.get("name", ""), query)
        desc_s = _score_field(sticker.get("description", ""), query) * 0.88
        sid = str(sticker.get("sticker_id", "")).strip()
        q_norm = _normalize_text(query)
        id_s = 0.0
        if sid and q_norm:
            sid_norm = _normalize_text(sid)
            if sid_norm == q_norm:
                id_s = 100.0
            elif q_norm in sid_norm:
                id_s = 84.0
        scored.append((max(name_s, desc_s, id_s), sticker))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[0][0] if scored else 0
    if top <= 0:
        return [s for _, s in scored[:safe_limit]]

    if top >= 22:
        floor = 18.0
    elif top >= 12:
        floor = max(10.0, top * 0.5)
    else:
        floor = max(6.0, top * 0.35)

    filtered = [pair for pair in scored if pair[0] >= floor]
    out = filtered if filtered else scored
    return [s for _, s in out[:safe_limit]]


def build_face_msg_body(
    face_index: int,
    face_type: int = 1,
    data: Optional[str] = None,
) -> list:
    """
    构?TIMFaceElem 消息体?

    Yuanbao 约定?
      - index 固定?0（服务通过 data 字识别具体表情?
      - data ?JSON 字串，包含 sticker_id / package_id 等字?

    Args:
        face_index: 保留字，暂时不影响 wire format（Yuanbao 固定 index=0）?
                    ?face_index > 0 时为旧?QQ 表情 ID，直接放?index?
        face_type:  保留字（兼容旧接口，当前未使用）?
        data:       已序列化?JSON 字串；?None 时仅?index?

    Returns:
        符合 Yuanbao TIM 协?msg_body list，::

            [{"msg_type": "TIMFaceElem", "msg_content": {"index": 0, "data": "..."}}]
    """
    msg_content: dict = {"index": face_index}
    if data is not None:
        msg_content["data"] = data
    return [{"msg_type": "TIMFaceElem", "msg_content": msg_content}]


def build_sticker_msg_body(sticker: dict) -> list:
    """
    ?STICKER_MAP 业 sticker dict 直接构?TIMFaceElem 消息体?

    这是 send_sticker() 的内部辅助，硿 data 字与原?JS 插件致?
    """
    data_payload = json.dumps(
        {
            "sticker_id": sticker["sticker_id"],
            "package_id": sticker["package_id"],
            "width": sticker.get("width", 128),
            "height": sticker.get("height", 128),
            "formats": sticker.get("formats", "png"),
            "name": sticker["name"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return build_face_msg_body(face_index=0, data=data_payload)
