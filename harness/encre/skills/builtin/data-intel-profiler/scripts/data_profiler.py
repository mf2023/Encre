#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
data_profiler.py 鈥?CSV 鏁版嵁鐢诲儚涓庡紓甯告娴嬪姪鎵嬶紙绾爣鍑嗗簱锛?

璇诲彇 CSV锛岃緭鍑烘瘡鍒楃殑缁熻鎽樿銆佺己澶辩巼銆佸紓甯稿€兼娴嬶紙IQR/Z-score锛夛紝
缁欏嚭鏁版嵁璐ㄩ噺璇勫垎涓庢竻娲楀缓璁€備粎鍋氬垎鏋愪笌寤鸿锛屼笉淇敼鍘熷鏂囦欢銆?

鐢ㄦ硶锛?
    python3 data_profiler.py --input data.csv
    python3 data_profiler.py --input data.csv --method zscore
    python3 data_profiler.py --input data.csv --sample 1000
"""
import argparse
import csv
import math
import re
import sys
from collections import Counter


_CSV_INJECTION_RE = re.compile(r"^[=+\-@]")


def sanitize_md_cell(text):
    """杞箟 Markdown 琛ㄦ牸鍗曞厓鏍间腑鐨勭敤鎴峰瓧娈点€傞『搴? & 鈫?< > 鈫?| 鈫?鎹㈣ 鈫?琛岄瀛楃銆?""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("|", "&#124;")
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("\t", " ")
    if text.startswith("="):
        text = "&#61;" + text[1:]
    if text.startswith("+"):
        text = "\\" + text
    if text.startswith("-"):
        text = "\\" + text
    if text.startswith("@"):
        text = "\\" + text
    return text


def load_csv(path, sample=None):
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                headers = [sanitize_md_cell(h) for h in reader.fieldnames]
                rows = []
                for i, row in enumerate(reader):
                    if sample and i >= sample:
                        break
                    rows.append(row)
                return headers, rows
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    print(f"[閿欒] 鏃犳硶璇诲彇鏂囦欢鎴栫紪鐮佷笉鍖归厤锛歿path}", file=sys.stderr)
    sys.exit(1)


def is_numeric(values):
    count = 0
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        try:
            float(str(v).replace(",", "").replace(" ", ""))
            count += 1
        except ValueError:
            return False
    return count > len(values) * 0.7


def parse_numeric(values):
    result = []
    for v in values:
        if v is None or str(v).strip() == "":
            result.append(None)
        else:
            try:
                result.append(float(str(v).replace(",", "").replace(" ", "")))
            except ValueError:
                result.append(None)
    return result


