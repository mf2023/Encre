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
yuanbao_media.py 鈥?鍏冨疂骞冲彴濯掍綋澶勭悊妯″潡

鎻愪緵 COS 涓婁紶銆佹枃浠朵笅杞姐€乀IM 濯掍綋娑堟伅鏋勫缓绛夊姛鑳姐€?
绉绘鑷?TypeScript 鐗?media.ts锛坹uanbao-openclaw-plugin锛夛紝
浣跨敤 httpx 鏇夸唬 cos-nodejs-sdk-v5锛岄伩鍏嶅紩鍏ラ澶?SDK 渚濊禆銆?

COS 涓婁紶娴佺▼锛?
  1. 璋冪敤 genUploadInfo 鑾峰彇涓存椂鍑瘉锛坱mpSecretId/tmpSecretKey/sessionToken锛?
  2. 鐢ㄤ复鏃跺嚟璇侀€氳繃 HMAC-SHA1 绛惧悕鏋勫缓 Authorization 澶?
  3. HTTP PUT 涓婁紶鍒?COS

TIM 娑堟伅浣撴瀯寤猴細
  - buildImageMsgBody() 鈫?TIMImageElem
  - buildFileMsgBody()  鈫?TIMFileElem
"""

import hashlib
import hmac
import logging
import os
import secrets
import struct
import time
import urllib.parse
from typing import Optional, Any

import httpx

logger = logging.getLogger(__name__)

# ============ 甯搁噺 ============

UPLOAD_INFO_PATH = "/api/resource/genUploadInfo"
DEFAULT_API_DOMAIN = "yuanbao.tencent.com"
DEFAULT_MAX_SIZE_MB = 50

# COS 鍔犻€熷煙鍚嶅悗缂€锛堜紭鍏堜娇鐢ㄥ叏鐞冨姞閫燂級
COS_USE_ACCELERATE = True

# ============ 绫诲瀷鏄犲皠 ============

# MIME 鈫?image_format 鏁板瓧锛圱IM 鍗忚瀛楁锛?
_MIME_TO_IMAGE_FORMAT: dict[str, int] = {
    "image/jpeg": 1,
    "image/jpg": 1,
    "image/gif": 2,
    "image/png": 3,
    "image/bmp": 4,
    "image/webp": 255,
    "image/heic": 255,
    "image/tiff": 255,
}

# 鏂囦欢鎵╁睍鍚?鈫?MIME
_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".tiff": "image/tiff",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".webm": "video/webm",
}


# ============ 宸ュ叿鍑芥暟 ============

def guess_mime_type(filename: str) -> str:
    """鏍规嵁鏂囦欢鎵╁睍鍚嶇寽娴?MIME 绫诲瀷銆?""
    ext = os.path.splitext(filename)[-1].lower()
    return _EXT_TO_MIME.get(ext, "application/octet-stream")


def is_image(filename: str, mime_type: str = "") -> bool:
    """鍒ゆ柇鏄惁涓哄浘鐗囩被鍨嬨€?""
    if mime_type.startswith("image/"):
        return True
    ext = os.path.splitext(filename)[-1].lower()
    return ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tiff", ".ico"}


def get_image_format(mime_type: str) -> int:
    """鑾峰彇 TIM 鍥剧墖鏍煎紡缂栧彿銆?""
    return _MIME_TO_IMAGE_FORMAT.get(mime_type.lower(), 255)


def md5_hex(data: bytes) -> str:
    """璁＄畻 MD5 鍗佸叚杩涘埗鎽樿銆?""
    return hashlib.md5(data).hexdigest()


def generate_file_id() -> str:
    """鐢熸垚闅忔満鏂囦欢 ID锛?2 浣?hex锛夈€?""
    return secrets.token_hex(16)



# ============ 鍥剧墖灏哄瑙ｆ瀽锛堢函 Python锛屾棤闇€ Pillow锛?============

