# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

#!/usr/bin/env python3
from __future__ import annotations

"""鐏北寮曟搸鐭俊鍙戦€?API - openclaw涓撶敤鎺ュ彛 (2026-01-01).

Version: 2026-01-01
鍒嗙粍: openclaw涓撶敤

6涓帴鍙?
    - send_sms: 鍙戦€佺煭淇?
    - list_sms_send_log: 鏌ヨ鍙戦€佽褰?
    - list_sub_account: 鏌ヨ娑堟伅缁勫垪琛?
    - list_signature: 鏌ヨ绛惧悕鍒楄〃
    - list_sms_template: 鏌ヨ妯℃澘鍒楄〃
    - list_total_send_count_stat: 鏌ヨ鍙戦€佺粺璁?

Usage:
    python volc_sms.py <action> [options]

Examples:
    #  Send SMS

    python volc_sms.py send_sms \
        --sub-account 77da1acf --signature "鐏北寮曟搸" --template-id "ST_xxx" \
        --mobiles "13800138000" --template-param '{"code":"123456"}'

    # 
    python volc_sms.py list_sub_account

    #  Query signatures

    python volc_sms.py list_signature --signature "鐏北寮曟搸"

    #  Query templates

    python volc_sms.py list_sms_template --signatures "鐏北寮曟搸"

    #  Query send records

    python volc_sms.py list_sms_send_log \
        --sub-account 77da1acf --from-time 1773113285 --to-time 1773213285

    #  Query send statistics

    python volc_sms.py list_total_send_count_stat \
        --start-time 1773113285 --end-time 1773213285
"""

import argparse
import json
import os
import sys

SERVICE = "volcSMS"
VERSION = "2026-01-01"


def get_credentials() -> tuple:
    api_key = os.getenv("ARK_SKILL_API_KEY")
    api_base = os.getenv("ARK_SKILL_API_BASE")
    if not api_key or not api_base:
        raise ValueError(
            "鏈壘鍒板嚟璇侊紝璇疯缃幆澧冨彉閲?ARK_SKILL_API_KEY 鍜?ARK_SKILL_API_BASE\n"
            "閰嶇疆鏂囦欢浣嶇疆: /root/.openclaw/.env\n"
            "绀轰緥:\n"
            "  ARK_SKILL_API_KEY=sk-xxxx\n"
            "  ARK_SKILL_API_BASE=http://xxx"
        )
    return api_key, api_base


def call_api(action: str, body: dict) -> dict:
    try:
        import requests
    except ImportError:
        print("Error: requests not installed. Run: pip install requests", file=sys.stderr)
        sys.exit(1)

    api_key, api_base = get_credentials()
    
    api_base = api_base.rstrip("/")
    
    url = f"{api_base}?Action={action}&Version={VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "ServiceName": SERVICE,
        "Authorization": f"Bearer {api_key}",
    }
    
    body_str = json.dumps(body, ensure_ascii=False)
    
    response = requests.post(url, headers=headers, data=body_str.encode("utf-8"), timeout=30)
    response.raise_for_status()
    return response.json()


def send_sms(args) -> dict:
    """鍙戦€佺煭淇?(SendSmsForAgent).

    Request:
        "Account": "",
        "SubAccount": "",
        "Signature": "",
        "TemplateId": "",
        "Mobiles": "",
        "TemplateParam": ""

    Response:
        "MessageIds": ["xxx", "xxx"]
    """
    body = {
        "SubAccount": args.sub_account,
        "Signature": args.signature,
        "TemplateId": args.template_id,
        "Mobiles": args.mobiles,
    }

    if args.account:
        body["Account"] = args.account
    if args.template_param:
        body["TemplateParam"] = args.template_param

    return call_api("SendSmsForAgent", body)


def list_sms_send_log(args) -> dict:
    """鏌ヨ鍙戦€佽褰?(ListSmsSendLogForAgent).

    Request:
        "SubAccount": "",
        "FromTime": 1773113285,
        "ToTime": 1773113285,
        "Mobile": "",
        "TemplateId": "",
        "Signature": "",
        "MessageId": "",
        "Page": 1,
        "PageSize": 100

    Response:
        "Total": 123,
        "List": [...]
    """
    body = {
        "SubAccount": args.sub_account,
        "Page": args.page,
        "PageSize": args.page_size,
    }

    if args.from_time:
        body["FromTime"] = args.from_time
    if args.to_time:
        body["ToTime"] = args.to_time
    if args.mobile:
        body["Mobile"] = args.mobile
    if args.template_id:
        body["TemplateId"] = args.template_id
    if args.signature:
        body["Signature"] = args.signature
    if args.message_id:
        body["MessageId"] = args.message_id

    return call_api("ListSmsSendLogForAgent", body)


def list_sub_account(args) -> dict:
    """鏌ヨ娑堟伅缁勫垪琛?(ListSubAccountForAgent).

    璇存槑: 鍙繑鍥炲鏍搁€氳繃鐨勬秷鎭粍

    Request:
        "SubAccountName": ""

    Response:
        "Total": 123,
        "List": [{"SubAccountName": "", "SubAccount": ""}]
    """
    body = {}
    if args.sub_account_name:
        body["SubAccountName"] = args.sub_account_name
    return call_api("ListSubAccountForAgent", body)


