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
SFT LoRA 训练任务提交脚本模板（FinetuneLoRA）
------------------------------------------------------------
使用说明：
1. 将本文件复制到当前实验子目录（experiments/exp_xxx/job.py），再按实际情况改值。
2. hyperparameters 只能填 `ark get foundation-model --model <X> --version <Y> --fields hyperparameters`
   查询返回的字段；查询输出中没有出现的字段一律不允许出现。
3. 提交命令：`python job.py`（在实验子目录内执行）。

常见踩坑：
- model_version 必须传字符串（"250615"），而不是整数。
- data.training_set 必须是 TrainingDataset 对象，且至少包含 local_files / tos_bucket / datasets 之一。
- SFT 任务严禁加 custom_rl_pipeline / enable_trajectory。
- SFT 字段是 learning_rate，不是 lr；两者不可互换。
- 不允许凭印象加 dyn_bsz、freeze_vit 之类的字段。
"""

import sys
import os

# Add working directory to Python path
sys.path.insert(0, os.getcwd())

from ark_sdk.resources.model_customization_job import ModelCustomizationJob
from ark_sdk.types.model_customization_job.model_customization_job import (
    CustomizationType,
)


if __name__ == "__main__":
    mcj = ModelCustomizationJob(
        name="sft-lora-demo",
        model_reference={
            "foundation_model": {
                "name": "doubao-seed-1-6",
                "model_version": "250615",  # 字符串！
            }
        },
        customization_type=CustomizationType.FinetuneLoRA,
        hyperparameters={
            # 只允许出现 ark get foundation-model ... --fields hyperparameters
            # 返回的 FinetuneLoRA 小节里的字段
            "epoch": "1",
            "batch_size": "8",
            "learning_rate": "0.00001",  # SFT 字段是 learning_rate，不是 lr
            "warmup_step_rate": "0.05",
            "seq_len": "32768",
            "lora_rank": "32",
            "lora_alpha": "4",
            "save_model_per_epoch": "1",
        },
        data={
            "training_set": {
                "local_files": [
                    "./data/sft_train_data.jsonl",
                ],
            },
            # 验证集二选一：
            "validation_percentage": 10,
            # "validation_set": {"local_files": ["./data/sft_val_data.jsonl"]},
        },
        save_model_limit=1,
    )

    mcj.submit()
    print(f"Job submitted. view job at {mcj.url}")
