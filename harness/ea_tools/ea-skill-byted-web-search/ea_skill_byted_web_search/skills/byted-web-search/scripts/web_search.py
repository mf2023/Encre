from __future__ import annotations

"""鐏北寮曟搸鑱旂綉鎼滅储 API 瀹埛绔"""

# Credential priority: 1) WEB_SEARCH_API_KEY or --api-key  2) VOLCENGINE_ACCESS_KEY+SECRET_KEY  3) VeFaaS IAM

# Examples:
#   python web_search.py "beijing weather"
#   python web_search.py "OpenAI latest release" --time-range OneWeek
#   python web_search.py "<query>" --type image --count 3


import argparse
import datetime
import getpass
import hashlib
import hmac
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote

SERVICE = "volc_torchlight_api"
VERSION = "2025-01-01"
REGION = "cn-beijing"
HOST = "mercury.volcengineapi.com"
ACTION = "WebSearch"
INTERNAL_API_URL = "https://open.feedcoopapi.com/search_api/web_search"
TRAFFIC_TAG_HEADER = "X-Traffic-Tag"
TRAFFIC_TAG_VALUE = "skill_web_search_common"
TIME_RANGE_SHORTCUTS = {"OneDay", "OneWeek", "OneMonth", "OneYear"}
DATE_RANGE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")
LEGACY_ENV_PATH = "/root/.openclaw/.env"
USER_ENV_PATH = str(Path.home() / ".openclaw/.env")
SUMMARY_PREVIEW_LIMIT = 1000
ERROR_HINTS = {
    "10400": "鎻愮ず锛氬弬鏁伴敊璇傝妫鏌?Query銆丆ount銆乀imeRange 绛夊弬鏁版牸寮忔槸鍚︽纭?",
    "10402": "鎻愮ず锛氭悳绱㈢被鍨嬮潪娉曘傚綋鍓嶄粎鏀寔 web 鎴?image銆?",
    "10403": "鎻愮ず锛氳处鍙锋垨鏉冮檺寮傚父銆傝纭 API Key 鏉ヨ嚜鑱旂綉鎼滅储鎺у埗鍙帮紝鎴栨鏌ヨ处鍙锋潈闄愩?",
    "10406": "鎻愮ず锛氬厤璐归搴凡鑰楀敖銆傝妫鏌ヨ处鎴烽搴︽垨鑱旂郴鏀寔銆?",
    "10407": "鎻愮ず锛氬綋鍓嶆棤鍙敤鍏嶈垂绛栫暐銆傝妫鏌ヨ处鎴风姸鎬佹垨鑱旂郴鏀寔銆?",
    "10500": "鎻愮ず锛氭湇鍔唴閮ㄩ敊璇傚缓璁◢鍚庨噸璇曪紝鎴栬仈绯绘敮鎸併?",
    "700429": "鎻愮ず锛氬厤璐归摼璺Е鍙戦檺娴併傝闄嶉鍚庨噸璇曘?",
    "100013": "鎻愮ず锛氬瓙璐彿鏈巿鏉?TorchlightApiFullAccess銆?",
}


#  ---- Dependency loading ----


