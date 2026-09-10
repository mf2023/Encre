from __future__ import annotations

"""
璁粌浠诲姟绠悊妯潡
"""

import datetime
from pathlib import Path

from loguru import logger
from ark_sdk.resources.model_customization_job import ModelCustomizationJob


# =========================================================================
# HEARTBEAT.md
# =========================================================================

# AI  6 锛圫KILL.md  HEARTBEAT 锛?
HEARTBEAT_SYSTEM_REMINDER = """# byted-ark-trainer蹇冭烦鐩戞帶浠诲姟鍒楄

> 鈿狅笍銆愮郴缁熸彁閱?路 AI鎺ユ墜璁粌浠诲姟鏃跺繀璇汇?
> 1. **蹇呴』鍏堝姞杞?byted-ark-trainer skill**锛氫繚鎸?byted-ark-trainer skill 濮嬬粓鍦ㄤ笂涓嬫枃涓紝鑻ヤ笉鍦ㄥ垯涓诲姩鍔犺浇 byted-ark-trainer skill锛堣鍙栬skill鐨凷KILL.md锛夈?
> 2. **鎺ユ墜浠诲姟鍓嶅繀椤诲厛璇诲彇瀵瑰簲鐨勫疄楠岀洰褰?*锛氬湪澶勭悊涓嬭浠讳綍浠诲姟鍓嶏紝蹇呴』鍏堟墦寮璇ヤ换鍔°屽疄楠岀洰褰曠粷瀵硅矾寰勩嶄笅鐨?`EXPERIMENT.md`锛岀悊瑙ｅ疄楠岃鍒掋佸凡涓庣敤鎴风‘璁ょ殑鍏抽敭閰嶇疆銆佸悗缁祦绋嬨?*涓嶈瀹?`EXPERIMENT.md` 涓嶅厑璁告墽琛屼换浣曞姩浣?*銆?
> 3. **閫愰」妫鏌ヤ换鍔姸鎬?*锛氬涓嬭姣忎釜ARK璁粌浠诲姟鎵ц `byted-ark-trainer-helper job status --job-id <浠诲姟ID>` 鏌ヨ鏈鏂扮姸鎬侊紝骞舵妸缁撴灉鍚屾鍥炰笅琛ㄧ殑銆屾渶鏂扮姸鎬併嶅垪銆?
> 4. **浠诲姟瀹屾垚涓旀湁鍚庣画娴佺▼鏃讹紝涓嶉渶瑕佺敤鎴蜂簩娆‘璁?*锛氳嫢浠诲姟鐘舵佸彉涓?Completed锛屾寜璇ヤ换鍔?`EXPERIMENT.md` 涓屽悗缁祦绋嬨嶇殑璁板綍**绔嬪嵆鎵ц涓嬩竴姝?*锛堜緥濡?RFT 瀹屾垚鍚庢彁浜?GRPO銆佽缁冨畬鎴愬悗鍦ㄦ祴璇曢泦涓婅瘎浼帮級锛屾墽琛屽畬姣曞悗鍐嶉氱煡鐢ㄦ埛缁撴灉锛屽苟鎶婄粨鏋滃閲忔洿鏂板埌 `EXPERIMENT.md`銆?
> 5. **浠诲姟澶辫触蹇呴』鎶ュ憡鐢ㄦ埛锛屼笉寰楄嚜琛岀Щ闄?*锛氱姸鎬佷负 Failed/Terminated 鏃讹紝绔嬪嵆鍚戠敤鎴峰睍绀哄畬鏁撮敊璇俊鎭拰澶辫触鍘熷洜锛岃闂槸鍚﹂噸璇曟垨璋冩暣閰嶇疆锛?*鍙湁鍦ㄧ敤鎴锋槑纭‘璁ゅ悗鎵嶈兘灏嗚浠诲姟浠庝笅琛ㄤ腑绉婚櫎**锛屽湪鐢ㄦ埛纭涔嬪墠蹇呴』淇濈暀璇ユ潯鐩互渚胯拷婧?
> 6. **涓ョ缂栭犱笂涓嬫枃**锛氬鏋滃疄楠岀洰褰曟垨 `EXPERIMENT.md` 缂哄け瀵艰嚧鏃犳硶鐞嗚В浠诲姟鎰忓浘锛屼笉寰楄嚜琛岀寽娴嬶紝蹇呴』鍏堣闂敤鎴枫?
"""

HEARTBEAT_TABLE_HEADER = (
    "| 浠诲姟ID | 浠诲姟绫诲瀷 | 鎻愪氦鏃堕棿 | 鏈鏂扮姸鎬?| 浠诲姟閾炬帴 | 瀹為獙鐩綍缁濆璺緞 |\n"
    "|--------|----------|----------|----------|----------|------------------|\n"
)

