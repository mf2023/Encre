#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_profiler.py — CSV 数据画像与异常检测助手（纯标准库）

读取 CSV，输出每列的统计摘要、缺失率、异常值检测（IQR/Z-score），
给出数据质量评分与清洗建议。仅做分析与建议，不修改原始文件。

用法：
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
    """转义 Markdown 表格单元格中的用户字段。顺序: & → < > → | → 换行 → 行首字符。"""
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
    print(f"[错误] 无法读取文件或编码不匹配：{path}", file=sys.stderr)
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
    """检测语义异常（负数量、不可能折扣等）"""
    issues = []
    clean_name = col_name.lower()
    nums = parse_numeric(values)
    for i, v in enumerate(nums):
        if v is None:
            continue
        if any(kw in clean_name for kw in ["qty", "quantity", "数量", "销量"]) and v < 0:
            issues.append((i + 1, f"负数量 {v}"))
        if any(kw in clean_name for kw in ["discount", "折扣"]) and (v < 0 or v > 100):
            issues.append((i + 1, f"不合理折扣 {v}%"))
        if any(kw in clean_name for kw in ["price", "单价"]) and v <= 0:
            issues.append((i + 1, f"非正价格 {v}"))
    return issues


def profile_column(values, col_name, method="iqr"):
    n = len(values)
    nulls = sum(1 for v in values if v is None)
    null_pct = nulls / n * 100 if n else 0
    present = [v for v in values if v is not None]
    uniq = len(set(present))

    result = {"nulls": nulls, "null_pct": null_pct, "uniq": uniq, "is_numeric": False, "dtype": "文本/分类"}
    if not present:
        result["dtype"] = "空列"
        result["dist"] = "整列为空"
        return result

    if is_numeric(present):
        nums = parse_numeric(present)
        clean = [x for x in nums if x is not None]
        if clean:
            clean.sort()
            nc = len(clean)
            result.update({
                "is_numeric": True, "dtype": "数值",
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
            result["dist"] = f"含 {o} 个异常值（低{lo}/高{hi}）" if o else "无明显异常值"
    else:
        str_vals = [str(v).strip() for v in present if str(v).strip()]
        counter = Counter(str_vals)
        top = counter.most_common(3)
        result["top_values"] = ", ".join(f"{sanitize_md_cell(k)}({v}次)" for k, v in top)
        single_ratio = (counter.most_common(1)[0][1] / len(present) * 100) if counter else 0
        if single_ratio > 95:
            result["dist"] = f"单一值占比 {single_ratio:.0f}%，方差为零"
        elif uniq / n < 0.01 and n > 100:
            result["dist"] = f"基数极低（{uniq}唯一值/{n}行）"
        else:
            result["dist"] = f"{uniq} 个唯一值"

    return result


def main():
    ap = argparse.ArgumentParser(description="CSV 数据画像与异常检测助手（纯标准库）")
    ap.add_argument("--input", required=True, help="CSV 文件路径")
    ap.add_argument("--method", choices=["iqr", "zscore"], default="iqr", help="异常检测方法")
    ap.add_argument("--sample", type=int, default=None, help="抽样行数")
    args = ap.parse_args()

    headers, rows = load_csv(args.input, args.sample)
    if not rows:
        print("[提示] 数据文件无有效数据行。")
        return

    n_rows = len(rows)
    print(f"## 数据画像报告\n")
    print(f"**文件**：{sanitize_md_cell(args.input)}  ")
    print(f"**行数**：{n_rows}  |  **列数**：{len(headers)}  |  **方法**：{args.method.upper()}")
    if args.sample:
        print(f"  * 抽样 {args.sample} 行（全量 {n_rows} 行）")
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
            issues.append((h, f"缺失率 {p['null_pct']:.1f}% > 20%"))
        if p.get("outliers", 0) > n_rows * 0.05 and n_rows > 20:
            issues.append((h, f"异常值比例 {p['outliers']/n_rows*100:.1f}% > 5%"))
        sem = detect_semantic_anomalies(h, col_data[h])
        if sem:
            for row_idx, desc in sem:
                semantic_all.append((h, row_idx, desc))

    # 数值列
    num_cols = [(h, p) for h, p in profiles.items() if p.get("is_numeric")]
    if num_cols:
        print("### 数值列画像\n")
        print("| 列名 | 缺失(%) | 均值 | 中位数 | 标准差 | 最小值 | 最大值 | 异常值 | 分布评价 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for h, p in num_cols:
            print(f"| {h} | {p['null_pct']:.1f} | {p['mean']:.2f} | {p['median']:.2f} | {p['std']:.2f} | {p['min_val']:.2f} | {p['max_val']:.2f} | {p.get('outliers', 0)} | {p['dist']} |")
        print()

    # 文本列
    txt_cols = [(h, p) for h, p in profiles.items() if not p.get("is_numeric")]
    if txt_cols:
        print("### 文本/分类列画像\n")
        print("| 列名 | 缺失(%) | 唯一值 | 高频值 | 分布评价 |")
        print("|---|---|---|---|---|")
        for h, p in txt_cols:
            top = p.get("top_values", "—")
            print(f"| {h} | {p['null_pct']:.1f} | {p['uniq']} | {top} | {p['dist']} |")
        print()

    # 语义异常
    if semantic_all:
        print("### 语义异常检测\n")
        print("| 列名 | 行号 | 问题 |")
        print("|---|---|---|")
        for col, row_idx, desc in semantic_all[:20]:
            print(f"| {col} | {row_idx} | {desc} |")
        print()

    # 质量评分
    print("### 数据质量评分\n")
    null_avg = sum(p.get("null_pct", 0) for p in profiles.values()) / len(profiles)
    outlier_total = sum(p.get("outliers", 0) for p in profiles.values())
    outlier_pct = outlier_total / n_rows / len(profiles) * 100 if n_rows else 0
    print("| 维度 | 评分(1-5) | 说明 |")
    print("|---|---|---|")
    print(f"| 完整性 | {min(5, max(1, int(5 - null_avg / 5)))} | 平均缺失率 {null_avg:.1f}% |")
    print(f"| 异常值 | {min(5, max(1, int(5 - outlier_pct)))} | 异常值占比 {outlier_pct:.1f}% |")
    print()

    if issues:
        print("### 需关注的问题\n")
        for col, desc in issues[:10]:
            print(f"- **{col}**：{desc}")
        print()

    print("> 以上分析基于所提供数据，结论仅供参考。")


if __name__ == "__main__":
    main()
