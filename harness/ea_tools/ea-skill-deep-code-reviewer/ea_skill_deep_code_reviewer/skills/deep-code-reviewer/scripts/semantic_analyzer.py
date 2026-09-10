from __future__ import annotations

"""
Semantic Analyzer Engine
璇箟鍒嗘瀽寮曟搸锛堥昏緫婕忔礊銆佸彲璇绘с佹灦鏋勶級
"""

import re
from typing import Dict, List


class SemanticAnalyzer:
    """Semantic analyzer engine."""

    def analyze(self, code: str, language: str) -> List[Dict]:
        """鎵ц璇箟鍒嗘瀽"""
        issues = []

        issues.extend(self._check_logic_bugs(code, language))
        issues.extend(self._check_readability(code, language))
        issues.extend(self._check_architecture(code, language))

        return issues

    def _check_logic_bugs(self, code: str, language: str) -> List[Dict]:
        """妫鏌ラ昏緫婕忔礊"""
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
                                    "rule": "绌哄煎紩鐢ㄩ闄?",
                                    "severity": "涓瓑",
                                    "line": i + 1,
                                    "code": stripped[:60],
                                    "description": f"鍙橀噺'{var_name}'鍙兘涓篘one锛岀洿鎺ヨ闂睘鎬у瓨鍦ˋttributeError椋庨櫓",
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
                            "rule": "闄ら浂閿欒",
                            "severity": "涓ラ噸",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "妫娴嬪埌闄ゆ硶/鍙栨ā杩愮畻涓櫎鏁颁负0",
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
                                "rule": "鏃犻檺寰幆",
                                "severity": "涓ラ噸",
                                "line": i + 1,
                                "code": stripped[:60],
                                "description": "妫娴嬪埌寰幆鏉′欢姘歌繙涓虹湡涓旂己灏慴reak/return锛屽彲鑳藉鑷存棤闄愬惊鐜?",
                                "fix": "娣诲姞閫鍑烘潯浠舵垨break璇彞",
                                "example": "while True:\n    if not has_data(): break\n    process()"
                            })

            #  Resource not released

            if language == "python":
                if re.search(r"open\s*\([^)]+\)", stripped) and "with" not in stripped:
                    prev_lines = "\n".join(lines[max(0, i-3):i])
                    if "with" not in prev_lines:
                        issues.append({
                            "rule": "璧勬簮鏈噴鏀?",
                            "severity": "涓瓑",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "妫娴嬪埌鏂囦欢鎵撳紑浣嗘湭浣跨敤with璇彞锛屽紓甯告椂鍙兘涓嶅叧闂?",
                            "fix": "浣跨敤with璇彞纭繚璧勬簮閲婃斁",
                            "example": "with open('file.txt') as f:\n    data = f.read()"
                        })

        return issues

    def _extract_loop_body(self, lines: List[str], start_idx: int) -> str:
        """鎻愬彇寰幆浣撳唴瀹癸紙绠鍖栫増锛"""
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
        """妫鏌ュ彲璇绘у弽妯紡"""
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
                    "description": f"Found magic number {num}; hard to read and maintain",
                    "fix": "Extract to a named constant",
                    "example": f"MAX_RETRY_COUNT = {num}  # instead of a bare number"
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
                    "description": f"Function body is {func_len} lines, exceeding the recommended {threshold} lines; responsibility may not be single.",
                    "fix": "Split by responsibility into multiple small functions, one job per function.",
                    "example": "# before: process_order() 100 lines\n# after: validate_order() + calculate_price() + save_order() + send_notification()"
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
                "rule": "宓屽杩囨繁",
                "severity": "杞诲井",
                "line": max_depth_line,
                "code": lines[max_depth_line - 1].strip()[:60],
                "description": f"Detected nesting depth of {max_depth} levels; readability and maintainability suffer",
                "fix": "浣跨敤鍗鍙ユ彁鍓嶈繑鍥炪佹彁鍙栧嚱鏁般佹垨浣跨敤绛栫暐妯紡鍑忓皯宓屽",
                "example": "# 鍗鍙nif not condition: return\n# 鏇夸唬澶氬眰if宓屽"
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
                        "rule": "comment-code mismatch",
                        "severity": "涓瓑",
                        "line": i + 1,
                        "code": f"{line[:40]} -> {next_line[:40]}",
                        "description": "Comment says add but code deletes; may mislead maintainers.",
                        "fix": "鏇存柊娉ㄩ噴鎴栦慨姝ｄ唬鐮侊紝纭繚娉ㄩ噴鍑嗙‘鎻忚堪浠ｇ爜琛屼负",
                        "example": "# Update the comment to match the actual code.",
                    })

        #  Dead code

        if language == "python":
            # 
            imports = re.findall(r"^(?:import|from)\s+(\w+)", code, re.MULTILINE)
            for imp in imports:
                if imp not in ["os", "sys", "typing"] and imp not in code.split("import")[1]:
                    # 锛?
                    usage_count = len(re.findall(rf"\b{imp}\b", code))
                    if usage_count <= 1:  # 鍙湪瀵煎叆琛屽嚭鐜?
                        for match in re.finditer(rf"^(?:import|from)\s+{imp}\b", code, re.MULTILINE):
                            line_num = code[:match.start()].count("\n") + 1
                            issues.append({
                                "rule": "鏈娇鐢ㄧ殑瀵煎叆",
                                "severity": "杞诲井",
                                "line": line_num,
                                "code": match.group(0),
                                "description": f"瀵煎叆鐨勬ā鍧?{imp}'鏈浣跨敤",
                                "fix": "鍒犻櫎鏈娇鐢ㄧ殑瀵煎叆锛屽噺灏戜緷璧栧拰鍚姩鏃堕棿",
                                "example": "# 鍒犻櫎璇ヨ"
                            })

        return issues

    def _check_architecture(self, code: str, language: str) -> List[Dict]:
        """妫鏌ユ灦鏋勮璁￠棶棰"""
        issues = []

        #  Duplicate code妫娴嬶紙绠鍖栵細鐩镐技琛屾ā寮忥級

        lines = code.split("\n")
        seen_patterns = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) > 20:
                # 锛堬級
                pattern = re.sub(r"\w+", "VAR", stripped)
                if pattern in seen_patterns:
                    first_line = seen_patterns[pattern]
                    if i - first_line > 5:  # 閬垮厤鐩搁偦琛岀殑璇垽
                        issues.append({
                            "rule": "閲嶅浠ｇ爜",
                            "severity": "涓瓑",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": f"妫娴嬪埌涓庣{first_line + 1}琛岀浉浼肩殑浠ｇ爜鐗囨锛屽瓨鍦ㄩ噸澶?",
                            "fix": "鎻愬彇涓哄叕鍏卞嚱鏁版垨甯搁噺",
                            "example": "# 鎻愬彇鍏叡鍑芥暟\ndef common_logic(x, y): ..."
                        })
                else:
                    seen_patterns[pattern] = i

        # /锛?
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(r"def\s+\w+\s*\([^)]{80,}\)", stripped):
                issues.append({
                    "rule": "鍙傛暟杩囧",
                    "severity": "涓瓑",
                    "line": i + 1,
                    "code": stripped[:60],
                    "description": "鍑芥暟鍙傛暟杩囧锛堣秴杩?涓級锛屽缓璁娇鐢ㄩ厤缃璞垨Builder妯紡",
                    "fix": "灏嗙浉鍏冲弬鏁板皝瑁呬负瀵硅薄锛屾垨浣跨敤榛樿鍙傛暟/閰嶇疆绫?",
                    "example": "# 鏇夸唬锛歝onfig = ServerConfig(host, port, timeout, retry, ssl)\nstart_server(config)"
                })

        # 锛?
        if language in ["python", "java"]:
            for match in re.finditer(r"=\s*new\s+\w+\(\)", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "绱ц悎",
                    "severity": "杞诲井",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": "妫娴嬪埌鐩存帴瀹炰緥鍖栧叿浣撶被锛岃繚鍙嶄緷璧栧掔疆鍘熷垯",
                    "fix": "浣跨敤渚濊禆娉ㄥ叆鎴栧伐鍘傛ā寮忥紝渚濊禆鎺ュ彛鑰岄潪瀹炵幇",
                    "example": "# service = UserService()  # 绱ц悎\nservice = container.get(UserServiceInterface)  # 鏉捐悎"
                })

        return issues


# 
def analyze_semantic(code: str, language: str) -> List[Dict]:
    analyzer = SemanticAnalyzer()
    return analyzer.analyze(code, language)
