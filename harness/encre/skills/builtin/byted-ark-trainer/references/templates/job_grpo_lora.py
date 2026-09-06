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

from __future__ import annotations

"""
GRPO LoRA 璁粌浠诲姟鎻愪氦鑴氭湰妯℃澘锛圙RPOLoRA锛?
------------------------------------------------------------
浣跨敤璇存槑锛?
1. 灏嗘湰鏂囦欢澶嶅埗鍒板綋鍓嶅疄楠屽瓙鐩綍锛坋xperiments/exp_xxx/job.py锛夛紝鍐嶆寜瀹為檯鎯呭喌鏀瑰€笺€?
2. hyperparameters 瀛楁浠?`ark get foundation-model --model <X> --version <Y> --fields hyperparameters`
   杩斿洖鐨?GRPOLoRA 灏忚妭涓哄噯锛涙煡璇㈣緭鍑轰腑娌℃湁鍑虹幇鐨勫瓧娈典竴寰嬩笉鍏佽鍑虹幇銆?
3. 鎻愪氦鍛戒护锛歚python job.py`锛堝湪瀹為獙瀛愮洰褰曞唴鎵ц锛夈€?
4. enable_trajectory 寮虹儓寤鸿寮€鍚紙True锛夛紝渚夸簬鍦ㄦ帶鍒跺彴鍋氳建杩瑰垎鏋愶紙闇€棰勫厛寮€閫?TLS 鏃ュ織鏈嶅姟锛夈€?

甯歌韪╁潙锛?
- model_version 蹇呴』浼犲瓧绗︿覆銆?
- GRPO 瀛楁鏄?lr锛堜笉鏄?learning_rate锛夛紱涓嶈鎶?SFT 瀛楁鎼繃鏉ャ€?
- num_generations 蹇呴』钀藉湪鏌ヨ杩斿洖鐨勭鏁ｉ泦鍚堝唴锛堝父瑙?{8, 16, 32}锛夈€?
- GRPO 蹇呴』閰?custom_rl_pipeline锛汼FT 缁濅笉鑳介厤銆?
- 涓嶅厑璁稿嚟鍗拌薄鍔?loss_name 绛夊唴閮ㄥ瓧娈点€?
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

# rollout  grader 锛?
from plugins.random_reward import random_reward_fn
from plugins.weather_rollout import demo_rollout


if __name__ == "__main__":
    mcj = ModelCustomizationJob(
        name="grpo-lora-demo",
        # model_reference 锛?
        model_reference={
            # (a) 锛?
            # "foundation_model": {
            #     "name": "doubao-seed-1-6-flash",
            #      "model_version": "250615",  # String锛?

            # },
            # (b)  RFT/SFT 锛圙RPO 锛夛細
            "custom_model_id": "cm-xxxxxxxxxxxxxx-xxxxx",
        },
        customization_type=CustomizationType.GRPOLoRA,
        hyperparameters={
            # ark get foundation-model ... --fields hyperparameters
            # GRPOLoRA
            "num_steps": "20",
            "batch_size": "32",  # GRPOLoRA batch_size 鍙厑璁告灇涓惧€硷紝鏈€灏忓€兼槸32
            "lr": "0.000001",  # GRPO 瀛楁鏄?lr锛堜笉鏄?learning_rate锛?
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
            # 锛?
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
        enable_trajectory=True,  # RL 寤鸿寮€鍚紙闇€棰勫厛寮€閫?TLS 鏃ュ織鏈嶅姟锛?
        save_model_limit=1,
    )

    mcj.submit()
    print(f"Job submitted. view job at {mcj.url}")
