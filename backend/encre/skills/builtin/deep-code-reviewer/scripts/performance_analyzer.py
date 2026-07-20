#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Analyzer Engine
性能陷阱检测引擎
"""

import re
from typing import Dict, List


class PerformanceAnalyzer:
    """性能分析器"""

    def analyze(self, code: str, language: str) -> List[Dict]:
        """执行性能分析"""
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
        """检查时间复杂度问题"""
        issues = []

        # 检测嵌套循环
        lines = code.split("\n")
        loop_stack = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 检测循环开始
            if re.match(r"^(for|while)\s+", stripped):
                indent = len(line) - len(line.lstrip())
                loop_stack.append({"line": i + 1, "indent": indent})
            # 检测循环结束（简化：缩进减少）
            elif loop_stack and stripped:
                indent = len(line) - len(line.lstrip())
                while loop_stack and indent <= loop_stack[-1]["indent"]:
                    loop_stack.pop()

            # 3层及以上嵌套循环
            if len(loop_stack) >= 3:
                issues.append({
                    "rule": "嵌套循环过深",
                    "severity": "中等",
                    "line": loop_stack[0]["line"],
                    "code": lines[loop_stack[0]["line"] - 1].strip()[:60],
                    "description": f"检测到{len(loop_stack)}层嵌套循环，时间复杂度可能为O(n^{len(loop_stack)})",
                    "fix": "考虑使用哈希表、排序+双指针、分治等算法优化，或提取循环内不变量",
                    "example": "# 用字典将O(n^2)降为O(n)\nlookup = {x: i for i, x in enumerate(arr)}"
                })
                loop_stack = []  # 避免重复报告

        # 检测递归（无记忆化）
        if language == "python":
            for match in re.finditer(r"def\s+(\w+)\s*\([^)]*\).*?:.*?\n(?:.*\n)*?\s+\1\s*\(", code):
                func_name = match.group(1)
                # 检查是否有lru_cache或memo
                func_block = code[match.start():match.start() + 500]
                if "lru_cache" not in func_block and "memo" not in func_block:
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "递归无记忆化",
                        "severity": "中等",
                        "line": line_num,
                        "code": f"def {func_name}(...)",
                        "description": "检测到递归函数但未使用记忆化，可能导致指数级时间复杂度",
                        "fix": "使用functools.lru_cache或手动实现记忆化字典",
                        "example": "@functools.lru_cache(maxsize=None)\ndef fib(n): ..."
                    })

        return issues

    def _check_n_plus_one(self, code: str, language: str) -> List[Dict]:
        """检查N+1查询"""
        issues = []

        if language == "python":
            # 检测循环内查询模式
            patterns = [
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\.filter\s*\(",
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\.objects\.get",
                r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+session\.query",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.DOTALL):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "N+1查询",
                        "severity": "严重",
                        "line": line_num,
                        "code": match.group(0).split("\n")[0][:60],
                        "description": "检测到循环内执行数据库查询，产生N+1查询问题",
                        "fix": "使用select_related/prefetch_related（Django）或join/eager load（SQLAlchemy）",
                        "example": "# Django\nusers = User.objects.prefetch_related('orders').all()\nfor user in users:\n    for order in user.orders.all(): ..."
                    })

        return issues

    def _check_memory_leak(self, code: str, language: str) -> List[Dict]:
        """检查内存泄漏"""
        issues = []

        if language == "python":
            # 循环中累积大列表
            patterns = [
                r"(\w+)\s*=\s*\[\].*?\n(?:.*\n)*?\s+\1\.append",
                r"(\w+)\s*=\s*\{\}.*?\n(?:.*\n)*?\s+\1\[",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.DOTALL):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "内存累积",
                        "severity": "严重",
                        "line": line_num,
                        "code": match.group(0).split("\n")[0][:60],
                        "description": "检测到循环中持续累积数据到列表/字典，可能导致内存溢出",
                        "fix": "使用生成器yield代替列表、分批处理、或定期清理缓存",
                        "example": "# 使用生成器\ndef process_large_file():\n    with open('data.txt') as f:\n        for line in f:\n            yield process(line)"
                    })

        # 闭包捕获大对象
        if language in ["javascript", "typescript"]:
            for match in re.finditer(r"setInterval\s*\(\s*function", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "定时器未清理",
                    "severity": "中等",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": "检测到setInterval/setTimeout可能未清理，导致内存泄漏",
                    "fix": "在组件卸载时调用clearInterval/clearTimeout",
                    "example": "const timer = setInterval(...);\nreturn () => clearInterval(timer);"
                })

        return issues

    def _check_string_concat(self, code: str, language: str) -> List[Dict]:
        """检查字符串拼接问题"""
        issues = []

        if language == "python":
            # 循环中字符串拼接
            for match in re.finditer(r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+\w+\s*\+\s*=", code, re.DOTALL):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "循环内字符串拼接",
                    "severity": "轻微",
                    "line": line_num,
                    "code": match.group(0).split("\n")[-1].strip()[:60],
                    "description": "循环中使用+=拼接字符串，时间复杂度O(n^2)",
                    "fix": "使用列表join或StringIO",
                    "example": "result = ''.join(items)  # 或 io.StringIO()"
                })

        return issues

    def _check_blocking_io(self, code: str, language: str) -> List[Dict]:
        """检查阻塞IO"""
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
                    "rule": "同步阻塞调用",
                    "severity": "中等",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": f"检测到同步阻塞调用{func}，在高并发场景会影响性能",
                    "fix": "使用异步替代方案（asyncio/aiohttp、Promise/async-await、NIO）",
                    "example": "# Python\nasync with aiohttp.ClientSession() as session:\n    async with session.get(url) as resp: ..."
                })

        return issues

    def _check_redundant_computation(self, code: str, language: str) -> List[Dict]:
        """检查重复计算"""
        issues = []

        # 循环内重复调用不变函数
        patterns = [
            r"for\s+\w+\s+in\s+[^:]+:.*?\n(?:.*\n)*?\s+len\s*\(\s*\w+\s*\)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, code, re.DOTALL):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "循环内重复计算",
                    "severity": "轻微",
                    "line": line_num,
                    "code": match.group(0).split("\n")[-1].strip()[:60],
                    "description": "循环中重复计算不变量（如len()），可提取到循环外",
                    "fix": "将不变量提取到循环外",
                    "example": "n = len(arr)\nfor i in range(n): ..."
                })

        return issues

    def _check_sql_performance(self, code: str, language: str) -> List[Dict]:
        """检查SQL性能问题"""
        issues = []

        # 检测慢查询模式
        slow_patterns = [
            (r"SELECT\s+\*\s+FROM", "SELECT * 全字段查询"),
            (r"OFFSET\s+\d{4,}", "大OFFSET深度分页"),
            (r"LIKE\s+['\"]%", "前模糊LIKE无法使用索引"),
            (r"NOT\s+IN\s*\(", "NOT IN性能差"),
        ]

        for pattern, desc in slow_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "SQL慢查询",
                    "severity": "严重",
                    "line": line_num,
                    "code": match.group(0)[:60],
                    "description": f"检测到{desc}，可能导致全表扫描或性能下降",
                    "fix": "指定所需字段、使用覆盖索引、改用游标分页或ES搜索",
                    "example": "SELECT id, name FROM users WHERE created_at > ? ORDER BY id LIMIT ?"
                })

        return issues


# 对外入口
def analyze_performance(code: str, language: str) -> List[Dict]:
    analyzer = PerformanceAnalyzer()
    return analyzer.analyze(code, language)
