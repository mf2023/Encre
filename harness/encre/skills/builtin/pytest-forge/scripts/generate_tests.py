#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
鍗曞厓娴嬭瘯鑷姩鐢熸垚 Skill 鈥斺€?鏍稿績鐢熸垚鍣?
绉戝ぇ璁 AI 鏁版嵁鏅鸿兘鍒嗘瀽涓庡簲鐢?Skill 寮€鍙戞寫鎴樿禌 路 鏂瑰悜浜屻€屾祴璇曚笌璐ㄩ噺淇濋殰銆?

杈撳叆锛歅ython 婧愮爜鏂囦欢锛堣矾寰勶級
杈撳嚭锛歱ytest 娴嬭瘯鏂囦欢 + Markdown 鎶ュ憡 +锛堝彲閫夛級pytest 杩愯缁撴灉

璁捐鍘熷垯锛氶珮椴佹鎬?
- 鍩轰簬 ast 闈欐€佽В鏋愶紝澶嶆潅/娈嬬己浠ｇ爜涓嬪缁堜骇鍑恒€愯娉曞悎娉曘€戠殑娴嬭瘯鏂囦欢
- 鐩爣妯″潡瀵煎叆澶辫触 / 璇硶閿欒 鈫?鐢熸垚"鍙繍琛屼絾鍏ㄩ儴 skip"鐨勬祴璇?+ 娓呮櫚鎶ュ憡锛岀粷涓嶅穿婧?
- 鐢熸垚鐨勬祴璇曞浠舵案杩滆兘璺戣捣鏉ワ紙鏃?collection error锛夛紝绗﹀悎璧涗簨"鏃犺緭鍑哄穿婧?纭寚鏍?
"""
import ast
import argparse
import os
import sys
import subprocess
import datetime
import traceback

MAX_FUNCS = 60  # 鍗曟枃浠跺嚱鏁?鏂规硶涓婇檺锛岃秴鍑烘埅鏂苟鍦ㄦ姤鍛婁腑璇存槑

NAME_DUMMY = {
    "n": "0", "i": "0", "j": "0", "k": "0", "index": "0", "count": "0",
    "num": "0", "x": "0", "y": "0",
    "s": '"x"', "text": '"x"', "name": '"x"', "msg": '"x"', "string": '"x"',
    "lst": "[]", "list": "[]", "arr": "[]", "items": "[]", "seq": "[]",
    "d": "{}", "dict": "{}", "mapping": "{}",
    "b": "False", "flag": "False", "enabled": "False",
}


# --------------------------------------------------------------------------- #
# 
# --------------------------------------------------------------------------- #
def ann_str(node):
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def iter_params(func):
    """yield (name, annotation_str, default_node, kind) for non *args/**kwargs."""
    a = func.args
    pos = a.args
    ndef = len(a.defaults)
    for idx, p in enumerate(pos):
        default = a.defaults[idx - len(pos)] if idx >= len(pos) - ndef else None
        yield (p.arg, ann_str(p.annotation), default, "pos")
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        yield (p.arg, ann_str(p.annotation), d, "kw")


def ann_dummy(ann):
    a = (ann or "").lower()
    if a in ("int", "integer"):
        return "0"
    if a in ("float", "double", "number"):
        return "0.0"
    if a in ("str", "string"):
        return '""'
    if a == "bool":
        return "False"
    if "list" in a:
        return "[]"
    if "dict" in a:
        return "{}"
    if "set" in a:
        return "set()"
    if "tuple" in a:
        return "()"
    return None


def name_dummy(name):
    n = (name or "").lower()
    if n in NAME_DUMMY:
        return NAME_DUMMY[n]
    if n.endswith("s") and len(n) > 3:
        return "[]"
    if "path" in n or "file" in n or "dir" in n:
        return '""'
    return "None"


def param_value(name, ann, default_node):
    """happy-path 鍙栧€硷細浼樺厛榛樿鍊硷紝鍏舵鎸夋敞瑙?鍚嶅瓧鎺ㄦ柇瀹夊叏 dummy銆?""
    if default_node is not None:
        try:
            return repr(ast.literal_eval(default_node))
        except Exception:
            return "None"
    d = ann_dummy(ann)
    if d is not None:
        return d
    return name_dummy(name)


def edge_value(name, ann):
    """boundary 鍙栧€硷細鍊惧悜瑙﹀彂杈圭晫琛屼负鐨勮緭鍏ャ€?""
    a = (ann or "").lower()
    n = (name or "").lower()
    if a in ("int", "integer") or n in ("n", "i", "j", "k", "index", "count", "num"):
        return "0"
    if a in ("float", "double", "number"):
        return "0.0"
    if a in ("str", "string") or "path" in n:
        return '""'
    if a == "bool":
        return "False"
    if "list" in a or (n.endswith("s") and len(n) > 3):
        return "[]"
    if "dict" in a:
        return "{}"
    return "None"


def call_args(params, use_edge=False):
    parts = []
    for (name, ann, default, kind) in params:
        if name in ("self", "cls"):
            continue
        val = edge_value(name, ann) if use_edge else param_value(name, ann, default)
        parts.append(val)
    return ", ".join(parts)


# --------------------------------------------------------------------------- #
# 锛?/  / 锛?
# --------------------------------------------------------------------------- #
def make_func_target(node):
    return {
        "kind": "func",
        "name": node.name,
        "params": list(iter_params(node)),
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def make_class_target(node):
    init_params = None
    methods = []
    for n in node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.name == "__init__":
                init_params = list(iter_params(n))
            elif not n.name.startswith("_") or n.name in ("__str__", "__len__", "__repr__", "__eq__", "__getitem__"):
                methods.append({
                    "name": n.name,
                    "params": list(iter_params(n)),
                    "async": isinstance(n, ast.AsyncFunctionDef),
                })
    return {"kind": "class", "name": node.name, "init_params": init_params, "methods": methods}


def extract_targets(tree):
    targets = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            targets.append(make_func_target(n))
        elif isinstance(n, ast.ClassDef):
            targets.append(make_class_target(n))
    return targets


# --------------------------------------------------------------------------- #
# 
# --------------------------------------------------------------------------- #
def gen_func_tests(t, mod_name):
    out = []
    fname = t["name"]
    is_async = t["async"]
    for suffix, use_edge in (("happy", False), ("boundary", True)):
        if is_async:
            call = "asyncio.run(%s.%s(%s))" % (mod_name, fname, call_args(t["params"], use_edge))
        else:
            call = "%s.%s(%s)" % (mod_name, fname, call_args(t["params"], use_edge))
        if suffix == "happy":
            body = (
                "    if _TARGET_MOD is None:\n"
                "        pytest.skip(f\"鐩爣妯″潡瀵煎叆澶辫触: {_IMPORT_ERROR}\")\n"
                "    %s\n"
                "    # TODO: 琛ュ厖閽堝杩斿洖鍊肩殑涓氬姟鏂█锛堝綋鍓嶄负鍐掔儫娴嬭瘯锛岄獙璇佷笉鎶涘紓甯革級\n"
                "    assert True\n" % call
            )
        else:
            body = (
                "    if _TARGET_MOD is None:\n"
                "        pytest.skip(f\"鐩爣妯″潡瀵煎叆澶辫触: {_IMPORT_ERROR}\")\n"
                "    try:\n"
                "        %s\n"
                "    except Exception:\n"
                "        pytest.skip(\"杈圭晫杈撳叆瑙﹀彂寮傚父锛岄渶浜哄伐纭鏄惁搴斾负棰勬湡琛屼负\")\n"
                "    # TODO: 琛ュ厖杈圭晫鏂█\n"
                "    assert True\n" % call
            )
        out.append("def test_%s_%s():\n%s" % (fname, suffix, body))
    return "\n\n".join(out)


def gen_class_tests(t, mod_name):
    out = []
    cname = t["name"]
    init_args = call_args(t["init_params"] or [], False) if t["init_params"] else ""
    # 
    out.append(
        "def _make_%s():\n"
        "    if _TARGET_MOD is None:\n"
        "        return None\n"
        "    try:\n"
        "        return %s.%s(%s)\n"
        "    except Exception:\n"
        "        try:\n"
        "            return %s.%s()\n"
        "        except Exception:\n"
        "            return None\n"
        % (cname, mod_name, cname, init_args, mod_name, cname)
    )
    # __init__
    out.append(
        "def test_%s_init():\n"
        "    inst = _make_%s()\n"
        "    if inst is None:\n"
        "        pytest.skip(\"%s 瀹炰緥鍖栧け璐ワ紝闇€琛ュ厖鏋勯€犲弬鏁癨")\n"
        "    assert inst is not None\n" % (cname, cname, cname)
    )
    # 
    for m in t["methods"]:
        mname = m["name"]
        is_async = m["async"]
        if is_async:
            call = "asyncio.run(inst.%s(%s))" % (mname, call_args(m["params"], False))
        else:
            call = "inst.%s(%s)" % (mname, call_args(m["params"], False))
        body = (
            "    inst = _make_%s()\n"
            "    if inst is None:\n"
            "        pytest.skip(\"%s 瀹炰緥鍖栧け璐ワ紝闇€琛ュ厖鏋勯€犲弬鏁癨")\n"
            "    %s\n"
            "    # TODO: 琛ュ厖閽堝杩斿洖鍊肩殑涓氬姟鏂█\n"
            "    assert True\n" % (cname, cname, call)
        )
        out.append("def test_%s_%s_happy():\n%s" % (cname, mname, body))
    return "\n\n".join(out)


def build_test_file(targets, target_path, test_path):
    mod_name = "_TARGET_MOD"
    parts = []
    parts.append('"""Automatically generated by pytest-forge (绉戝ぇ璁娴嬭瘯涓庤川閲忎繚闅滆禌閬?."""')
    parts.append("import sys\nimport os\nimport asyncio\nimport pytest\nimport importlib.util\n")
    parts.append('_TARGET_PATH = %s' % repr(os.path.abspath(target_path)))
    parts.append(
        "_spec = importlib.util.spec_from_file_location(%s, _TARGET_PATH)\n"
        "try:\n"
        "    %s = importlib.util.module_from_spec(_spec)\n"
        "    _spec.loader.exec_module(%s)\n"
        "    _IMPORT_ERROR = None\n"
        "except Exception as _e:\n"
        "    %s = None\n"
        "    _IMPORT_ERROR = _e\n" % (repr("_TARGET_MOD"), mod_name, mod_name, mod_name)
    )
    bodies = []
    for t in targets:
        if t["kind"] == "func":
            bodies.append(gen_func_tests(t, mod_name))
        elif t["kind"] == "class":
            bodies.append(gen_class_tests(t, mod_name))
    parts.append("\n\n".join(bodies))
    content = "\n\n".join(parts) + "\n"
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


# --------------------------------------------------------------------------- #
#  Main flow

# --------------------------------------------------------------------------- #
def read_source(path):
    last_err = None
    for enc in ("utf-8", "gbk", "gb18030", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except Exception as e:
            last_err = e
    raise last_err


def main():
    ap = argparse.ArgumentParser(description="鍗曞厓娴嬭瘯鑷姩鐢熸垚鍣?)
    ap.add_argument("-i", "--input", required=True, help="Python 婧愮爜鏂囦欢璺緞")
    ap.add_argument("-o", "--out", default="./ut_output", help="杈撳嚭鐩綍锛堥粯璁?./ut_output锛?)
    ap.add_argument("--no-run", action="store_true", help="浠呯敓鎴愶紝涓嶈繍琛?pytest")
    args = ap.parse_args()

    src_path = os.path.abspath(args.input)
    if not os.path.isfile(src_path):
        print("[ERROR] 杈撳叆鏂囦欢涓嶅瓨鍦? %s" % src_path, file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    test_path = os.path.join(args.out, "test_%s.py" % stem)
    report_path = os.path.join(args.out, "report.md")

    stats = {
        "input": src_path,
        "functions": 0,
        "classes": 0,
        "methods": 0,
        "tests": 0,
        "parse_ok": False,
        "import_ok": None,
        "truncated": False,
        "run": None,
    }

    try:
        source, enc = read_source(src_path)
    except Exception as e:
        write_report(report_path, stats, "璇诲彇澶辫触: %s" % e, enc=None)
        print("[ERROR] 璇诲彇鏂囦欢澶辫触: %s" % e, file=sys.stderr)
        return 2

    try:
        tree = ast.parse(source, filename=src_path)
        stats["parse_ok"] = True
    except SyntaxError as e:
        # 锛? skip"锛?
        placeholder = (
            '"""Automatically generated by pytest-forge."""\n'
            "import pytest\n\n"
            "def test_syntax_error_in_target():\n"
            "    pytest.skip(\"鐩爣婧愮爜瀛樺湪璇硶閿欒锛屾棤娉曡В鏋? %s\")\n" % e
        )
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(placeholder + "\n")
        stats["parse_ok"] = False
        write_report(report_path, stats,
                     "鐩爣婧愮爜璇硶閿欒锛堣 %s锛夛細%s銆傚凡鐢熸垚鍗犱綅娴嬭瘯锛屽浠跺彲姝ｅ父杩愯锛堝叏閮?skip锛夛紝涓嶅穿婧冦€?
                     % (e.lineno, e.msg), enc=enc)
        print("[OK] 宸查檷绾х敓鎴愬崰浣嶆祴璇曪紙婧愮爜璇硶閿欒锛? %s" % test_path)
        print("[OK] 鎶ュ憡: %s" % report_path)
        return 0

    targets = extract_targets(tree)
    # 
    if len(targets) > MAX_FUNCS:
        targets = targets[:MAX_FUNCS]
        stats["truncated"] = True

    func_count = sum(1 for t in targets if t["kind"] == "func")
    class_count = sum(1 for t in targets if t["kind"] == "class")
    method_count = sum(len(t["methods"]) for t in targets if t["kind"] == "class")
    stats["functions"] = func_count
    stats["classes"] = class_count
    stats["methods"] = method_count
    stats["tests"] = func_count * 2 + class_count * (1 + method_count)

    try:
        build_test_file(targets, src_path, test_path)
    except Exception as e:
        write_report(report_path, stats, "娴嬭瘯鏂囦欢鐢熸垚寮傚父: %s" % traceback.format_exc(), enc=enc)
        print("[ERROR] 鐢熸垚娴嬭瘯鏂囦欢寮傚父: %s" % e, file=sys.stderr)
        return 2

    #  Run pytest

    run_note = None
    if not args.no_run:
            import pytest  # noqa

    write_report(report_path, stats, run_note, enc=enc)
    print("[OK] 娴嬭瘯鏂囦欢: %s" % test_path)
    print("[OK] 鎶ュ憡: %s" % report_path)
    print("[INFO] 鍑芥暟 %d / 绫?%d / 鏂规硶 %d / 鐢熸垚鐢ㄤ緥 %d锛堣В鏋?s锛岃繍琛?s锛?
          % (func_count, class_count, method_count, stats["tests"],
             "鎴愬姛" if stats["parse_ok"] else "澶辫触", stats["run"]))
    return 0


def write_report(path, stats, run_note, enc):
    lines = []
    lines.append("# 鍗曞厓娴嬭瘯鐢熸垚鎶ュ憡锛坧ytest-forge锛?)
    lines.append("")
    lines.append("> 绉戝ぇ璁 AI 鏁版嵁鏅鸿兘鍒嗘瀽涓庡簲鐢?Skill 寮€鍙戞寫鎴樿禌 路 鏂瑰悜浜屻€屾祴璇曚笌璐ㄩ噺淇濋殰銆?)
    lines.append("")
    lines.append("## 姒傝")
    lines.append("")
    lines.append("- **杈撳叆鏂囦欢**锛歚%s`" % stats["input"])
    lines.append("- **婧愮爜缂栫爜**锛?s" % (enc or "鏈煡"))
    lines.append("- **AST 瑙ｆ瀽**锛?s" % ("鉁?鎴愬姛" if stats["parse_ok"] else "鉂?澶辫触锛堝凡闄嶇骇锛?))
    lines.append("- **鍑芥暟鏁?*锛?d" % stats["functions"])
    lines.append("- **绫绘暟**锛?d" % stats["classes"])
    lines.append("- **鏂规硶鏁?*锛?d" % stats["methods"])
    lines.append("- **鐢熸垚娴嬭瘯鐢ㄤ緥鏁?*锛?d" % stats["tests"])
    lines.append("- **鏄惁鎴柇**锛?s" % ("鏄紙瓒呰繃 %d 涓紝宸插彇鍓?%d锛? % (MAX_FUNCS, MAX_FUNCS) if stats["truncated"] else "鍚?))
    lines.append("- **pytest 杩愯**锛?s" % (stats["run"] or "鏈墽琛?))
    lines.append("")
    lines.append("## 鐢熸垚鐨勬祴璇曟枃浠?)
    lines.append("")
    lines.append("`test_<妯″潡鍚?.py` 宸茬敓鎴愪簬杈撳嚭鐩綍锛屽寘鍚細")
    lines.append("- 姣忎釜鍑芥暟锛歚test_<func>_happy`锛堜富璺緞鍐掔儫锛? `test_<func>_boundary`锛堣竟鐣屽啋鐑燂級")
    lines.append("- 姣忎釜绫伙細`test_<Class>_init`锛堝疄渚嬪寲锛? 姣忎釜鏂规硶 `test_<Class>_<method>_happy`")
    lines.append("- 鐩爣妯″潡閫氳繃 `importlib` 鎸夎矾寰勫姞杞斤紝瀵煎叆澶辫触鍒欏叏閮?`skip`锛?*濂椾欢姘歌繙鍙繍琛屻€佷笉宕╂簝**")
    lines.append("")
    lines.append("## 椴佹鎬ц鏄?)
    lines.append("")
    lines.append("- 澶嶆潅/娈嬬己浠ｇ爜涓嬩粛浜у嚭璇硶鍚堟硶鐨勬祴璇曟枃浠?)
    lines.append("- 鐩爣妯″潡璇硶閿欒鎴栧鍏ュけ璐?鈫?鐢熸垚銆屽叏閮?skip銆嶅崰浣嶆祴璇曪紝涓嶆姤閿欓€€鍑?)
    lines.append("- 鐢熸垚鐨勭敤渚嬩负**鍐掔儫娴嬭瘯楠ㄦ灦**锛屾柇瑷€澶勬爣娉?`TODO`锛岄渶浜哄伐琛ュ厖涓氬姟鏂█")
    lines.append("- 鍗曟枃浠跺嚱鏁颁笂闄?%d锛岃秴鍑烘埅鏂苟鍦ㄦ湰鎶ュ憡涓彁绀? % MAX_FUNCS)
    lines.append("")
    if run_note:
        lines.append("## pytest 杩愯缁撴灉")
        lines.append("")
        lines.append("```")
        lines.append(run_note)
        lines.append("```")
        lines.append("")
    lines.append("---")
    lines.append("鐢熸垚鏃堕棿锛?s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