def parse_image_size(data: bytes) -> Optional[dict[str, int]]:
    """
    瑙ｆ瀽鍥剧墖瀹介珮锛堟敮鎸?JPEG/PNG/GIF/WebP锛夛紝鏃犻渶绗笁鏂逛緷璧栥€?
    杩斿洖 {"width": w, "height": h} 鎴?None锛堟棤娉曡瘑鍒級銆?
    """
    return (
        _parse_png_size(data)
        or _parse_jpeg_size(data)
        or _parse_gif_size(data)
        or _parse_webp_size(data)
    )


def _parse_png_size(buf: bytes) -> Optional[dict[str, int]]:
    if len(buf) < 24:
        return None
    if buf[:4] != b"\x89PNG":
        return None
    w = struct.unpack(">I", buf[16:20])[0]
    h = struct.unpack(">I", buf[20:24])[0]
    return {"width": w, "height": h}


def _parse_jpeg_size(buf: bytes) -> Optional[dict[str, int]]:
    if len(buf) < 4 or buf[0] != 0xFF or buf[1] != 0xD8:
        return None
    i = 2
    while i < len(buf) - 9:
        if buf[i] != 0xFF:
            i += 1
            continue
        marker = buf[i + 1]
        if marker in {0xC0, 0xC2}:
            h = struct.unpack(">H", buf[i + 5: i + 7])[0]
            w = struct.unpack(">H", buf[i + 7: i + 9])[0]
            return {"width": w, "height": h}
        if i + 3 < len(buf):
            i += 2 + struct.unpack(">H", buf[i + 2: i + 4])[0]
        else:
            break
    return None


def _parse_gif_size(buf: bytes) -> Optional[dict[str, int]]:
    if len(buf) < 10:
        return None
    sig = buf[:6].decode("ascii", errors="replace")
    if sig not in {"GIF87a", "GIF89a"}:
        return None
    w = struct.unpack("<H", buf[6:8])[0]
    h = struct.unpack("<H", buf[8:10])[0]
    return {"width": w, "height": h}


