"""
Byted-Voice-to-Text (ASR) using Volcengine BigModel ASR API.
Ref: https://www.volcengine.com/docs/6561/1354870
閴存潈: 鏂扮増鎺у埗鍙?API Key 鏂规 https://www.volcengine.com/docs/6561/2119699
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import time
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from api_key import get_speech_api_key

ASR_ENDPOINT = os.getenv(
    "MODEL_SPEECH_ASR_API_BASE",
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
)
ASR_RESOURCE_ID = os.getenv("MODEL_SPEECH_ASR_RESOURCE_ID", "volc.bigasr.auc_turbo")


def log(msg: str) -> None:
    print(f"[byted-voice-to-text] {msg}", file=sys.stderr)


def fail(msg: str) -> None:
    full = f"[byted-voice-to-text ERROR] {msg}"
    print(full, file=sys.stderr)
    print(full)
    sys.exit(1)


try:
    import requests
except ImportError:
    fail("requests 搴撴湭瀹夎锛岃鎵ц pip install requests")


# ============================================================
# Download Feishu audio file by file_key
# ============================================================
def download_feishu_audio(file_key: str, tenant_token: str) -> str:
    """
    Download audio file from Feishu via file_key to temp directory.

    Feishu audio message format:
      - message_type: "audio"
      - content: {"file_key": "file_v2_xxxx"}
      - audio codec: Opus in OGG container
    """
    """
    閫氳繃椋炰功 file_key 涓嬭浇璇煶鏂囦欢鍒颁复鏃剁洰褰曪紝杩斿洖鏈湴鏂囦欢璺緞銆?

    椋炰功璇煶娑堟伅鏍煎紡锛?
      - message_type: "audio"
      - content: {"file_key": "file_v2_xxxx"}
      - 闊抽缂栫爜: Opus in OGG 瀹瑰櫒

    璋冪敤椋炰功銆屼笅杞芥枃浠躲嶆帴鍙?
      GET https://open.feishu.cn/open-apis/im/v1/files/{file_key}
    """
    download_url = f"https://open.feishu.cn/open-apis/im/v1/files/{file_key}"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    log(f"姝ｅ湪浠庨涔笅杞借闊虫枃浠? file_key={file_key}")
    resp = requests.get(download_url, headers=headers, timeout=30)

    if resp.status_code != 200:
        fail(
            f"椋炰功鏂囦欢涓嬭浇澶辫触: HTTP {resp.status_code}, "
            f"鍝嶅簲: {resp.text[:500]}"
        )

    tmp_file = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp_file.write(resp.content)
    tmp_file.close()

    file_size = len(resp.content)
    log(f"璇煶鏂囦欢宸蹭笅杞? {tmp_file.name} ({file_size} bytes)")
    return tmp_file.name


# ============================================================
# Volcano Engine ASR recognition
# ============================================================
def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_headers(appid: str | None = None, token: str | None = None) -> dict:
    """鏋勫缓璇锋眰澶淬傛敮鎸佹柊鐗堟帶鍒跺彴(X-Api-Key)鍜屾棫鐗?X-Api-App-Key + X-Api-Access-Key)銆"""
    app_id = appid or os.getenv("MODEL_SPEECH_APP_ID", "").strip()
    api_key = token or get_speech_api_key().strip()

    if not api_key:
        raise PermissionError(
            "MODEL_SPEECH_API_KEY must be configured as an environment variable."
            " See: https://www.volcengine.com/docs/6561/2119699"
        )

    headers = {
        "X-Api-Resource-Id": ASR_RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }

    if app_id:
        headers["X-Api-App-Key"] = app_id
        headers["X-Api-Access-Key"] = api_key
    else:
        headers["X-Api-Key"] = api_key

    return headers


def recognize(
    audio_url: str | None = None,
    file_path: str | None = None,
    appid: str | None = None,
    token: str | None = None,
    language: str | None = None,
) -> str:
    """璋冪敤鐏北寮曟搸 BigModel ASR Flash 鎺ュ彛锛岃繑鍥炶瘑鍒枃鏈"""
    headers = _build_headers(appid=appid, token=token)

    audio_data: dict = {}
    if audio_url:
        audio_data["url"] = audio_url
    elif file_path:
        audio_data["data"] = file_to_base64(file_path)
    else:
        raise ValueError("蹇呴』鎻愪緵 audio_url 鎴?file_path")

    if language:
        audio_data["language"] = language

    payload = {
        "user": {"uid": headers.get("X-Api-App-Key", "skill_asr_user")},
        "audio": audio_data,
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
        },
    }

    log("姝ｅ湪璋冪敤鐏北寮曟搸 ASR...")
    resp = requests.post(ASR_ENDPOINT, json=payload, headers=headers, timeout=60)

    status_code = resp.headers.get("X-Api-Status-Code", "")
    if status_code != "20000000":
        msg = resp.headers.get("X-Api-Message", "鏈煡閿欒")
        logid = resp.headers.get("X-Tt-Logid", "N/A")
        fail(f"ASR 璇锋眰澶辫触: code={status_code}, msg={msg}, logid={logid}")

    result = resp.json()
    text_parts: list[str] = []

    if "result" in result:
        res = result["result"]
        if isinstance(res, list):
            for item in res:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
        elif isinstance(res, dict):
            if "text" in res:
                text_parts.append(res["text"])
            elif "utterances" in res:
                for utt in res["utterances"]:
                    if "text" in utt:
                        text_parts.append(utt["text"])

    if not text_parts and "utterances" in result:
        for utt in result["utterances"]:
            if "text" in utt:
                text_parts.append(utt["text"])

    if not text_parts:
        fail(f"鏃犳硶浠庡搷搴斾腑鎻愬彇鏂囨湰锛屽師濮嬪搷搴? {json.dumps(result, ensure_ascii=False)}")

    text = "".join(text_parts)
    log(f"璇嗗埆鎴愬姛锛屾枃鏈暱搴? {len(text)} 瀛楃")
    return text


# ============================================================
# Main entry point
# ============================================================
def main() -> None:
    """CLI main entry point for Volcano Engine BigModel ASR Flash."""
    parser = argparse.ArgumentParser(
        description="璇煶杞枃瀛楀伐鍏凤紙鐏北寮曟搸 BigModel ASR锛?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥鐢ㄦ硶:

  #  Method 1: Pass audio URL directly

  python asr_flash.py --url "https://example.com/audio.mp3"

  #  Method 2: Pass local audio file

  python asr_flash.py --file "/path/to/audio.ogg"

  #  Method 3: Pass Feishu audio message file_key

  python asr_flash.py --file-key "file_v2_xxxx" --feishu-token "t-g104xxx"

椋炰功璇煶娑堟伅澶勭悊娴佺▼:
  鏀跺埌 audio 娑堟伅 鈫?鎻愬彇 content.file_key 鈫?鏈剼鏈笅杞?璇嗗埆 鈫?杩斿洖鏂囧瓧
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="闊抽鏂囦欢鐨?URL 鍦板潃")
    group.add_argument("--file", help="鏈湴闊抽鏂囦欢璺緞")
    group.add_argument("--file-key", help="椋炰功璇煶娑堟伅鐨?file_key")

    parser.add_argument(
        "--feishu-token",
        help="椋炰功 tenant_access_token (涔熷彲閫氳繃鐜鍙橀噺 FEISHU_TENANT_TOKEN 璁剧疆)",
    )
    parser.add_argument(
        "--appid",
        help="鐏北寮曟搸 ASR App ID (涔熷彲閫氳繃鐜鍙橀噺 MODEL_SPEECH_APP_ID 璁剧疆)",
    )
    parser.add_argument(
        "--token",
        help="鐏北寮曟搸 ASR API Key (涔熷彲閫氳繃鐜鍙橀噺 MODEL_SPEECH_API_KEY 璁剧疆)",
    )
    parser.add_argument(
        "--language",
        help="璇█浠ｇ爜锛屽 zh-CN, ja-JP, en-US (鍙夛紝涓嶄紶鍒欒嚜鍔ㄨ瘑鍒?",
    )

    args = parser.parse_args()

    log(f"鍚姩鍙傛暟: file={args.file}, url={args.url}, file_key={args.file_key}")
    log(
        "env: MODEL_SPEECH_APP_ID=%s, MODEL_SPEECH_API_KEY=%s, FEISHU_TENANT_TOKEN=%s"
        % (
            "set" if os.environ.get("MODEL_SPEECH_APP_ID") else "unset",
            "set" if os.environ.get("MODEL_SPEECH_API_KEY") else "unset",
            "set" if os.environ.get("FEISHU_TENANT_TOKEN") else "unset",
        )
    )

    if args.file:
        if not os.path.exists(args.file):
            fail(f"闊抽鏂囦欢涓嶅瓨鍦? {args.file}")
        file_size = os.path.getsize(args.file)
        log(f"闊抽鏂囦欢: {args.file} ({file_size} bytes)")
        if file_size == 0:
            fail(f"闊抽鏂囦欢涓虹┖: {args.file}")

    local_file = None
    try:
        if args.file_key:
            feishu_token = args.feishu_token or os.environ.get(
                "FEISHU_TENANT_TOKEN", ""
            )
            if not feishu_token:
                fail(
                    "浣跨敤 --file-key 鏃堕渶瑕侀涔?token銆?"
                    "璇烽氳繃 --feishu-token 鍙傛暟鎴栫幆澧冨彉閲?FEISHU_TENANT_TOKEN 鎻愪緵"
                )
            local_file = download_feishu_audio(args.file_key, feishu_token)

        text = recognize(
            audio_url=args.url,
            file_path=args.file or local_file,
            appid=args.appid,
            token=args.token,
            language=args.language,
        )

        print(text)

    except PermissionError as e:
        fail(str(e))
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))
    finally:
        if local_file and os.path.exists(local_file):
            os.unlink(local_file)


if __name__ == "__main__":
    main()
