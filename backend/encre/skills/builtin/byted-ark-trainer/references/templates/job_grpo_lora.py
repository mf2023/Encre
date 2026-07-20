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
GRPO LoRA 训练任务提交脚本模板（GRPOLoRA）
------------------------------------------------------------
使用说明：
1. 将本文件复制到当前实验子目录（experiments/exp_xxx/job.py），再按实际情况改值。
2. hyperparameters 字段以 `ark get foundation-model --model <X> --version <Y> --fields hyperparameters`
   返回的 GRPOLoRA 小节为准；查询输出中没有出现的字段一律不允许出现。
3. 提交命令：`python job.py`（在实验子目录内执行）。
4. enable_trajectory 强烈建议开启（True），便于在控制台做轨迹分析（需预先开通 TLS 日志服务）。

常见踩坑：
- model_version 必须传字符串。
- GRPO 字段是 lr（不是 learning_rate）；不要把 SFT 字段搬过来。
- num_generations 必须落在查询返回的离散集合内（常见 {8, 16, 32}）。
- GRPO 必须配 custom_rl_pipeline；SFT 绝不能配。
- 不允许凭印象加 loss_name 等内部字段。
"""

import sys
import os

# Add working directory to Python path so plugins can be imported
sys.path.insert(0, os.getcwd())

from ark_sdk.resources.model_customization_job import ModelCustomizationJob
from ark_sdk.resources.pipeline_plugin import PipelinePluginWrapper
from ark_sdk.resources.pipeline_plugin.pipeline_plugin import GRPOPipeline
from ark_sdk.types.model_customization_job.model_customization_job import (
    CustomizationType,
)

# rollout 和 grader 插件函数：按实际路径导入
from plugins.random_reward import random_reward_fn
from plugins.weather_rollout import demo_rollout


if __name__ == "__main__":
    mcj = ModelCustomizationJob(
        name="grpo-lora-demo",
        # model_reference 两种写法二选一：
        model_reference={
            # (a) 直接基于基础模型训练：
            # "foundation_model": {
            #     "name": "doubao-seed-1-6-flash",
            #     "model_version": "250615",  # 字符串！
            # },
            # (b) 基于 RFT/SFT 产出的自定义模型继续训练（GRPO 常见场景）：
            "custom_model_id": "cm-xxxxxxxxxxxxxx-xxxxx",
        },
        customization_type=CustomizationType.GRPOLoRA,
        hyperparameters={
            # 只允许出现 ark get foundation-model ... --fields hyperparameters
            # 返回的 GRPOLoRA 小节里的字段
            "num_steps": "20",
            "batch_size": "32",  # GRPOLoRA batch_size 只允许枚举值，最小值是32
            "lr": "0.000001",  # GRPO 字段是 lr（不是 learning_rate）
            "lr_warmup_steps": "5",
            "num_generations": "8",
            "num_iterations_per_batch": "2",
            "temperature": "1.0",
            "top_p": "1",
            "max_new_tokens": "1024",
            "clip_ratio_high": "0.2",
            "clip_ratio_low": "0.2",
            "kl_coefficient": "0.001",
            "loss_agg_mode": "seq-mean-token-mean",
            "save_every_n_steps": "10",
            "test_every_n_steps": "5",
            "test_num_generations": "1",
            "test_top_p": "1",
            "lora_rank": "32",
            "lora_alpha": "4",
        },
        data={
            "training_set": {
                "local_files": [
                    "./data/rl_train_data.jsonl",
                ],
            },
            # 若有测试集：
            # "validation_set": {"local_files": ["./data/rl_test_data.jsonl"]},
        },
        custom_rl_pipeline=GRPOPipeline(
            graders=[
                PipelinePluginWrapper(
                    plugin=random_reward_fn,
                    envs={"foo": "bar"},
                    weight=0.5,
                ),
            ],
            rollout=PipelinePluginWrapper(
                plugin=demo_rollout,
                envs={"foo": "bar"},
            ),
        ),
        enable_trajectory=True,  # RL 建议开启（需预先开通 TLS 日志服务）
        save_model_limit=1,
    )

    mcj.submit()
    print(f"Job submitted. view job at {mcj.url}")
