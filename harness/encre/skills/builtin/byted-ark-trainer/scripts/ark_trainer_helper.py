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

from __future__ import annotations

"""
ARK璁粌鍔╂墜CLI宸ュ叿

涓€涓畝鍗曟槗鐢ㄧ殑鍛戒护琛屽伐鍏凤紝鐢ㄤ簬ARK璁粌鐩稿叧鎿嶄綔锛屽寘鎷細
- 妯″瀷璁粌浠诲姟绠＄悊
  - 鏌ヨ璁粌浠诲姟鐘舵€?
  - 鑾峰彇璁粌瀹屾垚鐨勬ā鍨婭D
- 鍩虹妯″瀷绠＄悊
  - 鏌ヨ鍩虹妯″瀷鍒楄〃锛堟敮鎸佸悕绉版ā绯婃煡璇㈠拰璁粌绫诲瀷绛涢€夛級
  - 鏌ヨ鍩虹妯″瀷鎵€鏈夊彲鐢ㄧ増鏈?
- 绔偣绠＄悊
  - 鍒涘缓绔偣
  - 鍒楀嚭绔偣
  - 鑾峰彇绔偣璇︽儏
  - 鑾峰彇绔偣璇佷功
  - 鍋滄绔偣
  - 鍒犻櫎绔偣
- 璁粌宸ュ叿
  - 妯″瀷璇勪及锛堣绠桞ON/AON/AvgN鎸囨爣锛?
  - RFT璁粌鏁版嵁鏀堕泦

浣跨敤绀轰緥锛?
  #  Query training task status

  ark-trainer-helper job status --job-id mcj-20260225163459-thh2g

  # ID
  ark-trainer-helper job get-model --job-id mcj-20260225163459-thh2g

  # 锛坉oubaoFinetuneLoRA锛?
  ark-trainer-helper model list-models --name doubao --supported-customization-type FinetuneLoRA

  # 
  ark-trainer-helper model list-versions --model-name doubao-seed-1-6

  #  Create endpoint

  ark-trainer-helper endpoint create --name my-endpoint --description "娴嬭瘯绔偣" --custom-model-id cm-123456

  #  List endpoints

  ark-trainer-helper endpoint list

  # 锛?rollout.py  model= 锛?rollout.py 锛?
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py

  #  RFT data collection

  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json --output-file ./rft_data.jsonl --rollout rollout.py
"""

import argparse
import os

