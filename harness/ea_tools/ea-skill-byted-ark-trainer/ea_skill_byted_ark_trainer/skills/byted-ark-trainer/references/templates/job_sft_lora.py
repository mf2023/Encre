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
SFT LoRA 璁粌浠诲姟鎻愪氦鑴氭湰妯℃澘锛團inetuneLoRA锛?
------------------------------------------------------------
浣跨敤璇存槑锛?
1. 灏嗘湰鏂囦欢澶嶅埗鍒板綋鍓嶅疄楠屽瓙鐩綍锛坋xperiments/exp_xxx/job.py锛夛紝鍐嶆寜瀹為檯鎯呭喌鏀瑰€笺€?
2. hyperparameters 鍙兘濉?`ark get foundation-model --model <X> --version <Y> --fields hyperparameters`
   鏌ヨ杩斿洖鐨勫瓧娈碉紱鏌ヨ杈撳嚭涓病鏈夊嚭鐜扮殑瀛楁涓€寰嬩笉鍏佽鍑虹幇銆?
3. 鎻愪氦鍛戒护锛歚python job.py`锛堝湪瀹為獙瀛愮洰褰曞唴鎵ц锛夈€?

甯歌韪╁潙锛?
- model_version 蹇呴』浼犲瓧绗︿覆锛?250615"锛夛紝鑰屼笉鏄暣鏁般€?
- data.training_set 蹇呴』鏄?TrainingDataset 瀵硅薄锛屼笖鑷冲皯鍖呭惈 local_files / tos_bucket / datasets 涔嬩竴銆?
- SFT 浠诲姟涓ョ鍔?custom_rl_pipeline / enable_trajectory銆?
- SFT 瀛楁鏄?learning_rate锛屼笉鏄?lr锛涗袱鑰呬笉鍙簰鎹€?
- 涓嶅厑璁稿嚟鍗拌薄鍔?dyn_bsz銆乫reeze_vit 涔嬬被鐨勫瓧娈点€?
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
                "model_version": "250615",  # 瀛楃涓诧紒
            }
        },
        customization_type=CustomizationType.FinetuneLoRA,
        hyperparameters={
            # ark get foundation-model ... --fields hyperparameters
            # FinetuneLoRA
            "epoch": "1",
            "batch_size": "8",
            "learning_rate": "0.00001",  # SFT 瀛楁鏄?learning_rate锛屼笉鏄?lr
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
            # 锛?
            "validation_percentage": 10,
            # "validation_set": {"local_files": ["./data/sft_val_data.jsonl"]},
        },
        save_model_limit=1,
    )

    mcj.submit()
    print(f"Job submitted. view job at {mcj.url}")
