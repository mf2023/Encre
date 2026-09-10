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

"""Instance property module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_get_phone_template(args):
    result = cli.get_client().get_phone_template(phone_template_id=args.phone_template_id, product_id=args.product_id)
    cli.print_result(result)


def cmd_list_phone_templates(args):
    result = cli.get_client().list_phone_templates(
        max_results=args.max_results,
        next_token=args.next_token,
        product_id=args.product_id,
        PhoneTemplateName=args.phone_template_name,
        Status=args.status,
        PhoneTemplateId=args.phone_template_id,
        TagId=args.tag_id,
        AospVersion=args.aosp_version,
    )
    cli.print_result(result)


def cmd_add_phone_template(args):
    result = cli.get_client().add_phone_template(
        phone_template_name=args.phone_template_name,
        aosp_version=args.aosp_version,
        status=args.status,
        overlay_property=cli.parse_json_option(args.overlay_property, '--overlay-property', list),
        overlay_persist_property=cli.parse_json_option(args.overlay_persist_property, '--overlay-persist-property', list),
        overlay_settings=cli.parse_json_option(args.overlay_settings, '--overlay-settings', list),
    )
    cli.print_result(result)


def cmd_update_phone_template(args):
    result = cli.get_client().update_phone_template(
        phone_template_id=args.phone_template_id,
        phone_template_name=args.phone_template_name,
        status=args.status,
    )
    cli.print_result(result)


def cmd_remove_phone_template(args):
    result = cli.get_client().remove_phone_template(
        phone_template_id=args.phone_template_id,
    )
    cli.print_result(result)


def cmd_get_pod_property(args):
    result = cli.get_client().get_pod_property(pod_id=args.pod_id, product_id=args.product_id)
    cli.print_result(result)


def cmd_update_pod_property(args):
    result = cli.get_client().update_pod_property(
        product_id=args.product_id,
        pod_id=args.pod_id,
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        pod_settings=cli.parse_json_option(args.pod_settings, '--pod-settings', list),
        pod_properties=cli.parse_json_option(args.pod_properties, '--pod-properties', list),
        pod_persist_properties=cli.parse_json_option(args.pod_persist_properties, '--pod-persist-properties', list),
        phone_template_id=args.phone_template_id,
    )
    cli.print_result(result)


def register(subparsers):

    get_phone_template_parser = subparsers.add_parser('get-phone-template', help='鏌ヨ鏈哄瀷搴撹鎯?')
    get_phone_template_parser.add_argument('product_id', help='浜у搧 ID')
    get_phone_template_parser.add_argument('phone_template_id', help='鏈哄瀷搴?ID')
    get_phone_template_parser.set_defaults(func=cmd_get_phone_template)

    list_templates_parser = subparsers.add_parser('list-phone-templates', help='鏌ヨ鏈哄瀷搴撳垪琛?')
    list_templates_parser.add_argument('product_id', help='浜у搧 ID')
    list_templates_parser.add_argument('--phone-template-name', help='鏈哄瀷搴撳悕绉?')
    list_templates_parser.add_argument('--status', type=int, help='鐘舵€侊細1=宸插彂甯冿紝2=娴嬭瘯涓紝3=宸插簾寮?')
    list_templates_parser.add_argument('--phone-template-id', help='鏈哄瀷搴?ID')
    list_templates_parser.add_argument('--tag-id', help='鏍囩 ID')
    list_templates_parser.add_argument('--aosp-version', help='AOSP 鐗堟湰')
    list_templates_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺')
    list_templates_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_templates_parser.set_defaults(func=cmd_list_phone_templates)

    add_phone_template_parser = subparsers.add_parser('add-phone-template', help='娣诲姞鏈哄瀷搴?')
    add_phone_template_parser.add_argument('--phone-template-name', required=True, help='鏈哄瀷搴撳悕绉?')
    add_phone_template_parser.add_argument('--aosp-version', required=True, help='AOSP 鐗堟湰')
    add_phone_template_parser.add_argument('--status', type=int, required=True, help='鐘舵€侊細1=宸插彂甯冿紝2=娴嬭瘯涓紝3=宸插簾寮?')
    add_phone_template_parser.add_argument('--overlay-property', help='闈炴寔涔呭寲绯荤粺灞炴€?JSON 鏁扮粍')
    add_phone_template_parser.add_argument('--overlay-persist-property', help='鎸佷箙鍖栫郴缁熷睘鎬?JSON 鏁扮粍')
    add_phone_template_parser.add_argument('--overlay-settings', help='Settings 灞炴€?JSON 鏁扮粍')
    add_phone_template_parser.set_defaults(func=cmd_add_phone_template)

    update_phone_template_parser = subparsers.add_parser('update-phone-template', help='鏇存柊鏈哄瀷搴?')
    update_phone_template_parser.add_argument('--phone-template-id', required=True, help='鏈哄瀷搴?ID')
    update_phone_template_parser.add_argument('--phone-template-name', help='鏈哄瀷搴撳悕绉?')
    update_phone_template_parser.add_argument('--status', type=int, help='鐘舵€侊細1=宸插彂甯冿紝2=娴嬭瘯涓紝3=宸插簾寮?')
    update_phone_template_parser.set_defaults(func=cmd_update_phone_template)

    remove_phone_template_parser = subparsers.add_parser('remove-phone-template', help='鍒犻櫎鏈哄瀷搴?')
    remove_phone_template_parser.add_argument('--phone-template-id', required=True, help='鏈哄瀷搴?ID')
    remove_phone_template_parser.set_defaults(func=cmd_remove_phone_template)

    get_pod_property_parser = subparsers.add_parser('get-pod-property', help='鏌ヨ瀹炰緥灞炴€у垪琛?')
    get_pod_property_parser.add_argument('product_id', help='浜у搧 ID')
    get_pod_property_parser.add_argument('pod_id', help='瀹炰緥 ID')
    get_pod_property_parser.set_defaults(func=cmd_get_pod_property)

    update_pod_property_parser = subparsers.add_parser('update-pod-property', help='鏇存柊瀹炰緥灞炴€?')
    update_pod_property_parser.add_argument('product_id', help='浜у搧 ID')
    update_pod_property_parser.add_argument('--pod-id', help='鍗曚釜瀹炰緥 ID')
    update_pod_property_parser.add_argument('--pod-id-list', help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    update_pod_property_parser.add_argument('--phone-template-id', help='鏈哄瀷搴?ID')
    update_pod_property_parser.add_argument('--pod-settings', help='PodSettings JSON 鏁扮粍')
    update_pod_property_parser.add_argument('--pod-properties', help='PodProperties JSON 鏁扮粍')
    update_pod_property_parser.add_argument('--pod-persist-properties', help='PodPersistProperties JSON 鏁扮粍')
    update_pod_property_parser.set_defaults(func=cmd_update_pod_property)