def _require_requests():
    try:
        import requests
    except ImportError:
        print("Error: requests not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)
    return requests


def _load_legacy_env_file(env_path: str = LEGACY_ENV_PATH) -> None:
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue

                try:
                    parsed = shlex.split(value, comments=True)
                    value = parsed[0] if parsed else ""
                except ValueError:
                    value = value.strip("\"'")

                os.environ.setdefault(key, value)
    except OSError:
        return


def _load_legacy_env_files() -> None:
    seen_paths = set()
    for env_path in (LEGACY_ENV_PATH, USER_ENV_PATH):
        normalized = os.path.abspath(os.path.expanduser(env_path))
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        _load_legacy_env_file(normalized)


# ----  HMAC-SHA256  () ----

def _hmac_sha256(key: bytes, content: str) -> bytes:
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def _hash_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _norm_query(params: dict) -> str:
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for value in params[key]:
                query += quote(key, safe="-_.~") + "=" + quote(value, safe="-_.~") + "&"
        else:
            query += quote(key, safe="-_.~") + "=" + quote(str(params[key]), safe="-_.~") + "&"
    return query[:-1].replace("+", "%20") if query else ""


def _utc_now():
    try:
        from datetime import timezone
        return datetime.datetime.now(timezone.utc)
    except ImportError:
        return datetime.datetime.utcnow()


def _sign_request(method: str, ak: str, sk: str, body: str, session_token: str = "") -> dict:
    now = _utc_now()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]
    x_content_sha256 = _hash_sha256(body)
    content_type = "application/json"

    query_params = {"Action": ACTION, "Version": VERSION}

    signed_header_keys = ["content-type", "host", "x-content-sha256", "x-date", "x-traffic-tag"]
    if session_token:
        signed_header_keys.append("x-security-token")
    signed_header_keys.sort()
    signed_headers_str = ";".join(signed_header_keys)

    canonical_header_lines = [
        f"content-type:{content_type}",
        f"host:{HOST}",
        f"x-content-sha256:{x_content_sha256}",
        f"x-date:{x_date}",
        f"x-traffic-tag:{TRAFFIC_TAG_VALUE}",
    ]
    if session_token:
        canonical_header_lines.append(f"x-security-token:{session_token}")
        canonical_header_lines.sort()

    canonical_request = "\n".join(
        [
            method.upper(),
            "/",
            _norm_query(query_params),
            "\n".join(canonical_header_lines),
            "",
            signed_headers_str,
            x_content_sha256,
        ]
    )

    credential_scope = f"{short_date}/{REGION}/{SERVICE}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            _hash_sha256(canonical_request),
        ]
    )

    k_date = _hmac_sha256(sk.encode("utf-8"), short_date)
    k_region = _hmac_sha256(k_date, REGION)
    k_service = _hmac_sha256(k_region, SERVICE)
    k_signing = _hmac_sha256(k_service, "request")
    signature = _hmac_sha256(k_signing, string_to_sign).hex()

    authorization = (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "Host": HOST,
        "X-Date": x_date,
        "X-Content-Sha256": x_content_sha256,
        TRAFFIC_TAG_HEADER: TRAFFIC_TAG_VALUE,
        "Authorization": authorization,
    }
    if session_token:
        headers["X-Security-Token"] = session_token
    return headers


#  ---- Credential retrieval ----


def _get_credentials() -> tuple:
    """杩斿洖 (ak, sk, session_token)銆?"""
    ak = os.getenv("VOLCENGINE_ACCESS_KEY")
    sk = os.getenv("VOLCENGINE_SECRET_KEY")
    if ak and sk:
        return ak, sk, ""

    try:
        from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

        cred = get_credential_from_vefaas_iam()
        return cred.access_key_id, cred.secret_access_key, cred.session_token
    except Exception:
        return None, None, ""


#  ---- Request construction ----


def _get_api_key(cli_api_key: Optional[str]) -> Optional[str]:
    api_key = cli_api_key or os.getenv("WEB_SEARCH_API_KEY")
    return api_key.strip() if api_key else None


def _validate_time_range(time_range: Optional[str]) -> Optional[str]:
    if not time_range:
        return None
    if time_range in TIME_RANGE_SHORTCUTS:
        return time_range

    match = DATE_RANGE_PATTERN.match(time_range)
    if not match:
        raise ValueError(
            "--time-range 闇涓?OneDay/OneWeek/OneMonth/OneYear锛屾垨鏃ユ湡鍖洪棿 YYYY-MM-DD..YYYY-MM-DD銆?"
        )

    start_text, end_text = match.groups()
    try:
        start_date = datetime.date.fromisoformat(start_text)
        end_date = datetime.date.fromisoformat(end_text)
    except ValueError as exc:
        raise ValueError("--time-range dates must be valid YYYY-MM-DD.") from exc

    if start_date > end_date:
        raise ValueError("--time-range start date must not be after end date.")

    return time_range


def build_body(
        query: str,
        search_type: str = "web",
        count: int = 10,
        time_range: Optional[str] = None,
        auth_level: int = 0,
        query_rewrite: bool = False,
) -> dict:
    body = {"Query": query, "SearchType": search_type, "Count": count}

    if search_type == "web":
        body["NeedSummary"] = True
        filters = {}
        if auth_level > 0:
            filters["AuthInfoLevel"] = auth_level
        if filters:
            body["Filter"] = filters
        if time_range:
            body["TimeRange"] = time_range

    if query_rewrite:
        body["QueryControl"] = {"QueryRewrite": True}

    return body


#  ---- API invocation ----


