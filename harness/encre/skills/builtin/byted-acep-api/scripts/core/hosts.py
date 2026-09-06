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

"""浜戞満妯″潡銆?""
from . import cli_common as cli


def cmd_list_hosts(args):
    result = cli.get_client().list_hosts(
        max_results=args.max_results,
        next_token=args.next_token,
        product_id=args.product_id,
        HostIdList=cli.parse_csv_values(args.host_id_list),
        StatusList=cli.parse_csv_values(args.status_list, int),
        Dc=args.dc,
        Region=args.region,
        ConfigurationCode=args.configuration_code,
        VolcRegion=args.volc_region,
        ResourceSetId=args.resource_set_id,
        UseStatus=args.use_status,
        AuthorityStatus=args.authority_status,
        PodIdList=cli.parse_csv_values(args.pod_id_list),
        ExpireTimeBefore=args.expire_time_before,
        SyncRenewType=args.sync_renew_type,
    )
    cli.print_result(result)


def cmd_detail_host(args):
    cli.print_result(cli.get_client().detail_host(host_id=args.host_id, product_id=args.product_id))


def cmd_update_host(args):
    cli.print_result(cli.get_client().update_host(
        host_id_list=cli.parse_csv(args.host_id_list),
        configuration_code=args.configuration_code,
        **cli.request_kwargs(args),
    ))


def cmd_reboot_host(args):
    cli.print_result(cli.get_client().reboot_host(
        host_id_list=cli.parse_csv(args.host_id_list),
        force=args.force,
        **cli.request_kwargs(args),
    ))


def cmd_reset_host(args):
    cli.print_result(cli.get_client().reset_host(
        host_id_list=cli.parse_csv(args.host_id_list),
        force=args.force,
        **cli.request_kwargs(args),
    ))


def register(subparsers):

    list_hosts_parser = subparsers.add_parser('list-hosts', help='鏌ヨ浜戞満鍒楄〃')
    list_hosts_parser.add_argument('product_id', help='浜у搧 ID')
    list_hosts_parser.add_argument('--host-id-list', help='浜戞満 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_hosts_parser.add_argument('--status-list', help='鐘舵€佸垪琛紝閫楀彿鍒嗛殧')
    list_hosts_parser.add_argument('--dc', help='鏈烘埧 ID')
    list_hosts_parser.add_argument('--region', help='澶у尯 ID')
    list_hosts_parser.add_argument('--configuration-code', help='瀹炰緥瑙勬牸 ID')
    list_hosts_parser.add_argument('--volc-region', help='鐗╃悊鍦板煙')
    list_hosts_parser.add_argument('--resource-set-id', help='璧勬簮缁?ID')
    list_hosts_parser.add_argument('--use-status', type=int, help='鍗犵敤鐘舵€?)
    list_hosts_parser.add_argument('--authority-status', type=int, help='杩愮淮鎺堟潈鐘舵€?)
    list_hosts_parser.add_argument('--pod-id-list', help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_hosts_parser.add_argument('--expire-time-before', help='杩囨湡鏃堕棿鏃╀簬璇ュ€?)
    list_hosts_parser.add_argument('--sync-renew-type', action='store_true', help='杩斿洖缁垂绫诲瀷')
    list_hosts_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺')
    list_hosts_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_hosts_parser.set_defaults(func=cmd_list_hosts)

    detail_host_parser = subparsers.add_parser('detail-host', help='鏌ヨ浜戞満璇︽儏')
    detail_host_parser.add_argument('product_id', help='浜у搧 ID')
    detail_host_parser.add_argument('host_id', help='浜戞満 ID')
    detail_host_parser.set_defaults(func=cmd_detail_host)

    update_host_parser = subparsers.add_parser('update-host', help='鏇存柊浜戞満鍙繍琛屽疄渚嬭鏍?)
    update_host_parser.add_argument('product_id', help='浜у搧 ID')
    update_host_parser.add_argument('host_id_list', help='浜戞満 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    update_host_parser.add_argument('--configuration-code', help='鐩爣瀹炰緥瑙勬牸 ID')
    update_host_parser.set_defaults(func=cmd_update_host)

    reboot_host_parser = subparsers.add_parser('reboot-host', help='閲嶅惎浜戞満')
    reboot_host_parser.add_argument('product_id', help='浜у搧 ID')
    reboot_host_parser.add_argument('host_id_list', help='浜戞満 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    reboot_host_parser.add_argument('--force', action='store_true', help='寮哄埗閲嶅惎')
    reboot_host_parser.set_defaults(func=cmd_reboot_host)

    reset_host_parser = subparsers.add_parser('reset-host', help='閲嶇疆浜戞満')
    reset_host_parser.add_argument('product_id', help='浜у搧 ID')
    reset_host_parser.add_argument('host_id_list', help='浜戞満 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    reset_host_parser.add_argument('--force', action='store_true', help='寮哄埗閲嶇疆')
    reset_host_parser.set_defaults(func=cmd_reset_host)
