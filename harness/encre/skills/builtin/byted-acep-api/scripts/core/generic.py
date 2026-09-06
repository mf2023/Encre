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

"""閫氱敤 Action 璋冪敤妯″潡銆?""

from . import cli_common as cli


def cmd_action_call(args):
    params = cli.parse_json_option(args.params_json, "--params-json", dict) or {}
    params.update(cli.parse_key_value_params(args.param, "--param"))
    if args.product_id and "ProductId" not in params:
        params["ProductId"] = args.product_id

    result = cli.get_client().request_action(
        args.action,
        json_body=args.json_body,
        version=args.version,
        **params,
    )
    cli.print_result(result)


def register(subparsers):
    action_call_parser = subparsers.add_parser(
        "action-call",
        help="閫氱敤 Action 璋冪敤",
        description="閫氱敤 Action 璋冪敤",
        epilog=(
            "绀轰緥:\n"
            "  vephone action-call ListOperableProduct --json-body --param Count=10\n"
            "  vephone action-call SetProxy --json-body --param ProductId=pid --param ProxyStatus=1 "
            '--param PodIdList=["pod-1","pod-2"]\n'
            "  vephone action-call CreatePod --param ProductId=pid --param PodName=demo "
            "--param Start=true --param UpBandwidthLimit=10\n"
            "\n"
            "澶氫釜鍙傛暟鍙噸澶嶄紶鍏?--param锛屽舰寮忎负 --param Key=Value --param Key2=Value2銆?
        ),
        formatter_class=cli.argparse.RawDescriptionHelpFormatter,
    )
    action_call_parser.add_argument(
        "action", help="OpenAPI Action 鍚嶇О锛屼緥濡?ListOperableProduct"
    )
    action_call_parser.add_argument(
        "--json-body",
        action="store_true",
        help="浠?JSON body 鏂瑰紡璋冪敤锛涢粯璁ゆ寜 query string 鏂瑰紡璋冪敤",
    )
    action_call_parser.add_argument(
        "--version",
        help="鏄惧紡鎸囧畾 API Version锛涗笉浼犲垯浣跨敤瀹㈡埛绔唴缃殑 Action-Version 鏄犲皠",
    )
    action_call_parser.add_argument(
        "--product-id",
        help="渚挎嵎鍙傛暟锛涙湭鍦ㄥ叾浠栧弬鏁颁腑鎻愪緵 ProductId 鏃讹紝鑷姩娉ㄥ叆涓?ProductId",
    )
    action_call_parser.add_argument(
        "--param",
        action="append",
        metavar="Key=Value",
        help="鍗曚釜璇锋眰鍙傛暟锛沄alue 浼氫紭鍏堟寜 JSON 瑙ｆ瀽锛屽け璐ユ椂鎸夊瓧绗︿覆澶勭悊锛屽彲閲嶅浼犲叆",
    )
    action_call_parser.add_argument(
        "--params-json",
        help="鎵归噺璇锋眰鍙傛暟 JSON 瀵硅薄锛涗細鍏堝悎骞讹紝鍐嶇敱 --param 瑕嗙洊鍚屽悕閿€傚懡浠よ涓鏁翠綋鍔犲紩鍙凤紝渚嬪 --params-json '{\"Count\":1}'",
    )
    action_call_parser.set_defaults(func=cmd_action_call)
