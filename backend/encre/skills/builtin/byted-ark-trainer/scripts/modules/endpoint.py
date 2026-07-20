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
端点管理模块
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
    初始化 API 客户端
    从环境变量获取认证信息
    """
    load_dotenv()
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")

    if not access_key or not secret_key:
        print("错误: 请设置认证信息")
        print("请设置环境变量 VOLCENGINE_ACCESS_KEY 和 VOLCENGINE_SECRET_KEY")
        return None

    # 创建配置
    config = Configuration()
    config.ak = access_key
    config.sk = secret_key
    config.region = "cn-beijing"
    config.endpoint = "ark.cn-beijing.volces.com"

    # 设置默认配置
    Configuration.set_default(config)

    # 直接使用无参数构造函数
    return ARKApi()


def create_endpoint(api, args):
    """
    创建端点
    """
    print("=== 创建端点 ===")

    # 构建模型引用
    model_reference = ModelReferenceForCreateEndpointInput()

    # 使用自定义模型ID
    if args.custom_model_id:
        model_reference.custom_model_id = args.custom_model_id
        print(f"使用自定义模型: {args.custom_model_id}")
    else:
        print("错误: 请提供 --custom-model-id 参数")
        return None

    # 构建创建端点请求
    request = CreateEndpointRequest(
        name=args.name,
        description=args.description,
        model_reference=model_reference,
        project_name=args.project_name,
    )

    try:
        response = api.create_endpoint(request)
        print(f"创建成功！端点ID: {response.id}")
        return response.id
    except Exception as e:
        print(f"创建失败: {str(e)}")
        return None


def list_endpoints(api, args):
    """
    列出端点
    """
    print("\n=== 列出端点 ===")

    # 构建列出端点请求
    request = ListEndpointsRequest(
        page_size=args.page_size,
        page_number=args.page_number,
        project_name=args.project_name,
    )

    try:
        response = api.list_endpoints(request)
        print(f"找到 {len(response.items)} 个端点:")
        for item in response.items:
            print(f"- ID: {item.id}, 名称: {item.name}, 状态: {item.status}")
        return response.items
    except Exception as e:
        print(f"列出失败: {str(e)}")
        return []


def get_endpoint(api, args):
    """
    获取端点详情
    """
    print(f"\n=== 获取端点详情 ({args.endpoint_id}) ===")

    # 构建获取端点请求
    request = GetEndpointRequest(id=args.endpoint_id)

    try:
        response = api.get_endpoint(request)
        print(f"端点名称: {response.name}")
        print(f"端点状态: {response.status}")
        print(f"端点描述: {response.description}")
        print(f"创建时间: {response.create_time}")
        if response.model_reference:
            if (
                hasattr(response.model_reference, "custom_model_id")
                and response.model_reference.custom_model_id
            ):
                print(f"自定义模型ID: {response.model_reference.custom_model_id}")
        return response
    except Exception as e:
        print(f"获取失败: {str(e)}")
        return None


def get_endpoint_certificate(api, args):
    """
    获取端点证书
    """
    print(f"\n=== 获取端点证书 ({args.endpoint_id}) ===")

    # 构建获取端点证书请求
    request = GetEndpointCertificateRequest(id=args.endpoint_id)

    try:
        response = api.get_endpoint_certificate(request)
        print(f"证书有效期从: {response.not_before}")
        print(f"证书有效期至: {response.not_after}")
        print(f"PCA名称: {response.pca_name}")
        print(f"PCA主机: {response.pca_host}")
        return response
    except Exception as e:
        print(f"获取失败: {str(e)}")
        return None


def stop_endpoint(api, args):
    """
    停止端点
    """
    print(f"\n=== 停止端点 ({args.endpoint_id}) ===")

    # 构建停止端点请求
    request = StopEndpointRequest(id=args.endpoint_id)

    try:
        response = api.stop_endpoint(request)
        print("停止请求已成功提交")
        return response
    except Exception as e:
        print(f"停止失败: {str(e)}")
        return None


def delete_endpoint(api, args):
    """
    删除端点
    """
    print(f"\n=== 删除端点 ({args.endpoint_id}) ===")

    # 构建删除端点请求
    request = DeleteEndpointRequest(id=args.endpoint_id)

    try:
        response = api.delete_endpoint(request)
        print("删除请求已成功提交")
        return response
    except Exception as e:
        print(f"删除失败: {str(e)}")
        return None
