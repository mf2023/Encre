#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
娴嬭瘯瑕嗙洊鐜囩洸鍖哄垎鏋愬櫒锛坧ytest-forge 瀛愯兘鍔涳級
绉戝ぇ璁 AI 鏁版嵁鏅鸿兘鍒嗘瀽涓庡簲鐢?Skill 寮€鍙戞寫鎴樿禌 路 鏂瑰悜浜屻€屾祴璇曚笌璐ㄩ噺淇濋殰銆?

杈撳叆锛歅ython 婧愮爜鏂囦欢 + 锛堝彲閫夌殑锛夌幇鏈夋祴璇曟枃浠?鐩綍
杈撳嚭锛氱洸鍖哄垎鏋愭姤鍛?report.md + 鍙洿鎺ヨ繍琛岀殑缂哄彛娴嬭瘯楠ㄦ灦 test_<妯″潡>_gaps.py

涓?generate_tests.py 褰㈡垚銆岀粍鍚堟嫵銆嶏細
  1) generate_tests.py 浠庨浂閾洪噺锛堜负鎵€鏈夊嚱鏁扮敓鎴愬啋鐑熸祴璇曪級
  2) analyze_coverage.py 鏌ユ紡琛ョ己锛堟壘鍑虹幇鏈夋祴璇曚腑鏈鐩栫殑鍑芥暟/鏂规硶锛屾寜椋庨櫓鎺掑簭锛屽苟鑷姩涓虹己鍙ｈˉ楠ㄦ灦锛?

璁捐鍘熷垯锛氶珮椴佹鎬?
- 涓昏矾寰勭敤 coverage.py 瀹炴祴琛岃鐩栵紱coverage 涓嶅彲鐢?娴嬭瘯杩愯澶辫触鏃惰嚜鍔ㄩ檷绾т负闈欐€佸悕绉板尮閰?
- 鏈彁渚涗换浣曟祴璇?鈫?瑙嗕负鍏ㄩ儴鐩插尯锛堢瓑浠蜂簬鎻愮ず鐢?generate_tests.py 浠庨浂鐢熸垚锛夛紝涓嶅穿婧?
- 澶嶇敤 generate_tests.build_test_file 鐢熸垚缂哄彛楠ㄦ灦锛屼繚璇侀鏋舵案杩滆娉曞悎娉曘€佸彲杩愯
- 鎵€鏈夊紓甯歌鍚炴帀骞剁粰鍑哄彲璇绘彁绀猴紝宸ュ叿鑷韩闆跺穿婧?
"""
import ast
import json
import os
import sys
import argparse
import subprocess
import datetime
import traceback

# generate_tests 锛?pytest 锛?
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GEN_PATH = os.path.join(SCRIPT_DIR, "generate_tests.py")
_spec = __import__("importlib.util").util.spec_from_file_location("utg_generate", GEN_PATH)
gen = __import__("importlib.util").util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

SPECIAL_DUNDERS = {"__str__", "__len__", "__repr__", "__eq__", "__getitem__"}


# --------------------------------------------------------------------------- #
# 锛?/  / __init__锛?
# --------------------------------------------------------------------------- #
def count_branches(node):
    """缁熻鍒嗘敮/鍐崇瓥鐐规暟閲忥紝浣滀负澶嶆潅搴︽潈閲嶃€?""
    c = 0
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While,
                          ast.With, ast.AsyncWith, ast.Try, ast.ExceptHandler,
                          ast.IfExp, ast.BoolOp, ast.comprehension, ast.Assert)):
            c += 1
    return c


def make_unit(node, qual, kind, parent=None):
    name = node.name
    exposure = 0.4 if (name.startswith("_") and not name.startswith("__")) else 1.0
    return {
        "qual": qual,
        "name": name,
        "kind": kind,
        "parent": parent,
        "node": node,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "params": list(gen.iter_params(node)),
        "start": node.lineno,
        "end": getattr(node, "end_lineno", node.lineno),
        "branches": count_branches(node),
        "exposure": exposure,
    }


def is_testable_method(m):
    if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if m.name == "__init__":
        return True
    if m.name.startswith("_") and m.name not in SPECIAL_DUNDERS:
        return False
    return True


def extract_units(tree):
    units = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append(make_unit(n, qual=n.name, kind="func"))
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_testable_method(m):
                    units.append(make_unit(m, qual="%s.%s" % (n.name, m.name),
                                           kind="method", parent=n.name))
    return units


