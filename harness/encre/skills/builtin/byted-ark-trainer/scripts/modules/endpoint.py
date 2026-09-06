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
绔偣绠＄悊妯″潡
"""

import os
from dotenv import load_dotenv
from volcenginesdkark.api.ark_api import ARKApi
from volcenginesdkark.models.create_endpoint_request import CreateEndpointRequest
from volcenginesdkark.models.model_reference_for_create_endpoint_input import (
    ModelReferenceForCreateEndpointInput,
)
from volcenginesdkark.models.list_endpoints_request import ListEndpointsRequest
from volcenginesdkark.models.get_endpoint_request import GetEndpointRequest
from volcenginesdkark.models.get_endpoint_certificate_request import (
    GetEndpointCertificateRequest,
)
from volcenginesdkark.models.stop_endpoint_request import StopEndpointRequest
from volcenginesdkark.models.delete_endpoint_request import DeleteEndpointRequest
from volcenginesdkcore.configuration import Configuration


def init_api_client():
    """
    鍒濆鍖?API 瀹㈡埛绔?
    浠庣幆澧冨彉閲忚幏鍙栬璇佷俊鎭?
    """
    load_dotenv()
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")

    if not access_key or not secret_key:
        print("閿欒: 璇疯缃璇佷俊鎭?)
        print("璇疯缃幆澧冨彉閲?VOLCENGINE_ACCESS_KEY 鍜?VOLCENGINE_SECRET_KEY")
        return None

    # 
    config = Configuration()
    config.ak = access_key
    config.sk = secret_key
    config.region = "cn-beijing"
    config.endpoint = "ark.cn-beijing.volces.com"

    # 
    Configuration.set_default(config)

    #  Use parameterless constructor directly

    return ARKApi()


def create_endpoint(api, args):
    """
    鍒涘缓绔偣
    """
    print("=== 鍒涘缓绔偣 ===")

    # 
    model_reference = ModelReferenceForCreateEndpointInput()

    #  Use custom model ID

    if args.custom_model_id:
        model_reference.custom_model_id = args.custom_model_id
        print(f"浣跨敤鑷畾涔夋ā鍨? {args.custom_model_id}")
    else:
        print("閿欒: 璇锋彁渚?--custom-model-id 鍙傛暟")
        return None

    #  鏋勫缓Create endpoint璇锋眰

    request = CreateEndpointRequest(
        name=args.name,
        description=args.description,
        model_reference=model_reference,
        project_name=args.project_name,
    )

    try:
        response = api.create_endpoint(request)
        print(f"鍒涘缓鎴愬姛锛佺鐐笽D: {response.id}")
        return response.id
    except Exception as e:
        print(f"鍒涘缓澶辫触: {str(e)}")
        return None


def list_endpoints(api, args):
    """
    鍒楀嚭绔偣
    """
    print("\n=== 鍒楀嚭绔偣 ===")

    #  鏋勫缓List endpoints璇锋眰

    request = ListEndpointsRequest(
        page_size=args.page_size,
        page_number=args.page_number,
        project_name=args.project_name,
    )

    try:
        response = api.list_endpoints(request)
        print(f"鎵惧埌 {len(response.items)} 涓鐐?")
        for item in response.items:
            print(f"- ID: {item.id}, 鍚嶇О: {item.name}, 鐘舵€? {item.status}")
        return response.items
    except Exception as e:
        print(f"鍒楀嚭澶辫触: {str(e)}")
        return []


def get_endpoint(api, args):
    """
    鑾峰彇绔偣璇︽儏
    """
    print(f"\n=== 鑾峰彇绔偣璇︽儏 ({args.endpoint_id}) ===")

    # 
    request = GetEndpointRequest(id=args.endpoint_id)

    try:
        response = api.get_endpoint(request)
        print(f"绔偣鍚嶇О: {response.name}")
        print(f"绔偣鐘舵€? {response.status}")
        print(f"绔偣鎻忚堪: {response.description}")
        print(f"鍒涘缓鏃堕棿: {response.create_time}")
        if response.model_reference:
            if (
                hasattr(response.model_reference, "custom_model_id")
                and response.model_reference.custom_model_id
            ):
                print(f"鑷畾涔夋ā鍨婭D: {response.model_reference.custom_model_id}")
        return response
    except Exception as e:
        print(f"鑾峰彇澶辫触: {str(e)}")
        return None


def get_endpoint_certificate(api, args):
    """
    鑾峰彇绔偣璇佷功
    """
    print(f"\n=== 鑾峰彇绔偣璇佷功 ({args.endpoint_id}) ===")

    # 
    request = GetEndpointCertificateRequest(id=args.endpoint_id)

    try:
        response = api.get_endpoint_certificate(request)
        print(f"璇佷功鏈夋晥鏈熶粠: {response.not_before}")
        print(f"璇佷功鏈夋晥鏈熻嚦: {response.not_after}")
        print(f"PCA鍚嶇О: {response.pca_name}")
        print(f"PCA涓绘満: {response.pca_host}")
        return response
    except Exception as e:
        print(f"鑾峰彇澶辫触: {str(e)}")
        return None


def stop_endpoint(api, args):
    """
    鍋滄绔偣
    """
    print(f"\n=== 鍋滄绔偣 ({args.endpoint_id}) ===")

    # 
    request = StopEndpointRequest(id=args.endpoint_id)

    try:
        response = api.stop_endpoint(request)
        print("鍋滄璇锋眰宸叉垚鍔熸彁浜?)
        return response
    except Exception as e:
        print(f"鍋滄澶辫触: {str(e)}")
        return None


def delete_endpoint(api, args):
    """
    鍒犻櫎绔偣
    """
    print(f"\n=== 鍒犻櫎绔偣 ({args.endpoint_id}) ===")

    # 
    request = DeleteEndpointRequest(id=args.endpoint_id)

    try:
        response = api.delete_endpoint(request)
        print("鍒犻櫎璇锋眰宸叉垚鍔熸彁浜?)
        return response
    except Exception as e:
        print(f"鍒犻櫎澶辫触: {str(e)}")
        return None
