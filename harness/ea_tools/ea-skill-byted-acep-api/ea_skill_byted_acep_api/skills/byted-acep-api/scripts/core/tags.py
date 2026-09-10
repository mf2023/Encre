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

"""Tags module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_list_tags(args):
    cli.print_result(cli.get_client().list_tags(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        TagName=args.tag_name,
        TagNameFuzzy=args.tag_name_fuzzy,
    ))


def cmd_create_tag(args):
    cli.print_result(cli.get_client().create_tag(
        tag_name=args.tag_name,
        product_id=args.product_id,
        tag_desc=args.tag_desc,
    ))


def cmd_update_tag(args):
    cli.print_result(cli.get_client().update_tag(
        tag_id=args.tag_id,
        product_id=args.product_id,
        tag_name=args.tag_name,
        tag_desc=args.tag_desc,
    ))


def cmd_delete_tag(args):
    cli.print_result(cli.get_client().delete_tag(
        tag_id_list=cli.parse_csv_values(args.tag_id_list),
        product_id=args.product_id,
    ))


def cmd_attach_tag(args):
    cli.print_result(cli.get_client().attach_tag(
        tag_id=args.tag_id,
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        product_id=args.product_id,
    ))


def register(subparsers):

    list_tags_parser = subparsers.add_parser('list-tags', help='鏌ヨ鏍囩鍒楄〃')
    list_tags_parser.add_argument('product_id', help='浜у搧 ID')
    list_tags_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_tags_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_tags_parser.add_argument('--tag-name', help='鏍囩鍚嶇О绮剧‘鍖归厤')
    list_tags_parser.add_argument('--tag-name-fuzzy', help='鏍囩鍚嶇О妯＄硦鍖归厤')
    list_tags_parser.set_defaults(func=cmd_list_tags)

    create_tag_parser = subparsers.add_parser('create-tag', help='鍒涘缓鏍囩')
    create_tag_parser.add_argument('product_id', help='浜у搧 ID')
    create_tag_parser.add_argument('--tag-name', required=True, help='鏍囩鍚嶇О')
    create_tag_parser.add_argument('--tag-desc', help='鏍囩鎻忚堪')
    create_tag_parser.set_defaults(func=cmd_create_tag)

    update_tag_parser = subparsers.add_parser('update-tag', help='鏇存柊鏍囩')
    update_tag_parser.add_argument('product_id', help='浜у搧 ID')
    update_tag_parser.add_argument('--tag-id', required=True, help='鏍囩 ID')
    update_tag_parser.add_argument('--tag-name', help='鏍囩鍚嶇О')
    update_tag_parser.add_argument('--tag-desc', help='鏍囩鎻忚堪')
    update_tag_parser.set_defaults(func=cmd_update_tag)

    delete_tag_parser = subparsers.add_parser('delete-tag', help='鍒犻櫎鏍囩')
    delete_tag_parser.add_argument('product_id', help='浜у搧 ID')
    delete_tag_parser.add_argument('--tag-id-list', required=True, help='鏍囩 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    delete_tag_parser.set_defaults(func=cmd_delete_tag)

    attach_tag_parser = subparsers.add_parser('attach-tag', help='缁戝畾鏍囩')
    attach_tag_parser.add_argument('product_id', help='浜у搧 ID')
    attach_tag_parser.add_argument('--tag-id', required=True, help='鏍囩 ID')
    attach_tag_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    attach_tag_parser.set_defaults(func=cmd_attach_tag)
