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

"""
基础模型管理模块
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

# 加载.env文件配置
load_dotenv()


# ARK API通用请求函数 - 可复用
def ark_api_request(action, method="POST", body=None, params=None):
    """
    通用ARK API请求函数，自动处理签名
    :param action: API操作名称，例如 ListFoundationModels
    :param method: HTTP方法，默认POST
    :param body: 请求体字典
    :param params: URL查询参数字典
    :return: 响应JSON字典
    """
    # 从环境变量获取凭证信息
    ak = os.getenv("VOLCENGINE_ACCESS_KEY")
    sk = os.getenv("VOLCENGINE_SECRET_KEY")
    region = os.getenv("ARK_REGION") or os.getenv("REGION") or "cn-beijing"
    session_token = os.getenv("ARK_SESSION_TOKEN") or os.getenv("SESSION_TOKEN")

    if not ak or not sk:
        raise ValueError("请配置VOLCENGINE_ACCESS_KEY和VOLCENGINE_SECRET_KEY环境变量")

    # 服务配置
    service = "ark"
    version = "2024-01-01"
    host = f"ark.{region}.volcengineapi.com"
    content_type = "application/json; charset=utf-8"

    # 处理请求体
    request_body = json.dumps(body) if body else ""

    # 处理查询参数
    query_params = params or {}
    query_params.update(
        {
            "Action": action,
            "Version": version,
        }
    )

    # 获取当前时间
    now = utc_now()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]

    # 计算签名
    x_content_sha256 = hash_sha256(request_body)
    sign_result = {
        "Host": host,
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": content_type,
    }

    # 如果有安全令牌，添加到请求头
    if session_token:
        sign_result["X-Security-Token"] = session_token

    # 构建正规化请求
    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    if "X-Security-Token" in sign_result:
        signed_headers_list.append("x-security-token")

    signed_headers_str = ";".join(sorted(signed_headers_list))

    # 构建签名用的headers字符串
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

    # 计算签名
    k_date = hmac_sha256(sk.encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()

    # 构建Authorization头
    sign_result["Authorization"] = (
        "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
            ak + "/" + credential_scope,
            signed_headers_str,
            signature,
        )
    )

    # 发送请求
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


# 签名辅助函数
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
    列出符合条件的基础模型列表
    """
    print("\n=== 查询基础模型列表 ===")
    try:
        # 构建请求参数
        filter_params = {"FoundationModelTag": {"Domains": ["LLM"]}}

        # 添加名称模糊查询
        if args.name:
            filter_params["Name"] = args.name

        # 添加支持的训练类型筛选
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

        # 调用通用API请求函数
        resp_data = ark_api_request(
            action="ListFoundationModels", method="POST", body=request_body
        )

        # 处理响应
        result = resp_data.get("Result", {})
        items = result.get("Items", [])
        total_count = result.get("TotalCount", len(items))
        print(f"查询到 {total_count} 个基础模型（当前页{len(items)}个）:")
        print("-" * 150)
        print(f"{'模型名称':<30} {'主版本':<15} {'描述'}")
        print("-" * 150)

        for item in items:
            model_name = item.get("Name", "未知")
            primary_version = item.get("PrimaryVersion", "未知")
            description = item.get("Description", item.get("DisplayDescription", ""))

            # 截断过长的描述
            if len(description) > 200:
                description = description[:197] + "..."

            print(f"{model_name:<30} {primary_version:<15} {description}")

        return items
    except requests.exceptions.RequestException as e:
        print(f"查询失败: HTTP请求错误 - {str(e)}")
        if hasattr(e, "response") and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return None
    except Exception as e:
        print(f"查询失败: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def list_foundation_model_versions(args):
    """
    列出基础模型的所有可用版本
    """
    print(f"\n=== 查询基础模型版本列表 ({args.model_name}) ===")
    try:
        # 模型名称中的点替换为横杠
        model_name = args.model_name.replace(".", "-")

        req = ListFoundationModelVersionsRequest(
            FoundationModelName=model_name,
            PageSize=args.page_size,
            PageNumber=args.page_number,
        )
        ark_client = default_ark_client()
        resp = ark_client.list_foundation_model_versions(req)

        print(f"基础模型: {args.model_name}")
        # 兼容不同版本SDK的字段名
        items = getattr(resp, "Items", getattr(resp, "items", []))
        total = len(items)
        print(f"总共有 {total} 个版本:")
        print("-" * 100)
        print(f"{'版本号':<25} {'状态':<10} {'创建时间':<25} {'描述'}")
        print("-" * 100)

        for item in items:
            # 将item转为字典获取所有字段
            item_dict = (
                item.model_dump()
                if hasattr(item, "model_dump")
                else item.dict()
                if hasattr(item, "dict")
                else dict(item)
            )
            # 尝试所有可能的字段名
            model_version = item_dict.get(
                "ModelVersion", item_dict.get("model_version", "未知")
            )
            status = item_dict.get("Status", item_dict.get("status", "未知"))
            create_time = item_dict.get(
                "CreateTime", item_dict.get("create_time", "未知")
            )
            description = item_dict.get("Description", item_dict.get("description", ""))
            print(
                f"{model_version:<25} {status:<10} {create_time:<25} {description or ''}"
            )

        return resp.Items
    except Exception as e:
        print(f"查询失败: {str(e)}")
        return None
