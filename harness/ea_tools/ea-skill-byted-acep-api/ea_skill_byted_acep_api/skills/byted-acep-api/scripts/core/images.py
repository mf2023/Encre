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

"""Image module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_list_image_resources(args):
    cli.print_result(cli.get_client().list_image_resources(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        ImageIdList=args.image_id_list,
    ))


def cmd_get_image_preheating(args):
    cli.print_result(cli.get_client().get_image_preheating(
        image_id_list=cli.parse_csv_values(args.image_id_list),
        product_id=args.product_id,
        dc_id=args.dc_id,
    ))


def cmd_list_aosp_images(args):
    image_id_list = cli.parse_csv(args.image_id_list) if args.image_id_list else None
    cli.print_result(cli.get_client().list_aosp_images(
        product_id=args.product_id,
        image_id_list=image_id_list,
        image_name=args.image_name,
        aosp_version=args.aosp_version,
        is_public=args.is_public,
        image_status=args.image_status,
        expand_scope=args.expand_scope,
        max_results=args.max_results,
        next_token=args.next_token,
        PlatformType=args.platform_type,
    ))


def cmd_delete_aosp_image(args):
    cli.print_result(cli.get_client().delete_aosp_image(
        image_id_list=cli.parse_csv_values(args.image_id_list),
        product_id=args.product_id,
    ))


def cmd_update_aosp_image(args):
    cli.print_result(cli.get_client().update_aosp_image(
        image_id=args.image_id,
        product_id=args.product_id,
        image_name=args.image_name,
        image_annotation=args.image_annotation,
    ))


def cmd_create_image_one_step(args):
    cli.print_result(cli.get_client().create_image_one_step(
        image_id=args.image_id,
        product_id=args.product_id,
        image_name=args.image_name,
        image_annotation=args.image_annotation,
        file_url=args.file_url,
    ))


def cmd_build_aosp_image(args):
    cli.print_result(cli.get_client().build_aosp_image(
        product_id=args.product_id,
        image_name=args.image_name,
        image_annotation=args.image_annotation,
        image_file_format=args.image_file_format,
        system_url=args.system_url,
        vendor_url=args.vendor_url,
    ))


def register(subparsers):

    list_image_resources_parser = subparsers.add_parser('list-image-resources', help='鏌ヨ闀滃儚鍒嗗竷')
    list_image_resources_parser.add_argument('product_id', help='浜у搧 ID')
    list_image_resources_parser.add_argument('--image-id-list', help='闀滃儚 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_image_resources_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_image_resources_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_image_resources_parser.set_defaults(func=cmd_list_image_resources)

    get_image_preheating_parser = subparsers.add_parser('get-image-preheating', help='鏌ヨ闀滃儚棰勭儹淇℃伅')
    get_image_preheating_parser.add_argument('product_id', help='浜у搧 ID')
    get_image_preheating_parser.add_argument('image_id_list', help='闀滃儚 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    get_image_preheating_parser.add_argument('--dc-id', help='鏈烘埧 ID')
    get_image_preheating_parser.set_defaults(func=cmd_get_image_preheating)

    list_aosp_images_parser = subparsers.add_parser('list-aosp-images', help='鏌ヨ AOSP 闀滃儚鍒楄〃锛堝叕鍏遍暅鍍忎娇鐢?--is-public锛?')
    list_aosp_images_parser.add_argument('product_id', help='浜у搧 ID')
    list_aosp_images_parser.add_argument('--image-id-list', help='闀滃儚 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_aosp_images_parser.add_argument('--image-name', help='闀滃儚鍚嶇О')
    list_aosp_images_parser.add_argument('--aosp-version', choices=['10', '11', '12', '13'], help='AOSP 鐗堟湰')
    list_aosp_images_parser.add_argument('--is-public', action='store_true', help='鏌ヨ鍏叡闀滃儚锛涗笉浼犲垯鏌ヨ鑷畾涔夐暅鍍?')
    list_aosp_images_parser.add_argument('--image-status', type=int, help='闀滃儚鐘舵€侊細1=瀵煎叆/寰呮瀯寤猴紝2=鏋勫缓涓紝11=鏋勫缓瀹屾垚锛?1=鏋勫缓澶辫触')
    list_aosp_images_parser.add_argument('--expand-scope', action='store_true', help='鏌ヨ鍏叡闀滃儚鏃跺寘鍚湭鍙戝竷闀滃儚锛岄渶绮剧‘浼?ImageIdList')
    list_aosp_images_parser.add_argument('--platform-type', choices=['g2', 'g3'], help='鑺墖绫诲瀷')
    list_aosp_images_parser.add_argument('--max-results', type=int, default=10, help='鍒嗛〉澶у皬锛?-100')
    list_aosp_images_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_aosp_images_parser.set_defaults(func=cmd_list_aosp_images)

    delete_aosp_image_parser = subparsers.add_parser('delete-aosp-image', help='鍒犻櫎 AOSP 闀滃儚')
    delete_aosp_image_parser.add_argument('product_id', help='浜у搧 ID')
    delete_aosp_image_parser.add_argument('--image-id-list', required=True, help='闀滃儚 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    delete_aosp_image_parser.set_defaults(func=cmd_delete_aosp_image)

    update_aosp_image_parser = subparsers.add_parser('update-aosp-image', help='鏇存柊 AOSP 闀滃儚')
    update_aosp_image_parser.add_argument('product_id', help='浜у搧 ID')
    update_aosp_image_parser.add_argument('--image-id', required=True, help='闀滃儚 ID')
    update_aosp_image_parser.add_argument('--image-name', help='闀滃儚鍚嶇О')
    update_aosp_image_parser.add_argument('--image-annotation', help='闀滃儚澶囨敞')
    update_aosp_image_parser.set_defaults(func=cmd_update_aosp_image)

    create_image_one_step_parser = subparsers.add_parser('create-image-one-step', help='闀滃儚鍐呯疆搴旂敤/鏂囦欢')
    create_image_one_step_parser.add_argument('product_id', help='浜у搧 ID')
    create_image_one_step_parser.add_argument('--image-id', required=True, help='鍩虹嚎闀滃儚 ID')
    create_image_one_step_parser.add_argument('--image-name', help='鏂伴暅鍍忓悕绉?')
    create_image_one_step_parser.add_argument('--image-annotation', help='闀滃儚澶囨敞')
    create_image_one_step_parser.add_argument('--file-url', help='鍐呯疆搴旂敤鎴栨枃浠朵笅杞藉湴鍧€')
    create_image_one_step_parser.set_defaults(func=cmd_create_image_one_step)

    build_aosp_image_parser = subparsers.add_parser('build-aosp-image', help='鏋勫缓 AOSP 闀滃儚')
    build_aosp_image_parser.add_argument('product_id', help='浜у搧 ID')
    build_aosp_image_parser.add_argument('--image-name', help='闀滃儚鍚嶇О')
    build_aosp_image_parser.add_argument('--image-annotation', help='闀滃儚澶囨敞')
    build_aosp_image_parser.add_argument('--image-file-format', choices=['volc_tos', 'url'], help='闀滃儚鏂囦欢鏍煎紡')
    build_aosp_image_parser.add_argument('--system-url', help='system 闀滃儚 URL锛涘鏉?TOS 鍙傛暟闇€琛ュ厖涓撶敤鍛戒护鏀寔')
    build_aosp_image_parser.add_argument('--vendor-url', help='vendor 闀滃儚 URL锛涘鏉?TOS 鍙傛暟闇€琛ュ厖涓撶敤鍛戒护鏀寔')
    build_aosp_image_parser.set_defaults(func=cmd_build_aosp_image)
