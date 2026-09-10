from __future__ import annotations

"""
asr_standard.py 鈥?鐏北寮曟搸 BigModel ASR 鏍囧噯鐗堬紙褰曢煶鏂囦欢璇嗗埆锛夈?

寮傛 submit + poll 妯紡锛屾敮鎸?鈮? 灏忔椂闊抽銆?
鍙傝? auc_http_demo.py (submit_task 鈫?query_task 鈫?result)
閴存潈: 鏂扮増鎺у埗鍙?API Key 鏂规 https://www.volcengine.com/docs/6561/2119699

鐢ㄦ硶:
  #  URL recognition锛堟渶甯哥敤锛?

  python3 asr_standard.py --url "https://example.com/audio.mp3"

  #  Local file recognition

  python3 asr_standard.py --file "/path/to/long_audio.wav"

  #  Submit only (no polling)

  python3 asr_standard.py --url "https://..." --no-poll

  #  Query existing task

  python3 asr_standard.py --query-task-id <TASK_ID> --query-logid <X_TT_LOGID>
"""

import argparse
import base64
import json
import os
import sys
import time
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from api_key import get_speech_api_key

# ============================================================
# Endpoint and resource ID configuration
# Configurable via environment variables, with sensible defaults
# ============================================================
ASR_STANDARD_SUBMIT_URL = os.getenv(
    "MODEL_SPEECH_ASR_STANDARD_SUBMIT_URL",
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
)
ASR_STANDARD_QUERY_URL = os.getenv(
    "MODEL_SPEECH_ASR_STANDARD_QUERY_URL",
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
)
ASR_STANDARD_RESOURCE_ID = os.getenv(
    "MODEL_SPEECH_ASR_STANDARD_RESOURCE_ID", "volc.bigasr.auc"
)

# Polling parameters for async task completion
DEFAULT_POLL_INTERVAL = 3       # seconds between polls
DEFAULT_POLL_MAX_TIME = 10800   # 3 hour timeout

# Standard version maximum supported audio duration
STANDARD_MAX_SECONDS = 5 * 60 * 60  # 5 hours in seconds


def log(msg: str) -> None:
    print(f"[byted-asr-standard] {msg}", file=sys.stderr)


def fail_json(error_code: str, message: str, **extra) -> None:
    """杈撳嚭 JSON 鏍煎紡鐨勯敊璇苟閫鍑恒"""
    payload = {"error": error_code, "message": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(1)


try:
    import requests
except ImportError:
    fail_json("MISSING_DEPENDENCY", "requests 搴撴湭瀹夎锛岃鎵ц pip install requests")


# ============================================================
# Header
# ============================================================
def _build_headers(appid: str | None = None, token: str | None = None) -> dict:
    """
    Build request headers for standard ASR API.

    Authentication method (consistent with flash version asr_flash.py):
      - New console: X-Api-Key header
      - Legacy console: X-Api-App-Key + X-Api-Access-Key headers
    """
    app_id = appid or os.getenv("MODEL_SPEECH_APP_ID", "").strip()
    api_key = token or get_speech_api_key().strip()

    if not api_key:
        fail_json(
            "CREDENTIALS_NOT_CONFIGURED",
            "MODEL_SPEECH_API_KEY must be configured as an environment variable."
            " See: https://www.volcengine.com/docs/6561/2119699",
            missing_credentials=["MODEL_SPEECH_API_KEY"],
        )

    headers = {
        "X-Api-Resource-Id": ASR_STANDARD_RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }

    if app_id:
        headers["X-Api-App-Key"] = app_id
        headers["X-Api-Access-Key"] = api_key
    else:
        headers["X-Api-Key"] = api_key

    return headers


# ============================================================
# File to Base64 encoding
# ============================================================
def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ============================================================
# Submit Task
# ============================================================
def submit_task(
    audio_url: str | None = None,
    file_path: str | None = None,
    appid: str | None = None,
    token: str | None = None,
    language: str | None = None,
) -> dict:
    """
    Submit recognition task to Volcano Engine standard ASR.

    Args:
        audio_url: Audio URL (alternative to file_path).
        file_path: Local file path (will be Base64 encoded).
        appid: App ID (optional).
        token: API Key (optional).
        language: Language code (optional).

    Returns:
        {"task_id": str, "x_tt_logid": str}
    """
    headers = _build_headers(appid=appid, token=token)
    task_id = headers["X-Api-Request-Id"]

    audio_payload: dict = {}
    if audio_url:
        audio_payload["url"] = audio_url
    elif file_path:
        if not os.path.isfile(file_path):
            fail_json("FILE_NOT_FOUND", f"闊抽鏂囦欢涓嶅瓨鍦? {file_path}")
        if os.path.getsize(file_path) == 0:
            fail_json("FILE_EMPTY", f"闊抽鏂囦欢涓虹┖: {file_path}")
        audio_payload["data"] = file_to_base64(file_path)
    else:
        fail_json("NO_INPUT", "蹇呴』鎻愪緵 --url 鎴?--file")

    if language:
        audio_payload["language"] = language

    request_body = {
        "user": {"uid": headers.get("X-Api-App-Key", "skill_asr_user")},
        "audio": audio_payload,
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "show_utterances": True,
        },
    }

    log(f"姝ｅ湪鎻愪氦鏍囧噯鐗堣瘑鍒换鍔? task_id={task_id}")
    try:
        resp = requests.post(
            ASR_STANDARD_SUBMIT_URL,
            data=json.dumps(request_body),
            headers=headers,
            timeout=60,
        )
    except requests.RequestException as e:
        fail_json("NETWORK_ERROR", f"鎻愪氦璇锋眰缃戠粶寮傚父: {e}")

    resp_status = resp.headers.get("X-Api-Status-Code", "")
    x_tt_logid = resp.headers.get("X-Tt-Logid", "")

    if resp_status != "20000000":
        msg = resp.headers.get("X-Api-Message", "鏈煡閿欒")
        fail_json(
            "SUBMIT_FAILED",
            f"鏍囧噯鐗堜换鍔彁浜ゅけ璐? code={resp_status}, msg={msg}",
            task_id=task_id,
            logid=x_tt_logid,
        )

    log(f"浠诲姟宸叉彁浜? task_id={task_id}, logid={x_tt_logid}")
    return {"task_id": task_id, "x_tt_logid": x_tt_logid}


