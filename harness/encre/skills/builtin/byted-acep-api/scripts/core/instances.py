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

"""瀹炰緥妯″潡銆?""
from . import cli_common as cli


def cmd_create_pod(args):
    kwargs = {}
    for field, api_field in {
        'data_size': 'DataSize',
        'display_layout_id': 'DisplayLayoutId',
        'tag_id': 'TagId',
        'up_bandwidth_limit': 'UpBandwidthLimit',
        'down_bandwidth_limit': 'DownBandwidthLimit',
        'custom_route_id': 'CustomRouteId',
        'dns_id': 'DNSId',
        'ip_white_list': 'IPWhiteList',
        'resource_type': 'ResourceType',
        'host_id': 'HostId',
        'use_phone_template': 'UsePhoneTemplate',
        'phone_template_id': 'PhoneTemplateId',
        'is_selinux_on': 'IsSelinuxOn',
        'image_id': 'ImageId',
    }.items():
        value = getattr(args, field, None)
        if value is not None:
            kwargs[api_field] = value
    if getattr(args, 'start', False):
        kwargs['Start'] = True
    if getattr(args, 'port_mapping_rule_id_list', None):
        kwargs['PortMappingRuleIdList'] = cli.parse_csv_values(args.port_mapping_rule_id_list)
    result = cli.get_client().create_pod(
        name=args.name,
        template_id=args.template_id,
        configuration_code=args.configuration_code,
        count=args.count,
        product_id=args.product_id,
        dc_id=args.dc_id,
        **kwargs,
    )
    cli.print_result(result)


def cmd_list_pods(args):
    kwargs = cli.request_kwargs(args)
    for key, value in {
        'PodIdList': cli.parse_csv_values(args.pod_id_list),
        'ConfigurationCodeList': cli.parse_csv_values(args.configuration_code_list),
        'RegionList': cli.parse_csv_values(args.region_list),
        'DcList': cli.parse_csv_values(args.dc_list),
        'TagIdList': cli.parse_csv_values(args.tag_id_list),
        'OnlineList': cli.parse_csv_values(args.online_list, int),
        'StreamStatusList': cli.parse_csv_values(args.stream_status_list, int),
        'AuthorityStatus': args.authority_status,
        'ZoneId': args.zone_id,
        'ServerTypeCode': args.server_type_code,
        'HostId': args.host_id,
        'DNSId': args.dns_id,
        'PodName': args.pod_name,
        'ArchiveStatus': args.archive_status,
    }.items():
        if value is not None:
            kwargs[key] = value
    for key, value in {
        'page_size': args.page_size,
        'page_number': args.page_number,
        'max_results': args.max_results,
        'next_token': args.next_token,
    }.items():
        if value is not None:
            kwargs[key] = value
    cli.print_result(cli.get_client().list_pods(**kwargs))


def cmd_detail_pod(args):
    cli.print_result(cli.get_client().detail_pod(
        pod_id=args.pod_id,
        product_id=args.product_id,
    ))


def cmd_delete_pod(args):
    kwargs = cli.request_kwargs(args)
    if getattr(args, "force_destroy", False):
        kwargs["ForceDestroyFlag"] = True
    cli.print_result(cli.get_client().delete_pod(args.pod_id, **kwargs))


def cmd_update_pod(args):
    kwargs = {}
    for field, api_field in {
        'pod_name': 'PodName',
        'data_size': 'DataSize',
        'configuration_code': 'ConfigurationCode',
        'display_layout_id': 'DisplayLayoutId',
        'up_bandwidth_limit': 'UpBandwidthLimit',
        'down_bandwidth_limit': 'DownBandwidthLimit',
        'custom_route_id': 'CustomRouteId',
        'dns_id': 'DNSId',
        'ip_white_list': 'IPWhiteList',
        'is_selinux_on': 'IsSelinuxOn',
    }.items():
        value = getattr(args, field, None)
        if value is not None:
            kwargs[api_field] = value
    if getattr(args, 'port_mapping_rule_id_list', None):
        kwargs['PortMappingRuleIdList'] = cli.parse_csv_values(args.port_mapping_rule_id_list)
    result = cli.get_client().update_pod(
        args.pod_id,
        product_id=args.product_id,
        image_id=args.image_id,
        force=args.force,
        **kwargs,
    )
    cli.print_result(result)


def _simple_pod_command(method_name, pod_id, args):
    cli.print_result(getattr(cli.get_client(), method_name)(pod_id, **cli.request_kwargs(args)))


def cmd_power_on_pod(args):
    _simple_pod_command('power_on_pod', args.pod_id, args)


def cmd_power_off_pod(args):
    _simple_pod_command('power_off_pod', args.pod_id, args)


def cmd_reboot_pod(args):
    _simple_pod_command('reboot_pod', args.pod_id, args)


def cmd_reset_pod(args):
    _simple_pod_command('reset_pod', args.pod_id, args)


def cmd_get_pod_metric(args):
    cli.print_result(cli.get_client().get_pod_metric(pod_id=args.pod_id, product_id=args.product_id))


def cmd_set_proxy(args):
    cli.print_result(cli.get_client().set_proxy(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        proxy_status=args.proxy_status,
        proxy_config=cli.parse_json_option(args.proxy_config, '--proxy-config', dict),
        product_id=args.product_id,
    ))


def cmd_get_proxy(args):
    cli.print_result(cli.get_client().get_proxy(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        product_id=args.product_id,
    ))


def cmd_get_presigned_edge_url(args):
    cli.print_result(cli.get_client().get_presigned_edge_url(
        args.pod_id,
        api_type=args.api_type,
        api_payload=cli.parse_string_params(args.payload),
        api_path=args.api_path,
        ttl=args.ttl,
        timeout=args.timeout,
        single_use=args.single_use,
        product_id=args.product_id,
    ))


def cmd_pod_mute(args):
    cli.print_result(cli.get_client().pod_mute(
        pod_id=args.pod_id,
        mute=cli.parse_bool_flag(args.mute),
        display_list=cli.parse_csv_values(args.display_list),
        product_id=args.product_id,
    ))


def cmd_pod_adb(args):
    cli.print_result(cli.get_client().pod_adb(
        pod_id=args.pod_id,
        enable=cli.parse_bool_flag(args.enable),
        product_id=args.product_id,
    ))


def cmd_pod_stop(args):
    cli.print_result(cli.get_client().pod_stop(pod_id=args.pod_id, product_id=args.product_id))


def cmd_pod_data_delete(args):
    cli.print_result(cli.get_client().pod_data_delete(
        pod_id=args.pod_id,
        file_path_list=cli.parse_csv_values(args.file_path_list),
        package_list=cli.parse_csv_values(args.package_list),
        product_id=args.product_id,
    ))


def cmd_create_pod_one_step(args):
    result = cli.get_client().create_pod_one_step(
        configuration_code=args.configuration_code,
        dc=args.dc,
        app_list=cli.parse_app_list(args.app_list),
        product_id=args.product_id,
        pod_name=args.pod_name,
        image_id=args.image_id,
        data_size=args.data_size,
        display_layout_id=args.display_layout_id,
        overlay_settings=cli.parse_json_option(args.overlay_settings, '--overlay-settings', list),
        overlay_property=cli.parse_json_option(args.overlay_property, '--overlay-property', list),
        overlay_persist_property=cli.parse_json_option(args.overlay_persist_property, '--overlay-persist-property', list),
        tag_id=args.tag_id,
        up_bandwidth_limit=args.up_bandwidth_limit,
        down_bandwidth_limit=args.down_bandwidth_limit,
        custom_route_id=args.custom_route_id,
        dns_id=args.dns_id,
        port_mapping_rule_id_list=cli.parse_csv_values(args.port_mapping_rule_id_list),
        ip_white_list=args.ip_white_list,
        resource_type=args.resource_type,
        host_id=args.host_id,
        is_preinstall=cli.parse_bool_flag(args.is_preinstall) if args.is_preinstall is not None else None,
        use_phone_template=args.use_phone_template,
        phone_template_id=args.phone_template_id,
        is_selinux_on=cli.parse_bool_flag(args.is_selinux_on) if args.is_selinux_on is not None else None,
    )
    cli.print_result(result)


def cmd_update_pod_resource_apply_num(args):
    result = cli.get_client().update_pod_resource_apply_num(
        apply_num=args.apply_num,
        product_id=args.product_id,
        resource_set_id=args.resource_set_id,
        configuration_code=args.configuration_code,
        dc=args.dc,
    )
    cli.print_result(result)


def cmd_backup_pod(args):
    cli.print_result(cli.get_client().backup_pod(pod_id_list=cli.parse_csv_values(args.pod_id_list), product_id=args.product_id))


def cmd_cancel_backup_pod(args):
    cli.print_result(cli.get_client().cancel_backup_pod(pod_id_list=cli.parse_csv_values(args.pod_id_list), product_id=args.product_id))


def cmd_restore_pod(args):
    cli.print_result(cli.get_client().restore_pod(
        product_id=args.product_id,
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        specify_host_list=cli.parse_json_option(args.specify_host_list, '--specify-host-list', list),
    ))


def cmd_cancel_restore_pod(args):
    cli.print_result(cli.get_client().cancel_restore_pod(pod_id_list=cli.parse_csv_values(args.pod_id_list), product_id=args.product_id))


def cmd_pod_data_transfer(args):
    cli.print_result(cli.get_client().pod_data_transfer(
        origin_pod_id=args.origin_pod_id,
        dst_pod_id_list=cli.parse_csv_values(args.dst_pod_id_list),
        transfer_type=args.type,
        product_id=args.product_id,
    ))


def cmd_migrate_pod(args):
    cli.print_result(cli.get_client().migrate_pod(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        target_dc=args.target_dc,
        product_id=args.product_id,
    ))


def cmd_backup_data(args):
    cli.print_result(cli.get_client().backup_data(
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        description=args.description,
        backup_all=cli.parse_bool_flag(args.backup_all) if args.backup_all is not None else None,
        include_path_list=cli.parse_csv_values(args.include_path_list),
        exclude_path_list=cli.parse_csv_values(args.exclude_path_list),
        product_id=args.product_id,
    ))


def cmd_restore_data(args):
    cli.print_result(cli.get_client().restore_data(
        backup_data_id=args.backup_data_id,
        pod_id_list=cli.parse_csv_values(args.pod_id_list),
        create_pod_num=args.create_pod_num,
        product_id=args.product_id,
    ))


def cmd_list_backup_data(args):
    cli.print_result(cli.get_client().list_backup_data(
        source_pod_id=args.source_pod_id,
        backup_data_id_list=cli.parse_csv_values(args.backup_data_id_list),
        status=args.status,
        max_results=args.max_results,
        next_token=args.next_token,
        product_id=args.product_id,
    ))


def cmd_delete_backup_data(args):
    cli.print_result(cli.get_client().delete_backup_data(
        backup_data_id_list=cli.parse_csv_values(args.backup_data_id_list),
        product_id=args.product_id,
    ))


def register(subparsers):

    create_pod_parser = subparsers.add_parser('create-pod', help='鍒涘缓浜戞墜鏈哄疄渚?)
    create_pod_parser.add_argument('product_id', help='浜у搧 ID')
    create_pod_parser.add_argument('--name', required=True, help='瀹炰緥鍚嶇О')
    create_pod_parser.add_argument('--template-id', required=True, help='鏈哄瀷妯℃澘 ID')
    create_pod_parser.add_argument('--configuration-code', required=True, help='濂楅浠ｇ爜')
    create_pod_parser.add_argument('--count', type=int, default=1, help='鍒涘缓鏁伴噺')
    create_pod_parser.add_argument('--dc-id', help='鏈烘埧 ID锛堟寜闇€鎸囧畾锛涗笉浠庨厤缃粯璁よ鍙栵級')
    create_pod_parser.add_argument('--image-id', help='瀹炰緥闀滃儚 ID')
    create_pod_parser.add_argument('--data-size', help='浜戠洏瀛樺偍瀹归噺锛屽 32Gi')
    create_pod_parser.add_argument('--display-layout-id', help='灞忓箷甯冨眬 ID')
    create_pod_parser.add_argument('--start', action='store_true', help='鍒涘缓瀹屾垚鍚庣珛鍗冲紑鏈?)
    create_pod_parser.add_argument('--tag-id', help='鏍囩 ID')
    create_pod_parser.add_argument('--up-bandwidth-limit', type=int, help='涓婅甯﹀涓婇檺 Mbps锛? 琛ㄧず涓嶉檺閫?)
    create_pod_parser.add_argument('--down-bandwidth-limit', type=int, help='涓嬭甯﹀涓婇檺 Mbps锛? 琛ㄧず涓嶉檺閫?)
    create_pod_parser.add_argument('--custom-route-id', help='鑷畾涔夎矾鐢辫鍒?ID')
    create_pod_parser.add_argument('--dns-id', help='鑷畾涔?DNS 瑙勫垯 ID')
    create_pod_parser.add_argument('--port-mapping-rule-id-list', help='绔彛鏄犲皠瑙勫垯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    create_pod_parser.add_argument('--ip-white-list', help='鐧藉悕鍗?IP锛岄€楀彿鍒嗛殧')
    create_pod_parser.add_argument('--host-id', help='鏈湴瀛樺偍涓氬姟鎸囧畾浜戞満 ID')
    create_pod_parser.add_argument('--use-phone-template', type=int, choices=[1, 2], help='鏄惁浣跨敤鏈哄瀷搴擄細1=浣跨敤锛?=涓嶄娇鐢?)
    create_pod_parser.add_argument('--phone-template-id', help='鏈哄瀷搴?ID')
    create_pod_parser.add_argument('--is-selinux-on', action='store_true', help='寮€鍚?SELinux')
    create_pod_parser.add_argument('--resource-type', type=int, choices=[100, 200], help='涓氬姟璧勬簮绫诲瀷锛?00=浜戠洏瀛樺偍锛?00=鏈湴瀛樺偍')
    create_pod_parser.set_defaults(func=cmd_create_pod)

    list_pods_parser = subparsers.add_parser('list-pods', help='鏌ヨ浜戞墜鏈哄疄渚嬪垪琛?)
    list_pods_parser.add_argument('product_id', help='浜у搧 ID')
    list_pods_parser.add_argument('--page-size', type=int, help='鍏煎鏃у弬鏁帮細姣忛〉鏁伴噺')
    list_pods_parser.add_argument('--page-number', type=int, help='鍏煎鏃у弬鏁帮細椤电爜')
    list_pods_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺锛屾渶澶?100')
    list_pods_parser.add_argument('--next-token', help='鍒嗛〉鏌ヨ鍑瘉')
    list_pods_parser.add_argument('--pod-id-list', help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_pods_parser.add_argument('--configuration-code-list', help='瀹炰緥瑙勬牸 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_pods_parser.add_argument('--region-list', help='澶у尯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_pods_parser.add_argument('--dc-list', help='鏈烘埧 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_pods_parser.add_argument('--tag-id-list', help='鏍囩 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_pods_parser.add_argument('--online-list', help='杩愯鐘舵€佸垪琛紝閫楀彿鍒嗛殧')
    list_pods_parser.add_argument('--stream-status-list', help='鎺ㄦ祦鐘舵€佸垪琛紝閫楀彿鍒嗛殧')
    list_pods_parser.add_argument('--authority-status', type=int, help='杩愮淮鎺堟潈鐘舵€侊細1=鏈巿鏉冿紝2=宸叉巿鏉?)
    list_pods_parser.add_argument('--zone-id', help='鐗囧尯 ID')
    list_pods_parser.add_argument('--server-type-code', help='浜戞満瑙勬牸')
    list_pods_parser.add_argument('--host-id', help='浜戞満 ID')
    list_pods_parser.add_argument('--dns-id', help='DNS 瑙勫垯 ID')
    list_pods_parser.add_argument('--pod-name', help='瀹炰緥鍚嶇О锛岀簿纭煡鎵?)
    list_pods_parser.add_argument('--archive-status', type=int, help='澶囦唤/杩樺師鐘舵€?)
    list_pods_parser.set_defaults(func=cmd_list_pods)

    detail_pod_parser = subparsers.add_parser('detail-pod', help='鏌ヨ浜戞墜鏈哄疄渚嬭鎯?)
    detail_pod_parser.add_argument('product_id', help='浜у搧 ID')
    detail_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    detail_pod_parser.set_defaults(func=cmd_detail_pod)

    delete_pod_parser = subparsers.add_parser('delete-pod', help='鍒犻櫎浜戞墜鏈哄疄渚?)
    delete_pod_parser.add_argument('product_id', help='浜у搧 ID')
    delete_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    delete_pod_parser.set_defaults(func=cmd_delete_pod)

    power_on_pod_parser = subparsers.add_parser('power-on-pod', help='寮€鏈?)
    power_on_pod_parser.add_argument('product_id', help='浜у搧 ID')
    power_on_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    power_on_pod_parser.set_defaults(func=cmd_power_on_pod)

    power_off_pod_parser = subparsers.add_parser('power-off-pod', help='鍏虫満')
    power_off_pod_parser.add_argument('product_id', help='浜у搧 ID')
    power_off_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    power_off_pod_parser.set_defaults(func=cmd_power_off_pod)

    reboot_pod_parser = subparsers.add_parser('reboot-pod', help='閲嶅惎瀹炰緥')
    reboot_pod_parser.add_argument('product_id', help='浜у搧 ID')
    reboot_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    reboot_pod_parser.set_defaults(func=cmd_reboot_pod)

    reset_pod_parser = subparsers.add_parser('reset-pod', help='閲嶇疆瀹炰緥')
    reset_pod_parser.add_argument('product_id', help='浜у搧 ID')
    reset_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    reset_pod_parser.set_defaults(func=cmd_reset_pod)

    get_pod_metric_parser = subparsers.add_parser('get-pod-metric', help='鏌ヨ瀹炰緥璧勬簮鐘舵€?)
    get_pod_metric_parser.add_argument('product_id', help='浜у搧 ID')
    get_pod_metric_parser.add_argument('pod_id', help='瀹炰緥 ID')
    get_pod_metric_parser.set_defaults(func=cmd_get_pod_metric)

    update_pod_parser = subparsers.add_parser('update-pod', help='鏇存柊瀹炰緥閰嶇疆鎴栭暅鍍?)
    update_pod_parser.add_argument('product_id', help='浜у搧 ID')
    update_pod_parser.add_argument('pod_id', help='瀹炰緥 ID')
    update_pod_parser.add_argument('--image-id', help='鐩爣闀滃儚 ID')
    update_pod_parser.add_argument('--pod-name', help='瀹炰緥鏂板悕绉?)
    update_pod_parser.add_argument('--data-size', help='浜戠洏瀛樺偍瀹归噺锛屽 32Gi')
    update_pod_parser.add_argument('--configuration-code', help='鐩爣濂楅瑙勬牸 ID')
    update_pod_parser.add_argument('--display-layout-id', help='灞忓箷甯冨眬 ID')
    update_pod_parser.add_argument('--up-bandwidth-limit', type=int, help='涓婅甯﹀涓婇檺 Mbps')
    update_pod_parser.add_argument('--down-bandwidth-limit', type=int, help='涓嬭甯﹀涓婇檺 Mbps')
    update_pod_parser.add_argument('--custom-route-id', help='鑷畾涔夎矾鐢辫鍒?ID')
    update_pod_parser.add_argument('--dns-id', help='鑷畾涔?DNS 瑙勫垯 ID')
    update_pod_parser.add_argument('--port-mapping-rule-id-list', help='绔彛鏄犲皠瑙勫垯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    update_pod_parser.add_argument('--ip-white-list', help='鐧藉悕鍗?IP锛岄€楀彿鍒嗛殧')
    update_pod_parser.add_argument('--is-selinux-on', action='store_true', help='寮€鍚?SELinux')
    update_pod_parser.add_argument('--force', action='store_true', help='浼?Force=true 寮哄埗鏇存柊杩愯涓疄渚嬶紱闀滃儚闇€閲嶅惎鍚庣敓鏁?)
    update_pod_parser.set_defaults(func=cmd_update_pod)

    set_proxy_parser = subparsers.add_parser('set-proxy', help='璁剧疆浠ｇ悊鏈嶅姟')
    set_proxy_parser.add_argument('product_id', help='浜у搧 ID')
    set_proxy_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    set_proxy_parser.add_argument('--proxy-status', type=int, choices=[0, 1], required=True, help='浠ｇ悊鐘舵€侊細1=寮€鍚紝0=鍏抽棴')
    set_proxy_parser.add_argument('--proxy-config', help='ProxyConfig JSON 瀵硅薄锛涘紑鍚唬鐞嗘椂蹇呭～')
    set_proxy_parser.set_defaults(func=cmd_set_proxy)

    get_proxy_parser = subparsers.add_parser('get-proxy', help='鑾峰彇浠ｇ悊鏈嶅姟璁剧疆')
    get_proxy_parser.add_argument('product_id', help='浜у搧 ID')
    get_proxy_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    get_proxy_parser.set_defaults(func=cmd_get_proxy)

    get_edge_url_parser = subparsers.add_parser('get-presigned-edge-url', help='鑾峰彇瀹炰緥鐩磋繛棰勭鍚?URL锛圙etPreSignedEdgeURL锛?)
    get_edge_url_parser.add_argument('product_id', help='浜у搧 ID')
    get_edge_url_parser.add_argument('pod_id', help='瀹炰緥 ID')
    get_edge_url_parser.add_argument('--api-type', required=True, help='API 绫诲瀷锛屽 TakeScreenshot 鎴?Sandbox')
    get_edge_url_parser.add_argument('--api-path', help='API 璺緞锛屽 /screenshot銆?sandbox/ws銆?sandbox/exec銆?sandbox/healthz')
    get_edge_url_parser.add_argument('--payload', action='append', help='APIPayload 閿€煎锛孠ey=Value锛屽彲閲嶅锛沄alue 鎬绘槸鎸夊瓧绗︿覆浼犻€?)
    get_edge_url_parser.add_argument('--ttl', type=int, help='棰勭鍚嶉摼鎺ユ湁鏁堟湡锛屽崟浣嶇锛岄粯璁?60锛屾渶澶?86400')
    get_edge_url_parser.add_argument('--timeout', type=int, help='鐩磋繛璇锋眰瓒呮椂鏃堕棿锛屽崟浣嶇')
    get_edge_url_parser.add_argument('--single-use', action='store_true', default=None, help='鐢熸垚鍗曟浣跨敤 URL')
    get_edge_url_parser.set_defaults(func=cmd_get_presigned_edge_url)

    pod_mute_parser = subparsers.add_parser('pod-mute', help='鏆傚仠/鎭㈠瀹炰緥鎺ㄦ祦')
    pod_mute_parser.add_argument('product_id', help='浜у搧 ID')
    pod_mute_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    pod_mute_parser.add_argument('--mute', required=True, type=cli.parse_bool_flag, help='true=鏆傚仠鎺ㄦ祦锛宖alse=鎭㈠鎺ㄦ祦')
    pod_mute_parser.add_argument('--display-list', help='灞忓箷 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    pod_mute_parser.set_defaults(func=cmd_pod_mute)

    pod_adb_parser = subparsers.add_parser('pod-adb', help='鎵撳紑/鍏抽棴瀹炰緥 ADB')
    pod_adb_parser.add_argument('product_id', help='浜у搧 ID')
    pod_adb_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    pod_adb_parser.add_argument('--enable', required=True, type=cli.parse_bool_flag, help='true=寮€鍚?ADB锛宖alse=鍏抽棴 ADB')
    pod_adb_parser.set_defaults(func=cmd_pod_adb)

    pod_stop_parser = subparsers.add_parser('pod-stop', help='鍋滄瀹炰緥鎺ㄦ祦')
    pod_stop_parser.add_argument('product_id', help='浜у搧 ID')
    pod_stop_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    pod_stop_parser.set_defaults(func=cmd_pod_stop)

    pod_data_delete_parser = subparsers.add_parser('pod-data-delete', help='娓呯悊鐢ㄦ埛鏁版嵁')
    pod_data_delete_parser.add_argument('product_id', help='浜у搧 ID')
    pod_data_delete_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    pod_data_delete_parser.add_argument('--file-path-list', required=True, help='璺緞鍒楄〃锛岄€楀彿鍒嗛殧')
    pod_data_delete_parser.add_argument('--package-list', help='鍖呭悕鍒楄〃锛岄€楀彿鍒嗛殧')
    pod_data_delete_parser.set_defaults(func=cmd_pod_data_delete)

    create_pod_one_step_parser = subparsers.add_parser('create-pod-one-step', help='鍒涘缓瀹夊崜瀹炰緥骞堕儴缃插簲鐢?)
    create_pod_one_step_parser.add_argument('product_id', help='浜у搧 ID')
    create_pod_one_step_parser.add_argument('--pod-name', help='瀹炰緥鍚嶇О')
    create_pod_one_step_parser.add_argument('--image-id', help='闀滃儚 ID')
    create_pod_one_step_parser.add_argument('--configuration-code', required=True, help='濂楅瑙勬牸 ID')
    create_pod_one_step_parser.add_argument('--data-size', help='浜戠洏瀛樺偍瀹归噺锛屽 8Gi')
    create_pod_one_step_parser.add_argument('--dc', required=True, help='鏈烘埧 ID')
    create_pod_one_step_parser.add_argument('--display-layout-id', help='灞忓箷甯冨眬 ID')
    create_pod_one_step_parser.add_argument('--overlay-settings', help='OverlaySettings JSON 鏁扮粍')
    create_pod_one_step_parser.add_argument('--overlay-property', help='OverlayProperty JSON 鏁扮粍')
    create_pod_one_step_parser.add_argument('--overlay-persist-property', help='OverlayPersistProperty JSON 鏁扮粍')
    create_pod_one_step_parser.add_argument('--tag-id', help='鏍囩 ID')
    create_pod_one_step_parser.add_argument('--up-bandwidth-limit', type=int, help='涓婅甯﹀闄愬埗 Mbps')
    create_pod_one_step_parser.add_argument('--down-bandwidth-limit', type=int, help='涓嬭甯﹀闄愬埗 Mbps')
    create_pod_one_step_parser.add_argument('--app-list', required=True, help='搴旂敤鍒楄〃锛屾敮鎸?AppId:VersionId,AppId2:VersionId2 鎴?JSON 鏁扮粍')
    create_pod_one_step_parser.add_argument('--custom-route-id', help='鑷畾涔夎矾鐢?ID')
    create_pod_one_step_parser.add_argument('--dns-id', help='DNS 瑙勫垯 ID')
    create_pod_one_step_parser.add_argument('--port-mapping-rule-id-list', help='绔彛鏄犲皠瑙勫垯 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    create_pod_one_step_parser.add_argument('--ip-white-list', help='鐧藉悕鍗?IP锛岄€楀彿鍒嗛殧')
    create_pod_one_step_parser.add_argument('--resource-type', type=int, choices=[100, 200], help='璧勬簮绫诲瀷')
    create_pod_one_step_parser.add_argument('--host-id', help='浜戞満 ID')
    create_pod_one_step_parser.add_argument('--is-preinstall', type=cli.parse_bool_flag, help='鏄惁鏍囪涓洪瑁呭簲鐢細true/false')
    create_pod_one_step_parser.add_argument('--use-phone-template', type=int, choices=[1, 2], help='鏄惁浣跨敤鏈哄瀷搴?)
    create_pod_one_step_parser.add_argument('--phone-template-id', help='鏈哄瀷搴?ID')
    create_pod_one_step_parser.add_argument('--is-selinux-on', type=cli.parse_bool_flag, help='鏄惁寮€鍚?SELinux锛歵rue/false')
    create_pod_one_step_parser.set_defaults(func=cmd_create_pod_one_step)

    update_pod_resource_apply_num_parser = subparsers.add_parser('update-pod-resource-apply-num', help='淇敼瀹炰緥璁㈠崟骞跺彂鏁伴噺')
    update_pod_resource_apply_num_parser.add_argument('product_id', help='浜у搧 ID')
    update_pod_resource_apply_num_parser.add_argument('--resource-set-id', help='璧勬簮缁?ID')
    update_pod_resource_apply_num_parser.add_argument('--configuration-code', help='瀹炰緥瑙勬牸 ID')
    update_pod_resource_apply_num_parser.add_argument('--dc', help='鏈烘埧 ID')
    update_pod_resource_apply_num_parser.add_argument('--apply-num', type=int, required=True, help='淇敼鍚庣殑瀹炰緥鏁伴噺')
    update_pod_resource_apply_num_parser.set_defaults(func=cmd_update_pod_resource_apply_num)

    backup_pod_parser = subparsers.add_parser('backup-pod', help='澶囦唤瀹炰緥')
    backup_pod_parser.add_argument('product_id', help='浜у搧 ID')
    backup_pod_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    backup_pod_parser.set_defaults(func=cmd_backup_pod)

    cancel_backup_pod_parser = subparsers.add_parser('cancel-backup-pod', help='鍙栨秷澶囦唤瀹炰緥')
    cancel_backup_pod_parser.add_argument('product_id', help='浜у搧 ID')
    cancel_backup_pod_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    cancel_backup_pod_parser.set_defaults(func=cmd_cancel_backup_pod)

    restore_pod_parser = subparsers.add_parser('restore-pod', help='杩樺師瀹炰緥')
    restore_pod_parser.add_argument('product_id', help='浜у搧 ID')
    restore_pod_parser.add_argument('--pod-id-list', help='寰呰繕鍘熷疄渚?ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    restore_pod_parser.add_argument('--specify-host-list', help='SpecifyHostList JSON 鏁扮粍')
    restore_pod_parser.set_defaults(func=cmd_restore_pod)

    cancel_restore_pod_parser = subparsers.add_parser('cancel-restore-pod', help='鍙栨秷杩樺師瀹炰緥')
    cancel_restore_pod_parser.add_argument('product_id', help='浜у搧 ID')
    cancel_restore_pod_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    cancel_restore_pod_parser.set_defaults(func=cmd_cancel_restore_pod)

    pod_data_transfer_parser = subparsers.add_parser('pod-data-transfer', help='瀹炰緥鏁版嵁澶嶅埗杩佺Щ')
    pod_data_transfer_parser.add_argument('product_id', help='浜у搧 ID')
    pod_data_transfer_parser.add_argument('--origin-pod-id', required=True, help='婧愬疄渚?ID')
    pod_data_transfer_parser.add_argument('--dst-pod-id-list', required=True, help='鐩爣瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    pod_data_transfer_parser.add_argument('--type', type=int, help='澶嶅埗杩佺Щ鏂瑰紡')
    pod_data_transfer_parser.set_defaults(func=cmd_pod_data_transfer)

    migrate_pod_parser = subparsers.add_parser('migrate-pod', help='杩佺Щ瀹炰緥')
    migrate_pod_parser.add_argument('product_id', help='浜у搧 ID')
    migrate_pod_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    migrate_pod_parser.add_argument('--target-dc', help='鐩爣鏈烘埧 ID')
    migrate_pod_parser.set_defaults(func=cmd_migrate_pod)

    backup_data_parser = subparsers.add_parser('backup-data', help='澶囦唤鏁版嵁')
    backup_data_parser.add_argument('product_id', help='浜у搧 ID')
    backup_data_parser.add_argument('--pod-id-list', required=True, help='瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    backup_data_parser.add_argument('--description', help='澶囦唤鎻忚堪')
    backup_data_parser.add_argument('--backup-all', type=cli.parse_bool_flag, help='鏄惁鍏ㄩ噺澶囦唤锛歵rue/false')
    backup_data_parser.add_argument('--include-path-list', help='鍖呭惈璺緞鍒楄〃锛岄€楀彿鍒嗛殧')
    backup_data_parser.add_argument('--exclude-path-list', help='鎺掗櫎璺緞鍒楄〃锛岄€楀彿鍒嗛殧')
    backup_data_parser.set_defaults(func=cmd_backup_data)

    restore_data_parser = subparsers.add_parser('restore-data', help='鎭㈠鏁版嵁')
    restore_data_parser.add_argument('product_id', help='浜у搧 ID')
    restore_data_parser.add_argument('--backup-data-id', required=True, help='澶囦唤鏁版嵁 ID')
    restore_data_parser.add_argument('--pod-id-list', help='鐩爣瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    restore_data_parser.add_argument('--create-pod-num', type=int, help='鑷姩鍒涘缓瀹炰緥鏁伴噺')
    restore_data_parser.set_defaults(func=cmd_restore_data)

    list_backup_data_parser = subparsers.add_parser('list-backup-data', help='鏌ヨ澶囦唤鏁版嵁')
    list_backup_data_parser.add_argument('product_id', help='浜у搧 ID')
    list_backup_data_parser.add_argument('--source-pod-id', help='婧愬疄渚?ID')
    list_backup_data_parser.add_argument('--backup-data-id-list', help='澶囦唤鏁版嵁 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    list_backup_data_parser.add_argument('--status', help='澶囦唤鏁版嵁鐘舵€?)
    list_backup_data_parser.add_argument('--max-results', type=int, default=10, help='姣忛〉鏁伴噺')
    list_backup_data_parser.add_argument('--next-token', help='鍒嗛〉娓告爣')
    list_backup_data_parser.set_defaults(func=cmd_list_backup_data)

    delete_backup_data_parser = subparsers.add_parser('delete-backup-data', help='鍒犻櫎澶囦唤鏁版嵁')
    delete_backup_data_parser.add_argument('product_id', help='浜у搧 ID')
    delete_backup_data_parser.add_argument('--backup-data-id-list', required=True, help='澶囦唤鏁版嵁 ID 鍒楄〃锛岄€楀彿鍒嗛殧')
    delete_backup_data_parser.set_defaults(func=cmd_delete_backup_data)
