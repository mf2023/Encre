#!/usr/bin/env python3
# coding: utf-8
# Copyright 2026 Beijing Volcano Engine Technology Co., Ltd.
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

"""
ARK训练助手CLI工具

一个简单易用的命令行工具，用于ARK训练相关操作，包括：
- 模型训练任务管理
  - 查询训练任务状态
  - 获取训练完成的模型ID
- 基础模型管理
  - 查询基础模型列表（支持名称模糊查询和训练类型筛选）
  - 查询基础模型所有可用版本
- 端点管理
  - 创建端点
  - 列出端点
  - 获取端点详情
  - 获取端点证书
  - 停止端点
  - 删除端点
- 训练工具
  - 模型评估（计算BON/AON/AvgN指标）
  - RFT训练数据收集

使用示例：
  # 查询训练任务状态
  ark-trainer-helper job status --job-id mcj-20260225163459-thh2g

  # 获取训练输出模型ID
  ark-trainer-helper job get-model --job-id mcj-20260225163459-thh2g

  # 查询基础模型列表（名称包含doubao且支持FinetuneLoRA）
  ark-trainer-helper model list-models --name doubao --supported-customization-type FinetuneLoRA

  # 查询基础模型版本
  ark-trainer-helper model list-versions --model-name doubao-seed-1-6

  # 创建端点
  ark-trainer-helper endpoint create --name my-endpoint --description "测试端点" --custom-model-id cm-123456

  # 列出端点
  ark-trainer-helper endpoint list

  # 模型评估（评估哪个模型由 rollout.py 内的 model= 字段决定，请先手工改 rollout.py 再运行）
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py

  # RFT数据收集
  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json --output-file ./rft_data.jsonl --rollout rollout.py
"""

import argparse
import os

# 导入各模块功能
from modules.job import (
    job_status_command,
    job_get_model_command,
    register_heartbeat_command,
)
from modules.model import list_foundation_model_versions, list_foundation_models
from modules.endpoint import (
    init_api_client,
    create_endpoint,
    list_endpoints,
    get_endpoint,
    get_endpoint_certificate,
    stop_endpoint,
    delete_endpoint,
)
from modules.train import evaluate_command, rft_data_collect_command