# token锛堬級
_REMINDER_TOKENS = [
    "銆愮郴缁熸彁閱?路 AI鎺ユ墜璁粌浠诲姟鏃跺繀璇汇?",
    "蹇呴』鍏堝姞杞?byted-ark-trainer skill",
    "蹇呴』鍏堣鍙栧搴旂殑瀹為獙鐩綍",
    "閫愰」妫鏌ヤ换鍔姸鎬?",
    "涓嶉渶瑕佺敤鎴蜂簩娆‘璁?",
    "浠诲姟澶辫触蹇呴』鎶ュ憡鐢ㄦ埛锛屼笉寰楄嚜琛岀Щ闄?",
    "涓ョ缂栭犱笂涓嬫枃",
]


def _reminder_block_intact(text: str) -> bool:
    """鍒ゆ柇 HEARTBEAT.md 寮澶寸殑绯荤粺鎻愰啋鍧?6 鏉槸鍚﹂綈鍏ㄣ"""
    last_idx = -1
    for tok in _REMINDER_TOKENS:
        idx = text.find(tok)
        if idx == -1 or idx < last_idx:
            return False
        last_idx = idx
    return True


def _append_task_row(heartbeat_text: str, row: str, job_id: str) -> tuple[str, bool]:
    """
    灏嗕换鍔杩藉姞鍒?HEARTBEAT.md 鐨勮鏍兼湯灏俱傝嫢鍚?job_id 宸插瓨鍦ㄥ垯涓嶉噸澶嶈拷鍔犮?
    杩斿洖 (鏂版枃鏈? 鏄惁鏂板)
    """
    if job_id in heartbeat_text:
        return heartbeat_text, False
    # 
    if not heartbeat_text.endswith("\n"):
        heartbeat_text += "\n"
    # 锛?
    if "| 浠诲姟ID |" not in heartbeat_text:
        heartbeat_text += "\n" + HEARTBEAT_TABLE_HEADER
    heartbeat_text += row + "\n"
    return heartbeat_text, True


def register_heartbeat_command(args):
    """
    鐧昏涓涓缁冧换鍔埌 HEARTBEAT.md銆?
    - 鑻ユ枃浠朵笉瀛樺湪锛氱敤瀹屾暣妯澘鍒涘缓锛堢郴缁熸彁閱掑潡 + 琛ㄥご + 鏂颁换鍔锛?
    - 鑻ユ枃浠跺凡瀛樺湪浣嗙郴缁熸彁閱掑潡缂哄け/涓嶅畬鏁达細鍦ㄦ枃浠舵渶椤堕儴琛ラ綈鎻愰啋鍧楋紝鍐?append 浠诲姟琛?
    - 鑻ユ枃浠跺凡瀛樺湪涓?job-id 宸茬櫥璁帮細骞傜瓑璺宠繃锛堣繑鍥炴彁绀猴級
    绾︽潫锛?-heartbeat-file 蹇呴』浣嶄簬 ~/.openclaw 涔嬩笅锛圤penClaw 宸ヤ綔鍖烘牴锛夛紝闃叉鎶婂績璺虫枃浠跺啓鍒版棤鍏崇洰褰曘?
    """
    heartbeat_path = Path(args.heartbeat_file).expanduser().resolve()

    # 锛?~/.openclaw
    openclaw_root = Path("~/.openclaw").expanduser().resolve()
    try:
        heartbeat_path.relative_to(openclaw_root)
    except ValueError:
        raise SystemExit(
            f"REFUSED: --heartbeat-file must live under {openclaw_root}."
            f"Given path: {heartbeat_path}."
            f"Put HEARTBEAT.md inside an OpenClaw workspace, e.g. {openclaw_root}/workspace/<project>/HEARTBEAT.md, then re-login."
        )

    submit_time = args.submit_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    status = args.status or "Running"
    exp_dir = str(Path(args.exp_dir).expanduser().resolve())

    row = (
        f"| {args.job_id} | {args.job_type} | {submit_time} | {status} "
        f"| {args.job_url} | {exp_dir} |"
    )

    print(f"\n=== 鐧昏蹇冭烦浠诲姟 ({args.job_id}) ===")
    print(f"鐩爣 HEARTBEAT.md: {heartbeat_path}")

    if not heartbeat_path.exists():
        # 锛?
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        content = HEARTBEAT_SYSTEM_REMINDER + "\n" + HEARTBEAT_TABLE_HEADER + row + "\n"
        heartbeat_path.write_text(content, encoding="utf-8")
        print("鉁?HEARTBEAT.md 涓嶅瓨鍦紝宸茬敤瀹屾暣妯澘鍒涘缓锛堝惈绯荤粺鎻愰啋鍧?+ 鏂颁换鍔′竴琛岋級")
        print(f"鉁?宸茶拷鍔犱换鍔?{args.job_id} 鍒板績璺虫憳瑕佽")
        return

    # 锛?
    text = heartbeat_path.read_text(encoding="utf-8")
    reminder_ok = _reminder_block_intact(text)

    if not reminder_ok:
        # 
        text = HEARTBEAT_SYSTEM_REMINDER + "\n" + text
        print("鈿?妫娴嬪埌鏂囦欢椤堕儴绯荤粺鎻愰啋鍧楃己澶?涓嶅畬鏁达紝宸插湪鏂囦欢椤堕儴琛ラ綈瀹屾暣鎻愰啋鍧?")
    else:
        print("鉁?鏂囦欢椤堕儴绯荤粺鎻愰啋鍧楀凡榻愬叏锛屼繚鐣欎笉鍙?")

    new_text, added = _append_task_row(text, row, args.job_id)
    heartbeat_path.write_text(new_text, encoding="utf-8")

    if added:
        print(f"鉁?宸茶拷鍔犱换鍔?{args.job_id} 鍒板績璺虫憳瑕佽")
    else:
        print(f"鈩?浠诲姟 {args.job_id} 宸茬櫥璁拌繃锛岃烦杩囪拷鍔狅紙骞傜瓑锛?")


