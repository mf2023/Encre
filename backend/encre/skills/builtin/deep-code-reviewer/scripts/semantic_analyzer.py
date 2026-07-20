#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Analyzer Engine
语义分析引擎（逻辑漏洞、可读性、架构）
"""

import re
from typing import Dict, List


class SemanticAnalyzer:
    """语义分析器"""

    def analyze(self, code: str, language: str) -> List[Dict]:
        """执行语义分析"""
        issues = []

        issues.extend(self._check_logic_bugs(code, language))
        issues.extend(self._check_readability(code, language))
        issues.extend(self._check_architecture(code, language))

        return issues

    def _check_logic_bugs(self, code: str, language: str) -> List[Dict]:
        """检查逻辑漏洞"""
        issues = []
        lines = code.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 空指针/None引用
            if language == "python":
                # 未判空即访问属性
                if re.search(r"\w+\.[\w\[\(]", stripped):
                    var = re.search(r"(\w+)\.", stripped)
                    if var:
                        var_name = var.group(1)
                        # 检查前面是否有判空
                        prev_lines = "\n".join(lines[max(0, i-5):i])
                        if var_name not in prev_lines or f"if {var_name}" not in prev_lines:
                            if not any(safe in stripped for safe in ["try:", "except", "get(", "or ", "if "]):
                                issues.append({
                                    "rule": "空值引用风险",
                                    "severity": "中等",
                                    "line": i + 1,
                                    "code": stripped[:60],
                                    "description": f"变量'{var_name}'可能为None，直接访问属性存在AttributeError风险",
                                    "fix": f"在使用前判空：if {var_name} is not None: ... 或使用 {var_name}.get('key')",
                                    "example": f"value = {var_name}.get('key') if {var_name} else default"
                                })

            # 除零错误
            if re.search(r"/\s*\w+\b", stripped) or re.search(r"%\s*\w+\b", stripped):
                divisor = re.search(r"[/|%]\s*(\w+)", stripped)
                if divisor:
                    div_var = divisor.group(1)
                    # 简单检查：是否为字面量0
                    if div_var == "0":
                        issues.append({
                            "rule": "除零错误",
                            "severity": "严重",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "检测到除法/取模运算中除数为0",
                            "fix": "在除法前校验除数不为0",
                            "example": "if divisor != 0: result = dividend / divisor"
                        })

            # 无限循环风险
            if re.match(r"^(while|for)\s+", stripped):
                # 检查循环体内是否有break或return
                loop_body = self._extract_loop_body(lines, i)
                if loop_body and not any(kw in loop_body for kw in ["break", "return", "raise", "yield"]):
                    # 检查条件是否永远为真
                    condition = re.search(r"(?:while|for)\s+(.+?)[\s:{", stripped)
                    if condition:
                        cond = condition.group(1).strip()
                        if cond in ["True", "true", "1", "1 == 1"]:
                            issues.append({
                                "rule": "无限循环",
                                "severity": "严重",
                                "line": i + 1,
                                "code": stripped[:60],
                                "description": "检测到循环条件永远为真且缺少break/return，可能导致无限循环",
                                "fix": "添加退出条件或break语句",
                                "example": "while True:\n    if not has_data(): break\n    process()"
                            })

            # 资源未释放
            if language == "python":
                if re.search(r"open\s*\([^)]+\)", stripped) and "with" not in stripped:
                    prev_lines = "\n".join(lines[max(0, i-3):i])
                    if "with" not in prev_lines:
                        issues.append({
                            "rule": "资源未释放",
                            "severity": "中等",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": "检测到文件打开但未使用with语句，异常时可能不关闭",
                            "fix": "使用with语句确保资源释放",
                            "example": "with open('file.txt') as f:\n    data = f.read()"
                        })

        return issues

    def _extract_loop_body(self, lines: List[str], start_idx: int) -> str:
        """提取循环体内容（简化版）"""
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
        """检查可读性反模式"""
        issues = []
        lines = code.split("\n")

        # 魔法数字
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 匹配裸数字（排除0, 1, -1, 索引, 行号等）
            matches = re.finditer(r"(?<![\w\d_])([2-9]\d{2,}|[2-9]\d{1,2}(?!\s*px|\s*%|\s*em|\s*rem|\s*ms|\s*s))(?![\w\d_])", stripped)
            for match in matches:
                num = match.group(1)
                # 排除常见合法数字
                if num in ["200", "404", "500", "401", "403", "301", "302"]:
                    continue
                issues.append({
                    "rule": "魔法数字",
                    "severity": "轻微",
                    "line": i + 1,
                    "code": stripped[:60],
                    "description": f"检测到未命名的数字{num}，可读性差且难以维护",
                    "fix": "提取为命名常量",
                    "example": f"MAX_RETRY_COUNT = {num}  # 代替裸数字"
                })

        # 过长函数
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
            # 估算函数长度（到下一个同缩进或空行）
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
                    "rule": "函数过长",
                    "severity": "轻微",
                    "line": start + 1,
                    "code": lines[start].strip()[:60],
                    "description": f"函数体长达{func_len}行，超过建议阈值{threshold}行，职责可能不单一",
                    "fix": "按职责拆分为多个小函数，每个函数只做一件事",
                    "example": "# 拆分前：process_order() 100行\n# 拆分后：validate_order() + calculate_price() + save_order() + send_notification()"
                })

        # 嵌套过深
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
                # 简化：遇到非控制流语句时减少深度
                if current_depth > 0:
                    current_depth -= 1

        if max_depth > 4:
            issues.append({
                "rule": "嵌套过深",
                "severity": "轻微",
                "line": max_depth_line,
                "code": lines[max_depth_line - 1].strip()[:60],
                "description": f"检测到代码嵌套深度达{max_depth}层，可读性和维护性差",
                "fix": "使用卫语句提前返回、提取函数、或使用策略模式减少嵌套",
                "example": "# 卫语句\nif not condition: return\n# 替代多层if嵌套"
            })

        # 注释与代码不符
        for i in range(len(lines) - 1):
            line = lines[i].strip()
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

            if line.startswith("#") or line.startswith("//"):
                comment = line.lstrip("#/ ").lower()
                code_lower = next_line.lower()
                # 简单检查：注释说"增加"但代码是"删除"
                if ("add" in comment or "增加" in comment or "添加" in comment) and ("remove" in code_lower or "delete" in code_lower or "del " in code_lower):
                    issues.append({
                        "rule": "注释与代码不符",
                        "severity": "中等",
                        "line": i + 1,
                        "code": f"{line[:40]} -> {next_line[:40]}",
                        "description": "注释描述的行为与实际代码不一致，可能误导维护者",
                        "fix": "更新注释或修正代码，确保注释准确描述代码行为",
                        "example": "# 更新注释以匹配实际代码行为"
                    })

        # 死代码
        if language == "python":
            # 未使用的导入
            imports = re.findall(r"^(?:import|from)\s+(\w+)", code, re.MULTILINE)
            for imp in imports:
                if imp not in ["os", "sys", "typing"] and imp not in code.split("import")[1]:
                    # 简化检查：导入后是否被使用
                    usage_count = len(re.findall(rf"\b{imp}\b", code))
                    if usage_count <= 1:  # 只在导入行出现
                        for match in re.finditer(rf"^(?:import|from)\s+{imp}\b", code, re.MULTILINE):
                            line_num = code[:match.start()].count("\n") + 1
                            issues.append({
                                "rule": "未使用的导入",
                                "severity": "轻微",
                                "line": line_num,
                                "code": match.group(0),
                                "description": f"导入的模块'{imp}'未被使用",
                                "fix": "删除未使用的导入，减少依赖和启动时间",
                                "example": "# 删除该行"
                            })

        return issues

    def _check_architecture(self, code: str, language: str) -> List[Dict]:
        """检查架构设计问题"""
        issues = []

        # 重复代码检测（简化：相似行模式）
        lines = code.split("\n")
        seen_patterns = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) > 20:
                # 提取模式（去除变量名）
                pattern = re.sub(r"\w+", "VAR", stripped)
                if pattern in seen_patterns:
                    first_line = seen_patterns[pattern]
                    if i - first_line > 5:  # 避免相邻行的误判
                        issues.append({
                            "rule": "重复代码",
                            "severity": "中等",
                            "line": i + 1,
                            "code": stripped[:60],
                            "description": f"检测到与第{first_line + 1}行相似的代码片段，存在重复",
                            "fix": "提取为公共函数或常量",
                            "example": "# 提取公共函数\ndef common_logic(x, y): ..."
                        })
                else:
                    seen_patterns[pattern] = i

        # 上帝类/函数：参数过多
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(r"def\s+\w+\s*\([^)]{80,}\)", stripped):
                issues.append({
                    "rule": "参数过多",
                    "severity": "中等",
                    "line": i + 1,
                    "code": stripped[:60],
                    "description": "函数参数过多（超过5个），建议使用配置对象或Builder模式",
                    "fix": "将相关参数封装为对象，或使用默认参数/配置类",
                    "example": "# 替代：config = ServerConfig(host, port, timeout, retry, ssl)\nstart_server(config)"
                })

        # 紧耦合：直接实例化
        if language in ["python", "java"]:
            for match in re.finditer(r"=\s*new\s+\w+\(\)", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "紧耦合",
                    "severity": "轻微",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": "检测到直接实例化具体类，违反依赖倒置原则",
                    "fix": "使用依赖注入或工厂模式，依赖接口而非实现",
                    "example": "# service = UserService()  # 紧耦合\nservice = container.get(UserServiceInterface)  # 松耦合"
                })

        return issues


# 对外入口
def analyze_semantic(code: str, language: str) -> List[Dict]:
    analyzer = SemanticAnalyzer()
    return analyzer.analyze(code, language)