def main():
    """
    主函数
    构建命令行参数解析器
    """
    # 创建主解析器
    parser = argparse.ArgumentParser(
        prog="ark-trainer-helper",
        description="ARK训练助手CLI工具",
        epilog="示例: ark-trainer-helper job status --job-id mcj-20260225163459-thh2g",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 创建子解析器
    subparsers = parser.add_subparsers(
        dest="module", title="可用模块", description="选择要操作的模块", help="模块帮助"
    )

    # 全局参数
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument(
        "--project-name", default="default", help="项目名称 (默认: default)"
    )

    # ==================== job 模块 ====================
    job_parser = subparsers.add_parser("job", help="训练任务管理")
    job_subparsers = job_parser.add_subparsers(
        dest="job_command", title="训练任务命令", help="训练任务操作命令"
    )

    # job status 命令
    job_status_parser = job_subparsers.add_parser("status", help="查询训练任务状态")
    job_status_parser.add_argument(
        "--job-id", required=True, help="训练任务ID (例如: mcj-20260225163459-thh2g)"
    )

    # job get-model 命令
    job_get_model_parser = job_subparsers.add_parser(
        "get-model", help="获取训练完成的模型ID"
    )
    job_get_model_parser.add_argument(
        "--job-id", required=True, help="训练任务ID (例如: mcj-20260225163459-thh2g)"
    )

    # job register-heartbeat 命令：登记训练任务到 HEARTBEAT.md
    register_hb_parser = job_subparsers.add_parser(
        "register-heartbeat",
        help="把训练任务登记到工作区 HEARTBEAT.md（自动维护顶部系统提醒块）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 在当前工作区根目录的 HEARTBEAT.md 登记一个 SFT 任务
  ark-trainer-helper job register-heartbeat \\
      --job-id mcj-20260425143200-sft01 \\
      --job-type SFT \\
      --job-url https://console.volcengine.com/ark/region:ark+cn-beijing/finetune/detail?Id=mcj-20260425143200-sft01 \\
      --exp-dir /abs/path/workspace/experiments/exp_20260425_143200_sft_lora

行为：
  - 若 HEARTBEAT.md 不存在，用完整模板创建（含 6 条 AI 接手必读系统提醒 + 表头 + 新任务行）。
  - 若已存在但顶部系统提醒块缺失/不完整，自动在文件最顶部补齐。
  - 若同 --job-id 已登记，幂等跳过。
        """,
    )
    register_hb_parser.add_argument(
        "--job-id", required=True, help="训练任务ID (例如: mcj-20260425143200-sft01)"
    )
    register_hb_parser.add_argument(
        "--job-type",
        required=True,
        help="任务类型标签，用于心跳表格展示 (例如: SFT / RFT / GRPO / RFT+GRPO)",
    )
    register_hb_parser.add_argument(
        "--job-url", required=True, help="任务详情页链接（控制台 URL）"
    )
    register_hb_parser.add_argument(
        "--exp-dir",
        required=True,
        help="本次实验的实验子目录绝对路径 (例如: /abs/path/workspace/experiments/exp_xxx)",
    )
    register_hb_parser.add_argument(
        "--submit-time",
        default=None,
        help="任务提交时间字符串，默认当前时间 (格式建议: 'YYYY-MM-DD HH:MM')",
    )
    register_hb_parser.add_argument(
        "--status",
        default="Running",
        help="写入表格的初始状态字面值 (默认: Running)",
    )
    register_hb_parser.add_argument(
        "--heartbeat-file",
        default=os.path.expanduser("~/.openclaw/workspace/HEARTBEAT.md"),
        help=(
            "HEARTBEAT.md 路径，默认 ~/.openclaw/workspace/HEARTBEAT.md。"
            "OpenClaw 只在该路径下触发心跳，必须是此目录或其子目录下的 HEARTBEAT.md。"
        ),
    )

    # ==================== model 模块 ====================
    model_parser = subparsers.add_parser("model", help="基础模型管理")
    model_subparsers = model_parser.add_subparsers(
        dest="model_command", title="基础模型命令", help="基础模型操作命令"
    )

    # model list-models 命令
    model_list_parser = model_subparsers.add_parser(
        "list-models",
        help="查询基础模型列表，支持名称模糊查询和训练类型筛选",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询所有LLM基础模型
  ark-trainer-helper model list-models

  # 模糊查询名称包含'doubao'的模型
  ark-trainer-helper model list-models --name doubao

  # 查询支持FinetuneLoRA训练的模型
  ark-trainer-helper model list-models --supported-customization-type FinetuneLoRA

  # 组合查询：名称包含'doubao'且支持GRPOLoRA的模型
  ark-trainer-helper model list-models --name doubao --supported-customization-type GRPOLoRA
        """,
    )
    model_list_parser.add_argument("--name", help="模型名称模糊查询关键词")
    model_list_parser.add_argument(
        "--supported-customization-type",
        help="支持的训练类型筛选 (例如: FinetuneLoRA, GRPOLoRA, FinetuneSft, GRPO)",
    )
    model_list_parser.add_argument(
        "--page-size", type=int, default=10, help="每页数量 (默认: 10)"
    )
    model_list_parser.add_argument(
        "--page-number", type=int, default=1, help="页码 (默认: 1)"
    )

    # model list-versions 命令
    model_list_versions_parser = model_subparsers.add_parser(
        "list-versions", help="查询基础模型的所有可用版本"
    )
    model_list_versions_parser.add_argument(
        "--model-name", required=True, help="基础模型名称 (例如: doubao-seed-1-6)"
    )
    model_list_versions_parser.add_argument(
        "--page-size", type=int, default=50, help="每页数量 (默认: 50)"
    )
    model_list_versions_parser.add_argument(
        "--page-number", type=int, default=1, help="页码 (默认: 1)"
    )

    # ==================== endpoint 模块 ====================
    endpoint_parser = subparsers.add_parser("endpoint", help="端点管理")
    endpoint_subparsers = endpoint_parser.add_subparsers(
        dest="endpoint_command", title="端点命令", help="端点操作命令"
    )

    # endpoint create 命令
    create_parser = endpoint_subparsers.add_parser(
        "create", parents=[global_parser], help="创建新端点"
    )
    create_parser.add_argument("--name", required=True, help="端点名称")
    create_parser.add_argument("--description", default="", help="端点描述")
    create_parser.add_argument("--custom-model-id", required=True, help="自定义模型ID")

    # endpoint list 命令
    list_parser = endpoint_subparsers.add_parser(
        "list", parents=[global_parser], help="列出所有端点"
    )
    list_parser.add_argument(
        "--page-size", type=int, default=10, help="每页数量 (默认: 10)"
    )
    list_parser.add_argument(
        "--page-number", type=int, default=1, help="页码 (默认: 1)"
    )

    # endpoint get 命令
    get_parser = endpoint_subparsers.add_parser("get", help="获取端点详情")
    get_parser.add_argument("--endpoint-id", required=True, help="端点ID")

    # endpoint certificate 命令
    certificate_parser = endpoint_subparsers.add_parser(
        "certificate", help="获取端点证书"
    )
    certificate_parser.add_argument("--endpoint-id", required=True, help="端点ID")

    # endpoint stop 命令
    stop_parser = endpoint_subparsers.add_parser("stop", help="停止端点")
    stop_parser.add_argument("--endpoint-id", required=True, help="端点ID")

    # endpoint delete 命令
    delete_parser = endpoint_subparsers.add_parser("delete", help="删除端点")
    delete_parser.add_argument("--endpoint-id", required=True, help="端点ID")

    # ==================== train 模块 ====================
    train_parser = subparsers.add_parser("train", help="训练工具集")
    train_subparsers = train_parser.add_subparsers(
        dest="train_command", title="训练工具命令", help="训练相关工具操作命令"
    )

    # train evaluate 命令
    evaluate_parser = train_subparsers.add_parser(
        "evaluate",
        help="模型评估（计算BON/AON/AvgN指标）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
重要：要评估哪个模型由 rollout.py 自己决定——即 rollout 里调用 chat.completions.create(model=...) 时传入的那个字符串。
本命令不再接收 --model 参数。运行 evaluate 之前，请先手工把 rollout.py 中的 model 字段改成目标模型名/版本/端点ID/自定义模型ID，再执行本命令。

示例:
  # 基础评估
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py

  # 自定义参数
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py \\
                     --n-rollouts 8 --max-concurrency 15

  # 保存结果到自定义目录
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py \\
                     --output-dir ./my_results
        """,
    )
    evaluate_parser.add_argument(
        "--dataset", type=str, required=True, help="评估数据集路径 (JSON或JSONL格式)"
    )
    evaluate_parser.add_argument(
        "--rollout",
        type=str,
        required=True,
        help="rollout函数Python文件路径（该文件内部的 model= 字段决定实际评估的模型）",
    )
    evaluate_parser.add_argument(
        "--grader", type=str, required=True, help="grader函数Python文件路径"
    )
    evaluate_parser.add_argument(
        "--n-rollouts", type=int, default=8, help="每个样本的rollout次数 (默认: 8)"
    )
    evaluate_parser.add_argument(
        "--batch-size", type=int, default=15, help="评估批次大小 (默认: 15)"
    )
    evaluate_parser.add_argument(
        "--max-concurrency", type=int, default=15, help="最大并发数 (默认: 15)"
    )
    evaluate_parser.add_argument(
        "--output-dir",
        type=str,
        default="./eval_output",
        help="评估结果输出目录 (默认: ./eval_output)",
    )
    evaluate_parser.add_argument("--verbose", action="store_true", help="启用详细日志")

    # train rft-data-collect 命令
    rft_data_parser = train_subparsers.add_parser(
        "rft-data-collect",
        help="RFT训练数据收集：从评估结果中筛选优质轨迹生成训练数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从评估结果中收集RFT数据
  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json \\
                                            --output-file ./rft_train_data.jsonl \\
                                            --rollout ./rollout.py

  # 或显式传入tools定义文件（JSON数组，或包含tools字段的JSON对象）
  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json \\
                                            --output-file ./rft_train_data.jsonl \\
                                            --tools-file ./tools.json
        """,
    )
    rft_data_parser.add_argument(
        "--eval-results",
        type=str,
        required=True,
        help="评估结果JSON文件路径 (由evaluate命令生成)",
    )
    rft_data_parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="输出的RFT训练数据文件路径 (JSONL格式)",
    )
    rft_data_parser.add_argument(
        "--rollout",
        type=str,
        help="可选：rollout插件路径，用于从rollout_tools/tools变量补充Function Calling样本必需的顶层tools字段",
    )
    rft_data_parser.add_argument(
        "--tools-file",
        type=str,
        help="可选：tools定义文件路径，支持JSON数组或包含tools字段的JSON对象；优先级高于--rollout",
    )

    # 解析参数
    args = parser.parse_args()

    # 检查是否提供了模块
    if not args.module:
        parser.print_help()
        return

    # 处理job模块命令
    if args.module == "job":
        if not args.job_command:
            job_parser.print_help()
            return

        if args.job_command == "status":
            job_status_command(args)
        elif args.job_command == "get-model":
            job_get_model_command(args)
        elif args.job_command == "register-heartbeat":
            register_heartbeat_command(args)

    # 处理model模块命令
    elif args.module == "model":
        if not args.model_command:
            model_parser.print_help()
            return

        if args.model_command == "list-models":
            list_foundation_models(args)
        elif args.model_command == "list-versions":
            list_foundation_model_versions(args)

    # 处理endpoint模块命令
    elif args.module == "endpoint":
        if not args.endpoint_command:
            endpoint_parser.print_help()
            return

        # 获取API实例
        api = init_api_client()
        if not api:
            return

        # 执行命令
        if args.endpoint_command == "create":
            create_endpoint(api, args)
        elif args.endpoint_command == "list":
            list_endpoints(api, args)
        elif args.endpoint_command == "get":
            get_endpoint(api, args)
        elif args.endpoint_command == "certificate":
            get_endpoint_certificate(api, args)
        elif args.endpoint_command == "stop":
            stop_endpoint(api, args)
        elif args.endpoint_command == "delete":
            delete_endpoint(api, args)

    # 处理train模块命令
    elif args.module == "train":
        if not args.train_command:
            train_parser.print_help()
            return

        if args.train_command == "evaluate":
            evaluate_command(args)
        elif args.train_command == "rft-data-collect":
            rft_data_collect_command(args)


if __name__ == "__main__":
    main()