def get_job_status(job_id: str) -> ModelCustomizationJob:
    """
    鑾峰彇璁粌浠诲姟鐘舵?
    :param job_id: 璁粌浠诲姟ID
    :return: 璁粌浠诲姟瀵硅薄
    """
    job = ModelCustomizationJob.get(job_id)
    return job


def get_output_model_id(job_id: str) -> str:
    """
    鑾峰彇璁粌瀹岀殑妯瀷ID
    :param job_id: 璁粌浠诲姟ID
    :return: 璁粌瀹岀殑妯瀷ID
    """
    #  Use ark_sdk to get model info

    job = ModelCustomizationJob.get(job_id)
    finetune_status = job.phase
    logger.info(f"Task {job_id} finetune status is {finetune_status}")
    if finetune_status == "Completed":
        # 锛?outputs
        job.refresh()
        # outputs
        if hasattr(job, "_ModelCustomizationJob__outputs"):
            outputs = getattr(job, "_ModelCustomizationJob__outputs")
            logger.info(f"Outputs found: {outputs}")
            if outputs and len(outputs) > 0:
                # 锛孋ustomModelId锛堬級
                for output in reversed(outputs):
                    if hasattr(output, "CustomModelId") and output.CustomModelId:
                        return output.CustomModelId
                    # 
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
    澶勭悊job status鍛戒护
    """
    print(f"\n=== 鏌ヨ璁粌浠诲姟鐘舵?({args.job_id}) ===")
    try:
        job = get_job_status(args.job_id)
        print(f"浠诲姟ID: {job.id}")
        print(f"浠诲姟鍚嶇О: {job.name}")
        print(f"浠诲姟鐘舵? {job.phase}")
        print(f"鐘舵佹椂闂? {job.status.PhaseTime}")
        print(f"鏄惁鍙仮澶? {job.status.Resumable}")
        print(f"閲嶈瘯娆暟闄愬埗: {job.status.RetryLimit}")

        if job.status.Message:
            print(f"鐘舵佹秷鎭? {job.status.Message}")
        if job.status.QueuePosition is not None:
            print(f"闃熷垪浣嶇疆: {job.status.QueuePosition}")
        if job.status.BillableTokens is not None:
            print(f"璁垂Token鏁? {job.status.BillableTokens}")
        if job.status.TrainingTokensPerEpoch is not None:
            print(f"姣忚疆璁粌Token鏁? {job.status.TrainingTokensPerEpoch}")
        if job.status.RLPluginInfos:
            print(f"RL鎻掍欢淇伅: {job.status.RLPluginInfos}")

        print(f"\n浠诲姟鎻忚堪: {job.description}")
        print(f"椤圭洰: {job.project}")
        print(f"瀹氬埗绫诲瀷: {job.customization_type}")
        print(f"妯瀷寮曠敤: {job.model_reference}")
        return job
    except Exception as e:
        print(f"鏌ヨ澶辫触: {str(e)}")
        return None


def job_get_model_command(args):
    """
    澶勭悊job get-model鍛戒护
    """
    print(f"\n=== 鑾峰彇璁粌杈撳嚭妯瀷ID ({args.job_id}) ===")
    try:
        model_id = get_output_model_id(args.job_id)
        print(f"璁粌瀹屾垚锛佹ā鍨婭D: {model_id}")
        return model_id
    except Exception as e:
        print(f"鑾峰彇澶辫触: {str(e)}")
        return None