def _parse_webp_size(buf: bytes) -> Optional[dict[str, int]]:
    if len(buf) < 16:
        return None
    if buf[:4] != b"RIFF" or buf[8:12] != b"WEBP":
        return None
    chunk = buf[12:16].decode("ascii", errors="replace")
    if chunk == "VP8 ":
        if len(buf) >= 30 and buf[23] == 0x9D and buf[24] == 0x01 and buf[25] == 0x2A:
            w = struct.unpack("<H", buf[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", buf[28:30])[0] & 0x3FFF
            return {"width": w, "height": h}
    elif chunk == "VP8L":
        if len(buf) >= 25 and buf[20] == 0x2F:
            bits = struct.unpack("<I", buf[21:25])[0]
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            return {"width": w, "height": h}
    elif chunk == "VP8X":
        if len(buf) >= 30:
            w = (buf[24] | (buf[25] << 8) | (buf[26] << 16)) + 1
            h = (buf[27] | (buf[28] << 8) | (buf[29] << 16)) + 1
            return {"width": w, "height": h}
    return None


# ============ URL 涓嬭浇 ============

async def download_url(
    url: str,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> tuple[bytes, str]:
    """
    涓嬭浇 URL 鍐呭锛岃繑鍥?(bytes, content_type)銆?

    Args:
        url:          HTTP(S) URL
        max_size_mb:  鏈€澶у厑璁稿ぇ灏忥紙MB锛夛紝瓒呰繃鍒欐姏鍑哄紓甯?

    Returns:
        (data_bytes, content_type_string)

    Raises:
        ValueError:  鍐呭瓒呰繃澶у皬闄愬埗
        httpx.HTTPError: 缃戠粶/HTTP 閿欒
    """
    # SSRF protection: yuanbao downloads model-supplied and inbound URLs
    # server-side. Reject private/internal targets up front, and re-validate
    # every redirect hop so a public URL can't 302 to http://169.254.169.254/.
    from encre.ssrf import EncreSSRFGuard

    if not EncreSSRFGuard().validate_url(url):
        raise ValueError(f"Blocked unsafe URL (SSRF protection): {url}")

    async def _redirect_guard(response: httpx.Response) -> None:
        if response.is_redirect and response.next_request:
            redirect_url = str(response.next_request.url)
            if not is_safe_url(redirect_url):
                raise ValueError(
                    f"Blocked redirect to private/internal address: {redirect_url}"
                )

    max_bytes = max_size_mb * 1024 * 1024
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        event_hooks={"response": [_redirect_guard]},
    ) as client:
        # 鍏?HEAD 妫€鏌ュぇ灏?
        try:
            head = await client.head(url)
            content_length = int(head.headers.get("content-length", 0) or 0)
            if content_length > 0 and content_length > max_bytes:
                raise ValueError(
                    f"鏂囦欢杩囧ぇ: {content_length / 1024 / 1024:.1f} MB > {max_size_mb} MB"
                )
        except httpx.HTTPStatusError:
            pass  # 閮ㄥ垎鏈嶅姟鍣ㄤ笉鏀寔 HEAD锛屽拷鐣?

        # GET 涓嬭浇锛堟祦寮忚鍙栵紝闃叉瓒呴檺锛?
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()

            chunks: list[bytes] = []
            downloaded = 0
            async for chunk in resp.aiter_bytes(65536):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError(
                        f"鏂囦欢杩囧ぇ: 宸茶秴杩?{max_size_mb} MB 闄愬埗"
                    )
                chunks.append(chunk)

        data = b"".join(chunks)
        return data, content_type


# ============ COS 閴存潈锛圚MAC-SHA1锛?============

def _cos_sign(
    method: str,
    path: str,
    params: dict[str, str],
    headers: dict[str, str],
    secret_id: str,
    secret_key: str,
    start_time: Optional[int] = None,
    expire_seconds: int = 3600,
) -> str:
    """
    鏋勫缓 COS 璇锋眰绛惧悕锛坬-sign-algorithm=sha1 鏂规锛夈€?
    鍙傝€冿細https://cloud.tencent.com/document/product/436/7778

    Args:
        method:         HTTP 鏂规硶锛堝皬鍐欙紝濡?"put"锛?
        path:           URL 璺緞锛圲RL encode 鍚庣殑灏忓啓锛?
        params:         URL 鏌ヨ鍙傛暟 dict锛堢敤浜庣鍚嶏級
        headers:        鍙備笌绛惧悕鐨勮姹傚ご dict锛坘ey 闇€灏忓啓锛?
        secret_id:      涓存椂 SecretId锛坱mpSecretId锛?
        secret_key:     涓存椂 SecretKey锛坱mpSecretKey锛?
        start_time:     绛惧悕璧峰 Unix 鏃堕棿鎴筹紙榛樿 now锛?
        expire_seconds: 绛惧悕鏈夋晥鏈燂紙绉掞紝榛樿 3600锛?

    Returns:
        Authorization header 鍊硷紙瀹屾暣瀛楃涓诧級
    """
    now = int(time.time())
    q_sign_time = f"{start_time or now};{(start_time or now) + expire_seconds}"

    # Step 1: SignKey = HMAC-SHA1(SecretKey, q-sign-time)
    sign_key = hmac.new(
        secret_key.encode("utf-8"),
        q_sign_time.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    # Step 2: HttpString
    # 鍙傛暟鍜屽ご閮ㄩ渶鎸夊瓧鍏稿簭鎺掑垪锛宬ey 灏忓啓
    sorted_params = sorted((k.lower(), urllib.parse.quote(str(v), safe="") ) for k, v in params.items())
    sorted_headers = sorted((k.lower(), urllib.parse.quote(str(v), safe="") ) for k, v in headers.items())

    url_param_list = ";".join(k for k, _ in sorted_params)
    url_params = "&".join(f"{k}={v}" for k, v in sorted_params)
    header_list = ";".join(k for k, _ in sorted_headers)
    header_str = "&".join(f"{k}={v}" for k, v in sorted_headers)

    http_string = "\n".join([
        method.lower(),
        path,
        url_params,
        header_str,
        "",
    ])

    # Step 3: StringToSign = sha1 hash of HttpString
    sha1_of_http = hashlib.sha1(http_string.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join([
        "sha1",
        q_sign_time,
        sha1_of_http,
        "",
    ])

    # Step 4: Signature = HMAC-SHA1(SignKey, StringToSign)
    signature = hmac.new(
        sign_key.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    return (
        f"q-sign-algorithm=sha1"
        f"&q-ak={secret_id}"
        f"&q-sign-time={q_sign_time}"
        f"&q-key-time={q_sign_time}"
        f"&q-header-list={header_list}"
        f"&q-url-param-list={url_param_list}"
        f"&q-signature={signature}"
    )


# ============ 涓昏鍏紑 API ============

async def get_cos_credentials(
    app_key: str,
    api_domain: str,
    token: str,
    filename: str = "file",
    file_id: Optional[str] = None,
    bot_id: str = "",
    route_env: str = "",
) -> dict:
    """
    璋冪敤 genUploadInfo 鎺ュ彛鑾峰彇 COS 涓存椂瀵嗛挜鍙婁笂浼犻厤缃€?

    Args:
        app_key:        搴旂敤 Key锛堢敤浜?X-ID 澶达級
        api_domain:     API 鍩熷悕锛堝 https://bot.yuanbao.tencent.com锛?
        token:          褰撳墠鏈夋晥鐨勭绁?token锛圶-Token 澶达級
        filename:       寰呬笂浼犵殑鏂囦欢鍚嶏紙鍚墿灞曞悕锛?
        file_id:        瀹㈡埛绔敓鎴愮殑鍞竴鏂囦欢 ID锛堜笉浼犲垯鑷姩鐢熸垚锛?
        bot_id:         Bot 璐﹀彿 ID锛堢敤浜?X-ID 澶达級

    Returns:
        COS 涓婁紶閰嶇疆 dict锛屽寘鍚互涓嬪瓧娈碉細
            bucketName         (str)  鈥?COS Bucket 鍚嶇О
            region             (str)  鈥?COS 鍦板煙
            location           (str)  鈥?涓婁紶 Key锛堝璞¤矾寰勶級
            encryptTmpSecretId (str)  鈥?涓存椂 SecretId
            encryptTmpSecretKey(str)  鈥?涓存椂 SecretKey
            encryptToken       (str)  鈥?SessionToken
            startTime          (int)  鈥?鍑瘉璧峰鏃堕棿鎴筹紙Unix锛?
            expiredTime        (int)  鈥?鍑瘉杩囨湡鏃堕棿鎴筹紙Unix锛?
            resourceUrl        (str)  鈥?涓婁紶鍚庣殑鍏綉璁块棶 URL
            resourceID         (str)  鈥?璧勬簮 ID锛堝彲閫夛級

    Raises:
        RuntimeError: 鎺ュ彛杩斿洖闈?0 code 鎴栧瓧娈电己澶?
    """
    if file_id is None:
        file_id = generate_file_id()

    upload_url = f"{api_domain.rstrip('/')}{UPLOAD_INFO_PATH}"

    headers = {
        "Content-Type": "application/json",
        "X-Token": token,
        "X-ID": bot_id or app_key,
        "X-Source": "web",
    }
    if route_env:
        headers["X-Route-Env"] = route_env
    body = {
        "fileName": filename,
        "fileId": file_id,
        "docFrom": "localDoc",
        "docOpenId": "",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(upload_url, json=body, headers=headers)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()

    code = result.get("code")
    if code != 0 and code is not None:
        raise RuntimeError(
            f"genUploadInfo 澶辫触: code={code}, msg={result.get('msg', '')}"
        )

    data = result.get("data") or result
    required_fields = ["bucketName", "location"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        raise RuntimeError(
            f"genUploadInfo 杩斿洖瀛楁涓嶅畬鏁? 缂哄皯瀛楁 {missing}"
        )

    return data


async def upload_to_cos(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    credentials: dict,
    bucket: str,
    region: str,
) -> dict:
    """
    閫氳繃 httpx PUT 璇锋眰灏嗘枃浠朵笂浼犲埌 COS銆?
    浣跨敤涓存椂鍑瘉锛坱mpSecretId/tmpSecretKey/sessionToken锛夋瀯寤?HMAC-SHA1 绛惧悕銆?

    Args:
        file_bytes:   鏂囦欢浜岃繘鍒跺唴瀹?
        filename:     鏂囦欢鍚嶏紙鐢ㄤ簬杈呭姪璁＄畻 MIME銆乁UID锛?
        content_type: MIME 绫诲瀷锛堝 "image/jpeg"锛?
        credentials:  get_cos_credentials() 杩斿洖鐨?dict锛屽寘鍚細
                        encryptTmpSecretId  鈫?tmpSecretId
                        encryptTmpSecretKey 鈫?tmpSecretKey
                        encryptToken        鈫?sessionToken
                        location            鈫?COS key锛堝璞¤矾寰勶級
                        resourceUrl         鈫?涓婁紶鍚庡叕缃?URL
                        startTime           鈫?鍑瘉璧峰鏃堕棿锛圲nix锛?
                        expiredTime         鈫?鍑瘉杩囨湡鏃堕棿锛圲nix锛?
        bucket:       COS Bucket 鍚嶇О锛堝 chatbot-1234567890锛?
        region:       COS 鍦板煙锛堝 ap-guangzhou锛?

    Returns:
        涓婁紶缁撴灉 dict锛屽寘鍚細
            url       (str)           鈥?COS 鍏綉璁块棶 URL
            uuid      (str)           鈥?鏂囦欢鍐呭 MD5
            size      (int)           鈥?鏂囦欢澶у皬锛堝瓧鑺傦級
            width     (int, optional) 鈥?鍥剧墖瀹藉害锛堜粎鍥剧墖锛?
            height    (int, optional) 鈥?鍥剧墖楂樺害锛堜粎鍥剧墖锛?

    Raises:
        httpx.HTTPStatusError: COS 杩斿洖闈?2xx 鐘舵€?
        RuntimeError:          credentials 瀛楁缂哄け
    """
    secret_id: str = credentials.get("encryptTmpSecretId", "")
    secret_key: str = credentials.get("encryptTmpSecretKey", "")
    session_token: str = credentials.get("encryptToken", "")
    cos_key: str = credentials.get("location", "")
    resource_url: str = credentials.get("resourceUrl", "")
    start_time: Optional[int] = credentials.get("startTime")
    expired_time: Optional[int] = credentials.get("expiredTime")

    if not secret_id or not secret_key or not cos_key:
        raise RuntimeError(
            f"COS credentials 涓嶅畬鏁? secretId={bool(secret_id)}, "
            f"secretKey={bool(secret_key)}, location={bool(cos_key)}"
        )

    # 鏋勫缓 COS 涓婁紶 URL锛堜紭鍏堜娇鐢ㄥ叏鐞冨姞閫熷煙鍚嶏級
    if COS_USE_ACCELERATE:
        cos_host = f"{bucket}.cos.accelerate.myqcloud.com"
    else:
        cos_host = f"{bucket}.cos.{region}.myqcloud.com"

    # URL encode cos_key锛堜繚鐣?/锛?
    encoded_key = urllib.parse.quote(cos_key, safe="/")
    cos_url = f"https://{cos_host}/{encoded_key.lstrip('/')}"

    # 纭畾 Content-Type
    if not content_type or content_type == "application/octet-stream":
        if is_image(filename):
            content_type = guess_mime_type(filename)
        else:
            content_type = "application/octet-stream"

    # 璁＄畻鏂囦欢 MD5 + size
    file_uuid = md5_hex(file_bytes)
    file_size = len(file_bytes)

    # 鍙備笌绛惧悕鐨勮姹傚ご
    sign_headers = {
        "host": cos_host,
        "content-type": content_type,
        "x-cos-security-token": session_token,
    }

    # 璁＄畻绛惧悕鏈夋晥鏈?
    now = int(time.time())
    sign_start = start_time if start_time else now
    sign_expire = (expired_time - now) if expired_time and expired_time > now else 3600

    authorization = _cos_sign(
        method="put",
        path=f"/{encoded_key.lstrip('/')}",
        params={},
        headers=sign_headers,
        secret_id=secret_id,
        secret_key=secret_key,
        start_time=sign_start,
        expire_seconds=sign_expire,
    )

    put_headers = {
        "Authorization": authorization,
        "Content-Type": content_type,
        "x-cos-security-token": session_token,
    }

    logger.info(
        "COS PUT: bucket=%s region=%s key=%s size=%d mime=%s",
        bucket, region, cos_key, file_size, content_type,
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.put(
            cos_url,
            content=file_bytes,
            headers=put_headers,
        )
        resp.raise_for_status()

    # 瑙ｆ瀽鍥剧墖灏哄锛堜粎鍥剧墖绫诲瀷锛?
    result: dict[str, Any] = {
        "url": resource_url or cos_url,
        "uuid": file_uuid,
        "size": file_size,
    }

    if content_type.startswith("image/"):
        size_info = parse_image_size(file_bytes)
        if size_info:
            result["width"] = size_info["width"]
            result["height"] = size_info["height"]

    logger.info(
        "COS 涓婁紶鎴愬姛: url=%s size=%d",
        result["url"], file_size,
    )
    return result


# ============ TIM 濯掍綋娑堟伅鏋勫缓 ============

def build_image_msg_body(
    url: str,
    uuid: Optional[str] = None,
    filename: Optional[str] = None,
    size: int = 0,
    width: int = 0,
    height: int = 0,
    mime_type: str = "",
) -> list[dict]:
    """
    鏋勫缓鑵捐 IM TIMImageElem 娑堟伅浣撱€?
    鍙傝€冿細https://cloud.tencent.com/document/product/269/2720

    Args:
        url:       鍥剧墖鍏綉璁块棶 URL锛圕OS resourceUrl锛?
        uuid:      鏂囦欢 UUID锛圡D5 鎴栧叾浠栧敮涓€鏍囪瘑锛?
        filename:  鏂囦欢鍚嶏紙uuid 涓虹┖鏃朵綔涓哄鐢級
        size:      鏂囦欢澶у皬锛堝瓧鑺傦級
        width:     鍥剧墖瀹藉害锛堝儚绱狅級
        height:    鍥剧墖楂樺害锛堝儚绱狅級
        mime_type: MIME 绫诲瀷锛堢敤浜庣‘瀹?image_format锛?

    Returns:
        TIMImageElem 娑堟伅浣撳垪琛紙閫傚悎鐩存帴鏀惧叆 msg_body锛?
    """
    _uuid = uuid or filename or _basename_from_url(url) or "image"
    image_format = get_image_format(mime_type) if mime_type else 255

    return [
        {
            "msg_type": "TIMImageElem",
            "msg_content": {
                "uuid": _uuid,
                "image_format": image_format,
                "image_info_array": [
                    {
                        "type": 1,       # 1 = 鍘熷浘
                        "size": size,
                        "width": width,
                        "height": height,
                        "url": url,
                    }
                ],
            },
        }
    ]


def build_file_msg_body(
    url: str,
    filename: str,
    uuid: Optional[str] = None,
    size: int = 0,
) -> list[dict]:
    """
    鏋勫缓鑵捐 IM TIMFileElem 娑堟伅浣撱€?
    鍙傝€冿細https://cloud.tencent.com/document/product/269/2720

    Args:
        url:      鏂囦欢鍏綉璁块棶 URL锛圕OS resourceUrl锛?
        filename: 鏂囦欢鍚嶏紙鍚墿灞曞悕锛?
        uuid:     鏂囦欢 UUID锛圡D5 鎴栧叾浠栧敮涓€鏍囪瘑锛屼笉浼犲垯浣跨敤 filename锛?
        size:     鏂囦欢澶у皬锛堝瓧鑺傦級

    Returns:
        TIMFileElem 娑堟伅浣撳垪琛紙閫傚悎鐩存帴鏀惧叆 msg_body锛?
    """
    _uuid = uuid or filename

    return [
        {
            "msg_type": "TIMFileElem",
            "msg_content": {
                "uuid": _uuid,
                "file_name": filename,
                "file_size": size,
                "url": url,
            },
        }
    ]


# ============ 鍐呴儴宸ュ叿 ============

def _basename_from_url(url: str) -> str:
    """浠?URL 鎻愬彇鏂囦欢鍚嶃€?""
    try:
        parsed = urllib.parse.urlparse(url)
        return os.path.basename(parsed.path)
    except Exception:
        return ""