def list_signature(args) -> dict:
    """鏌ヨ绛惧悕鍒楄〃 (ListSignatureForAgent).

    璇存槑: 杩斿洖瀹℃牳閫氳繃鐨勭鍚?

    Request:
        "Signature": "qm",
        "SubAccounts": ["a", "b"],
        "Page": 1,
        "PageSize": 2

    Response:
        "Total": 100,
        "List": [{"Signature": "", "Description": "", "Status": 1, ...}]
    """
    body = {
        "Page": args.page,
        "PageSize": args.page_size,
    }

    if args.signature:
        body["Signature"] = args.signature
    if args.sub_accounts:
        body["SubAccounts"] = args.sub_accounts.split(",")

    return call_api("ListSignatureForAgent", body)


def list_sms_template(args) -> dict:
    """鏌ヨ妯℃澘鍒楄〃 (ListSmsTemplateForAgent).

    璇存槑: 杩斿洖瀹℃牳閫氳繃鐨勬ā鏉夸俊鎭?

    Request:
        "TemplateId": "qm",
        "SubAccounts": ["a", "b"],
        "Signatures": ["aqm", "bqm"],
        "Page": 1,
        "PageSize": 2

    Response:
        "Total": 100,
        "List": [{"TemplateId": "", "SecondTemplateId": "", ...}]
    """
    body = {
        "Page": args.page,
        "PageSize": args.page_size,
    }

    if args.template_id:
        body["TemplateId"] = args.template_id
    if args.sub_accounts:
        body["SubAccounts"] = args.sub_accounts.split(",")
    if args.signatures:
        body["Signatures"] = args.signatures.split(",")

    return call_api("ListSmsTemplateForAgent", body)


def list_total_send_count_stat(args) -> dict:
    """鏌ヨ鍙戦€佺粺璁?(ListTotalSendCountStatForAgent).

    Request:
        "StartTime": 16934224000,
        "EndTime": 16934224000,
        "SubAccount": "",
        "ChannelType": "",
        "Signature": "",
        "TemplateId": ""

    Response:
        "TotalSendCount": 1122,
        "TotalSendSuccessCount": 120,
        "TotalAllSendCount": 123,
        "TotalReceiptSuccessCount": 123,
        "TotalReceiptFailureCount": 123,
        "TotalSendSuccessRate": 0.87,
        "TotalReceiptSuccessRate": 0.99
    """
    body = {
        "StartTime": args.start_time,
        "EndTime": args.end_time,
    }

    if args.sub_account:
        body["SubAccount"] = args.sub_account
    if args.channel_type:
        body["ChannelType"] = args.channel_type
    if args.signature:
        body["Signature"] = args.signature
    if args.template_id:
        body["TemplateId"] = args.template_id

    return call_api("ListTotalSendCountStatForAgent", body)


def main():
    parser = argparse.ArgumentParser(
        description="鐏北寮曟搸鐭俊鍙戦€?API (openclaw涓撶敤)\nVersion: 2026-01-01",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("action", help="鎿嶄綔: send_sms, list_sms_send_log, list_sub_account, list_signature, list_sms_template, list_total_send_count_stat")

    # send_sms
    parser.add_argument("--account", help="璐﹀彿")
    parser.add_argument("--sub-account", help="瀛愯处鍙?娑堟伅缁処D")
    parser.add_argument("--signature", help="鐭俊绛惧悕")
    parser.add_argument("--template-id", help="鐭俊妯℃澘ID")
    parser.add_argument("--mobiles", help="鎵嬫満鍙?閫楀彿鍒嗛殧)")
    parser.add_argument("--template-param", help="妯℃澘鍙傛暟JSON")

    # list_sms_send_log
    parser.add_argument("--from-time", type=int, help="寮€濮嬫椂闂存埑")
    parser.add_argument("--to-time", type=int, help="缁撴潫鏃堕棿鎴?")
    parser.add_argument("--mobile", help="鎵嬫満鍙?")
    parser.add_argument("--message-id", help="娑堟伅ID")
    parser.add_argument("--page", type=int, default=1, help="椤电爜")
    parser.add_argument("--page-size", type=int, default=100, help="姣忛〉鏁伴噺")

    # list_sub_account
    parser.add_argument("--sub-account-name", help="娑堟伅缁勫悕绉?妯＄硦鍖归厤)")

    # list_signature
    parser.add_argument("--sub-accounts", help="瀛愯处鍙峰垪琛?閫楀彿鍒嗛殧)")

    # list_sms_template
    parser.add_argument("--signatures", help="绛惧悕鍒楄〃(閫楀彿鍒嗛殧)")

    # list_total_send_count_stat
    parser.add_argument("--start-time", type=int, help="寮€濮嬫椂闂存埑")
    parser.add_argument("--end-time", type=int, help="缁撴潫鏃堕棿鎴?")
    parser.add_argument("--channel-type", help="閫氶亾绫诲瀷")

    args = parser.parse_args()

    action_map = {
        "send_sms": send_sms,
        "list_sms_send_log": list_sms_send_log,
        "list_sub_account": list_sub_account,
        "list_signature": list_signature,
        "list_sms_template": list_sms_template,
        "list_total_send_count_stat": list_total_send_count_stat,
    }

    if args.action not in action_map:
        print(f"Error: 鏈煡鐨勬搷浣?{args.action}", file=sys.stderr)
        print(f"鏀寔鐨勬搷浣滀负: {', '.join(action_map.keys())}", file=sys.stderr)
        sys.exit(1)

    try:
        result = action_map[args.action](args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        response = getattr(exc, "response", None)
        if response is not None:
            print(f"HTTP Error: {exc}", file=sys.stderr)
            response_text = getattr(response, "text", None)
            if response_text:
                print(response_text, file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
