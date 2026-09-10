#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

from __future__ import annotations

"""Product module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_list_products(args):
    cli.print_result(cli.get_client().list_products(
        product_id=args.product_id,
        product_name=args.product_name,
        cloudphone_product_type=args.cloudphone_product_type,
        resource_type=args.resource_type,
        cloudphone_product_use_type=args.cloudphone_product_use_type,
        offset=args.offset,
        count=args.count,
    ))


def register(subparsers):
    list_products_parser = subparsers.add_parser('list-products', help='鑾峰彇涓氬姟鍒楄〃')
    list_products_parser.add_argument('--product-id', help='涓氬姟 ID')
    list_products_parser.add_argument('--product-name', help='涓氬姟鍚嶇О')
    list_products_parser.add_argument('--cloudphone-product-type', type=int, default=5, help='涓氬姟绫诲瀷锛?=IPaaS锛?=浜戞墜鏈?')
    list_products_parser.add_argument('--resource-type', type=int, help='璧勬簮绫诲瀷锛?00=浜戠洏瀛樺偍锛?00=鏈湴瀛樺偍')
    list_products_parser.add_argument('--cloudphone-product-use-type', type=int, help='鐢ㄩ€旓細1=浜戞墜鏈轰笟鍔★紝2=MUA涓氬姟')
    list_products_parser.add_argument('--offset', type=int, help='鍒嗛〉鍋忕Щ閲?')
    list_products_parser.add_argument('--count', type=int, help='鍗曢〉鏁伴噺')
    list_products_parser.set_defaults(func=cmd_list_products)
