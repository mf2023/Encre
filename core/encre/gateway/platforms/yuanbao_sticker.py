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
# Sticker catalogue 鈥?ported from builtin-stickers.json
# Key   : canonical name (Chinese)
# Value : {sticker_id, package_id, name, description, width, height, formats}
# ---------------------------------------------------------------------------
STICKER_MAP: dict[str, dict] = {
    "鍏叚鍏?: {
        "sticker_id": "278", "package_id": "1003", "name": "鍏叚鍏?,
        "description": "666 鍘夊 鐗?妫?缁濅簡 濂藉己 awesome",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎴戞兂寮€浜?: {
        "sticker_id": "262", "package_id": "1003", "name": "鎴戞兂寮€浜?,
        "description": "鎯冲紑 浣涚郴 閲婃€€ 椤挎偀 鐪嬫贰浜?鏃犳墍璋?,
        "width": 128, "height": 128, "formats": "png",
    },
    "瀹崇緸": {
        "sticker_id": "130", "package_id": "1003", "name": "瀹崇緸",
        "description": "鑵艰厗 涓嶅ソ鎰忔€?鑴哥孩 濞囩緸 缇炴订 鎹傝劯",
        "width": 128, "height": 128, "formats": "png",
    },
    "姣斿績": {
        "sticker_id": "252", "package_id": "1003", "name": "姣斿績",
        "description": "绗旇姱 鐖变綘 鐖卞績鎵嬪娍 love heart 鍠滄浣?,
        "width": 128, "height": 128, "formats": "png",
    },
    "濮斿眻": {
        "sticker_id": "125", "package_id": "1003", "name": "濮斿眻",
        "description": "闅捐繃 鎯冲摥 鍙€滃反宸?鐦槾 鍙椾激 琚璐?,
        "width": 128, "height": 128, "formats": "png",
    },
    "浜蹭翰": {
        "sticker_id": "146", "package_id": "1003", "name": "浜蹭翰",
        "description": "涔堜箞 mua 浜蹭竴涓?kiss 椋炲惢 鍟?,
        "width": 128, "height": 128, "formats": "png",
    },
    "閰?: {
        "sticker_id": "131", "package_id": "1003", "name": "閰?,
        "description": "甯?澧ㄩ暅 cool 楂樺喎 鏈夊瀷 swagger",
        "width": 128, "height": 128, "formats": "png",
    },
    "鐫?: {
        "sticker_id": "145", "package_id": "1003", "name": "鐫?,
        "description": "鐫¤ 鍥?zzZ 鎵撶浌 韬哄钩 浼戠湢 sleepy",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍙戝憜": {
        "sticker_id": "152", "package_id": "1003", "name": "鍙戝憜",
        "description": "鎳?鎰ｄ綇 鏀剧┖ 鍛嗘粸 鍑虹 鑴戝瓙绌虹櫧",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍙€?: {
        "sticker_id": "157", "package_id": "1003", "name": "鍙€?,
        "description": "鍗栬悓 姹傞ザ 濮斿眻宸村反 寮卞皬 鎷滄墭 鐪煎反宸?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鎽婃墜": {
        "sticker_id": "200", "package_id": "1003", "name": "鎽婃墜",
        "description": "鏃犲 娌″姙娉?鑰歌偐 闅忎究 閭ｅ拫鏁?whatever",
        "width": 128, "height": 128, "formats": "png",
    },
    "澶村ぇ": {
        "sticker_id": "213", "package_id": "1003", "name": "澶村ぇ",
        "description": "澶寸柤 鐑︽伡 閮侀椃 闅炬悶 宕╂簝 涓€鍥贡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍚?: {
        "sticker_id": "256", "package_id": "1003", "name": "鍚?,
        "description": "瀹虫€?鎯婃亹 闇囨儕 鍚撲竴璺?鎭愭€?鎬?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鍚愯": {
        "sticker_id": "203", "package_id": "1003", "name": "鍚愯",
        "description": "鏃犺 宕╂簝 琚浄 鍐呬激 涓€鍙ｈ€佽 灞?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鍝?: {
        "sticker_id": "185", "package_id": "1003", "name": "鍝?,
        "description": "鍌插▏ 鐢熸皵 涓嶆弧 鎾囧槾 涓嶇悊 璧屾皵",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍢垮樋": {
        "sticker_id": "220", "package_id": "1003", "name": "鍢垮樋",
        "description": "鍧忕瑧 鐚ョ悙绗?鍋风瑧 鎲ㄧ瑧 寰楁剰 浣犳噦鐨?,
        "width": 128, "height": 128, "formats": "png",
    },
    "澶寸": {
        "sticker_id": "218", "package_id": "1003", "name": "澶寸",
        "description": "绋嬪簭鍛?鍔犵彮 鐒﹁檻 娌″ご鍙?绉冧簡 鑲濈垎",
        "width": 128, "height": 128, "formats": "png",
    },
    "鏆椾腑瑙傚療": {
        "sticker_id": "221", "package_id": "1003", "name": "鏆椾腑瑙傚療",
        "description": "绐ュ睆 娼滄按 鍋峰伔鐪?瑙掕惤 鍥磋 灞忎綇鍛煎惛",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎴戦吀浜?: {
        "sticker_id": "224", "package_id": "1003", "name": "鎴戦吀浜?,
        "description": "瀚夊 鏌犳绮?缇℃厱 鍚冩煚妾?鐪肩孩 鎭版煚妾?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鎵揷all": {
        "sticker_id": "246", "package_id": "1003", "name": "鎵揷all",
        "description": "搴旀彺 鍔犳补 鏀寔 鍠濆僵 鍔╁▉ call",
        "width": 128, "height": 128, "formats": "png",
    },
    "搴嗙": {
        "sticker_id": "251", "package_id": "1003", "name": "搴嗙",
        "description": "绁濊春 寮€蹇?鑰?party 鑳滃埄 骞叉澂",
        "width": 128, "height": 128, "formats": "png",
    },
    "濂嬫枟": {
        "sticker_id": "151", "package_id": "1003", "name": "濂嬫枟",
        "description": "鍔姏 鍔犳补 鎷兼悘 鍐?骞插姴 鍗疯捣鏉?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鎯婅": {
        "sticker_id": "143", "package_id": "1003", "name": "鎯婅",
        "description": "闇囨儕 鍝?涓嶆暍鐩镐俊 OMG 灞呯劧 杩欎箞绂昏氨",
        "width": 128, "height": 128, "formats": "png",
    },
    "鐤戦棶": {
        "sticker_id": "144", "package_id": "1003", "name": "鐤戦棶",
        "description": "闂彿 涓嶆噦 鍟?涓轰粈涔?鍟ユ儏鍐?鎳甸€奸棶",
        "width": 128, "height": 128, "formats": "png",
    },
    "浠旂粏鍒嗘瀽": {
        "sticker_id": "248", "package_id": "1003", "name": "浠旂粏鍒嗘瀽",
        "description": "鎬濊€?鎺ㄦ暡 璁ょ湡 鐮旂┒ 鐞㈢（ 璁╂垜鎯虫兂",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎾呭槾": {
        "sticker_id": "184", "package_id": "1003", "name": "鎾呭槾",
        "description": "鍢熷槾 鍗栬悓 涓嶉珮鍏?鎾掑▏ 鍢寸繕",
        "width": 128, "height": 128, "formats": "png",
    },
    "娉": {
        "sticker_id": "199", "package_id": "1003", "name": "娉",
        "description": "澶у摥 浼ゅ績 鐮撮槻 鎰熷姩鍝?娉祦婊￠潰 鍛滃憸",
        "width": 128, "height": 128, "formats": "png",
    },
    "灏婂槦鍋囧槦": {
        "sticker_id": "276", "package_id": "1003", "name": "灏婂槦鍋囧槦",
        "description": "鐪熺殑鍋囩殑 鐪熷亣 鍙埍闂?浣犻獥鎴?鏄笉鏄?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鐣ョ暐鐣?: {
        "sticker_id": "113", "package_id": "1003", "name": "鐣ョ暐鐣?,
        "description": "璋冪毊 鍚愯垖 涓嶆湇 鐣?姘旀浣?楝艰劯",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍥?: {
        "sticker_id": "180", "package_id": "1003", "name": "鍥?,
        "description": "鎯崇潯 鍊?鎵撳搱娆?鐫佷笉寮€鐪?濂藉洶鍟?sleepy",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎶樼（": {
        "sticker_id": "181", "package_id": "1003", "name": "鎶樼（",
        "description": "闅惧彈 鐥涜嫤 鐓庣啲 铓屽煚浣忎簡 鍙椾笉浜?瑕佸懡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎶犻蓟": {
        "sticker_id": "182", "package_id": "1003", "name": "鎶犻蓟",
        "description": "涓嶅睉 鏃犺亰 娣″畾 鏃犳墍璋?閯欒 鎸栭蓟",
        "width": 128, "height": 128, "formats": "png",
    },
    "榧撴帉": {
        "sticker_id": "183", "package_id": "1003", "name": "榧撴帉",
        "description": "鎷嶆墜 鍙ソ 璧炲悓 666 鍠濆僵 鎺屽０",
        "width": 128, "height": 128, "formats": "png",
    },
    "鏂滅溂绗?: {
        "sticker_id": "204", "package_id": "1003", "name": "鏂滅溂绗?,
        "description": "婊戠ń 鍧忕瑧 doge 鎰忓懗娣遍暱 闃撮槼鎬皵 鍢垮樋鍢?,
        "width": 128, "height": 128, "formats": "png",
    },
    "杈ｇ溂鐫?: {
        "sticker_id": "216", "package_id": "1003", "name": "杈ｇ溂鐫?,
        "description": "鐪嬩笉涓嬪幓 cringe 姣佷笁瑙?澶笐浜?鐬庝簡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍝﹀摕": {
        "sticker_id": "217", "package_id": "1003", "name": "鍝﹀摕",
        "description": "鎯婅 璧峰搫 鍝囧摝 鏈夋垙 涓嶇畝鍗?鍝?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鍚冪摐": {
        "sticker_id": "222", "package_id": "1003", "name": "鍚冪摐",
        "description": "鍥磋 鐪嬫垙 鍏崷 璺汉 鐪嬬儹闂?鏉垮嚦",
        "width": 128, "height": 128, "formats": "png",
    },
    "鐙楀ご": {
        "sticker_id": "225", "package_id": "1003", "name": "鐙楀ご",
        "description": "doge 淇濆懡 寮€鐜╃瑧 婊戠ń 鍙嶈 鎳傜殑閮芥噦",
        "width": 128, "height": 128, "formats": "png",
    },
    "鏁ぜ": {
        "sticker_id": "227", "package_id": "1003", "name": "鏁ぜ",
        "description": "salute 灏婇噸 鏀跺埌 閬靛懡 鑷存暚 鎶ュ憡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鍝?: {
        "sticker_id": "231", "package_id": "1003", "name": "鍝?,
        "description": "鐭ラ亾浜?鏄庣櫧 鏁疯 鍡?杩欐牱鍟?鏀跺埌",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎷垮埌绾㈠寘": {
        "sticker_id": "236", "package_id": "1003", "name": "鎷垮埌绾㈠寘",
        "description": "绾㈠寘 璋㈣阿鑰佹澘 鍙戣储 寮€蹇?鎶㈠埌浜?娆ф皵",
        "width": 128, "height": 128, "formats": "png",
    },
    "鐗涘悥": {
        "sticker_id": "239", "package_id": "1003", "name": "鐗涘悥",
        "description": "鐗?鍘夊 寮?666 浣╂湇 澶т浆",
        "width": 128, "height": 128, "formats": "png",
    },
    "璐磋创": {
        "sticker_id": "272", "package_id": "1003", "name": "璐磋创",
        "description": "鎶辨姳 浜叉樀 韫弓 浜插瘑 闈犻潬 鎾掑▏璐?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鐖卞績": {
        "sticker_id": "138", "package_id": "1003", "name": "鐖卞績",
        "description": "蹇?love 鍠滄浣?绾㈠績 绀虹埍 涔堜箞鍝?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鏅氬畨": {
        "sticker_id": "170", "package_id": "1003", "name": "鏅氬畨",
        "description": "濂芥ⅵ 鐫′簡 night 鏃╃偣浼戞伅 瀹夊暒 moon",
        "width": 128, "height": 128, "formats": "png",
    },
    "澶槼": {
        "sticker_id": "176", "package_id": "1003", "name": "澶槼",
        "description": "鏅村ぉ 鏃╀笂濂?闃冲厜 morning 濂藉ぉ姘?鏃?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鏌犳": {
        "sticker_id": "266", "package_id": "1003", "name": "鏌犳",
        "description": "閰?瀚夊 鏌犳绮?缇℃厱 鎴戦吀 鎭版煚妾?,
        "width": 128, "height": 128, "formats": "png",
    },
    "澶у啢绉?: {
        "sticker_id": "267", "package_id": "1003", "name": "澶у啢绉?,
        "description": "鍊掗湁 鍚冧簭 鑷槻 濂藉績娌″ソ鎶?鑳岄攨 宸ュ叿浜?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鍚愪簡": {
        "sticker_id": "132", "package_id": "1003", "name": "鍚愪簡",
        "description": "鎭跺績 yue 鍙椾笉浜?瀚屽純 鎯冲悙 鐢熺悊涓嶉€?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鎬?: {
        "sticker_id": "134", "package_id": "1003", "name": "鎬?,
        "description": "鐢熸皵 鎰ゆ€?鐏ぇ 鏆磋簛 姘旂偢 鎬?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鐜懓": {
        "sticker_id": "165", "package_id": "1003", "name": "鐜懓",
        "description": "鑺?绀虹埍 琛ㄧ櫧 娴极 閫佷綘鑺?鎯呬汉鑺?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鍑嬭阿": {
        "sticker_id": "119", "package_id": "1003", "name": "鍑嬭阿",
        "description": "鑺辫阿 澶辨亱 闅捐繃 鏋悗 蹇冪 鍑変簡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鐐硅禐": {
        "sticker_id": "159", "package_id": "1003", "name": "鐐硅禐",
        "description": "璧?璁ゅ悓 濂芥 good like 澶ф媷鎸?椤?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鎻℃墜": {
        "sticker_id": "164", "package_id": "1003", "name": "鎻℃墜",
        "description": "鍚堜綔 浣犲ソ 鍟嗗姟 hello deal 鎴愪氦 鍙嬪ソ",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎶辨嫵": {
        "sticker_id": "163", "package_id": "1003", "name": "鎶辨嫵",
        "description": "璋㈣阿 澶辨暚 姹熸箹 鎵胯 鎷滄墭 鏈夌ぜ",
        "width": 128, "height": 128, "formats": "png",
    },
    "ok": {
        "sticker_id": "169", "package_id": "1003", "name": "ok",
        "description": "濂界殑 鏀跺埌 娌￠棶棰?okay 琛?鍙互 鎳備簡",
        "width": 128, "height": 128, "formats": "png",
    },
    "鎷冲ご": {
        "sticker_id": "174", "package_id": "1003", "name": "鎷冲ご",
        "description": "鍔犳补 骞?鍐?fight 鍔涢噺 鍑绘嫵 纭皵",
        "width": 128, "height": 128, "formats": "png",
    },
    "闉偖": {
        "sticker_id": "191", "package_id": "1003", "name": "闉偖",
        "description": "杩囧勾 鍠滃簡 鐖嗙 鏄ヨ妭 鍣奸噷鍟暒 绾?,
        "width": 128, "height": 128, "formats": "png",
    },
    "鐑熻姳": {
        "sticker_id": "258", "package_id": "1003", "name": "鐑熻姳",
        "description": "搴嗗吀 婕備寒 鏂板勾 鍢?缁芥斁 鑺傛棩蹇箰",
        "width": 128, "height": 128, "formats": "png",
    },
}


def get_sticker_by_name(name: str) -> Optional[dict]:
    """
    鎸夊悕绉版煡鎵捐创绾革紝鏀寔妯＄硦鍖归厤銆?

    鍖归厤浼樺厛绾э細
      1. 瀹屽叏鐩哥瓑锛坣ame锛?
      2. name 鍖呭惈鏌ヨ璇嶏紙鍓嶇紑/瀛愪覆锛?
      3. description 鍖呭惈鏌ヨ璇嶏紙鍚屼箟璇嶆悳绱級
      4. 閫氱敤妯＄硦璇勫垎锛堜笌 sticker-search 鍚岀畻娉曪級锛屽懡涓嵆杩斿洖寰楀垎鏈€楂樼殑涓€鏉?

    杩斿洖 sticker dict锛屾壘涓嶅埌杩斿洖 None銆?
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
    闅忔満杩斿洖涓€涓创绾搞€?

    鑻ユ寚瀹?category锛屽垯鍦?description 涓惈鏈夎鍏抽敭璇嶇殑璐寸焊閲岄殢鏈洪€夊彇锛?
    category 涓?None 鏃朵粠鍏ㄨ〃闅忔満銆?
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
    """鎸?sticker_id 绮剧‘鏌ユ壘璐寸焊銆?""
    if not sticker_id:
        return None
    sid = str(sticker_id).strip()
    for sticker in STICKER_MAP.values():
        if sticker.get("sticker_id") == sid:
            return sticker
    return None


# ---------------------------------------------------------------------------
# 妯＄硦鎼滅储锛堝榻?chatbot-web yuanbao-openclaw-plugin/sticker-cache.ts.searchStickers锛?
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\s\u3000\-_路.,锛屻€?锛?锛焅"鈥溾€?鈥樷€欍€?\\]+")


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
    鍦ㄥ唴缃创绾歌〃涓寜妯＄硦鍖归厤鎺掑簭杩斿洖鍓?N 鏉＄粨鏋溿€?

    璇勫垎缁煎悎 name/description 瀛楁鐨勫瓙涓层€佸瓧绗﹀閲嶉泦瑕嗙洊銆乥igram Jaccard銆佸瓙搴忓垪姣斾緥銆?
    name 鏉冮噸鐣ラ珮浜?description锛埫?.88锛夈€傜┖ query 鏃舵寜瀛楀吀椤哄簭杩斿洖鍓?N 鏉°€?
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
    鏋勯€?TIMFaceElem 娑堟伅浣撱€?

    Yuanbao 绾﹀畾锛?
      - index 鍥哄畾浼?0锛堟湇鍔＄閫氳繃 data 瀛楁璇嗗埆鍏蜂綋琛ㄦ儏锛?
      - data 涓?JSON 瀛楃涓诧紝鍖呭惈 sticker_id / package_id 绛夊瓧娈?

    Args:
        face_index: 淇濈暀瀛楁锛屾殏鏃朵笉褰卞搷 wire format锛圷uanbao 鍥哄畾 index=0锛夈€?
                    褰?face_index > 0 鏃惰涓烘棫鐗?QQ 琛ㄦ儏 ID锛岀洿鎺ユ斁鍏?index銆?
        face_type:  淇濈暀瀛楁锛堝吋瀹规棫鎺ュ彛锛屽綋鍓嶆湭浣跨敤锛夈€?
        data:       宸插簭鍒楀寲鐨?JSON 瀛楃涓诧紱涓?None 鏃朵粎浼?index銆?

    Returns:
        绗﹀悎 Yuanbao TIM 鍗忚鐨?msg_body list锛屽::

            [{"msg_type": "TIMFaceElem", "msg_content": {"index": 0, "data": "..."}}]
    """
    msg_content: dict = {"index": face_index}
    if data is not None:
        msg_content["data"] = data
    return [{"msg_type": "TIMFaceElem", "msg_content": msg_content}]


def build_sticker_msg_body(sticker: dict) -> list:
    """
    浠?STICKER_MAP 涓殑 sticker dict 鐩存帴鏋勯€?TIMFaceElem 娑堟伅浣撱€?

    杩欐槸 send_sticker() 鐨勫唴閮ㄨ緟鍔╋紝纭繚 data 瀛楁涓庡師濮?JS 鎻掍欢涓€鑷淬€?
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
