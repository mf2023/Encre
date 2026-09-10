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

"""Data Center Service (DCS) module for the ACEP API CLI."""
from . import cli_common as cli


def cmd_get_dc_bandwidth_daily_peak(args):
    cli.print_result(cli.get_client().get_dc_bandwidth_daily_peak(
        dc_id_list=cli.parse_csv(args.dc_id_list),
        product_id=args.product_id,
        StartDate=args.start_date,
        EndDate=args.end_date,
    ))


def cmd_list_dcs(args):
    cli.print_result(cli.get_client().list_dcs(
        product_id=args.product_id,
        volc_region=args.volc_region,
        region=args.region,
        isp=args.isp,
        server_type_code=args.server_type_code,
        offset=args.offset,
        count=args.count,
    ))


def register(subparsers):

    get_dc_bandwidth_daily_peak_parser = subparsers.add_parser('get-dc-bandwidth-daily-peak', help='鑾峰彇鏈烘埧甯﹀鏃ュ嘲鍊?')
    get_dc_bandwidth_daily_peak_parser.add_argument('product_id', help='浜у搧 ID')
    get_dc_bandwidth_daily_peak_parser.add_argument('dc_id_list', help='鏈烘埧 ID 鍒楄〃锛屽涓€肩敤閫楀彿鍒嗛殧')
    get_dc_bandwidth_daily_peak_parser.add_argument('--start-date', help='寮€濮嬫棩鏈?yyyy-MM-dd')
    get_dc_bandwidth_daily_peak_parser.add_argument('--end-date', help='缁撴潫鏃ユ湡 yyyy-MM-dd')
    get_dc_bandwidth_daily_peak_parser.set_defaults(func=cmd_get_dc_bandwidth_daily_peak)

    list_dcs_parser = subparsers.add_parser('list-dcs', help='鑾峰彇鏈烘埧鍒楄〃')
    list_dcs_parser.add_argument('product_id', help='浜у搧 ID')
    list_dcs_parser.add_argument('--volc-region', choices=['inner', 'cn-hongkong-pop'], help='鏈烘埧鎵€鍦ㄧ墿鐞嗗尯鍩?')
    list_dcs_parser.add_argument('--region', choices=['cn-north', 'cn-south', 'cn-east', 'cn-middle', 'cn-southwest', 'cn-hongkong-pop'], help='鏈烘埧鎵€鍦ㄥぇ鍖?ID')
    list_dcs_parser.add_argument('--isp', type=int, choices=[1, 2, 4, 7, 8], help='缃戠粶杩愯惀鍟?ID锛? 绉诲姩锛? 鑱旈€氾紝4 鐢典俊锛? 涓夌嚎锛? BGP')
    list_dcs_parser.add_argument('--server-type-code', choices=['g2.8c12g', 'g2.8c16g.basic', 'g2.8c16g.plus', 'g3.host8c24g256g'], help='浜戞満瑙勬牸锛屼粎鏈湴瀛樺偍涓氬姟閫傜敤')
    list_dcs_parser.add_argument('--offset', type=int, help='鏌ヨ鍋忕Щ閲?')
    list_dcs_parser.add_argument('--count', type=int, help='鍗曟杩斿洖鏉℃暟')
    list_dcs_parser.set_defaults(func=cmd_list_dcs)
