#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Performance Analyzer Engine
鎬ц兘闄烽槺妫€娴嬪紩鎿?
"""

import re
from typing import Dict, List


class PerformanceAnalyzer:
    """鎬ц兘鍒嗘瀽鍣?""

    def analyze(self, code: str, language: str) -> List[Dict]:
        """鎵ц鎬ц兘鍒嗘瀽"""
        issues = []

        issues.extend(self._check_time_complexity(code, language))
        issues.extend(self._check_n_plus_one(code, language))
        issues.extend(self._check_memory_leak(code, language))
        issues.extend(self._check_string_concat(code, language))
        issues.extend(self._check_blocking_io(code, language))
        issues.extend(self._check_redundant_computation(code, language))
        issues.extend(self._check_sql_performance(code, language))

        return issues

    def _check_time_complexity(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ユ椂闂村鏉傚害闂"""
        issues = []

        #  Detect nested loops

        lines = code.split("\n")
        loop_stack = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 
            if re.match(r"^(for|while)\s+", stripped):
                indent = len(line) - len(line.lstrip())
                loop_stack.append({"line": i + 1, "indent": indent})
            # 锛堬細锛?
            elif loop_stack and stripped:
                indent = len(line) - len(line.lstrip())
                while loop_stack and indent <= loop_stack[-1]["indent"]:
                    loop_stack.pop()

            # 3
            if len(loop_stack) >= 3:
                issues.append({
                    "rule": "宓屽寰幆杩囨繁",
                    "severity": "涓瓑",
                    "line": loop_stack[0]["line"],
                    "code": lines[loop_stack[0]["line"] - 1].strip()[:60],
                    "description": f"妫€娴嬪埌{len(loop_stack)}灞傚祵濂楀惊鐜紝鏃堕棿澶嶆潅搴﹀彲鑳戒负O(n^{len(loop_stack)})",
                    "fix": "鑰冭檻浣跨敤鍝堝笇琛ㄣ€佹帓搴?鍙屾寚閽堛€佸垎娌荤瓑绠楁硶浼樺寲锛屾垨鎻愬彇寰幆鍐呬笉鍙橀噺",
                    "example": "# 鐢ㄥ瓧鍏稿皢O(n^2)闄嶄负O(n)\nlookup = {x: i for i, x in enumerate(arr)}"
                })
                loop_stack = []  # 閬垮厤閲嶅鎶ュ憡

        # 锛堬級
        if language == "python":
            for match in re.finditer(r"def\s+(\w+)\s*\([^)]*\).*?:.*?\n(?:.*\n)*?\s+\1\s*\(", code):
                func_name = match.group(1)
                # lru_cachememo
                func_block = code[match.start():match.start() + 500]
                if "lru_cache" not in func_block and "memo" not in func_block:
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "閫掑綊鏃犺蹇嗗寲",
                        "severity": "涓瓑",
                        "line": line_num,
                        "code": f"def {func_name}(...)",
                        "description": "妫€娴嬪埌閫掑綊鍑芥暟浣嗘湭浣跨敤璁板繂鍖栵紝鍙兘瀵艰嚧鎸囨暟绾ф椂闂村鏉傚害",
                        "fix": "浣跨敤functools.lru_cache鎴栨墜鍔ㄥ疄鐜拌蹇嗗寲瀛楀吀",
                        "example": "@functools.lru_cache(maxsize=None)\ndef fib(n): ..."
                    })

        return issues

    def _check_n_plus_one(self, code: str, language: str) -> List[Dict]:
        """妫€鏌+1鏌ヨ"""
        issues = []

        if language == "python":
            # 
            patterns = [
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\.filter\s*\(",
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\.objects\.get",
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+session\.query",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.DOTALL):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "N+1鏌ヨ",
                        "severity": "涓ラ噸",
                        "line": line_num,
                        "code": match.group(0).split("\n")[0][:60],
                        "description": "妫€娴嬪埌寰幆鍐呮墽琛屾暟鎹簱鏌ヨ锛屼骇鐢烴+1鏌ヨ闂",
                        "fix": "浣跨敤select_related/prefetch_related锛圖jango锛夋垨join/eager load锛圫QLAlchemy锛?,
                        "example": "# Django\nusers = User.objects.prefetch_related('orders').all()\nfor user in users:\n    for order in user.orders.all(): ..."
                    })

        return issues

    def _check_memory_leak(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ュ唴瀛樻硠婕?""
        issues = []

        if language == "python":
            # 
            patterns = [
                r"(\w+)\s*=\s*\[\].*?\n(?:.*\n)*?\s+\1\.append",
                r"(\w+)\s*=\s*\{\}.*?\n(?:.*\n)*?\s+\1\[",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.DOTALL):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "鍐呭瓨绱Н",
                        "severity": "涓ラ噸",
                        "line": line_num,
                        "code": match.group(0).split("\n")[0][:60],
                        "description": "妫€娴嬪埌寰幆涓寔缁疮绉暟鎹埌鍒楄〃/瀛楀吀锛屽彲鑳藉鑷村唴瀛樻孩鍑?,
                        "fix": "浣跨敤鐢熸垚鍣▂ield浠ｆ浛鍒楄〃銆佸垎鎵瑰鐞嗐€佹垨瀹氭湡娓呯悊缂撳瓨",
                        "example": "# 浣跨敤鐢熸垚鍣╘ndef process_large_file():\n    with open('data.txt') as f:\n        for line in f:\n            yield process(line)"
                    })

        # 
        if language in ["javascript", "typescript"]:
            for match in re.finditer(r"setInterval\s*\(\s*function", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "瀹氭椂鍣ㄦ湭娓呯悊",
                    "severity": "涓瓑",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": "妫€娴嬪埌setInterval/setTimeout鍙兘鏈竻鐞嗭紝瀵艰嚧鍐呭瓨娉勬紡",
                    "fix": "鍦ㄧ粍浠跺嵏杞芥椂璋冪敤clearInterval/clearTimeout",
                    "example": "const timer = setInterval(...);\nreturn () => clearInterval(timer);"
                })

        return issues

    def _check_string_concat(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ュ瓧绗︿覆鎷兼帴闂"""
        issues = []

        if language == "python":
            #  寰幆涓璖tring鎷兼帴

            for match in re.finditer(r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\s*\+\s*=", code, re.DOTALL):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "寰幆鍐呭瓧绗︿覆鎷兼帴",
                    "severity": "杞诲井",
                    "line": line_num,
                    "code": match.group(0).split("\n")[-1].strip()[:60],
                    "description": "寰幆涓娇鐢?=鎷兼帴瀛楃涓诧紝鏃堕棿澶嶆潅搴(n^2)",
                    "fix": "浣跨敤鍒楄〃join鎴朣tringIO",
                    "example": "result = ''.join(items)  # 鎴?io.StringIO()"
                })

        return issues

    def _check_blocking_io(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ラ樆濉濱O"""
        issues = []

        blocking_patterns = {
            "python": ["time.sleep", "requests.get", "urllib.request"],
            "javascript": ["fs.readFileSync", "child_process.execSync"],
            "java": ["Thread.sleep", "FileInputStream"],
        }

        funcs = blocking_patterns.get(language, [])
        for func in funcs:
            for match in re.finditer(rf"\b{re.escape(func)}\s*\(", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "鍚屾闃诲璋冪敤",
                    "severity": "涓瓑",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": f"妫€娴嬪埌鍚屾闃诲璋冪敤{func}锛屽湪楂樺苟鍙戝満鏅細褰卞搷鎬ц兘",
                    "fix": "浣跨敤寮傛鏇夸唬鏂规锛坅syncio/aiohttp銆丳romise/async-await銆丯IO锛?,
                    "example": "# Python\nasync with aiohttp.ClientSession() as session:\n    async with session.get(url) as resp: ..."
                })

        return issues

    def _check_redundant_computation(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ラ噸澶嶈绠?""
        issues = []

        # 
        patterns = [
            r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+len\s*\(\s*\w+\s*\)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, code, re.DOTALL):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "寰幆鍐呴噸澶嶈绠?,
                    "severity": "杞诲井",
                    "line": line_num,
                    "code": match.group(0).split("\n")[-1].strip()[:60],
                    "description": "寰幆涓噸澶嶈绠椾笉鍙橀噺锛堝len()锛夛紝鍙彁鍙栧埌寰幆澶?,
                    "fix": "灏嗕笉鍙橀噺鎻愬彇鍒板惊鐜",
                    "example": "n = len(arr)\nfor i in range(n): ..."
                })

        return issues

    def _check_sql_performance(self, code: str, language: str) -> List[Dict]:
        """妫€鏌QL鎬ц兘闂"""
        issues = []

        # 
        slow_patterns = [
            (r"SELECT\s+\*\s+FROM", "SELECT * 鍏ㄥ瓧娈垫煡璇?),
            (r"OFFSET\s+\d{4,}", "澶FFSET娣卞害鍒嗛〉"),
            (r"LIKE\s+['\"]%", "鍓嶆ā绯奓IKE鏃犳硶浣跨敤绱㈠紩"),
            (r"NOT\s+IN\s*\(", "NOT IN鎬ц兘宸?),
        ]

        for pattern, desc in slow_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "SQL鎱㈡煡璇?,
                    "severity": "涓ラ噸",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": f"妫€娴嬪埌{desc}锛屽彲鑳藉鑷村叏琛ㄦ壂鎻忔垨鎬ц兘涓嬮檷",
                    "fix": "鎸囧畾鎵€闇€瀛楁銆佷娇鐢ㄨ鐩栫储寮曘€佹敼鐢ㄦ父鏍囧垎椤垫垨ES鎼滅储",
                    "example": "SELECT id, name FROM users WHERE created_at > ? ORDER BY id LIMIT ?"
                })

        return issues


# Public factory function for performance analysis
def analyze_performance(code: str, language: str) -> List[Dict]:
    analyzer = PerformanceAnalyzer()
    return analyzer.analyze(code, language)