def detect_outliers_iqr(nums):
    clean = sorted([x for x in nums if x is not None])
    if len(clean) < 4:
        return 0, 0, 0
    n = len(clean)
    q1 = clean[n // 4]
    q3 = clean[3 * n // 4]
    iqr = q3 - q1
    if iqr == 0:
        return 0, 0, 0
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    low_ct = sum(1 for x in nums if x is not None and x < lo)
    high_ct = sum(1 for x in nums if x is not None and x > hi)
    return low_ct + high_ct, low_ct, high_ct


def detect_outliers_zscore(nums):
    clean = [x for x in nums if x is not None]
    if len(clean) < 3:
        return 0, 0, 0
    mu = sum(clean) / len(clean)
    sigma = math.sqrt(sum((x - mu) ** 2 for x in clean) / len(clean))
    if sigma == 0:
        return 0, 0, 0
    count = sum(1 for x in nums if x is not None and abs((x - mu) / sigma) > 3)
    return count, 0, 0


def detect_semantic_anomalies(col_name, values):
    """妫€娴嬭涔夊紓甯革紙璐熸暟閲忋€佷笉鍙兘鎶樻墸绛夛級"""
    issues = []
    clean_name = col_name.lower()
    nums = parse_numeric(values)
    for i, v in enumerate(nums):
        if v is None:
            continue
        if any(kw in clean_name for kw in ["qty", "quantity", "鏁伴噺", "閿€閲?]) and v < 0:
            issues.append((i + 1, f"璐熸暟閲?{v}"))
        if any(kw in clean_name for kw in ["discount", "鎶樻墸"]) and (v < 0 or v > 100):
            issues.append((i + 1, f"涓嶅悎鐞嗘姌鎵?{v}%"))
        if any(kw in clean_name for kw in ["price", "鍗曚环"]) and v <= 0:
            issues.append((i + 1, f"闈炴浠锋牸 {v}"))
    return issues


def profile_column(values, col_name, method="iqr"):
    n = len(values)
    nulls = sum(1 for v in values if v is None)
    null_pct = nulls / n * 100 if n else 0
    present = [v for v in values if v is not None]
    uniq = len(set(present))

    result = {"nulls": nulls, "null_pct": null_pct, "uniq": uniq, "is_numeric": False, "dtype": "鏂囨湰/鍒嗙被"}
    if not present:
        result["dtype"] = "绌哄垪"
        result["dist"] = "鏁村垪涓虹┖"
        return result

    if is_numeric(present):
        nums = parse_numeric(present)
        clean = [x for x in nums if x is not None]
        if clean:
            clean.sort()
            nc = len(clean)
            result.update({
                "is_numeric": True, "dtype": "鏁板€?,
                "mean": sum(clean) / nc,
                "median": clean[nc // 2],
                "std": math.sqrt(sum((x - sum(clean) / nc) ** 2 for x in clean) / nc) if nc > 1 else 0,
                "min_val": clean[0], "max_val": clean[-1],
                "p25": clean[nc // 4], "p75": clean[3 * nc // 4],
            })
            if method == "zscore":
                o, lo, hi = detect_outliers_zscore(nums)
            else:
                o, lo, hi = detect_outliers_iqr(nums)
            result["outliers"] = o
            result["outlier_low"] = lo
            result["outlier_high"] = hi
            result["dist"] = f"鍚?{o} 涓紓甯稿€硷紙浣巤lo}/楂榹hi}锛? if o else "鏃犳槑鏄惧紓甯稿€?
    else:
        str_vals = [str(v).strip() for v in present if str(v).strip()]
        counter = Counter(str_vals)
        top = counter.most_common(3)
        result["top_values"] = ", ".join(f"{sanitize_md_cell(k)}({v}娆?" for k, v in top)
        single_ratio = (counter.most_common(1)[0][1] / len(present) * 100) if counter else 0
        if single_ratio > 95:
            result["dist"] = f"鍗曚竴鍊煎崰姣?{single_ratio:.0f}%锛屾柟宸负闆?
        elif uniq / n < 0.01 and n > 100:
            result["dist"] = f"鍩烘暟鏋佷綆锛坽uniq}鍞竴鍊?{n}琛岋級"
        else:
            result["dist"] = f"{uniq} 涓敮涓€鍊?

    return result


def main():
    ap = argparse.ArgumentParser(description="CSV 鏁版嵁鐢诲儚涓庡紓甯告娴嬪姪鎵嬶紙绾爣鍑嗗簱锛?)
    ap.add_argument("--input", required=True, help="CSV 鏂囦欢璺緞")
    ap.add_argument("--method", choices=["iqr", "zscore"], default="iqr", help="寮傚父妫€娴嬫柟娉?)
    ap.add_argument("--sample", type=int, default=None, help="鎶芥牱琛屾暟")
    args = ap.parse_args()

    headers, rows = load_csv(args.input, args.sample)
    if not rows:
        print("[鎻愮ず] 鏁版嵁鏂囦欢鏃犳湁鏁堟暟鎹銆?)
        return

    n_rows = len(rows)
    print(f"## 鏁版嵁鐢诲儚鎶ュ憡\n")
    print(f"**鏂囦欢**锛歿sanitize_md_cell(args.input)}  ")
    print(f"**琛屾暟**锛歿n_rows}  |  **鍒楁暟**锛歿len(headers)}  |  **鏂规硶**锛歿args.method.upper()}")
    if args.sample:
        print(f"  * 鎶芥牱 {args.sample} 琛岋紙鍏ㄩ噺 {n_rows} 琛岋級")
    print()

    col_data = {h: [] for h in headers}
    for row in rows:
        for h in headers:
            v = row.get(h, "")
            col_data[h].append(v if v and str(v).strip() else None)

    profiles = {}
    issues = []
    semantic_all = []
    for h in headers:
        p = profile_column(col_data[h], h, args.method)
        profiles[h] = p
        if p.get("null_pct", 0) > 20:
            issues.append((h, f"缂哄け鐜?{p['null_pct']:.1f}% > 20%"))
        if p.get("outliers", 0) > n_rows * 0.05 and n_rows > 20:
            issues.append((h, f"寮傚父鍊兼瘮渚?{p['outliers']/n_rows*100:.1f}% > 5%"))
        sem = detect_semantic_anomalies(h, col_data[h])
        if sem:
            for row_idx, desc in sem:
                semantic_all.append((h, row_idx, desc))

    # 
    num_cols = [(h, p) for h, p in profiles.items() if p.get("is_numeric")]
    if num_cols:
        print("### 鏁板€煎垪鐢诲儚\n")
        print("| 鍒楀悕 | 缂哄け(%) | 鍧囧€?| 涓綅鏁?| 鏍囧噯宸?| 鏈€灏忓€?| 鏈€澶у€?| 寮傚父鍊?| 鍒嗗竷璇勪环 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for h, p in num_cols:
            print(f"| {h} | {p['null_pct']:.1f} | {p['mean']:.2f} | {p['median']:.2f} | {p['std']:.2f} | {p['min_val']:.2f} | {p['max_val']:.2f} | {p.get('outliers', 0)} | {p['dist']} |")
        print()

    # 
    txt_cols = [(h, p) for h, p in profiles.items() if not p.get("is_numeric")]
    if txt_cols:
        print("### 鏂囨湰/鍒嗙被鍒楃敾鍍廫n")
        print("| 鍒楀悕 | 缂哄け(%) | 鍞竴鍊?| 楂橀鍊?| 鍒嗗竷璇勪环 |")
        print("|---|---|---|---|---|")
        for h, p in txt_cols:
            top = p.get("top_values", "鈥?)
            print(f"| {h} | {p['null_pct']:.1f} | {p['uniq']} | {top} | {p['dist']} |")
        print()

    # 
    if semantic_all:
        print("### 璇箟寮傚父妫€娴媆n")
        print("| 鍒楀悕 | 琛屽彿 | 闂 |")
        print("|---|---|---|")
        for col, row_idx, desc in semantic_all[:20]:
            print(f"| {col} | {row_idx} | {desc} |")
        print()

    # 
    print("### 鏁版嵁璐ㄩ噺璇勫垎\n")
    null_avg = sum(p.get("null_pct", 0) for p in profiles.values()) / len(profiles)
    outlier_total = sum(p.get("outliers", 0) for p in profiles.values())
    outlier_pct = outlier_total / n_rows / len(profiles) * 100 if n_rows else 0
    print("| 缁村害 | 璇勫垎(1-5) | 璇存槑 |")
    print("|---|---|---|")
    print(f"| 瀹屾暣鎬?| {min(5, max(1, int(5 - null_avg / 5)))} | 骞冲潎缂哄け鐜?{null_avg:.1f}% |")
    print(f"| 寮傚父鍊?| {min(5, max(1, int(5 - outlier_pct)))} | 寮傚父鍊煎崰姣?{outlier_pct:.1f}% |")
    print()

    if issues:
        print("### 闇€鍏虫敞鐨勯棶棰榎n")
        for col, desc in issues[:10]:
            print(f"- **{col}**锛歿desc}")
        print()

    print("> 浠ヤ笂鍒嗘瀽鍩轰簬鎵€鎻愪緵鏁版嵁锛岀粨璁轰粎渚涘弬鑰冦€?)


if __name__ == "__main__":
    main()