def do_search(
        body: dict,
        api_key: Optional[str] = None,
        ak: Optional[str] = None,
        sk: Optional[str] = None,
        session_token: str = "",
):
    requests = _require_requests()
    body_str = json.dumps(body, ensure_ascii=False)
    if api_key:
        headers = {
            "Content-Type": "application/json",
            TRAFFIC_TAG_HEADER: TRAFFIC_TAG_VALUE,
            "Authorization": f"Bearer {api_key}",
        }
        url = INTERNAL_API_URL
    else:
        if not ak or not sk:
            raise ValueError("missing volcengine credentials")
        headers = _sign_request("POST", ak, sk, body_str, session_token)
        url = f"https://{HOST}?Action={ACTION}&Version={VERSION}"

    response = requests.post(url, headers=headers, data=body_str.encode("utf-8"), timeout=30)
    response.raise_for_status()
    return response.json()


# ----  ----

def format_output(data: dict, search_type: str) -> str:
    result = data.get("Result", {})
    lines = [f"缁撴灉鏁? {result.get('ResultCount', 0)}  鑰楁椂: {result.get('TimeCost', 0)}ms", ""]

    if search_type == "web":
        for item in result.get("WebResults") or []:
            lines.append(f"[{item.get('SortId', '')}] {item.get('Title', '')}")

            meta_parts = [part for part in [item.get("SiteName", ""), item.get("AuthInfoDes", "")] if part]
            if meta_parts:
                lines.append(f"    {' | '.join(meta_parts)}")

            if item.get("Url"):
                lines.append(f"    {item['Url']}")

            summary = item.get("Summary") or item.get("Snippet", "")
            if summary:
                lines.append(f"    {summary[:SUMMARY_PREVIEW_LIMIT]}")
            lines.append("")

    elif search_type == "image":
        for item in result.get("ImageResults") or []:
            image = item.get("Image", {})
            lines.append(f"[{item.get('SortId', '')}] {item.get('Title', '')}")
            if image.get("Url"):
                lines.append(f"    {image['Url']}")
            lines.append(f"    {image.get('Width', '?')}x{image.get('Height', '?')} ({image.get('Shape', '')})")
            lines.append("")

    return "\n".join(lines)


# ---- CLI ----