# 
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
    涓诲嚱鏁?
    鏋勫缓鍛戒护琛屽弬鏁拌В鏋愬櫒
    """
    # 
    parser = argparse.ArgumentParser(
        prog="ark-trainer-helper",
        description="ARK璁粌鍔╂墜CLI宸ュ叿",
        epilog="绀轰緥: ark-trainer-helper job status --job-id mcj-20260225163459-thh2g",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 
    subparsers = parser.add_subparsers(
        dest="module", title="鍙敤妯″潡", description="閫夋嫨瑕佹搷浣滅殑妯″潡", help="妯″潡甯姪"
    )

    #  Global parameters

    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument(
        "--project-name", default="default", help="椤圭洰鍚嶇О (榛樿: default)"
    )

    #  ==================== job 妯″潡 =======================

    job_parser = subparsers.add_parser("job", help="璁粌浠诲姟绠＄悊")
    job_subparsers = job_parser.add_subparsers(
        dest="job_command", title="璁粌浠诲姟鍛戒护", help="璁粌浠诲姟鎿嶄綔鍛戒护"
    )

    # job status
    job_status_parser = job_subparsers.add_parser("status", help="鏌ヨ璁粌浠诲姟鐘舵€?)
    job_status_parser.add_argument(
        "--job-id", required=True, help="璁粌浠诲姟ID (渚嬪: mcj-20260225163459-thh2g)"
    )

    # job get-model
    job_get_model_parser = job_subparsers.add_parser(
        "get-model", help="鑾峰彇璁粌瀹屾垚鐨勬ā鍨婭D"
    )
    job_get_model_parser.add_argument(
        "--job-id", required=True, help="璁粌浠诲姟ID (渚嬪: mcj-20260225163459-thh2g)"
    )

    # job register-heartbeat 锛?HEARTBEAT.md
    register_hb_parser = job_subparsers.add_parser(
        "register-heartbeat",
        help="鎶婅缁冧换鍔＄櫥璁板埌宸ヤ綔鍖?HEARTBEAT.md锛堣嚜鍔ㄧ淮鎶ら《閮ㄧ郴缁熸彁閱掑潡锛?,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥锛?
  # HEARTBEAT.md  SFT
  ark-trainer-helper job register-heartbeat \\
      --job-id mcj-20260425143200-sft01 \\
      --job-type SFT \\
      --job-url https://console.volcengine.com/ark/region:ark+cn-beijing/finetune/detail?Id=mcj-20260425143200-sft01 \\
      --exp-dir /abs/path/workspace/experiments/exp_20260425_143200_sft_lora

琛屼负锛?
  - 鑻?HEARTBEAT.md 涓嶅瓨鍦紝鐢ㄥ畬鏁存ā鏉垮垱寤猴紙鍚?6 鏉?AI 鎺ユ墜蹇呰绯荤粺鎻愰啋 + 琛ㄥご + 鏂颁换鍔¤锛夈€?
  - 鑻ュ凡瀛樺湪浣嗛《閮ㄧ郴缁熸彁閱掑潡缂哄け/涓嶅畬鏁达紝鑷姩鍦ㄦ枃浠舵渶椤堕儴琛ラ綈銆?
  - 鑻ュ悓 --job-id 宸茬櫥璁帮紝骞傜瓑璺宠繃銆?
        """,
    )
    register_hb_parser.add_argument(
        "--job-id", required=True, help="璁粌浠诲姟ID (渚嬪: mcj-20260425143200-sft01)"
    )
    register_hb_parser.add_argument(
        "--job-type",
        required=True,
        help="浠诲姟绫诲瀷鏍囩锛岀敤浜庡績璺宠〃鏍煎睍绀?(渚嬪: SFT / RFT / GRPO / RFT+GRPO)",
    )
    register_hb_parser.add_argument(
        "--job-url", required=True, help="浠诲姟璇︽儏椤甸摼鎺ワ紙鎺у埗鍙?URL锛?
    )
    register_hb_parser.add_argument(
        "--exp-dir",
        required=True,
        help="鏈瀹為獙鐨勫疄楠屽瓙鐩綍缁濆璺緞 (渚嬪: /abs/path/workspace/experiments/exp_xxx)",
    )
    register_hb_parser.add_argument(
        "--submit-time",
        default=None,
        help="浠诲姟鎻愪氦鏃堕棿瀛楃涓诧紝榛樿褰撳墠鏃堕棿 (鏍煎紡寤鸿: 'YYYY-MM-DD HH:MM')",
    )
    register_hb_parser.add_argument(
        "--status",
        default="Running",
        help="鍐欏叆琛ㄦ牸鐨勫垵濮嬬姸鎬佸瓧闈㈠€?(榛樿: Running)",
    )
    register_hb_parser.add_argument(
        "--heartbeat-file",
        default=os.path.expanduser("~/.openclaw/workspace/HEARTBEAT.md"),
        help=(
            "HEARTBEAT.md 璺緞锛岄粯璁?~/.openclaw/workspace/HEARTBEAT.md銆?
            "OpenClaw 鍙湪璇ヨ矾寰勪笅瑙﹀彂蹇冭烦锛屽繀椤绘槸姝ょ洰褰曟垨鍏跺瓙鐩綍涓嬬殑 HEARTBEAT.md銆?
        ),
    )

    #  ==================== model 妯″潡 =======================

    model_parser = subparsers.add_parser("model", help="鍩虹妯″瀷绠＄悊")
    model_subparsers = model_parser.add_subparsers(
        dest="model_command", title="鍩虹妯″瀷鍛戒护", help="鍩虹妯″瀷鎿嶄綔鍛戒护"
    )

    # model list-models
    model_list_parser = model_subparsers.add_parser(
        "list-models",
        help="鏌ヨ鍩虹妯″瀷鍒楄〃锛屾敮鎸佸悕绉版ā绯婃煡璇㈠拰璁粌绫诲瀷绛涢€?,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥:
  # LLM
  ark-trainer-helper model list-models

  # 'doubao'
  ark-trainer-helper model list-models --name doubao

  #  Query models supporting FinetuneLoRA training

  ark-trainer-helper model list-models --supported-customization-type FinetuneLoRA

  # 锛?doubao'GRPOLoRA
  ark-trainer-helper model list-models --name doubao --supported-customization-type GRPOLoRA
        """,
    )
    model_list_parser.add_argument("--name", help="妯″瀷鍚嶇О妯＄硦鏌ヨ鍏抽敭璇?)
    model_list_parser.add_argument(
        "--supported-customization-type",
        help="鏀寔鐨勮缁冪被鍨嬬瓫閫?(渚嬪: FinetuneLoRA, GRPOLoRA, FinetuneSft, GRPO)",
    )
    model_list_parser.add_argument(
        "--page-size", type=int, default=10, help="姣忛〉鏁伴噺 (榛樿: 10)"
    )
    model_list_parser.add_argument(
        "--page-number", type=int, default=1, help="椤电爜 (榛樿: 1)"
    )

    # model list-versions
    model_list_versions_parser = model_subparsers.add_parser(
        "list-versions", help="鏌ヨ鍩虹妯″瀷鐨勬墍鏈夊彲鐢ㄧ増鏈?
    )
    model_list_versions_parser.add_argument(
        "--model-name", required=True, help="鍩虹妯″瀷鍚嶇О (渚嬪: doubao-seed-1-6)"
    )
    model_list_versions_parser.add_argument(
        "--page-size", type=int, default=50, help="姣忛〉鏁伴噺 (榛樿: 50)"
    )
    model_list_versions_parser.add_argument(
        "--page-number", type=int, default=1, help="椤电爜 (榛樿: 1)"
    )

    #  ==================== endpoint 妯″潡 =======================

    endpoint_parser = subparsers.add_parser("endpoint", help="绔偣绠＄悊")
    endpoint_subparsers = endpoint_parser.add_subparsers(
        dest="endpoint_command", title="绔偣鍛戒护", help="绔偣鎿嶄綔鍛戒护"
    )

    # endpoint create
    create_parser = endpoint_subparsers.add_parser(
        "create", parents=[global_parser], help="鍒涘缓鏂扮鐐?
    )
    create_parser.add_argument("--name", required=True, help="绔偣鍚嶇О")
    create_parser.add_argument("--description", default="", help="绔偣鎻忚堪")
    create_parser.add_argument("--custom-model-id", required=True, help="鑷畾涔夋ā鍨婭D")

    # endpoint list
    list_parser = endpoint_subparsers.add_parser(
        "list", parents=[global_parser], help="鍒楀嚭鎵€鏈夌鐐?
    )
    list_parser.add_argument(
        "--page-size", type=int, default=10, help="姣忛〉鏁伴噺 (榛樿: 10)"
    )
    list_parser.add_argument(
        "--page-number", type=int, default=1, help="椤电爜 (榛樿: 1)"
    )

    # endpoint get
    get_parser = endpoint_subparsers.add_parser("get", help="鑾峰彇绔偣璇︽儏")
    get_parser.add_argument("--endpoint-id", required=True, help="绔偣ID")

    # endpoint certificate
    certificate_parser = endpoint_subparsers.add_parser(
        "certificate", help="鑾峰彇绔偣璇佷功"
    )
    certificate_parser.add_argument("--endpoint-id", required=True, help="绔偣ID")

    # endpoint stop
    stop_parser = endpoint_subparsers.add_parser("stop", help="鍋滄绔偣")
    stop_parser.add_argument("--endpoint-id", required=True, help="绔偣ID")

    # endpoint delete
    delete_parser = endpoint_subparsers.add_parser("delete", help="鍒犻櫎绔偣")
    delete_parser.add_argument("--endpoint-id", required=True, help="绔偣ID")

    #  ==================== train 妯″潡 =======================

    train_parser = subparsers.add_parser("train", help="璁粌宸ュ叿闆?)
    train_subparsers = train_parser.add_subparsers(
        dest="train_command", title="璁粌宸ュ叿鍛戒护", help="璁粌鐩稿叧宸ュ叿鎿嶄綔鍛戒护"
    )

    # train evaluate
    evaluate_parser = train_subparsers.add_parser(
        "evaluate",
        help="妯″瀷璇勪及锛堣绠桞ON/AON/AvgN鎸囨爣锛?,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
閲嶈锛氳璇勪及鍝釜妯″瀷鐢?rollout.py 鑷繁鍐冲畾鈥斺€斿嵆 rollout 閲岃皟鐢?chat.completions.create(model=...) 鏃朵紶鍏ョ殑閭ｄ釜瀛楃涓层€?
鏈懡浠や笉鍐嶆帴鏀?--model 鍙傛暟銆傝繍琛?evaluate 涔嬪墠锛岃鍏堟墜宸ユ妸 rollout.py 涓殑 model 瀛楁鏀规垚鐩爣妯″瀷鍚?鐗堟湰/绔偣ID/鑷畾涔夋ā鍨婭D锛屽啀鎵ц鏈懡浠ゃ€?

绀轰緥:
  # 
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py

  # 
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py \\
                     --n-rollouts 8 --max-concurrency 15

  # 
  ark-trainer-helper train evaluate --dataset test.jsonl --rollout rollout.py --grader grader.py \\
                     --output-dir ./my_results
        """,
    )
    evaluate_parser.add_argument(
        "--dataset", type=str, required=True, help="璇勪及鏁版嵁闆嗚矾寰?(JSON鎴朖SONL鏍煎紡)"
    )
    evaluate_parser.add_argument(
        "--rollout",
        type=str,
        required=True,
        help="rollout鍑芥暟Python鏂囦欢璺緞锛堣鏂囦欢鍐呴儴鐨?model= 瀛楁鍐冲畾瀹為檯璇勪及鐨勬ā鍨嬶級",
    )
    evaluate_parser.add_argument(
        "--grader", type=str, required=True, help="grader鍑芥暟Python鏂囦欢璺緞"
    )
    evaluate_parser.add_argument(
        "--n-rollouts", type=int, default=8, help="姣忎釜鏍锋湰鐨剅ollout娆℃暟 (榛樿: 8)"
    )
    evaluate_parser.add_argument(
        "--batch-size", type=int, default=15, help="璇勪及鎵规澶у皬 (榛樿: 15)"
    )
    evaluate_parser.add_argument(
        "--max-concurrency", type=int, default=15, help="鏈€澶у苟鍙戞暟 (榛樿: 15)"
    )
    evaluate_parser.add_argument(
        "--output-dir",
        type=str,
        default="./eval_output",
        help="璇勪及缁撴灉杈撳嚭鐩綍 (榛樿: ./eval_output)",
    )
    evaluate_parser.add_argument("--verbose", action="store_true", help="鍚敤璇︾粏鏃ュ織")

    # train rft-data-collect
    rft_data_parser = train_subparsers.add_parser(
        "rft-data-collect",
        help="RFT璁粌鏁版嵁鏀堕泦锛氫粠璇勪及缁撴灉涓瓫閫変紭璐ㄨ建杩圭敓鎴愯缁冩暟鎹?,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
绀轰緥:
  # RFT
  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json \\
                                            --output-file ./rft_train_data.jsonl \\
                                            --rollout ./rollout.py

  # tools锛圝SON锛宼oolsJSON锛?
  ark-trainer-helper train rft-data-collect --eval-results ./eval_output/eval_results.json \\
                                            --output-file ./rft_train_data.jsonl \\
                                            --tools-file ./tools.json
        """,
    )
    rft_data_parser.add_argument(
        "--eval-results",
        type=str,
        required=True,
        help="璇勪及缁撴灉JSON鏂囦欢璺緞 (鐢眅valuate鍛戒护鐢熸垚)",
    )
    rft_data_parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="杈撳嚭鐨凴FT璁粌鏁版嵁鏂囦欢璺緞 (JSONL鏍煎紡)",
    )
    rft_data_parser.add_argument(
        "--rollout",
        type=str,
        help="鍙€夛細rollout鎻掍欢璺緞锛岀敤浜庝粠rollout_tools/tools鍙橀噺琛ュ厖Function Calling鏍锋湰蹇呴渶鐨勯《灞倀ools瀛楁",
    )
    rft_data_parser.add_argument(
        "--tools-file",
        type=str,
        help="鍙€夛細tools瀹氫箟鏂囦欢璺緞锛屾敮鎸丣SON鏁扮粍鎴栧寘鍚玹ools瀛楁鐨凧SON瀵硅薄锛涗紭鍏堢骇楂樹簬--rollout",
    )

    # 
    args = parser.parse_args()

    # 
    if not args.module:
        parser.print_help()
        return

    # job
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

    # model
    elif args.module == "model":
        if not args.model_command:
            model_parser.print_help()
            return

        if args.model_command == "list-models":
            list_foundation_models(args)
        elif args.model_command == "list-versions":
            list_foundation_model_versions(args)

    # endpoint
    elif args.module == "endpoint":
        if not args.endpoint_command:
            endpoint_parser.print_help()
            return

        #  Get API instance

        api = init_api_client()
        if not api:
            return

        #  Execute command

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

    # train
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
