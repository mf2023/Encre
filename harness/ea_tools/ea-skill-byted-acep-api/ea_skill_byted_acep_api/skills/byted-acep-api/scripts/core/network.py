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

"""Network module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_list_port_mapping_rules(args):
    cli.print_result(cli.get_client().list_port_mapping_rules(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        PortMappingRuleId=args.port_mapping_rule_id,
        Protocol=args.protocol,
        VolcRegion=args.volc_region,
    ))


def cmd_detail_port_mapping_rule(args):
    cli.print_result(cli.get_client().detail_port_mapping_rule(port_mapping_rule_id=args.port_mapping_rule_id, product_id=args.product_id))


def cmd_create_port_mapping_rule(args):
    cli.print_result(cli.get_client().create_port_mapping_rule(
        source_port=args.source_port,
        product_id=args.product_id,
        port_mapping_rule_id=args.port_mapping_rule_id,
        protocol=args.protocol,
        isp=args.isp,
        direction=args.direction,
        volc_region=args.volc_region,
    ))


def cmd_bind_port_mapping_rule(args):
    cli.print_result(cli.get_client().bind_port_mapping_rule(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        port_mapping_rule_id_list=cli.parse_csv_values(args.port_mapping_rule_id_list),
        product_id=args.product_id,
    ))


def cmd_unbind_port_mapping_rule(args):
    cli.print_result(cli.get_client().unbind_port_mapping_rule(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        port_mapping_rule_id_list=cli.parse_csv_values(args.port_mapping_rule_id_list),
        product_id=args.product_id,
    ))


def cmd_list_dns_rules(args):
    cli.print_result(cli.get_client().list_dns_rules(
        offset=args.offset,
        count=args.count,
        product_id=args.product_id,
        DNSName=args.dns_name,
        Type=args.type,
    ))


def cmd_detail_dns_rule(args):
    cli.print_result(cli.get_client().detail_dns_rule(dns_id=args.dns_id, product_id=args.product_id))


def cmd_create_dns_rule(args):
    cli.print_result(cli.get_client().create_dns_rule(
        dc=args.dc,
        ip_list=cli.parse_csv_values(args.ip_list),
        product_id=args.product_id,
        dns_name=args.dns_name,
        type=args.type,
    ))


def cmd_update_dns_rule(args):
    cli.print_result(cli.get_client().update_dns_rule(
        dns_id=args.dns_id,
        product_id=args.product_id,
        dns_name=args.dns_name,
        type=args.type,
        ip_list=cli.parse_csv_values(args.ip_list) if args.ip_list else None,
    ))


def cmd_delete_dns_rule(args):
    cli.print_result(cli.get_client().delete_dns_rule(
        dns_id=args.dns_id,
        product_id=args.product_id,
    ))


def cmd_list_custom_routes(args):
    cli.print_result(cli.get_client().list_custom_routes(
        max_results=args.max_results,
        next_token=args.next_token,
        product_id=args.product_id,
        CustomRouteId=args.custom_route_id,
        CustomRouteName=args.custom_route_name,
        Zone=args.zone,
        DstIP=args.dst_ip,
    ))


def cmd_add_custom_route(args):
    cli.print_result(cli.get_client().add_custom_route(
        zone=args.zone,
        dst_ip=args.dst_ip,
        proxy_protocol=args.proxy_protocol,
        proxy_port=args.proxy_port,
        product_id=args.product_id,
        custom_route_name=args.custom_route_name,
        proxy_user_name=args.proxy_user_name,
        proxy_password=args.proxy_password,
        proxy_cipher=args.proxy_cipher,
    ))


def cmd_update_custom_route(args):
    cli.print_result(cli.get_client().update_custom_route(
        custom_route_id=args.custom_route_id,
        product_id=args.product_id,
        custom_route_name=args.custom_route_name,
        dst_ip=args.dst_ip,
        proxy_protocol=args.proxy_protocol,
        proxy_port=args.proxy_port,
        proxy_user_name=args.proxy_user_name,
        proxy_password=args.proxy_password,
        proxy_cipher=args.proxy_cipher,
    ))


def cmd_delete_custom_route(args):
    cli.print_result(cli.get_client().delete_custom_route(
        custom_route_id=args.custom_route_id,
        product_id=args.product_id,
    ))


def register(subparsers):
    list_port_mapping_rules_parser = subparsers.add_parser('list-port-mapping-rules', help='鏌ヨ绔彛鏄犲皠鍒楄〃')
    list_port_mapping_rules_parser.add_argument('product_id', help='浜у搧 ID')
    list_port_mapping_rules_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_port_mapping_rules_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_port_mapping_rules_parser.add_argument('--port-mapping-rule-id', help='绔彛鏄犲皠瑙勫垯 ID')
    list_port_mapping_rules_parser.add_argument('--protocol', choices=['tcp', 'udp'], help='鍗忚')
    list_port_mapping_rules_parser.add_argument('--volc-region', help='鐗╃悊鍦板煙')
    list_port_mapping_rules_parser.set_defaults(func=cmd_list_port_mapping_rules)

    detail_port_mapping_rule_parser = subparsers.add_parser('detail-port-mapping-rule', help='鏌ヨ绔彛鏄犲皠璇︽儏')
    detail_port_mapping_rule_parser.add_argument('product_id', help='浜у搧 ID')
    detail_port_mapping_rule_parser.add_argument('port_mapping_rule_id', help='绔彛鏄犲皠瑙勫垯 ID')
    detail_port_mapping_rule_parser.set_defaults(func=cmd_detail_port_mapping_rule)

    create_port_mapping_rule_parser = subparsers.add_parser('create-port-mapping-rule', help='鍒涘缓绔彛鏄犲皠瑙勫垯')
    create_port_mapping_rule_parser.add_argument('product_id', help='浜у搧 ID')
    create_port_mapping_rule_parser.add_argument('--port-mapping-rule-id', help='绔彛鏄犲皠瑙勫垯 ID')
    create_port_mapping_rule_parser.add_argument('--protocol', choices=['tcp', 'udp', 'all'], help='鍗忚')
    create_port_mapping_rule_parser.add_argument('--source-port', type=int, required=True, help='婧愮鍙?')
    create_port_mapping_rule_parser.add_argument('--isp', type=int, help='杩愯惀鍟?')
    create_port_mapping_rule_parser.add_argument('--direction', choices=['Inbound', 'Bidirectional'], help='娴侀噺鏂瑰悜')
    create_port_mapping_rule_parser.add_argument('--volc-region', help='鐗╃悊鍦板煙')
    create_port_mapping_rule_parser.set_defaults(func=cmd_create_port_mapping_rule)

    bind_port_mapping_rule_parser = subparsers.add_parser('bind-port-mapping-rule', help='缁戝畾绔彛鏄犲皠瑙勫垯')
    bind_port_mapping_rule_parser.add_argument('product_id', help='浜у搧 ID')
    bind_port_mapping_rule_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    bind_port_mapping_rule_parser.add_argument('--port-mapping-rule-id-list', required=True, help='瑙勫垯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    bind_port_mapping_rule_parser.set_defaults(func=cmd_bind_port_mapping_rule)

    unbind_port_mapping_rule_parser = subparsers.add_parser('unbind-port-mapping-rule', help='瑙ｇ粦绔彛鏄犲皠瑙勫垯')
    unbind_port_mapping_rule_parser.add_argument('product_id', help='浜у搧 ID')
    unbind_port_mapping_rule_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    unbind_port_mapping_rule_parser.add_argument('--port-mapping-rule-id-list', required=True, help='瑙勫垯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    unbind_port_mapping_rule_parser.set_defaults(func=cmd_unbind_port_mapping_rule)

    list_dns_rules_parser = subparsers.add_parser('list-dns-rules', help='鏌ヨ DNS 瑙勫垯鍒楄〃')
    list_dns_rules_parser.add_argument('product_id', help='浜у搧 ID')
    list_dns_rules_parser.add_argument('--offset', type=int, default=0, help='鏌ヨ璧峰浣嶇疆')
    list_dns_rules_parser.add_argument('--count', type=int, default=10, help='杩斿洖鏁伴噺')
    list_dns_rules_parser.add_argument('--dns-name', help='DNS 瑙勫垯鍚嶇О')
    list_dns_rules_parser.add_argument('--type', type=int, help='DNS 瑙勫垯绫诲瀷锛?=闈為粯璁わ紝1=榛樿')
    list_dns_rules_parser.set_defaults(func=cmd_list_dns_rules)

    detail_dns_rule_parser = subparsers.add_parser('detail-dns-rule', help='鏌ヨ DNS 瑙勫垯璇︽儏')
    detail_dns_rule_parser.add_argument('product_id', help='浜у搧 ID')
    detail_dns_rule_parser.add_argument('dns_id', help='DNS 瑙勫垯 ID')
    detail_dns_rule_parser.set_defaults(func=cmd_detail_dns_rule)

    create_dns_rule_parser = subparsers.add_parser('create-dns-rule', help='鍒涘缓 DNS 瑙勫垯')
    create_dns_rule_parser.add_argument('product_id', help='浜у搧 ID')
    create_dns_rule_parser.add_argument('--dc', required=True, help='鏈烘埧 ID')
    create_dns_rule_parser.add_argument('--dns-name', help='DNS 鍚嶇О')
    create_dns_rule_parser.add_argument('--type', type=int, help='绫诲瀷锛?=闈為粯璁わ紝1=榛樿')
    create_dns_rule_parser.add_argument('--ip-list', required=True, help='IP 鍒楄〃锛岄€楀彿鍒嗛殧')
    create_dns_rule_parser.set_defaults(func=cmd_create_dns_rule)

    update_dns_rule_parser = subparsers.add_parser('update-dns-rule', help='鏇存柊 DNS 瑙勫垯')
    update_dns_rule_parser.add_argument('product_id', help='浜у搧 ID')
    update_dns_rule_parser.add_argument('--dns-id', required=True, help='DNS 瑙勫垯 ID')
    update_dns_rule_parser.add_argument('--dns-name', help='DNS 鍚嶇О')
    update_dns_rule_parser.add_argument('--type', type=int, help='绫诲瀷')
    update_dns_rule_parser.add_argument('--ip-list', help='IP 鍒楄〃锛岄€楀彿鍒嗛殧')
    update_dns_rule_parser.set_defaults(func=cmd_update_dns_rule)

    delete_dns_rule_parser = subparsers.add_parser('delete-dns-rule', help='鍒犻櫎 DNS 瑙勫垯')
    delete_dns_rule_parser.add_argument('product_id', help='浜у搧 ID')
    delete_dns_rule_parser.add_argument('--dns-id', required=True, help='DNS 瑙勫垯 ID')
    delete_dns_rule_parser.set_defaults(func=cmd_delete_dns_rule)

    list_custom_routes_parser = subparsers.add_parser('list-custom-routes', help='鏌ヨ鑷畾涔夎矾鐢辫鍒?')
    list_custom_routes_parser.add_argument('product_id', help='浜у搧 ID')
    list_custom_routes_parser.add_argument('--custom-route-id', help='鑷畾涔夎矾鐢辫鍒?ID')
    list_custom_routes_parser.add_argument('--custom-route-name', help='鑷畾涔夎矾鐢卞悕绉?')
    list_custom_routes_parser.add_argument('--zone', help='鍖哄煙/鐗囧尯 ID')
    list_custom_routes_parser.add_argument('--dst-ip', help='浠ｇ悊鏈嶅姟鍣?IP')
    list_custom_routes_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺锛屾渶澶?100')
    list_custom_routes_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_custom_routes_parser.set_defaults(func=cmd_list_custom_routes)

    add_custom_route_parser = subparsers.add_parser('add-custom-route', help='鍒涘缓鑷畾涔夎矾鐢?')
    add_custom_route_parser.add_argument('product_id', help='浜у搧 ID')
    add_custom_route_parser.add_argument('--custom-route-name', help='瑙勫垯鍚嶇О')
    add_custom_route_parser.add_argument('--zone', required=True, help='鍖哄煙/鐗囧尯 ID')
    add_custom_route_parser.add_argument('--dst-ip', required=True, help='浠ｇ悊鏈嶅姟鍣?IP')
    add_custom_route_parser.add_argument('--proxy-protocol', choices=['ss', 'socks5'], required=True, help='浠ｇ悊鍗忚')
    add_custom_route_parser.add_argument('--proxy-port', type=int, required=True, help='浠ｇ悊绔彛')
    add_custom_route_parser.add_argument('--proxy-user-name', help='浠ｇ悊鐢ㄦ埛鍚?')
    add_custom_route_parser.add_argument('--proxy-password', help='浠ｇ悊瀵嗙爜')
    add_custom_route_parser.add_argument('--proxy-cipher', help='浠ｇ悊鍔犲瘑绠楁硶')
    add_custom_route_parser.set_defaults(func=cmd_add_custom_route)

    update_custom_route_parser = subparsers.add_parser('update-custom-route', help='鏇存柊鑷畾涔夎矾鐢?')
    update_custom_route_parser.add_argument('product_id', help='浜у搧 ID')
    update_custom_route_parser.add_argument('--custom-route-id', required=True, help='瑙勫垯 ID')
    update_custom_route_parser.add_argument('--custom-route-name', help='瑙勫垯鍚嶇О')
    update_custom_route_parser.add_argument('--dst-ip', help='浠ｇ悊鏈嶅姟鍣?IP')
    update_custom_route_parser.add_argument('--proxy-protocol', choices=['ss', 'socks5'], help='浠ｇ悊鍗忚')
    update_custom_route_parser.add_argument('--proxy-port', type=int, help='浠ｇ悊绔彛')
    update_custom_route_parser.add_argument('--proxy-user-name', help='浠ｇ悊鐢ㄦ埛鍚?')
    update_custom_route_parser.add_argument('--proxy-password', help='浠ｇ悊瀵嗙爜')
    update_custom_route_parser.add_argument('--proxy-cipher', help='浠ｇ悊鍔犲瘑绠楁硶')
    update_custom_route_parser.set_defaults(func=cmd_update_custom_route)

    delete_custom_route_parser = subparsers.add_parser('delete-custom-route', help='鍒犻櫎鑷畾涔夎矾鐢?')
    delete_custom_route_parser.add_argument('product_id', help='浜у搧 ID')
    delete_custom_route_parser.add_argument('--custom-route-id', required=True, help='瑙勫垯 ID')
    delete_custom_route_parser.set_defaults(func=cmd_delete_custom_route)