# --------------------------------------------------------------------------- #
# 
# --------------------------------------------------------------------------- #
def find_test_files(tests_path):
    """杩斿洖娴嬭瘯鏂囦欢璺緞鍒楄〃锛泃ests_path 鍙负鏂囦欢鎴栫洰褰曘€?""
    if tests_path is None:
        return []
    if os.path.isfile(tests_path):
        return [tests_path]
    if os.path.isdir(tests_path):
        files = []
        for fn in sorted(os.listdir(tests_path)):
            if fn.startswith("test_") and fn.endswith(".py"):
                files.append(os.path.join(tests_path, fn))
        return files
    return []


def read_test_source(files):
    chunks = []
    for f in files:
        try:
            src, _ = gen.read_source(f)
            chunks.append(src)
        except Exception:
            continue
    return "\n".join(chunks)


def coverage_run(src_abs, tests_path, out_dir):
    """鐢?coverage.py锛圥ython API锛夌簿纭祴閲忓崟涓簮鐮佹枃浠剁殑琛岃鐩栥€?

    鍏抽敭椴佹鎬ц璁★細
    - 鐢?`include=[src_abs]` 绮剧‘閿佸畾琚祴鏂囦欢锛岄伩鍏嶆妸鍚岀洰褰曞叾浠栨枃浠讹紙鍙兘鍚?
      璇硶閿欒鐨勬牱渚嬫枃浠讹級涔熺撼鍏ヨВ鏋愯€屽鑷?coverage 涓柇
    - 鍦ㄥ悓涓€杩涚▼鍐?`cov.start()` 鈫?`pytest.main()` 鈫?`cov.stop()`锛岀粫杩?
      `coverage run -m pytest` 鐨勫瓙杩涚▼鏂囦欢鍙戠幇姝т箟锛屽綊鍥犳渶鍑嗙‘

    杩斿洖 (executed_set, missing_set) 鎴?None锛堝け璐ユ椂鐢辫皟鐢ㄦ柟闄嶇骇锛夈€?
    """
    try:
        import coverage
        cov = coverage.Coverage(include=[src_abs])
        cov.start()
        try:
            import pytest
        except ImportError:
            cov.stop()
            return None
        rc = pytest.main([tests_path, "-q", "-p", "no:cacheprovider"])
        cov.stop()
        data = cov.get_data()
        # normcase 锛圵indows 锛?
        key = None
        for mf in data.measured_files():
            if os.path.normcase(os.path.abspath(mf)) == os.path.normcase(src_abs):
                key = mf
                break
        if key is None:
            return None
        executed = set(data.lines(key) or [])
        missing = set()
        try:
            missing = set(cov.analysis2(key)[3])
        except Exception:
            missing = set()
        return executed, missing
    except Exception:
        return None


def classify(units, mode, src_abs, tests_path, test_src, out_dir):
    """
    杩斿洖 (covered_map, ratio_map, mode_used)
    covered_map: qual -> bool
    ratio_map:   qual -> float (0~1)
    """
    cov_result = None
    mode_used = mode
    if mode in ("auto", "coverage"):
        cov_result = coverage_run(src_abs, tests_path, out_dir)
        if cov_result is not None:
            mode_used = "coverage"
        elif mode == "coverage":
            # coverage  鈫?锛?
            mode_used = "coverage(澶辫触鈫掑叏鐩插尯)"

    if cov_result is not None:
        executed, _ = cov_result
        covered = {}
        ratio = {}
        for u in units:
            # 锛?def 锛坕mport 锛岋級
            body = set(range(u["start"], u["end"] + 1))
            if u["end"] > u["start"]:
                body.discard(u["start"])
            if body:
                hit = body & executed
                covered[u["qual"]] = len(hit) > 0
                ratio[u["qual"]] = len(hit) / max(1, len(body))
            else:
                # 锛歞ef  body 锛?import 锛?
                # 
                name_hit = u["name"] in test_src
                covered[u["qual"]] = name_hit
                ratio[u["qual"]] = 1.0 if name_hit else 0.0
        return covered, ratio, mode_used

    # 锛?锛堬級
    mode_used = "static(鍚嶇О鍖归厤)" if mode_used != "coverage(澶辫触鈫掑叏鐩插尯)" else mode_used
    covered = {}
    ratio = {}
    for u in units:
        token = u["name"]
        covered[u["qual"]] = token in test_src
        ratio[u["qual"]] = 1.0 if token in test_src else 0.0
    return covered, ratio, mode_used


# --------------------------------------------------------------------------- #
# 锛?generate_tests.build_test_file锛?
# --------------------------------------------------------------------------- #
def build_gap_targets(units, tree, gap_quals):
    targets = []
    # 
    for u in units:
        if u["kind"] == "func" and u["qual"] in gap_quals:
            targets.append(gen.make_func_target(u["node"]))
    # 锛?parent
    seen = set()
    for u in units:
        if u["kind"] == "method" and u["qual"] in gap_quals:
            parent = u["parent"]
            if parent in seen:
                continue
            seen.add(parent)
            class_node = next((n for n in tree.body
                               if isinstance(n, ast.ClassDef) and n.name == parent), None)
            if class_node is None:
                continue
            ct = gen.make_class_target(class_node)
            ct["methods"] = [m for m in ct["methods"]
                             if ("%s.%s" % (parent, m["name"])) in gap_quals]
            targets.append(ct)
    return targets


# --------------------------------------------------------------------------- #
# &
# --------------------------------------------------------------------------- #
def priority_score(u, ratio):
    return (1.0 - ratio) * (1.0 + 0.15 * u["branches"]) * u["exposure"]


def prio_tag(score):
    if score >= 2.0:
        return "馃敶 楂?
    if score >= 1.0:
        return "馃煛 涓?
    return "馃煝 浣?


def reason_text(u, ratio):
    parts = ["瑕嗙洊鐜?%.0f%%" % (ratio * 100)]
    if u["branches"] >= 3:
        parts.append("鍒嗘敮澶嶆潅(%d)" % u["branches"])
    elif u["branches"] > 0:
        parts.append("鍚?d涓垎鏀? % u["branches"])
    else:
        parts.append("鏃犲垎鏀?)
    parts.append("鍏紑API" if u["exposure"] >= 1.0 else "鍐呴儴鏂规硶")
    return "锛?.join(parts)


def write_report(path, stats, units, covered_map, ratio_map, blind_sorted,
                 gap_test_rel, mode_used, no_tests, tests_path):
    L = []
    L.append("# 娴嬭瘯瑕嗙洊鐜囩洸鍖哄垎鏋愭姤鍛婏紙pytest-forge 路 鐩插尯鍒嗘瀽锛?)
    L.append("")
    L.append("> 绉戝ぇ璁 AI 鏁版嵁鏅鸿兘鍒嗘瀽涓庡簲鐢?Skill 寮€鍙戞寫鎴樿禌 路 鏂瑰悜浜屻€屾祴璇曚笌璐ㄩ噺淇濋殰銆?)
    L.append("")
    L.append("## 姒傝")
    L.append("")
    L.append("- **婧愮爜鏂囦欢**锛歚%s`" % stats["input"])
    L.append("- **鐜版湁娴嬭瘯**锛?s" % ("`%s`" % tests_path if tests_path else "鏈彁渚涳紙鍏ㄩ儴瑙嗕负鐩插尯锛?))
    L.append("- **鍒ゅ畾妯″紡**锛?s" % mode_used)
    L.append("- **鍙祴璇曞崟鍏冩暟**锛?d锛堝嚱鏁?%d / 绫绘柟娉?%d锛?
             % (stats["units"], stats["funcs"], stats["methods"]))
    cov_n = sum(1 for u in units if covered_map[u["qual"]])
    L.append("- **宸茶鐩?*锛?d銆€**鏈鐩栵紙鐩插尯锛?*锛?d銆€**鍗曞厓瑕嗙洊鐜?*锛?.0f%%"
             % (cov_n, len(units) - cov_n, (cov_n / max(1, len(units)) * 100)))
    L.append("- **鏄惁鎴柇**锛?s"
             % ("鏄紙瓒呰繃 %d 涓紝宸插彇鍓?%d锛? % (gen.MAX_FUNCS, gen.MAX_FUNCS) if stats["truncated"] else "鍚?))
    L.append("")

    # 
    L.append("## 閫愰」瑕嗙洊鏄庣粏")
    L.append("")
    L.append("| 鍗曞厓 | 绫诲瀷 | 琛屽尯闂?| 鍒嗘敮鏁?| 瑕嗙洊鐜?| 鐘舵€?|")
    L.append("|------|------|--------|--------|--------|------|")
    for u in units:
        typ = "鍑芥暟" if u["kind"] == "func" else "鏂规硶"
        rng = "%d-%d" % (u["start"], u["end"])
        st = "鉁?宸茶鐩? if covered_map[u["qual"]] else "鈿狅笍 鐩插尯"
        L.append("| `%s` | %s | %s | %d | %.0f%% | %s |"
                 % (u["qual"], typ, rng, u["branches"], ratio_map[u["qual"]] * 100, st))
    L.append("")

    # 
    L.append("## 鐩插尯琛ユ祴浼樺厛绾э紙鎸夐闄╂帓搴忥級")
    L.append("")
    if not blind_sorted:
        L.append("馃帀 鏈彂鐜扮洸鍖猴紝鐜版湁娴嬭瘯宸茶鐩栧叏閮ㄥ彲娴嬭瘯鍗曞厓銆?)
    else:
        L.append("| 浼樺厛绾?| 鍗曞厓 | 椋庨櫓绛夌骇 | 璇勫垎 | 璇存槑 |")
        L.append("|--------|------|----------|------|------|")
        for i, u in enumerate(blind_sorted, 1):
            L.append("| #%d | `%s` | %s | %.2f | %s |"
                     % (i, u["qual"], prio_tag(u["score"]), u["score"],
                        reason_text(u, ratio_map[u["qual"]])))
        L.append("")
        L.append("> 璇勫垎 = (1 鈭?瑕嗙洊鐜? 脳 (1 + 0.15脳鍒嗘敮鏁? 脳 鍏紑搴︽潈閲嶏紙鍏紑 1.0 / 鍐呴儴 0.4锛夈€?
                 "鍒嗗€艰秺楂樿秺搴斾紭鍏堣ˉ娴嬨€?)
    L.append("")

    # 
    L.append("## 缂哄彛娴嬭瘯楠ㄦ灦")
    L.append("")
    if gap_test_rel:
        L.append("- 宸茶嚜鍔ㄧ敓鎴愬彲鐩存帴杩愯鐨勭己鍙ｉ鏋讹細`%s`" % gap_test_rel)
        L.append("- 璇ユ枃浠跺鐢ㄤ笌 `generate_tests.py` 鐩稿悓鐨勯鏋舵ā鏉匡紙happy + boundary 鍐掔儫娴嬭瘯锛夛紝"
                 "寮€鍙戣€呭彧闇€鍦?`TODO` 澶勮ˉ鍏呬笟鍔℃柇瑷€鍗冲彲銆?)
    else:
        L.append("- 鏃犵洸鍖猴紝鏃犻渶鐢熸垚缂哄彛楠ㄦ灦銆?)
    L.append("")

    L.append("## 椴佹鎬ц鏄?)
    L.append("")
    L.append("- 瑕嗙洊鍒ゅ畾浼樺厛閲囩敤 `coverage.py` 瀹炴祴琛岃鐩栵紱涓嶅彲鐢ㄦ椂鑷姩闄嶇骇涓洪潤鎬佸悕绉板尮閰嶏紝缁濅笉宕╂簝")
    L.append("- 鏈彁渚涙祴璇曟枃浠舵椂锛屽叏閮ㄥ崟鍏冨垽涓虹洸鍖哄苟鎻愮ず鍙敤 `generate_tests.py` 浠庨浂鐢熸垚")
    L.append("- 缂哄彛楠ㄦ灦澶嶇敤 `generate_tests.build_test_file`锛屼繚璇佽娉曞悎娉曘€佸彲杩愯銆佸鍏ュけ璐ュ垯 skip")
    L.append("- 鍗曟枃浠跺崟鍏冧笂闄?%d锛岃秴鍑烘埅鏂苟鍦ㄦ湰鎶ュ憡鎻愮ず" % gen.MAX_FUNCS)
    L.append("")
    L.append("---")
    L.append("鐢熸垚鏃堕棿锛?s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# --------------------------------------------------------------------------- #
#  Main flow

# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="娴嬭瘯瑕嗙洊鐜囩洸鍖哄垎鏋愬櫒")
    ap.add_argument("-i", "--input", required=True, help="Python 婧愮爜鏂囦欢璺緞")
    ap.add_argument("-t", "--tests", default=None,
                    help="鐜版湁娴嬭瘯鏂囦欢鎴栫洰褰曪紙鍙€夛紱鐪佺暐鍒欏叏閮ㄨ涓虹洸鍖猴級")
    ap.add_argument("-o", "--out", default="./coverage_report", help="杈撳嚭鐩綍锛堥粯璁?./coverage_report锛?)
    ap.add_argument("--mode", choices=["auto", "coverage", "static"], default="auto",
                    help="瑕嗙洊鍒ゅ畾妯″紡锛堥粯璁?auto锛氫紭鍏?coverage锛屽け璐ラ檷绾?static锛?)
    args = ap.parse_args()

    src_path = os.path.abspath(args.input)
    if not os.path.isfile(src_path):
        print("[ERROR] 杈撳叆鏂囦欢涓嶅瓨鍦? %s" % src_path, file=sys.stderr)
        return 2

    # -t锛氾紝 test_<>.py
    tests_path = os.path.abspath(args.tests) if args.tests else None
    no_tests = False
    if not tests_path:
        stem = os.path.splitext(os.path.basename(src_path))[0]
        cand = os.path.join(os.path.dirname(src_path), "test_%s.py" % stem)
        if os.path.isfile(cand):
            tests_path = cand
        else:
            no_tests = True

    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    report_path = os.path.join(args.out, "report.md")
    gap_test_path = os.path.join(args.out, "test_%s_gaps.py" % stem)

    stats = {"input": src_path, "units": 0, "funcs": 0, "methods": 0,
             "truncated": False}

    try:
        source, enc = gen.read_source(src_path)
    except Exception as e:
        print("[ERROR] 璇诲彇婧愮爜澶辫触: %s" % e, file=sys.stderr)
        return 2

    try:
        tree = ast.parse(source, filename=src_path)
    except SyntaxError as e:
        # 锛?鈫?锛?
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 娴嬭瘯瑕嗙洊鐜囩洸鍖哄垎鏋愭姤鍛奬n\n"
                    "> 婧愮爜瀛樺湪璇硶閿欒锛堣 %s锛夛細%s銆傛棤娉曡В鏋愭彁鍙栧崟鍏冿紝璇峰厛淇婧愮爜銆俓n"
                    % (e.lineno, e.msg))
        print("[ERROR] 婧愮爜璇硶閿欒锛屾棤娉曞垎鏋? %s" % e, file=sys.stderr)
        return 2

    units = extract_units(tree)
    if len(units) > gen.MAX_FUNCS:
        units = units[:gen.MAX_FUNCS]
        stats["truncated"] = True
    stats["units"] = len(units)
    stats["funcs"] = sum(1 for u in units if u["kind"] == "func")
    stats["methods"] = sum(1 for u in units if u["kind"] == "method")

    test_files = [] if no_tests else find_test_files(tests_path)
    test_src = read_test_source(test_files)

    try:
        covered_map, ratio_map, mode_used = classify(
            units, args.mode, src_path, tests_path, test_src, args.out)
    except Exception as e:
        print("[WARN] 瑕嗙洊鍒ゅ畾寮傚父锛岄檷绾т负鍏ㄧ洸鍖? %s" % e, file=sys.stderr)
        covered_map = {u["qual"]: False for u in units}
        ratio_map = {u["qual"]: 0.0 for u in units}
        mode_used = "寮傚父鈫掑叏鐩插尯"

    gap_quals = set(u["qual"] for u in units if not covered_map[u["qual"]])
    blind = [u for u in units if not covered_map[u["qual"]]]
    for u in blind:
        u["score"] = priority_score(u, ratio_map[u["qual"]])
    blind_sorted = sorted(blind, key=lambda u: -u["score"])

    # 锛堬級
    gap_test_rel = None
    if gap_quals:
        try:
            gap_targets = build_gap_targets(units, tree, gap_quals)
            gen.build_test_file(gap_targets, src_path, gap_test_path)
            gap_test_rel = os.path.basename(gap_test_path)
        except Exception as e:
            print("[WARN] 缂哄彛楠ㄦ灦鐢熸垚寮傚父: %s" % traceback.format_exc(), file=sys.stderr)
            gap_test_rel = None

    write_report(report_path, stats, units, covered_map, ratio_map, blind_sorted,
                 gap_test_rel, mode_used, no_tests, tests_path)

    print("[OK] 鎶ュ憡: %s" % report_path)
    if gap_test_rel:
        print("[OK] 缂哄彛楠ㄦ灦: %s" % gap_test_path)
    print("[INFO] 鍗曞厓 %d锛堝嚱鏁?%d / 鏂规硶 %d锛夛綔宸茶鐩?%d锝滅洸鍖?%d锝滄ā寮?%s"
          % (stats["units"], stats["funcs"], stats["methods"],
             sum(1 for u in units if covered_map[u["qual"]]),
             len(units) - sum(1 for u in units if covered_map[u["qual"]]),
             mode_used))
    return 0


if __name__ == "__main__":
    sys.exit(main())
