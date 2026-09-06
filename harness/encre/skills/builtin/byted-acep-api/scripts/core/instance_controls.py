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

"""瀹炰緥鎺у埗妯″潡銆?""
from . import cli_common as cli

import tempfile
from pathlib import Path

from . import cli_common as cli


def cmd_start_recording(args):
    kwargs = cli.request_kwargs(args)
    if args.is_saved_on_pod is not None:
        kwargs['is_saved_on_pod'] = args.is_saved_on_pod
    cli.print_result(cli.get_client().start_recording(
        args.pod_id,
        duration_limit=args.duration_limit,
        round_id=args.round_id,
        **kwargs,
    ))


def cmd_stop_recording(args):
    cli.print_result(cli.get_client().stop_recording(args.pod_id, **cli.request_kwargs(args)))


def cmd_batch_screen_shot(args):
    kwargs = cli.request_kwargs(args)
    if args.pod_id_list:
        kwargs['pod_id_list'] = cli.parse_csv(args.pod_id_list)
    if (args.width is None) != (args.height is None):
        raise SystemExit('--width 鍜?--height 蹇呴』鍚屾椂浼犲叆')
    if args.width is not None:
        kwargs['width'] = args.width
    if args.height is not None:
        kwargs['height'] = args.height
    if args.quality is not None:
        kwargs['quality'] = args.quality
    if args.is_saved_on_pod is not None:
        kwargs['is_saved_on_pod'] = args.is_saved_on_pod
    if args.resize_mode is not None:
        kwargs['resize_mode'] = args.resize_mode
    if args.rotation is not None:
        kwargs['rotation'] = args.rotation
    if args.upload_type is not None:
        kwargs['upload_type'] = args.upload_type
    if args.round_id:
        kwargs['round_id'] = args.round_id
    if args.is_broadcasted is not None:
        kwargs['is_broadcasted'] = args.is_broadcasted
    if args.upload_type == 2 and not (args.tos_bucket and args.tos_region and args.tos_endpoint):
        raise SystemExit('--upload-type=2 鏃跺繀椤诲悓鏃朵紶鍏?--tos-bucket銆?-tos-region 鍜?--tos-endpoint')
    if args.tos_bucket or args.tos_region or args.tos_endpoint:
        if not (args.tos_bucket and args.tos_region and args.tos_endpoint):
            raise SystemExit('--tos-bucket銆?-tos-region 鍜?--tos-endpoint 蹇呴』鍚屾椂浼犲叆')
        kwargs['tos_info'] = {
            'Bucket': args.tos_bucket,
            'Region': args.tos_region,
            'Endpoint': args.tos_endpoint,
        }
    cli.print_result(cli.get_client().batch_screen_shot(args.pod_id, **kwargs))


def cmd_push_file(args):
    kwargs = cli.request_kwargs(args)
    if args.auto_unzip is not None:
        kwargs['AutoUnzip'] = args.auto_unzip == 0
    if args.overwrite is not None:
        kwargs['OverWrite'] = args.overwrite
    cli.print_result(cli.get_client().push_file(
        pod_id=args.pod_id,
        file_url=args.local_path,
        phone_path=args.phone_path,
        **kwargs,
    ))


def cmd_pull_file(args):
    kwargs = cli.request_kwargs(args)
    if args.range:
        kwargs['Range'] = args.range
    cli.print_result(cli.get_client().pull_file(
        pod_id=args.pod_id,
        phone_path=args.phone_path,
        output_path=args.output,
        **kwargs,
    ))


def cmd_run_command(args):
    kwargs = cli.request_kwargs(args)
    if args.permission_type:
        kwargs['permission_type'] = args.permission_type
    if args.timeout_seconds is not None:
        kwargs['timeout_seconds'] = args.timeout_seconds
    cli.print_result(cli.get_client().run_command(
        pod_id=args.pod_id,
        command=args.command,
        **kwargs,
    ))


def cmd_run_sync_command(args):
    kwargs = cli.request_kwargs(args)
    if args.permission_type:
        kwargs['PermissionType'] = args.permission_type
    if args.timeout_second is not None:
        kwargs['TimeoutSecond'] = args.timeout_second
    if args.result_length is not None:
        kwargs['ResultLength'] = args.result_length
    cli.print_result(cli.get_client().run_sync_command(
        pod_id=args.pod_id,
        command=args.command,
        **kwargs,
    ))


def cmd_pull_logcat(args):
    pod_id = args.pod_id
    local_path = Path(args.output).expanduser() if args.output else Path.cwd() / f'logcat_{pod_id}'
    filter_terms = args.filter_term or []
    if not args.no_default_filters:
        filter_terms = ['RunCommandHandler', 'AgentRPCServer', *filter_terms]
    max_bytes = args.max_bytes

    def logcat_paths(path: str) -> list[str]:
        aliases = ['/data/misc/logd/logcat']
        ordered = [path, *aliases]
        result = []
        for item in ordered:
            if item not in result:
                result.append(item)
        return result

    def filter_payload(payload: bytes) -> bytes:
        if not filter_terms:
            return payload
        encoded_terms = [term.encode('utf-8') for term in filter_terms]
        return b''.join(
            line for line in payload.splitlines(keepends=True)
            if not any(term in line for term in encoded_terms)
        )

    request_options = cli.request_kwargs(args)
    errors = {}
    raw_payload = None
    used_remote_path = None
    with tempfile.TemporaryDirectory(prefix=f'vephone-logcat-{pod_id}-') as tmpdir:
        temp_output = Path(tmpdir) / 'logcat.raw'
        for candidate in logcat_paths(args.remote_path):
            try:
                cli.get_client().pull_file(pod_id, candidate, output_path=str(temp_output), **request_options)
                raw_payload = temp_output.read_bytes()
                used_remote_path = candidate
                break
            except Exception as exc:
                errors[candidate] = str(exc)
        if raw_payload is None:
            detail = '; '.join(f'{path}: {message}' for path, message in errors.items())
            raise RuntimeError(f'pull-logcat failed for all candidate paths: {detail}')

    raw_size = len(raw_payload)
    filtered_payload = filter_payload(raw_payload)
    filtered_size = len(filtered_payload)
    output_payload = filtered_payload[-max_bytes:] if filtered_size > max_bytes else filtered_payload
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(output_payload)
    cli.print_result({
        'PodId': pod_id,
        'RemotePath': used_remote_path,
        'RequestedRemotePath': args.remote_path,
        'Output': str(local_path),
        'Size': len(output_payload),
        'RawSize': raw_size,
        'FilteredBytes': raw_size - filtered_size,
        'TruncatedBytes': filtered_size - len(output_payload),
        'FilterTerms': filter_terms,
        'SourceSize': raw_size,
        'SourceOffset': max(filtered_size - len(output_payload), 0),
        'MaxBytes': max_bytes,
        'Mode': 'PreSignedEdgeURL',
    })


def cmd_ban_user(args):
    cli.print_result(cli.get_client().ban_user(
        pod_id=args.pod_id,
        user_id=args.user_id,
        product_id=args.product_id,
        forbidden_interval=args.forbidden_interval,
        is_preview_stream=args.is_preview_stream,
    ))


def register(subparsers):

    start_recording_parser = subparsers.add_parser('start-recording', help='寮€濮嬪綍灞?)
    start_recording_parser.add_argument('product_id', help='浜у搧 ID')
    start_recording_parser.add_argument('pod_id', help='瀹炰緥 ID')
    start_recording_parser.add_argument('--duration-limit', type=int, required=True, help='鏈€澶у綍鍒舵椂闀匡紝绉掞紝鏈€澶?14400')
    start_recording_parser.add_argument('--round-id', required=True, help='褰曞睆璇锋眰鍞竴 ID')
    start_recording_parser.add_argument('--is-saved-on-pod', dest='is_saved_on_pod', action='store_true', help='鍦ㄤ簯鎵嬫満瀹炰緥涓繚鐣欏綍灞忔枃浠?)
    start_recording_parser.add_argument('--no-is-saved-on-pod', dest='is_saved_on_pod', action='store_false', help='涓嶅湪浜戞墜鏈哄疄渚嬩腑淇濈暀褰曞睆鏂囦欢')
    start_recording_parser.set_defaults(is_saved_on_pod=None)
    start_recording_parser.set_defaults(func=cmd_start_recording)

    stop_recording_parser = subparsers.add_parser('stop-recording', help='鍋滄褰曞睆')
    stop_recording_parser.add_argument('product_id', help='浜у搧 ID')
    stop_recording_parser.add_argument('pod_id', help='瀹炰緥 ID')
    stop_recording_parser.set_defaults(func=cmd_stop_recording)

    batch_screen_shot_parser = subparsers.add_parser('batch-screen-shot', help='鎵ц BatchScreenShot 鎴浘')
    batch_screen_shot_parser.add_argument('product_id', help='浜у搧 ID')
    batch_screen_shot_parser.add_argument('pod_id', help='瀹炰緥 ID')
    batch_screen_shot_parser.add_argument('--pod-id-list', help='鎵归噺鎴浘瀹炰緥 ID 鍒楄〃锛岄€楀彿鍒嗛殧锛涢粯璁や粎浣跨敤浣嶇疆鍙傛暟 pod_id')
    batch_screen_shot_parser.add_argument('--width', type=int, help='鎴浘瀹藉害锛岃寖鍥?200-2560锛涗笌 --height 浜掔浉渚濊禆')
    batch_screen_shot_parser.add_argument('--height', type=int, help='鎴浘楂樺害锛岃寖鍥?200-2560锛涗笌 --width 浜掔浉渚濊禆')
    batch_screen_shot_parser.add_argument('--quality', type=int, help='鎴浘鐢昏川鍘嬬缉姣斾緥锛岃寖鍥?1-100')
    batch_screen_shot_parser.add_argument('--is-saved-on-pod', dest='is_saved_on_pod', action='store_true', help='鍦ㄤ簯鎵嬫満瀹炰緥涓繚鐣欐埅鍥炬枃浠?)
    batch_screen_shot_parser.add_argument('--no-is-saved-on-pod', dest='is_saved_on_pod', action='store_false', help='涓嶅湪浜戞墜鏈哄疄渚嬩腑淇濈暀鎴浘鏂囦欢')
    batch_screen_shot_parser.set_defaults(is_saved_on_pod=None)
    batch_screen_shot_parser.add_argument('--resize-mode', type=int, choices=[0, 1, 2, 3, 4], help='鎴浘缂╂斁妯″紡')
    batch_screen_shot_parser.add_argument('--rotation', type=int, choices=[0, 1], help='鎴浘鏃嬭浆鏂瑰悜锛? 涓嶅鐞嗭紝1 杞负绔栧睆')
    batch_screen_shot_parser.add_argument('--upload-type', type=int, choices=[1, 2], help='涓婁紶鏂瑰紡锛? 涓婁紶鍒颁笟鍔″璞″瓨鍌紝2 涓婁紶鍒扮鏈夊瓨鍌ㄦ《')
    batch_screen_shot_parser.add_argument('--tos-bucket', help='UploadType=2 鏃剁殑 TOS Bucket')
    batch_screen_shot_parser.add_argument('--tos-region', help='UploadType=2 鏃剁殑 TOS Region')
    batch_screen_shot_parser.add_argument('--tos-endpoint', help='UploadType=2 鏃剁殑 TOS Endpoint')
    batch_screen_shot_parser.add_argument('--round-id', help='鎴浘璇锋眰鍞竴鏍囪瘑锛? 鍒嗛挓鍐呬笉鍙噸澶?)
    batch_screen_shot_parser.add_argument('--is-broadcasted', dest='is_broadcasted', action='store_true', help='骞挎挱鎴浘浜嬩欢')
    batch_screen_shot_parser.add_argument('--no-is-broadcasted', dest='is_broadcasted', action='store_false', help='涓嶅箍鎾埅鍥句簨浠?)
    batch_screen_shot_parser.set_defaults(is_broadcasted=None)
    batch_screen_shot_parser.set_defaults(func=cmd_batch_screen_shot)

    push_file_parser = subparsers.add_parser('push-file', help='涓婁紶鏂囦欢鍒颁簯鎵嬫満')
    push_file_parser.add_argument('product_id', help='浜у搧 ID')
    push_file_parser.add_argument('pod_id', help='瀹炰緥 ID')
    push_file_parser.add_argument('local_path', help='鏈湴鏂囦欢璺緞锛屾敮鎸?file:// 璺緞')
    push_file_parser.add_argument('phone_path', help='浜戞墜鏈虹洰鏍囨枃浠惰矾寰勶紱鑻ヤ紶鐩綍鍒欒嚜鍔ㄦ嫾鎺ユ湰鍦版枃浠跺悕')
    push_file_parser.add_argument('--auto-unzip', type=int, choices=[0, 1], help='鍏煎鏃у弬鏁帮細0 鑷姩瑙ｅ帇 zip锛? 涓嶈嚜鍔ㄨВ鍘?)
    push_file_parser.add_argument('--overwrite', dest='overwrite', action='store_true', help='瑕嗙洊鍚屽悕杩滅鏂囦欢')
    push_file_parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', help='涓嶈鐩栧悓鍚嶈繙绔枃浠?)
    push_file_parser.set_defaults(overwrite=None)
    push_file_parser.set_defaults(func=cmd_push_file)

    pull_file_parser = subparsers.add_parser('pull-file', help='浠庝簯鎵嬫満涓嬭浇鏂囦欢')
    pull_file_parser.add_argument('product_id', help='浜у搧 ID')
    pull_file_parser.add_argument('pod_id', help='瀹炰緥 ID')
    pull_file_parser.add_argument('phone_path', help='浜戞墜鏈轰笂鐨勬枃浠惰矾寰?)
    pull_file_parser.add_argument('--output', help='鏈湴杈撳嚭璺緞锛岄粯璁や娇鐢ㄥ綋鍓嶇洰褰曚笅鐨勫師鏂囦欢鍚?)
    pull_file_parser.add_argument('--range', help='HTTP Range 澶达紝濡?bytes=0-1023')
    pull_file_parser.set_defaults(func=cmd_pull_file)

    run_command_parser = subparsers.add_parser('run-command', help='寮傛鎵ц鍛戒护')
    run_command_parser.add_argument('product_id', help='浜у搧 ID')
    run_command_parser.add_argument('pod_id', help='瀹炰緥 ID')
    run_command_parser.add_argument('command', help='瑕佹墽琛岀殑鍛戒护')
    run_command_parser.add_argument('--permission-type', choices=['root', 'shell'], help='鍛戒护鎵ц鏉冮檺绫诲瀷')
    run_command_parser.add_argument('--timeout-seconds', type=int, help='寮傛鍛戒护瓒呮椂鏃堕暱锛屽崟浣嶇')
    run_command_parser.set_defaults(func=cmd_run_command)

    run_sync_command_parser = subparsers.add_parser('run-sync-command', help='鍚屾鎵ц鍛戒护')
    run_sync_command_parser.add_argument('product_id', help='浜у搧 ID')
    run_sync_command_parser.add_argument('pod_id', help='瀹炰緥 ID')
    run_sync_command_parser.add_argument('command', help='瑕佹墽琛岀殑鍛戒护')
    run_sync_command_parser.add_argument('--permission-type', choices=['root', 'shell'], help='鍛戒护鎵ц鏉冮檺绫诲瀷')
    run_sync_command_parser.add_argument('--timeout-second', type=int, help='鍛戒护瓒呮椂鏃堕棿锛屽崟浣嶇')
    run_sync_command_parser.add_argument('--result-length', type=int, help='stdout/stderr 鏈€澶ц繑鍥炲瓧鑺傛暟')
    run_sync_command_parser.set_defaults(func=cmd_run_sync_command)

    pull_logcat_parser = subparsers.add_parser('pull-logcat', help='閫氳繃 PreSignedEdgeURL 鐩磋繛鎷夊彇 logcat锛屽苟鍦ㄦ湰鍦拌繃婊?鎴柇')
    pull_logcat_parser.add_argument('product_id', help='浜у搧 ID')
    pull_logcat_parser.add_argument('pod_id', help='瀹炰緥 ID')
    pull_logcat_parser.add_argument('--output', help='鏈湴杈撳嚭鏂囦欢锛岄粯璁?./logcat_<pod_id>')
    pull_logcat_parser.add_argument('--remote-path', default='/data/misc/logd/logcat', help='杩滅 logcat 璺緞锛岄粯璁?/data/misc/logd/logcat')
    pull_logcat_parser.add_argument('--chunk-size', type=int, default=800, help='鍏煎鏃у弬鏁帮紝褰撳墠瀹炵幇涓嶅啀浣跨敤')
    pull_logcat_parser.add_argument('--max-bytes', type=int, default=5 * 1024 * 1024, help='鏈€澶氭媺鍙栨湯灏惧瓧鑺傛暟锛岄粯璁?5MB')
    pull_logcat_parser.add_argument('--concurrency', type=int, default=5, help='鍏煎鏃у弬鏁帮紝褰撳墠瀹炵幇涓嶅啀浣跨敤')
    pull_logcat_parser.add_argument('--retries', type=int, default=3, help='鍏煎鏃у弬鏁帮紝褰撳墠瀹炵幇涓嶅啀浣跨敤')
    pull_logcat_parser.add_argument('--resume', action='store_true', help='鍏煎鏃у弬鏁帮紝褰撳墠瀹炵幇涓嶅啀浣跨敤')
    pull_logcat_parser.add_argument('--cleanup-on-failure', action='store_true', help='鍏煎鏃у弬鏁帮紝褰撳墠瀹炵幇涓嶅啀浣跨敤')
    pull_logcat_parser.add_argument('--filter-term', action='append', help='棰濆杩囨护鍖呭惈璇ュ瓧绗︿覆鐨勮锛屽彲閲嶅')
    pull_logcat_parser.add_argument('--no-default-filters', action='store_true', help='涓嶉粯璁よ繃婊?RunCommandHandler/AgentRPCServer')
    pull_logcat_parser.set_defaults(func=cmd_pull_logcat)

    ban_user_parser = subparsers.add_parser('ban-user', help='灏佺鐢ㄦ埛')
    ban_user_parser.add_argument('product_id', help='浜у搧 ID')
    ban_user_parser.add_argument('--pod-id', required=True, help='瀹炰緥 ID')
    ban_user_parser.add_argument('--user-id', required=True, help='鐢ㄦ埛 ID')
    ban_user_parser.add_argument('--forbidden-interval', type=int, help='灏佺鏃堕暱绉?)
    ban_user_parser.add_argument('--is-preview-stream', action='store_true', help='灏忔祦')
    ban_user_parser.set_defaults(func=cmd_ban_user)
