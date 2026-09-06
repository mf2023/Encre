#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Semantic Analyzer Engine
璇箟鍒嗘瀽寮曟搸锛堥€昏緫婕忔礊銆佸彲璇绘€с€佹灦鏋勶級
"""

import re
from typing import Dict, List


class SemanticAnalyzer:
    """璇箟鍒嗘瀽鍣?""

    def analyze(self, code: str, language: str) -> List[Dict]:
        """鎵ц璇箟鍒嗘瀽"""
        issues = []

        issues.extend(self._check_logic_bugs(code, language))
        issues.extend(self._check_readability(code, language))
        issues.extend(self._check_architecture(code, language))

        return issues

    def _check_logic_bugs(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ラ€昏緫婕忔礊"""
        issues = []
        lines = code.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # /None
            if language == "python":
                # 
                if re.search(r"\w+\.[\w\[\(]", stripped):
                    var = re.search(r"(\w+)\.", stripped)
                    if var:
                        var_name = var.group(1)
                        # 
                        prev_lines = "\n".join(lines[max(0, i-5):i])
                        if var_name not in prev_lines or f"if {var_name}" not in prev_lines:
                            if not any(safe in stripped for safe in ["try:", "except", "get(", "or ", "if "]):
                                issues.append({
                                    "rule": "绌哄€煎紩鐢ㄩ闄?,
                                    "severity": "涓瓑",
                                    "line": i + 1,
                                    "code": stripped[:60],
                                    "description": f"鍙橀噺'{var_name}'鍙兘涓篘one锛岀洿鎺ヨ闂睘鎬у瓨鍦ˋttributeError椋庨櫓",
                                    "fix": f"鍦ㄤ娇鐢ㄥ墠鍒ょ┖锛歩f {var_name} is not None: ... 鎴栦娇鐢?{var_name}.get('key')",
                                    "example": f"value = {var_name}.get('key') if {var_name} else default"
                                })

            # 
            if re.search(r"/\s*\w+\b", stripped) or re.search(r"%\s*\w+\b", stripped):
                divisor = re.search(r"[/|%]\s*(\w+)", stripped)
                if divisor:
                    div_var = divisor.group(1)
                    # 锛?
                    if div_var == "0":
                        issues.append({
                            "rule": "闄ら浂閿欒",
                            "severity": "涓ラ噸",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "妫€娴嬪埌闄ゆ硶/鍙栨ā杩愮畻涓櫎鏁颁负0",
                            "fix": "鍦ㄩ櫎娉曞墠鏍￠獙闄ゆ暟涓嶄负0",
                            "example": "if divisor != 0: result = dividend / divisor"
                        })

            # 
            if re.match(r"^(while|for)\s+", stripped):
                # breakreturn
                loop_body = self._extract_loop_body(lines, i)
                if loop_body and not any(kw in loop_body for kw in ["break", "return", "raise", "yield"]):
                    # 
                    condition = re.search(r"(?:while|for)\s+(.+?)[\s:{", stripped)
                    if condition:
                        cond = condition.group(1).strip()
                        if cond in ["True", "true", "1", "1 == 1"]:
                            issues.append({
                                "rule": "鏃犻檺寰幆",
                                "severity": "涓ラ噸",
                                "line": i + 1,
                                "code": stripped[:60],
                                "description": "妫€娴嬪埌寰幆鏉′欢姘歌繙涓虹湡涓旂己灏慴reak/return锛屽彲鑳藉鑷存棤闄愬惊鐜?,
                                "fix": "娣诲姞閫€鍑烘潯浠舵垨break璇彞",
                                "example": "while True:\n    if not has_data(): break\n    process()"
                            })

            #  Resource not released

            if language == "python":
                if re.search(r"open\s*\([^)]+\)", stripped) and "with" not in stripped:
                    prev_lines = "\n".join(lines[max(0, i-3):i])
                    if "with" not in prev_lines:
                        issues.append({
                            "rule": "璧勬簮鏈噴鏀?,
                            "severity": "涓瓑",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "妫€娴嬪埌鏂囦欢鎵撳紑浣嗘湭浣跨敤with璇彞锛屽紓甯告椂鍙兘涓嶅叧闂?,
                            "fix": "浣跨敤with璇彞纭繚璧勬簮閲婃斁",
                            "example": "with open('file.txt') as f:\n    data = f.read()"
                        })

        return issues

    def _extract_loop_body(self, lines: List[str], start_idx: int) -> str:
        """鎻愬彇寰幆浣撳唴瀹癸紙绠€鍖栫増锛?""
        body = []
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())

        for j in range(start_idx + 1, min(start_idx + 20, len(lines))):
            line = lines[j]
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent and line.strip():
                break
            body.append(line)

        return "\n".join(body)

    def _check_readability(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ュ彲璇绘€у弽妯″紡"""
        issues = []
        lines = code.split("\n")

        #  Magic numbers

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 锛?, 1, -1, , 锛?
            matches = re.finditer(r"(?<![\w\d_])([2-9]\d{2,}|[2-9]\d{1,2}(?!\s*px|\s*%|\s*em|\s*rem|\s*ms|\s*s))(?![\w\d_])", stripped)
            for match in matches:
                num = match.group(1)
                # 
                if num in ["200", "404", "500", "401", "403", "301", "302"]:
                    continue
                issues.append({
                    "rule": "榄旀硶鏁板瓧",
                    "severity": "杞诲井",
                    "line": i + 1,
                    "code": stripped[:60],
                    "description": f"妫€娴嬪埌鏈懡鍚嶇殑鏁板瓧{num}锛屽彲璇绘€у樊涓旈毦浠ョ淮鎶?,
                    "fix": "鎻愬彇涓哄懡鍚嶅父閲?,
                    "example": f"MAX_RETRY_COUNT = {num}  # 浠ｆ浛瑁告暟瀛?
                })

        # 
        func_starts = []
        if language == "python":
            for i, line in enumerate(lines):
                if re.match(r"^def\s+\w+", line.strip()):
                    func_starts.append(i)
        elif language in ["javascript", "typescript"]:
            for i, line in enumerate(lines):
                if re.match(r"^(function|const|let|var)\s+\w+.*[=:].*function|\(.*\)\s*=>", line.strip()):
                    func_starts.append(i)
        elif language == "java":
            for i, line in enumerate(lines):
                if re.match(r"^(public|private|protected)?\s*(static)?\s*\w+.*\(", line.strip()):
                    func_starts.append(i)

        for start in func_starts:
            # 锛堬級
            func_len = 0
            base_indent = len(lines[start]) - len(lines[start].lstrip())
            for j in range(start + 1, min(start + 200, len(lines))):
                if not lines[j].strip():
                    continue
                indent = len(lines[j]) - len(lines[j].lstrip())
                if indent <= base_indent and lines[j].strip():
                    break
                func_len += 1

            threshold = 50 if language == "python" else 80
            if func_len > threshold:
                issues.append({
                    "rule": "鍑芥暟杩囬暱",
                    "severity": "杞诲井",
                    "line": start + 1,
                    "code": lines[start].strip()[:60],
                    "description": f"鍑芥暟浣撻暱杈緖func_len}琛岋紝瓒呰繃寤鸿闃堝€納threshold}琛岋紝鑱岃矗鍙兘涓嶅崟涓€",
                    "fix": "鎸夎亴璐ｆ媶鍒嗕负澶氫釜灏忓嚱鏁帮紝姣忎釜鍑芥暟鍙仛涓€浠朵簨",
                    "example": "# 鎷嗗垎鍓嶏細process_order() 100琛孿n# 鎷嗗垎鍚庯細validate_order() + calculate_price() + save_order() + send_notification()"
                })

        #  Nested too deep

        max_depth = 0
        max_depth_line = 0
        current_depth = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^(if|for|while|try|with|def|class)\s+", stripped):
                current_depth += 1
                if current_depth > max_depth:
                    max_depth = current_depth
                    max_depth_line = i + 1
            elif stripped and not stripped.startswith("elif") and not stripped.startswith("else"):
                # 锛?
                if current_depth > 0:
                    current_depth -= 1

        if max_depth > 4:
            issues.append({
                "rule": "宓屽杩囨繁",
                "severity": "杞诲井",
                "line": max_depth_line,
                "code": lines[max_depth_line - 1].strip()[:60],
                "description": f"妫€娴嬪埌浠ｇ爜宓屽娣卞害杈緖max_depth}灞傦紝鍙鎬у拰缁存姢鎬у樊",
                "fix": "浣跨敤鍗鍙ユ彁鍓嶈繑鍥炪€佹彁鍙栧嚱鏁般€佹垨浣跨敤绛栫暐妯″紡鍑忓皯宓屽",
                "example": "# 鍗鍙nif not condition: return\n# 鏇夸唬澶氬眰if宓屽"
            })

        # 
        for i in range(len(lines) - 1):
            line = lines[i].strip()
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

            if line.startswith("#") or line.startswith("//"):
                comment = line.lstrip("#/ ").lower()
                code_lower = next_line.lower()
                # 锛?"""
                if ("add" in comment or "澧炲姞" in comment or "娣诲姞" in comment) and ("remove" in code_lower or "delete" in code_lower or "del " in code_lower):
                    issues.append({
                        "rule": "娉ㄩ噴涓庝唬鐮佷笉绗?,
                        "severity": "涓瓑",
                        "line": i + 1,
                        "code": f"{line[:40]} -> {next_line[:40]}",
                        "description": "娉ㄩ噴鎻忚堪鐨勮涓轰笌瀹為檯浠ｇ爜涓嶄竴鑷达紝鍙兘璇缁存姢鑰?,
                        "fix": "鏇存柊娉ㄩ噴鎴栦慨姝ｄ唬鐮侊紝纭繚娉ㄩ噴鍑嗙‘鎻忚堪浠ｇ爜琛屼负",
                        "example": "# 鏇存柊娉ㄩ噴浠ュ尮閰嶅疄闄呬唬鐮佽涓?
                    })

        #  Dead code

        if language == "python":
            # 
            imports = re.findall(r"^(?:import|from)\s+(\w+)", code, re.MULTILINE)
            for imp in imports:
                if imp not in ["os", "sys", "typing"] and imp not in code.split("import")[1]:
                    # 锛?
                    usage_count = len(re.findall(rf"\b{imp}\b", code))
                    if usage_count <= 1:  # 鍙湪瀵煎叆琛屽嚭鐜?
                        for match in re.finditer(rf"^(?:import|from)\s+{imp}\b", code, re.MULTILINE):
                            line_num = code[:match.start()].count("\n") + 1
                            issues.append({
                                "rule": "鏈娇鐢ㄧ殑瀵煎叆",
                                "severity": "杞诲井",
                                "line": line_num,
                                "code": match.group(0),
                                "description": f"瀵煎叆鐨勬ā鍧?{imp}'鏈浣跨敤",
                                "fix": "鍒犻櫎鏈娇鐢ㄧ殑瀵煎叆锛屽噺灏戜緷璧栧拰鍚姩鏃堕棿",
                                "example": "# 鍒犻櫎璇ヨ"
                            })

        return issues

    def _check_architecture(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ユ灦鏋勮璁￠棶棰?""
        issues = []

        #  Duplicate code妫€娴嬶紙绠€鍖栵細鐩镐技琛屾ā寮忥級

        lines = code.split("\n")
        seen_patterns = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) > 20:
                # 锛堬級
                pattern = re.sub(r"\w+", "VAR", stripped)
                if pattern in seen_patterns:
                    first_line = seen_patterns[pattern]
                    if i - first_line > 5:  # 閬垮厤鐩搁偦琛岀殑璇垽
                        issues.append({
                            "rule": "閲嶅浠ｇ爜",
                            "severity": "涓瓑",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": f"妫€娴嬪埌涓庣{first_line + 1}琛岀浉浼肩殑浠ｇ爜鐗囨锛屽瓨鍦ㄩ噸澶?,
                            "fix": "鎻愬彇涓哄叕鍏卞嚱鏁版垨甯搁噺",
                            "example": "# 鎻愬彇鍏叡鍑芥暟\ndef common_logic(x, y): ..."
                        })
                else:
                    seen_patterns[pattern] = i

        # /锛?
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(r"def\s+\w+\s*\([^)]{80,}\)", stripped):
                issues.append({
                    "rule": "鍙傛暟杩囧",
                    "severity": "涓瓑",
                    "line": i + 1,
                    "code": stripped[:60],
                    "description": "鍑芥暟鍙傛暟杩囧锛堣秴杩?涓級锛屽缓璁娇鐢ㄩ厤缃璞℃垨Builder妯″紡",
                    "fix": "灏嗙浉鍏冲弬鏁板皝瑁呬负瀵硅薄锛屾垨浣跨敤榛樿鍙傛暟/閰嶇疆绫?,
                    "example": "# 鏇夸唬锛歝onfig = ServerConfig(host, port, timeout, retry, ssl)\nstart_server(config)"
                })

        # 锛?
        if language in ["python", "java"]:
            for match in re.finditer(r"=\s*new\s+\w+\(\)", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "绱ц€﹀悎",
                    "severity": "杞诲井",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": "妫€娴嬪埌鐩存帴瀹炰緥鍖栧叿浣撶被锛岃繚鍙嶄緷璧栧€掔疆鍘熷垯",
                    "fix": "浣跨敤渚濊禆娉ㄥ叆鎴栧伐鍘傛ā寮忥紝渚濊禆鎺ュ彛鑰岄潪瀹炵幇",
                    "example": "# service = UserService()  # 绱ц€﹀悎\nservice = container.get(UserServiceInterface)  # 鏉捐€﹀悎"
                })

        return issues


# 
def analyze_semantic(code: str, language: str) -> List[Dict]:
    analyzer = SemanticAnalyzer()
    return analyzer.analyze(code, language)
