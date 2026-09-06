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

"""搴旂敤妯″潡銆?""
from . import cli_common as cli


def parse_app_list(value: str) -> list[dict]:
    result = []
    for item in cli.parse_csv_values(value):
        app_id, sep, version_id = item.partition(':')
        if not app_id or not sep or not version_id:
            raise ValueError(f'Invalid --app-list item: {item!r}; expected AppId:VersionId')
        result.append({'AppId': app_id, 'VersionId': version_id})
    return result


def cmd_install_app(args):
    cli.print_result(cli.get_client().install_app(
        pod_id=args.pod_id,
        app_id=args.app_id,
        version_id=args.version_id,
        **cli.request_kwargs(args),
    ))


def cmd_launch_app(args):
    cli.print_result(cli.get_client().launch_app(
        pod_id=args.pod_id,
        package_name=args.package_name,
        **cli.request_kwargs(args),
    ))


def cmd_close_app(args):
    cli.print_result(cli.get_client().close_app(
        pod_id=args.pod_id,
        package_name=args.package_name,
        **cli.request_kwargs(args),
    ))


def cmd_uninstall_app(args):
    cli.print_result(cli.get_client().uninstall_app(
        pod_id=args.pod_id,
        app_id=args.app_id,
        **cli.request_kwargs(args),
    ))


def cmd_auto_install_app(args):
    kwargs = cli.request_kwargs(args)
    for field in ['install_type', 'download_url', 'package_name', 'version_code', 'image_id', 'absolute_path']:
        value = getattr(args, field, None)
        if value is not None:
            kwargs[field] = value
    if args.is_preinstall is not None:
        kwargs['IsPreinstall'] = args.is_preinstall
    cli.print_result(cli.get_client().auto_install_app(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        **kwargs,
    ))


def cmd_get_pod_app_list(args):
    cli.print_result(cli.get_client().get_pod_app_list(args.pod_id, **cli.request_kwargs(args)))


def cmd_detail_app(args):
    cli.print_result(cli.get_client().detail_app(app_id=args.app_id, product_id=args.product_id))


def cmd_list_apps(args):
    cli.print_result(cli.get_client().list_apps(
        max_results=args.max_results,
        next_token=args.next_token,
        product_id=args.product_id,
        AppId=args.app_id,
        AppName=args.app_name,
        AppType=args.app_type,
        PackageNameList=cli.parse_csv_values(args.package_name_list),
    ))


def cmd_list_app_version_deploys(args):
    cli.print_result(cli.get_client().list_app_version_deploys(
        app_id=args.app_id,
        product_id=args.product_id,
        VersionId=args.version_id,
    ))


def cmd_get_app_crash_log(args):
    cli.print_result(cli.get_client().get_app_crash_log(
        pod_id_list=args.pod_id_list,
        start_time=args.start_time,
        end_time=args.end_time,
        product_id=args.product_id,
    ))


def cmd_install_apps(args):
    cli.print_result(cli.get_client().install_apps(
        pod_id=args.pod_id,
        app_list=parse_app_list(args.app_list),
        product_id=args.product_id,
        install_type=args.install_type,
        is_preinstall=args.is_preinstall,
    ))


def cmd_upload_app(args):
    cli.print_result(cli.get_client().upload_app(
        app_type=args.app_type,
        download_url=args.download_url,
        product_id=args.product_id,
        app_id=args.app_id,
        app_name=args.app_name,
        rotation=args.rotation,
        app_desc=args.app_desc,
        parse_flag=args.parse_flag,
        app_mode=args.app_mode,
    ))


def cmd_update_app(args):
    cli.print_result(cli.get_client().update_app(
        app_id=args.app_id,
        product_id=args.product_id,
        app_name=args.app_name,
        rotation=args.rotation,
        icon_url=args.icon_url,
        app_desc=args.app_desc,
        app_mode=args.app_mode,
    ))


def cmd_delete_app(args):
    cli.print_result(cli.get_client().delete_app(app_id=args.app_id, product_id=args.product_id))


def cmd_delete_app_version(args):
    cli.print_result(cli.get_client().delete_app_version(version_id=args.version_id, product_id=args.product_id))


def cmd_launch_apps(args):
    cli.print_result(cli.get_client().launch_apps(
        pod_id=args.pod_id,
        package_name_list=cli.parse_csv_values(args.package_name_list),
        product_id=args.product_id,
    ))


def register(subparsers):

    install_app_parser = subparsers.add_parser('install-app', help='瀹夎搴旂敤')
    install_app_parser.add_argument('product_id', help='浜у搧 ID')
    install_app_parser.add_argument('pod_id', help='瀹炰緥 ID')
    install_app_parser.add_argument('app_id', help='搴旂敤 ID')
    install_app_parser.add_argument('version_id', help='搴旂敤鐗堟湰 ID')
    install_app_parser.set_defaults(func=cmd_install_app)

    launch_app_parser = subparsers.add_parser('launch-app', help='鍚姩搴旂敤')
    launch_app_parser.add_argument('product_id', help='浜у搧 ID')
    launch_app_parser.add_argument('pod_id', help='瀹炰緥 ID')
    launch_app_parser.add_argument('package_name', help='搴旂敤鍖呭悕')
    launch_app_parser.set_defaults(func=cmd_launch_app)

    close_app_parser = subparsers.add_parser('close-app', help='鍏抽棴搴旂敤')
    close_app_parser.add_argument('product_id', help='浜у搧 ID')
    close_app_parser.add_argument('pod_id', help='瀹炰緥 ID')
    close_app_parser.add_argument('package_name', help='搴旂敤鍖呭悕')
    close_app_parser.set_defaults(func=cmd_close_app)

    uninstall_app_parser = subparsers.add_parser('uninstall-app', help='鍗歌浇搴旂敤')
    uninstall_app_parser.add_argument('product_id', help='浜у搧 ID')
    uninstall_app_parser.add_argument('pod_id', help='瀹炰緥 ID')
    uninstall_app_parser.add_argument('app_id', help='搴旂敤 ID')
    uninstall_app_parser.set_defaults(func=cmd_uninstall_app)

    auto_install_app_parser = subparsers.add_parser('auto-install-app', help='鑷姩涓嬭浇瀹夎搴旂敤')
    auto_install_app_parser.add_argument('product_id', help='浜у搧 ID')
    auto_install_app_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    auto_install_app_parser.add_argument('--install-type', type=int, choices=[0, 1], help='瀹夎鏂瑰紡锛?=鏈鸿韩瀛樺偍鐙珛瀹夎锛?=搴旂敤闀滃儚瀹夎')
    auto_install_app_parser.add_argument('--download-url', help='搴旂敤涓嬭浇 URL')
    auto_install_app_parser.add_argument('--package-name', help='搴旂敤鍖呭悕')
    auto_install_app_parser.add_argument('--version-code', type=int, help='搴旂敤鐗堟湰鍙?)
    auto_install_app_parser.add_argument('--image-id', help='闀滃儚鍖?ID')
    auto_install_app_parser.add_argument('--absolute-path', help='搴旂敤缁濆璺緞鎴栧簲鐢ㄩ暅鍍忔牴鐩綍')
    auto_install_app_parser.add_argument('--is-preinstall', action='store_true', default=None, help='鏍囪涓洪瑁呭簲鐢?)
    auto_install_app_parser.set_defaults(func=cmd_auto_install_app)

    get_app_list_parser = subparsers.add_parser('get-pod-app-list', help='鑾峰彇瀹炰緥搴旂敤鍒楄〃')
    get_app_list_parser.add_argument('product_id', help='浜у搧 ID')
    get_app_list_parser.add_argument('pod_id', help='瀹炰緥 ID')
    get_app_list_parser.set_defaults(func=cmd_get_pod_app_list)

    detail_app_parser = subparsers.add_parser('detail-app', help='鏌ヨ搴旂敤淇℃伅')
    detail_app_parser.add_argument('product_id', help='浜у搧 ID')
    detail_app_parser.add_argument('app_id', help='搴旂敤 ID')
    detail_app_parser.set_defaults(func=cmd_detail_app)

    list_apps_parser = subparsers.add_parser('list-apps', help='鏌ヨ搴旂敤淇℃伅鍒楄〃')
    list_apps_parser.add_argument('product_id', help='浜у搧 ID')
    list_apps_parser.add_argument('--app-id', help='搴旂敤 ID')
    list_apps_parser.add_argument('--app-name', help='搴旂敤鍚嶇О')
    list_apps_parser.add_argument('--app-type', type=int, help='搴旂敤绫诲瀷')
    list_apps_parser.add_argument('--package-name-list', help='鍖呭悕鍒楄〃锛岄€楀彿鍒嗛殧')
    list_apps_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺')
    list_apps_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_apps_parser.set_defaults(func=cmd_list_apps)

    list_app_version_deploys_parser = subparsers.add_parser('list-app-version-deploys', help='鏌ヨ搴旂敤鐗堟湰閮ㄧ讲淇℃伅鍒楄〃')
    list_app_version_deploys_parser.add_argument('product_id', help='浜у搧 ID')
    list_app_version_deploys_parser.add_argument('app_id', help='搴旂敤 ID')
    list_app_version_deploys_parser.add_argument('--version-id', help='搴旂敤鐗堟湰 ID')
    list_app_version_deploys_parser.set_defaults(func=cmd_list_app_version_deploys)

    get_app_crash_log_parser = subparsers.add_parser('get-app-crash-log', help='鏌ヨ搴旂敤宕╂簝鏃ュ織')
    get_app_crash_log_parser.add_argument('product_id', help='浜у搧 ID')
    get_app_crash_log_parser.add_argument('pod_id_list', help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    get_app_crash_log_parser.add_argument('--start-time', type=int, required=True, help='寮€濮嬫椂闂?Unix 绉?)
    get_app_crash_log_parser.add_argument('--end-time', type=int, required=True, help='缁撴潫鏃堕棿 Unix 绉?)
    get_app_crash_log_parser.set_defaults(func=cmd_get_app_crash_log)

    install_apps_parser = subparsers.add_parser('install-apps', help='鎵归噺瀹夎搴旂敤')
    install_apps_parser.add_argument('product_id', help='浜у搧 ID')
    install_apps_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    install_apps_parser.add_argument('--app-list', required=True, help='搴旂敤鍒楄〃锛涙牸寮?AppId:VersionId,AppId2:VersionId2')
    install_apps_parser.add_argument('--install-type', type=int, help='瀹夎妯″紡')
    install_apps_parser.add_argument('--is-preinstall', action='store_true', help='鏍囪涓洪瑁呭簲鐢?)
    install_apps_parser.set_defaults(func=cmd_install_apps)

    upload_app_parser = subparsers.add_parser('upload-app', help='涓婁紶搴旂敤')
    upload_app_parser.add_argument('product_id', help='浜у搧 ID')
    upload_app_parser.add_argument('--app-type', type=int, required=True, help='搴旂敤绫诲瀷')
    upload_app_parser.add_argument('--download-url', required=True, help='搴旂敤鏂囦欢涓嬭浇 URL')
    upload_app_parser.add_argument('--app-id', help='搴旂敤 ID')
    upload_app_parser.add_argument('--app-name', help='搴旂敤鍚嶇О')
    upload_app_parser.add_argument('--rotation', type=int, help='鏂瑰悜锛?=绔栧睆锛?70=妯睆')
    upload_app_parser.add_argument('--app-desc', help='搴旂敤鎻忚堪')
    upload_app_parser.add_argument('--parse-flag', type=int, help='瑙ｆ瀽鏂瑰紡')
    upload_app_parser.add_argument('--app-mode', choices=['Public', 'Private'], help='搴旂敤鑼冨洿')
    upload_app_parser.set_defaults(func=cmd_upload_app)

    update_app_parser = subparsers.add_parser('update-app', help='淇敼搴旂敤')
    update_app_parser.add_argument('product_id', help='浜у搧 ID')
    update_app_parser.add_argument('--app-id', required=True, help='搴旂敤 ID')
    update_app_parser.add_argument('--app-name', help='搴旂敤鍚嶇О')
    update_app_parser.add_argument('--rotation', type=int, help='鏂瑰悜')
    update_app_parser.add_argument('--icon-url', help='鍥炬爣 URL')
    update_app_parser.add_argument('--app-desc', help='搴旂敤鎻忚堪')
    update_app_parser.add_argument('--app-mode', choices=['Public'], help='搴旂敤鑼冨洿')
    update_app_parser.set_defaults(func=cmd_update_app)

    delete_app_parser = subparsers.add_parser('delete-app', help='鍒犻櫎搴旂敤')
    delete_app_parser.add_argument('product_id', help='浜у搧 ID')
    delete_app_parser.add_argument('--app-id', required=True, help='搴旂敤 ID')
    delete_app_parser.set_defaults(func=cmd_delete_app)

    delete_app_version_parser = subparsers.add_parser('delete-app-version', help='鍒犻櫎搴旂敤鐗堟湰')
    delete_app_version_parser.add_argument('product_id', help='浜у搧 ID')
    delete_app_version_parser.add_argument('--version-id', required=True, help='搴旂敤鐗堟湰 ID')
    delete_app_version_parser.set_defaults(func=cmd_delete_app_version)

    launch_apps_parser = subparsers.add_parser('launch-apps', help='鎵归噺鍚姩搴旂敤')
    launch_apps_parser.add_argument('product_id', help='浜у搧 ID')
    launch_apps_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    launch_apps_parser.add_argument('--package-name-list', required=True, help='鍖呭悕鍒楄〃锛岄€楀彿鍒嗛殧')
    launch_apps_parser.set_defaults(func=cmd_launch_apps)
