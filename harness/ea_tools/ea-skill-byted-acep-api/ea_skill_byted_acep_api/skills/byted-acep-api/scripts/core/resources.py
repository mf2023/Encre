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

"""Resource module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_list_instance_configuration_specs(args):
    cli.print_result(cli.get_client().list_instance_configuration_specs(product_id=args.product_id))


def cmd_list_pod_resources(args):
    cli.print_result(cli.get_client().list_pod_resources(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        ConfigurationCode=args.configuration_code,
        Dc=args.dc,
        ImageId=args.image_id,
    ))


def cmd_get_product_resource(args):
    cli.print_result(cli.get_client().get_product_resource(**cli.request_kwargs(args)))


def cmd_update_product_resource(args):
    cli.print_result(cli.get_client().update_product_resource(
        apply_data_size=args.apply_data_size,
        product_id=args.product_id,
        volc_region=args.volc_region,
    ))


def cmd_list_pod_resource_set(args):
    cli.print_result(cli.get_client().list_pod_resource_set(
        offset=args.offset if args.offset is not None else 0,
        count=args.count if args.count is not None else 10,
        product_id=args.product_id,
        ResourceSetId=args.resource_set_id,
        ConfigurationCode=args.configuration_code,
        Dc=args.dc,
        VolcRegion=args.volc_region,
    ))

def cmd_list_configurations(args):
    cli.print_result(cli.get_client().list_configurations(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        ResourceClass=args.resource_class,
        ConfigurationCode=args.configuration_code,
    ))


def cmd_subscribe_resource_auto(args):
    kwargs = cli.request_kwargs(args)
    for field in ['configuration_code', 'server_type_code', 'dc', 'apply_num', 'resource_type', 'term', 'period', 'pay_type', 'charge_type', 'region', 'volc_region', 'round_id', 'auto_create_pod', 'image_id', 'display_layout_id']:
        value = getattr(args, field, None)
        if value is not None:
            parts = field.split('_')
            kwargs[parts[0].capitalize() + ''.join(part.capitalize() for part in parts[1:])] = value
    cli.print_result(cli.get_client().subscribe_resource_auto(**kwargs))


def cmd_renew_resource_auto(args):
    kwargs = cli.request_kwargs(args)
    for field in ['resource_set_id', 'host_id', 'term', 'period', 'round_id']:
        value = getattr(args, field, None)
        if value is not None:
            parts = field.split('_')
            kwargs[parts[0].capitalize() + ''.join(part.capitalize() for part in parts[1:])] = value
    cli.print_result(cli.get_client().renew_resource_auto(**kwargs))


def cmd_unsubscribe_host_resource(args):
    cli.print_result(cli.get_client().unsubscribe_host_resource(
        host_id_list=cli.parse_csv(args.host_id_list),
        force=args.force,
        **cli.request_kwargs(args),
    ))


def register(subparsers):
    list_instance_configuration_specs_parser = subparsers.add_parser('list-instance-configuration-specs', help='鏌ヨ瀹炰緥瑙勬牸鍒楄〃')
    list_instance_configuration_specs_parser.add_argument('product_id', help='浜у搧 ID')
    list_instance_configuration_specs_parser.set_defaults(func=cmd_list_instance_configuration_specs)

    subscribe_resource_parser = subparsers.add_parser('subscribe-resource-auto', help='鑷姩涓嬪崟璁㈣喘璧勬簮')
    subscribe_resource_parser.add_argument('product_id', help='浜у搧 ID')
    subscribe_resource_parser.add_argument('--configuration-code', help='瀹炰緥瑙勬牸 ID锛涙湰鍦板瓨鍌ㄤ笟鍔″繀濉?')
    subscribe_resource_parser.add_argument('--server-type-code', help='浜戞満瑙勬牸 ID')
    subscribe_resource_parser.add_argument('--dc', help='鏈烘埧 ID')
    subscribe_resource_parser.add_argument('--apply-num', type=int, help='璁㈣喘瀹炰緥鏁伴噺')
    subscribe_resource_parser.add_argument('--resource-type', type=int, required=True, choices=[100, 200], help='璧勬簮绫诲瀷锛堝繀濉級锛氫簯鐩?100锛屾湰鍦?200')
    subscribe_resource_parser.add_argument('--term', type=int, help='璁㈣喘鍛ㄦ湡鏁?')
    subscribe_resource_parser.add_argument('--period', help='璁㈣喘鍛ㄦ湡鍗曚綅')
    subscribe_resource_parser.add_argument('--pay-type', type=int, help='浠樿垂绫诲瀷')
    subscribe_resource_parser.add_argument('--charge-type', help='璁¤垂绫诲瀷')
    subscribe_resource_parser.add_argument('--region', help='璧勬簮鍦板煙')
    subscribe_resource_parser.add_argument('--volc-region', help='鐏北鍦板煙鏍囪瘑')
    subscribe_resource_parser.add_argument('--round-id', help='骞傜瓑璇锋眰 ID')
    subscribe_resource_parser.add_argument('--auto-create-pod', type=int, choices=[0, 1], help='鏄惁鑷姩鍒涘缓瀹炰緥')
    subscribe_resource_parser.add_argument('--image-id', help='鑷姩鍒涘缓瀹炰緥浣跨敤鐨勯暅鍍?ID')
    subscribe_resource_parser.add_argument('--display-layout-id', help='鑷姩鍒涘缓瀹炰緥浣跨敤鐨勫睆骞曞竷灞€ ID')
    subscribe_resource_parser.set_defaults(func=cmd_subscribe_resource_auto)

    renew_resource_parser = subparsers.add_parser('renew-resource-auto', help='鑷姩涓嬪崟缁璧勬簮')
    renew_resource_parser.add_argument('product_id', help='浜у搧 ID')
    renew_resource_parser.add_argument('--resource-set-id', help='璧勬簮缁?ID')
    renew_resource_parser.add_argument('--host-id', help='浜戞満 ID')
    renew_resource_parser.add_argument('--term', type=int, help='缁垂鍛ㄦ湡鏁?')
    renew_resource_parser.add_argument('--period', help='缁垂鍛ㄦ湡鍗曚綅')
    renew_resource_parser.add_argument('--round-id', help='骞傜瓑璇锋眰 ID')
    renew_resource_parser.set_defaults(func=cmd_renew_resource_auto)

    unsubscribe_host_parser = subparsers.add_parser('unsubscribe-host-resource', help='閫€璁㈠悗浠樿垂浜戞満璧勬簮')
    unsubscribe_host_parser.add_argument('product_id', help='浜у搧 ID')
    unsubscribe_host_parser.add_argument('host_id_list', help='浜戞満 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    unsubscribe_host_parser.add_argument('--force', action='store_true', help='寮哄埗閫€璁?')
    unsubscribe_host_parser.set_defaults(func=cmd_unsubscribe_host_resource)

    list_pod_resources_parser = subparsers.add_parser('list-pod-resources', help='鏌ヨ瀹炰緥璧勬簮鍒楄〃')
    list_pod_resources_parser.add_argument('product_id', help='浜у搧 ID')
    list_pod_resources_parser.add_argument('--configuration-code', help='瀹炰緥瑙勬牸 ID')
    list_pod_resources_parser.add_argument('--dc', help='鏈烘埧 ID')
    list_pod_resources_parser.add_argument('--image-id', help='闀滃儚 ID')
    list_pod_resources_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_pod_resources_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_pod_resources_parser.set_defaults(func=cmd_list_pod_resources)

    get_product_resource_parser = subparsers.add_parser('get-product-resource', help='鏌ヨ涓氬姟瀛樺偍璧勬簮')
    get_product_resource_parser.add_argument('product_id', help='浜у搧 ID')
    get_product_resource_parser.set_defaults(func=cmd_get_product_resource)

    list_configs_parser = subparsers.add_parser('list-configurations', help='鏌ヨ濂楅鍒楄〃')
    list_configs_parser.add_argument('product_id', help='浜у搧 ID')
    list_configs_parser.add_argument('--resource-class', type=int, help='璧勬簮绫诲瀷锛?=璁＄畻璧勬簮锛?=瀛樺偍璧勬簮锛?=甯﹀璧勬簮')
    list_configs_parser.add_argument('--configuration-code', help='濂楅瑙勬牸 ID')
    list_configs_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_configs_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_configs_parser.set_defaults(func=cmd_list_configurations)

    update_product_resource_parser = subparsers.add_parser('update-product-resource', help='鏇存柊涓氬姟瀛樺偍璧勬簮')
    update_product_resource_parser.add_argument('product_id', help='浜у搧 ID')
    update_product_resource_parser.add_argument('--apply-data-size', type=int, required=True, help='璁㈣喘瀛樺偍璧勬簮鎬诲閲?GB')
    update_product_resource_parser.add_argument('--volc-region', help='鐗╃悊鍦板煙')
    update_product_resource_parser.set_defaults(func=cmd_update_product_resource)

    list_pod_resource_set_parser = subparsers.add_parser('list-pod-resource-set', help='鏌ヨ瀹炰緥璧勬簮缁勫垪琛?')
    list_pod_resource_set_parser.add_argument('product_id', help='浜у搧 ID')
    list_pod_resource_set_parser.add_argument('--resource-set-id', help='璧勬簮缁?ID')
    list_pod_resource_set_parser.add_argument('--configuration-code', help='瀹炰緥瑙勬牸 ID')
    list_pod_resource_set_parser.add_argument('--dc', help='鏈烘埧 ID')
    list_pod_resource_set_parser.add_argument('--volc-region', help='鐗╃悊鍦板煙')
    list_pod_resource_set_parser.add_argument('--offset', type=int, default=0, help='璧峰浣嶇疆')
    list_pod_resource_set_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_pod_resource_set_parser.set_defaults(func=cmd_list_pod_resource_set)
