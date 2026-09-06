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

"""
鐏北浜戞墜鏈?CLI 宸ュ叿
"""

import argparse
import sys

from core import (
    apps,
    cli_common,
    dcs,
    display_layouts,
    generic,
    hosts,
    images,
    instance_controls,
    instance_properties,
    instances,
    network,
    products,
    resources,
    tags,
    tasks,
)

CLI_VERSION = "1.1.0"


def _extract_global_config_arg(argv):
    remaining = []
    config_path = None
    i = 0
    while i < len(argv):
        item = argv[i]
        if item == "--config":
            if i + 1 >= len(argv):
                raise SystemExit("閿欒: --config 闇€瑕佷紶鍏ユ枃浠惰矾寰?)
            config_path = argv[i + 1]
            i += 2
            continue
        if item.startswith("--config="):
            config_path = item.split("=", 1)[1]
            if not config_path:
                raise SystemExit("閿欒: --config 闇€瑕佷紶鍏ユ枃浠惰矾寰?)
            i += 1
            continue
        remaining.append(item)
        i += 1
    return remaining, config_path


COMMAND_GROUPS = (
    ("閫氱敤", "閫氱敤 Action 璋冪敤涓庡熀纭€鑳藉姏", (generic,)),
    ("浠诲姟", "浠诲姟鏌ヨ涓庢帓闅?, (tasks,)),
    ("瀹炰緥", "瀹炰緥鐢熷懡鍛ㄦ湡涓庡睘鎬?, (instances, instance_properties)),
    (
        "涓绘満涓庨暅鍍?,
        "涓绘満銆侀暅鍍忎笌鏈烘埧鏌ヨ",
        (hosts, images, dcs, products, resources, display_layouts),
    ),
    ("搴旂敤", "搴旂敤涓婁紶銆佸畨瑁呫€佸惎鍔ㄤ笌鏌ヨ", (apps,)),
    ("璁惧鎺у埗", "褰曞睆銆佹埅鍥俱€佹枃浠跺拰鍛戒护鎵ц", (instance_controls,)),
    ("鏍囩涓庣綉缁?, "鏍囩銆丏NS銆佽矾鐢卞拰绔彛鏄犲皠", (tags, network)),
)


def _register_command_groups(subparsers):
    groups = []
    for title, summary, modules in COMMAND_GROUPS:
        before = set(subparsers.choices)
        for module in modules:
            module.register(subparsers)
        commands = sorted(set(subparsers.choices) - before)
        groups.append(
            {
                "title": title,
                "summary": summary,
                "commands": commands,
            }
        )
    return groups


def _command_help_map(subparsers):
    return {action.dest: action.help or "" for action in subparsers._get_subactions()}


def _format_command_line(command, help_text):
    return f"    {command:<28} {help_text}".rstrip()


def print_top_level_help(parser, subparsers, groups):
    help_map = _command_help_map(subparsers)
    lines = [
        parser.description,
        "",
        "鐢ㄦ硶:",
        "  vephone <command> [args]",
        "  vephone <command> -h",
        "",
        "璇存槑:",
        "  澶у鏁颁笟鍔″懡浠ら兘闇€瑕佹樉寮忎紶鍏?product_id銆?,
        "  鍙€氳繃 --config 鎸囧畾 config.json 鏂囦欢璺緞銆?,
        "  鏌ョ湅鏌愪釜鍛戒护鐨勮缁嗗弬鏁帮紝璇蜂娇鐢?vephone <command> -h銆?,
        "",
        "鍛戒护鍒嗙粍:",
    ]

    for group in groups:
        lines.append(f"  {group['title']}  {group['summary']}")
        for command in group["commands"]:
            lines.append(_format_command_line(command, help_map.get(command, "")))
        lines.append("")

    lines.extend(
        [
            "绀轰緥:",
            "  vephone list-products --count 10",
            "  vephone action-call ListOperableProduct --json-body --param Count=10",
            "  vephone list-pods <product_id> --max-results 10",
            "  vephone detail-pod <product_id> <pod_id>",
            "  vephone get-task-info <product_id> <task_id>",
        ]
    )
    print("\n".join(lines).rstrip())


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vephone",
        description="鐏北浜戞墜鏈?CLI 宸ュ叿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", help="鎸囧畾 config.json 鏂囦欢璺緞")
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {CLI_VERSION}"
    )
    subparsers = parser.add_subparsers(
        dest="command", metavar="<command>", help="鍛戒护鍚嶇О"
    )
    groups = _register_command_groups(subparsers)
    return parser, subparsers, groups


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    argv, config_path = _extract_global_config_arg(argv)
    cli_common.set_config_path(config_path)
    parser, subparsers, groups = build_parser()

    if not argv or argv == ["-h"] or argv == ["--help"]:
        print_top_level_help(parser, subparsers, groups)
        sys.exit(0 if argv else 1)

    args = parser.parse_args(argv)
    if not args.command:
        print_top_level_help(parser, subparsers, groups)
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