# ============================================================
# Query task status
# ============================================================
def query_task(
    task_id: str,
    x_tt_logid: str,
    appid: str | None = None,
    token: str | None = None,
) -> dict:
    """
    鏌ヨ鏍囧噯鐗堣瘑鍒换鍔姸鎬併?

    Returns:
        {"status_code": str, "message": str, "logid": str, "body": dict}
    """
    headers = _build_headers(appid=appid, token=token)
    headers["X-Api-Request-Id"] = task_id
    headers["X-Tt-Logid"] = x_tt_logid

    try:
        resp = requests.post(
            ASR_STANDARD_QUERY_URL,
            data=json.dumps({}),
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as e:
        return {
            "status_code": "NETWORK_ERROR",
            "message": str(e),
            "logid": "",
            "body": {},
        }

    return {
        "status_code": resp.headers.get("X-Api-Status-Code", ""),
        "message": resp.headers.get("X-Api-Message", ""),
        "logid": resp.headers.get("X-Tt-Logid", ""),
        "body": resp.json() if resp.text.strip() else {},
    }


# ============================================================
# Poll until task completes
# ============================================================
def poll_until_done(
    task_id: str,
    x_tt_logid: str,
    appid: str | None = None,
    token: str | None = None,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    poll_max_time: int = DEFAULT_POLL_MAX_TIME,
) -> dict:
    """
    Poll standard ASR task until completion or timeout.

    Returns parsed result dict on success, exits on timeout/failure.
    """
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > poll_max_time:
            fail_json(
                "POLL_TIMEOUT",
                f"鏍囧噯鐗堣瘑鍒换鍔秴鏃? task_id={task_id}, "
                f"宸茬瓑寰?{int(elapsed)} 绉掞紙涓婇檺 {poll_max_time} 绉掞級",
                task_id=task_id,
            )

        qr = query_task(task_id, x_tt_logid, appid=appid, token=token)
        code = qr["status_code"]

        if code == "20000000":
            log(f"璇嗗埆瀹屾垚: task_id={task_id}")
            return qr["body"]
        elif code in ("20000001", "20000002"):
            log(
                f"浠诲姟杩涜涓? code={code}, "
                f"宸茬瓑寰?{int(elapsed)}s, {poll_interval}s 鍚庨噸璇?.."
            )
            time.sleep(poll_interval)
        else:
            fail_json(
                "TASK_FAILED",
                f"鏍囧噯鐗堣瘑鍒け璐? code={code}, msg={qr['message']}",
                task_id=task_id,
                logid=qr["logid"],
            )


# ============================================================
# Text extraction (unified format for all response types)
# ============================================================
def extract_text(result: dict) -> str:
    """
    Extract plain text from Volcano ASR standard response JSON.

    Compatible with multiple response formats:
      - result.text
      - result.utterances[].text
      - utterances[].text (top-level list)
      - result[] (array format)
    """
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

    return "".join(text_parts)


# ============================================================
# CLI main entry point
# ============================================================
def main() -> None:
    """
    CLI main entry point for Volcano Engine BigModel ASR Standard.

    Supports URL input, local file upload, and query of existing tasks.
    """
    parser = argparse.ArgumentParser(
        description="鐏北寮曟搸 BigModel ASR 鏍囧噯鐗堬紙褰曢煶鏂囦欢璇嗗埆锛屽紓姝?submit+poll锛?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
绀轰緥:
  #  URL recognition

  python3 asr_standard.py --url "https://example.com/audio.mp3"

  #  Local file recognition

  python3 asr_standard.py --file "/path/to/long_audio.wav"

  # 锛?
  python3 asr_standard.py --url "https://..." --no-poll

  #  Query existing task

  python3 asr_standard.py --query-task-id <ID> --query-logid <LOGID>
        """,
    )

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--url", help="闊抽鏂囦欢鐨?URL 鍦板潃")
    input_group.add_argument("--file", help="鏈湴闊抽鏂囦欢璺緞")

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
    parser.add_argument(
        "--no-poll",
        action="store_true",
        help="浠呮彁浜や换鍔★紝涓嶈疆璇㈢粨鏋滐紙杩斿洖 task_id 渚涘悗缁煡璇級",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"杞闂撮殧绉掓暟 (榛樿: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--poll-max-time",
        type=int,
        default=DEFAULT_POLL_MAX_TIME,
        help=f"鏈澶ц疆璇椂闂寸鏁?(榛樿: {DEFAULT_POLL_MAX_TIME})",
    )

    # 
    parser.add_argument(
        "--query-task-id",
        help="鏌ヨ宸叉湁浠诲姟鐨?task_id锛堜笌 --query-logid 閰嶅悎浣跨敤锛?",
    )
    parser.add_argument(
        "--query-logid",
        default="",
        help="鏌ヨ鏃朵紶鍏ョ殑 X-Tt-Logid锛堝彲閫夛級",
    )

    args = parser.parse_args()

    #  妯紡 1: Query existing task

    if args.query_task_id:
        log(f"鏌ヨ浠诲姟: task_id={args.query_task_id}")
        result = poll_until_done(
            task_id=args.query_task_id,
            x_tt_logid=args.query_logid,
            appid=args.appid,
            token=args.token,
            poll_interval=args.poll_interval,
            poll_max_time=args.poll_max_time,
        )
        text = extract_text(result)
        if text:
            print(text)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 2:
    if not args.url and not args.file:
        fail_json("NO_INPUT", "蹇呴』鎻愪緵 --url 鎴?--file锛堟垨 --query-task-id 鏌ヨ宸叉湁浠诲姟锛?")

    submit_result = submit_task(
        audio_url=args.url,
        file_path=args.file,
        appid=args.appid,
        token=args.token,
        language=args.language,
    )

    task_id = submit_result["task_id"]
    x_tt_logid = submit_result["x_tt_logid"]

    if args.no_poll:
        print(json.dumps({
            "task_id": task_id,
            "x_tt_logid": x_tt_logid,
            "status": "submitted",
            "message": "浠诲姟宸叉彁浜わ紝浣跨敤浠ヤ笅鍛戒护鏌ヨ缁撴灉:",
            "query_command": (
                f"python3 asr_standard.py "
                f"--query-task-id {task_id} --query-logid {x_tt_logid}"
            ),
        }, ensure_ascii=False, indent=2))
        return

    # 
    result = poll_until_done(
        task_id=task_id,
        x_tt_logid=x_tt_logid,
        appid=args.appid,
        token=args.token,
        poll_interval=args.poll_interval,
        poll_max_time=args.poll_max_time,
    )
    text = extract_text(result)
    if text:
        log(f"璇嗗埆鎴愬姛锛屾枃鏈暱搴? {len(text)} 瀛楃")
        print(text)
    else:
        log("璀憡: 鏈彁鍙栧埌鏂囨湰锛岃緭鍑哄師濮?JSON")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
