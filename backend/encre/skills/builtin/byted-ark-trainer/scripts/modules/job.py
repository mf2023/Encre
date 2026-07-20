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
训练任务管理模块
"""

import datetime
from pathlib import Path

from loguru import logger
from ark_sdk.resources.model_customization_job import ModelCustomizationJob


# =========================================================================
# HEARTBEAT.md 登记相关
# =========================================================================

# AI 接手时必读的 6 条系统提醒（SKILL.md 中 HEARTBEAT 章节的规范版）
HEARTBEAT_SYSTEM_REMINDER = """# byted-ark-trainer心跳监控任务列表

> ⚠️【系统提醒 · AI接手训练任务时必读】
> 1. **必须先加载 byted-ark-trainer skill**：保持 byted-ark-trainer skill 始终在上下文中，若不在则主动加载 byted-ark-trainer skill（读取该skill的SKILL.md）。
> 2. **接手任务前必须先读取对应的实验目录**：在处理下表任何任务前，必须先打开该任务「实验目录绝对路径」下的 `EXPERIMENT.md`，理解实验计划、已与用户确认的关键配置、后续流程。**不读完 `EXPERIMENT.md` 不允许执行任何动作**。
> 3. **逐项检查任务状态**：对下表每个ARK训练任务执行 `byted-ark-trainer-helper job status --job-id <任务ID>` 查询最新状态，并把结果同步回下表的「最新状态」列。
> 4. **任务完成且有后续流程时，不需要用户二次确认**：若任务状态变为 Completed，按该任务 `EXPERIMENT.md` 中「后续流程」的记录**立即执行下一步**（例如 RFT 完成后提交 GRPO、训练完成后在测试集上评估），执行完毕后再通知用户结果，并把结果增量更新到 `EXPERIMENT.md`。
> 5. **任务失败必须报告用户，不得自行移除**：状态为 Failed/Terminated 时，立即向用户展示完整错误信息和失败原因，询问是否重试或调整配置；**只有在用户明确确认后才能将该任务从下表中移除**，在用户确认之前必须保留该条目以便追溯。
> 6. **严禁编造上下文**：如果实验目录或 `EXPERIMENT.md` 缺失导致无法理解任务意图，不得自行猜测，必须先询问用户。
"""

HEARTBEAT_TABLE_HEADER = (
    "| 任务ID | 任务类型 | 提交时间 | 最新状态 | 任务链接 | 实验目录绝对路径 |\n"
    "|--------|----------|----------|----------|----------|------------------|\n"
)

# 用于判断系统提醒块齐全性的关键 token（必须按顺序全部出现）
_REMINDER_TOKENS = [
    "【系统提醒 · AI接手训练任务时必读】",
    "必须先加载 byted-ark-trainer skill",
    "必须先读取对应的实验目录",
    "逐项检查任务状态",
    "不需要用户二次确认",
    "任务失败必须报告用户，不得自行移除",
    "严禁编造上下文",
]


def _reminder_block_intact(text: str) -> bool:
    """判断 HEARTBEAT.md 开头的系统提醒块 6 条是否齐全。"""
    last_idx = -1
    for tok in _REMINDER_TOKENS:
        idx = text.find(tok)
        if idx == -1 or idx < last_idx:
            return False
        last_idx = idx
    return True


def _append_task_row(heartbeat_text: str, row: str, job_id: str) -> tuple[str, bool]:
    """
    将任务行追加到 HEARTBEAT.md 的表格末尾。若同 job_id 已存在则不重复追加。
    返回 (新文本, 是否新增)
    """
    if job_id in heartbeat_text:
        return heartbeat_text, False
    # 保证结尾有换行
    if not heartbeat_text.endswith("\n"):
        heartbeat_text += "\n"
    # 若文件里没有表头，补一个
    if "| 任务ID |" not in heartbeat_text:
        heartbeat_text += "\n" + HEARTBEAT_TABLE_HEADER
    heartbeat_text += row + "\n"
    return heartbeat_text, True


def register_heartbeat_command(args):
    """
    登记一个训练任务到 HEARTBEAT.md。
    - 若文件不存在：用完整模板创建（系统提醒块 + 表头 + 新任务行）
    - 若文件已存在但系统提醒块缺失/不完整：在文件最顶部补齐提醒块，再 append 任务行
    - 若文件已存在且 job-id 已登记：幂等跳过（返回提示）
    约束：--heartbeat-file 必须位于 ~/.openclaw 之下（OpenClaw 工作区根），防止把心跳文件写到无关目录。
    """
    heartbeat_path = Path(args.heartbeat_file).expanduser().resolve()

    # 路径约束：必须落在 ~/.openclaw 之下
    openclaw_root = Path("~/.openclaw").expanduser().resolve()
    try:
        heartbeat_path.relative_to(openclaw_root)
    except ValueError:
        raise SystemExit(
            f"❌ 拒绝登记：--heartbeat-file 必须位于 {openclaw_root} 之下，"
            f"当前给定路径为 {heartbeat_path}。\n"
            f"   请把 HEARTBEAT.md 放在 OpenClaw 工作区内（例如工作区根目录 "
            f"{openclaw_root}/workspace/<项目>/HEARTBEAT.md），再重新登记。"
        )

    submit_time = args.submit_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    status = args.status or "Running"
    exp_dir = str(Path(args.exp_dir).expanduser().resolve())

    row = (
        f"| {args.job_id} | {args.job_type} | {submit_time} | {status} "
        f"| {args.job_url} | {exp_dir} |"
    )

    print(f"\n=== 登记心跳任务 ({args.job_id}) ===")
    print(f"目标 HEARTBEAT.md: {heartbeat_path}")

    if not heartbeat_path.exists():
        # 新建：完整模板
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        content = HEARTBEAT_SYSTEM_REMINDER + "\n" + HEARTBEAT_TABLE_HEADER + row + "\n"
        heartbeat_path.write_text(content, encoding="utf-8")
        print("✓ HEARTBEAT.md 不存在，已用完整模板创建（含系统提醒块 + 新任务一行）")
        print(f"✓ 已追加任务 {args.job_id} 到心跳摘要表")
        return

    # 已存在：检查提醒块
    text = heartbeat_path.read_text(encoding="utf-8")
    reminder_ok = _reminder_block_intact(text)

    if not reminder_ok:
        # 在文件最顶部补齐系统提醒块
        text = HEARTBEAT_SYSTEM_REMINDER + "\n" + text
        print("⚠ 检测到文件顶部系统提醒块缺失/不完整，已在文件顶部补齐完整提醒块")
    else:
        print("✓ 文件顶部系统提醒块已齐全，保留不变")

    new_text, added = _append_task_row(text, row, args.job_id)
    heartbeat_path.write_text(new_text, encoding="utf-8")

    if added:
        print(f"✓ 已追加任务 {args.job_id} 到心跳摘要表")
    else:
        print(f"ℹ 任务 {args.job_id} 已登记过，跳过追加（幂等）")


def get_job_status(job_id: str) -> ModelCustomizationJob:
    """
    获取训练任务状态
    :param job_id: 训练任务ID
    :return: 训练任务对象
    """
    job = ModelCustomizationJob.get(job_id)
    return job


def get_output_model_id(job_id: str) -> str:
    """
    获取训练完的模型ID
    :param job_id: 训练任务ID
    :return: 训练完的模型ID
    """
    # 使用 ark_sdk 获取模型信息
    job = ModelCustomizationJob.get(job_id)
    finetune_status = job.phase
    logger.info(f"Task {job_id} finetune status is {finetune_status}")
    if finetune_status == "Completed":
        # 刷新获取最新状态，确保包含 outputs 信息
        job.refresh()
        # 通过私有属性获取 outputs
        if hasattr(job, "_ModelCustomizationJob__outputs"):
            outputs = getattr(job, "_ModelCustomizationJob__outputs")
            logger.info(f"Outputs found: {outputs}")
            if outputs and len(outputs) > 0:
                # 遍历所有输出，找到有CustomModelId的（最新的）
                for output in reversed(outputs):
                    if hasattr(output, "CustomModelId") and output.CustomModelId:
                        return output.CustomModelId
                    # 尝试其他可能的属性名
                    for attr in [
                        "custom_model_id",
                        "CustomModelID",
                        "model_id",
                        "ModelId",
                    ]:
                        if hasattr(output, attr) and getattr(output, attr):
                            return getattr(output, attr)

    raise ValueError(
        f"Task {job_id} finetune status is {finetune_status}, not Completed or no output model found"
    )


def job_status_command(args):
    """
    处理job status命令
    """
    print(f"\n=== 查询训练任务状态 ({args.job_id}) ===")
    try:
        job = get_job_status(args.job_id)
        print(f"任务ID: {job.id}")
        print(f"任务名称: {job.name}")
        print(f"任务状态: {job.phase}")
        print(f"状态时间: {job.status.PhaseTime}")
        print(f"是否可恢复: {job.status.Resumable}")
        print(f"重试次数限制: {job.status.RetryLimit}")

        if job.status.Message:
            print(f"状态消息: {job.status.Message}")
        if job.status.QueuePosition is not None:
            print(f"队列位置: {job.status.QueuePosition}")
        if job.status.BillableTokens is not None:
            print(f"计费Token数: {job.status.BillableTokens}")
        if job.status.TrainingTokensPerEpoch is not None:
            print(f"每轮训练Token数: {job.status.TrainingTokensPerEpoch}")
        if job.status.RLPluginInfos:
            print(f"RL插件信息: {job.status.RLPluginInfos}")

        print(f"\n任务描述: {job.description}")
        print(f"项目: {job.project}")
        print(f"定制类型: {job.customization_type}")
        print(f"模型引用: {job.model_reference}")
        return job
    except Exception as e:
        print(f"查询失败: {str(e)}")
        return None


def job_get_model_command(args):
    """
    处理job get-model命令
    """
    print(f"\n=== 获取训练输出模型ID ({args.job_id}) ===")
    try:
        model_id = get_output_model_id(args.job_id)
        print(f"训练完成！模型ID: {model_id}")
        return model_id
    except Exception as e:
        print(f"获取失败: {str(e)}")
        return None