def main():
    _load_legacy_env_files()
    #  Try loading .env from skill root directory (same level as scripts/)

    _skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _load_legacy_env_file(os.path.join(_skill_root, ".env"))

    parser = argparse.ArgumentParser(
        description="鐏北寮曟搸鑱旂綉鎼滅储 API\nhttps://www.volcengine.com/docs/85508/1650263\n"
                    "鍑瘉锛欳law 涓洿鎺ュ湪鑱婂ぉ妗嗗彂 Key 鍗冲彲锛涙垨 WEB_SEARCH_API_KEY / --api-key"
    )
    parser.add_argument("query", help="鎼滅储鍏抽敭璇?")
    parser.add_argument("--type", "-t", default="web", choices=["web", "image"])
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument(
        "--time-range",
        help="OneDay/OneWeek/OneMonth/OneYear/YYYY-MM-DD..YYYY-MM-DD",
    )
    parser.add_argument("--auth-level", type=int, default=0, choices=[0, 1])
    parser.add_argument("--query-rewrite", action="store_true", help="寮鍚?Query 鏀瑰啓")
    parser.add_argument("--api-key", help="API Key锛堜紭鍏堜簬鐜鍙橀噺 WEB_SEARCH_API_KEY锛?")
    parser.add_argument("--prompt-api-key", action="store_true", help="浜や簰寮忚緭鍏?API Key锛堜笉鍥炴樉锛?")

    args = parser.parse_args()

    if not args.query or not args.query.strip():
        print("Error: 璇疯緭鍏ユ悳绱㈣瘝銆?, file=sys.stderr")
        sys.exit(1)
    if len(args.query) > 100:
        print("Error: 鎼滅储璇嶈秴杩?100 瀛楃锛孉PI 鍙兘鎴柇銆傚缓璁簿绠鍚庨噸璇曘?, file=sys.stderr")
        sys.exit(1)

    if args.count < 1:
        print("Error: --count 闇 鈮?1銆?, file=sys.stderr")
        sys.exit(1)
    if args.type == "image" and args.count > 5:
        print("Error: image 绫诲瀷鏈澶氳繑鍥?5 鏉★紝璇疯皟鏁?--count銆?, file=sys.stderr")
        sys.exit(1)
    if args.type == "web" and args.count > 50:
        print("Error: web 绫诲瀷鏈澶氳繑鍥?50 鏉★紝璇疯皟鏁?--count銆?, file=sys.stderr")
        sys.exit(1)

    try:
        time_range = _validate_time_range(args.time_range)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    api_key = _get_api_key(args.api_key)
    if not api_key and args.prompt_api_key:
        entered = getpass.getpass("API Key: ").strip()
        api_key = entered or None

    ak = sk = session_token = None
    if not api_key:
        ak, sk, session_token = _get_credentials()
        if not ak or not sk:
            print(
                "Error: 鏈壘鍒板嚟璇併傝閰嶇疆浠ヤ笅浠讳竴鏂瑰紡锛歕n"
                "1) 銆愭帹鑽愩戣嫢鍦?Claw 涓娇鐢細鎷?Key 鍚庣洿鎺ュ湪鑱婂ぉ妗嗗彂缁欐垜鍗冲彲锛屾棤闇缂栬緫閰嶇疆\n"
                "2) API Key锛氳缃?WEB_SEARCH_API_KEY 鎴栦紶鍏?--api-key\n"
                "3) AK/SK锛氳缃?VOLCENGINE_ACCESS_KEY 鍜?VOLCENGINE_SECRET_KEY\n"
                "寮閫氭寚鍗楋細references/setup-guide.md 鎴?SKILL.md",
                file=sys.stderr,
            )
            sys.exit(1)

    body = build_body(
        query=args.query,
        search_type=args.type,
        count=args.count,
        time_range=time_range,
        auth_level=args.auth_level,
        query_rewrite=args.query_rewrite,
    )

    requests = _require_requests()
    try:
        data = do_search(body, api_key=api_key, ak=ak, sk=sk, session_token=session_token or "")
    except requests.exceptions.HTTPError as exc:
        print(f"HTTP Error: {exc}", file=sys.stderr)
        if exc.response is not None:
            status = exc.response.status_code
            body = exc.response.text or ""
            if status == 429:
                print(
                    "鎻愮ず锛氳姹傞鐜囪繃楂樿Е鍙戦檺娴侊紝寤鸿闄嶉鍚庨噸璇曘?"
                    "璇﹁ references/setup-guide.md",
                    file=sys.stderr,
                )
            elif status == 401 and ("InvalidAccessKey" in body or "invalid" in body.lower()):
                print(
                    "鎻愮ず锛欰K/SK 鏃犳晥鎴栧凡澶辨晥銆傝妫鏌?VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY锛?"
                    "鎴栨敼鐢?API Key锛圕law 涓彲鐩存帴鍦ㄨ亰澶╂鍙戠粰鎴戯級銆傝瑙?references/setup-guide.md",
                    file=sys.stderr,
                )
            else:
                print(body, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if data is None:
        print("No response.", file=sys.stderr)
        sys.exit(1)

    error = (data.get("ResponseMetadata") or {}).get("Error")
    if error:
        code = error.get("Code", "")
        msg = error.get("Message", "")
        print(f"API Error [{code}]: {msg}", file=sys.stderr)
        if str(code).lower() == "invalid_api_key" or "10403" in str(code):
            print(
                "鎻愮ず锛氳纭 API Key 鏉ヨ嚜鑱旂綉鎼滅储鎺у埗鍙?https://console.volcengine.com/search-infinity/api-key 锛?"
                "鑰岄潪鐏北鏂硅垷(Ark)銆傝嫢鍦?Claw 涓紝鍙噸鏂板湪鑱婂ぉ妗嗗彂姝ｇ‘鐨?Key 缁欐垜銆傝瑙?references/setup-guide.md",
                file=sys.stderr,
            )
        elif "429" in str(code) or "flowlimit" in str(code).lower() or "100018" in str(code):
            print(
                "鎻愮ず锛氳姹傞鐜囪繃楂樿Е鍙戦檺娴侊紝寤鸿闄嶉鍚庨噸璇曘?",
                file=sys.stderr,
            )
        else:
            hint = ERROR_HINTS.get(str(code))
            if hint:
                print(hint, file=sys.stderr)
        sys.exit(1)

    print(format_output(data, args.type))


if __name__ == "__main__":
    main()
