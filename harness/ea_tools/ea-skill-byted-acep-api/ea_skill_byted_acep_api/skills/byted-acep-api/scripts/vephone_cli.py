from __future__ import annotations

"""
鐏北浜戞墜鏈?CLI 宸ュ叿
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
                raise SystemExit("閿欒: --config 闇瑕佷紶鍏ユ枃浠惰矾寰?")
            config_path = argv[i + 1]
            i += 2
            continue
        if item.startswith("--config="):
            config_path = item.split("=", 1)[1]
            if not config_path:
                raise SystemExit("閿欒: --config 闇瑕佷紶鍏ユ枃浠惰矾寰?")
            i += 1
            continue
        remaining.append(item)
        i += 1
    return remaining, config_path


COMMAND_GROUPS = (
    ("common", "Generic action calls and core capabilities", (generic,)),
    ("task", "Task queries and troubleshooting", (tasks,)),
    ("instance", "Instance lifecycle and attributes", (instances, instance_properties)),
    (
        "hosts-images",
        "Hosts, images, and datacenter queries",
        (hosts, images, dcs, products, resources, display_layouts),
    ),
    ("app", "App upload, install, launch and query", (apps,)),
    ("device-control", "Screen capture, screenshots, files and command execution", (instance_controls,)),
    ("network", "Tags, DNS, routes and port mapping", (tags, network)),
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
        "  澶у鏁颁笟鍔懡浠ら兘闇瑕佹樉寮忎紶鍏?product_id銆?",
        "  鍙氳繃 --config 鎸囧畾 config.json 鏂囦欢璺緞銆?",
        "  鏌ョ湅鏌愪釜鍛戒护鐨勮缁嗗弬鏁帮紝璇蜂娇鐢?vephone <command> -h銆?",
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
        description="鐏北浜戞墜鏈?CLI 宸ュ叿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", help="鎸囧畾 config.json 鏂囦欢璺緞")
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
