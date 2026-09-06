#!/usr/bin/env python3
# coding: utf-8
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

"""
鍩虹妯″瀷绠＄悊妯″潡
"""

import os
import json
import datetime
import hashlib
import hmac
from urllib.parse import quote
import requests
from dotenv import load_dotenv
from ark_sdk.core.client.ark import default_ark_client
from ark_sdk.types.foundation_model.foundation_model import (
    ListFoundationModelVersionsRequest,
)

# .env
load_dotenv()


# ARK API -
def ark_api_request(action, method="POST", body=None, params=None):
    """
    閫氱敤ARK API璇锋眰鍑芥暟锛岃嚜鍔ㄥ鐞嗙鍚?
    :param action: API鎿嶄綔鍚嶇О锛屼緥濡?ListFoundationModels
    :param method: HTTP鏂规硶锛岄粯璁OST
    :param body: 璇锋眰浣撳瓧鍏?
    :param params: URL鏌ヨ鍙傛暟瀛楀吀
    :return: 鍝嶅簲JSON瀛楀吀
    """
    #  浠庣幆澧冨彉閲廏et credentials淇℃伅

    ak = os.getenv("VOLCENGINE_ACCESS_KEY")
    sk = os.getenv("VOLCENGINE_SECRET_KEY")
    region = os.getenv("ARK_REGION") or os.getenv("REGION") or "cn-beijing"
    session_token = os.getenv("ARK_SESSION_TOKEN") or os.getenv("SESSION_TOKEN")

    if not ak or not sk:
        raise ValueError("璇烽厤缃甐OLCENGINE_ACCESS_KEY鍜孷OLCENGINE_SECRET_KEY鐜鍙橀噺")

    # 
    service = "ark"
    version = "2024-01-01"
    host = f"ark.{region}.volcengineapi.com"
    content_type = "application/json; charset=utf-8"

    # 
    request_body = json.dumps(body) if body else ""

    # 
    query_params = params or {}
    query_params.update(
        {
            "Action": action,
            "Version": version,
        }
    )

    #  Get current time

    now = utc_now()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]

    # 
    x_content_sha256 = hash_sha256(request_body)
    sign_result = {
        "Host": host,
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": content_type,
    }

    # 锛?
    if session_token:
        sign_result["X-Security-Token"] = session_token

    # 
    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    if "X-Security-Token" in sign_result:
        signed_headers_list.append("x-security-token")

    signed_headers_str = ";".join(sorted(signed_headers_list))

    #  鏋勫缓绛惧悕鐢ㄧ殑headersString

    header_key_map = {
        "content-type": "Content-Type",
        "host": "Host",
        "x-content-sha256": "X-Content-Sha256",
        "x-date": "X-Date",
        "x-security-token": os.getenv("X-Security-Token", ""),
    }
    header_lines = []
    for header_key in sorted(signed_headers_list):
        header_value = sign_result[header_key_map[header_key]]
        header_lines.append(f"{header_key}:{header_value}")

    canonical_headers_str = "\n".join(header_lines)

    canonical_request_str = "\n".join(
        [
            method.upper(),
            "/",
            norm_query(query_params),
            canonical_headers_str,
            "",
            signed_headers_str,
            x_content_sha256,
        ]
    )

    hashed_canonical_request = hash_sha256(canonical_request_str)
    credential_scope = "/".join([short_x_date, region, service, "request"])
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    # 
    k_date = hmac_sha256(sk.encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()

    # Authorization
    sign_result["Authorization"] = (
        "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
            ak + "/" + credential_scope,
            signed_headers_str,
            signature,
        )
    )

    # 
    response = requests.request(
        method=method,
        url=f"https://{host}/",
        headers=sign_result,
        params=query_params,
        data=request_body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# 
def norm_query(params):
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for k in params[key]:
                query = (
                    query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&"
                )
        else:
            query = (
                query
                + quote(key, safe="-_.~")
                + "="
                + quote(params[key], safe="-_.~")
                + "&"
            )
    query = query[:-1]
    return query.replace("+", "%20")


def hmac_sha256(key: bytes, content: str):
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def hash_sha256(content: str):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def utc_now():
    try:
        from datetime import timezone

        return datetime.datetime.now(timezone.utc)
    except ImportError:

        class UTC(datetime.tzinfo):
            def utcoffset(self, dt):
                return datetime.timedelta(0)

            def tzname(self, dt):
                return "UTC"

            def dst(self, dt):
                return datetime.timedelta(0)

        return datetime.datetime.now(UTC())


def list_foundation_models(args):
    """
    鍒楀嚭绗﹀悎鏉′欢鐨勫熀纭€妯″瀷鍒楄〃
    """
    print("\n=== 鏌ヨ鍩虹妯″瀷鍒楄〃 ===")
    try:
        #  Build request鍙傛暟

        filter_params = {"FoundationModelTag": {"Domains": ["LLM"]}}

        # 
        if args.name:
            filter_params["Name"] = args.name

        # 
        if args.supported_customization_type:
            filter_params["SupportedCustomizationTypes"] = [
                args.supported_customization_type
            ]

        request_body = {
            "Filter": filter_params,
            "PageNumber": args.page_number,
            "PageSize": args.page_size,
            "SortBy": "CreateTime",
            "SortOrder": "Desc",
        }

        # API
        resp_data = ark_api_request(
            action="ListFoundationModels", method="POST", body=request_body
        )

        # 
        result = resp_data.get("Result", {})
        items = result.get("Items", [])
        total_count = result.get("TotalCount", len(items))
        print(f"鏌ヨ鍒?{total_count} 涓熀纭€妯″瀷锛堝綋鍓嶉〉{len(items)}涓級:")
        print("-" * 150)
        print(f"{'妯″瀷鍚嶇О':<30} {'涓荤増鏈?:<15} {'鎻忚堪'}")
        print("-" * 150)

        for item in items:
            model_name = item.get("Name", "鏈煡")
            primary_version = item.get("PrimaryVersion", "鏈煡")
            description = item.get("Description", item.get("DisplayDescription", ""))

            # 
            if len(description) > 200:
                description = description[:197] + "..."

            print(f"{model_name:<30} {primary_version:<15} {description}")

        return items
    except requests.exceptions.RequestException as e:
        print(f"鏌ヨ澶辫触: HTTP璇锋眰閿欒 - {str(e)}")
        if hasattr(e, "response") and e.response is not None:
            print(f"鍝嶅簲鍐呭: {e.response.text}")
        return None
    except Exception as e:
        print(f"鏌ヨ澶辫触: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def list_foundation_model_versions(args):
    """
    鍒楀嚭鍩虹妯″瀷鐨勬墍鏈夊彲鐢ㄧ増鏈?
    """
    print(f"\n=== 鏌ヨ鍩虹妯″瀷鐗堟湰鍒楄〃 ({args.model_name}) ===")
    try:
        # 
        model_name = args.model_name.replace(".", "-")

        req = ListFoundationModelVersionsRequest(
            FoundationModelName=model_name,
            PageSize=args.page_size,
            PageNumber=args.page_number,
        )
        ark_client = default_ark_client()
        resp = ark_client.list_foundation_model_versions(req)

        print(f"鍩虹妯″瀷: {args.model_name}")
        # SDK
        items = getattr(resp, "Items", getattr(resp, "items", []))
        total = len(items)
        print(f"鎬诲叡鏈?{total} 涓増鏈?")
        print("-" * 100)
        print(f"{'鐗堟湰鍙?:<25} {'鐘舵€?:<10} {'鍒涘缓鏃堕棿':<25} {'鎻忚堪'}")
        print("-" * 100)

        for item in items:
            # item
            item_dict = (
                item.model_dump()
                if hasattr(item, "model_dump")
                else item.dict()
                if hasattr(item, "dict")
                else dict(item)
            )
            # 
            model_version = item_dict.get(
                "ModelVersion", item_dict.get("model_version", "鏈煡")
            )
            status = item_dict.get("Status", item_dict.get("status", "鏈煡"))
            create_time = item_dict.get(
                "CreateTime", item_dict.get("create_time", "鏈煡")
            )
            description = item_dict.get("Description", item_dict.get("description", ""))
            print(
                f"{model_version:<25} {status:<10} {create_time:<25} {description or ''}"
            )

        return resp.Items
    except Exception as e:
        print(f"鏌ヨ澶辫触: {str(e)}")
        return None
