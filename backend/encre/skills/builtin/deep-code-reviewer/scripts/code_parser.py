#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Parser Engine
代码解析与语言识别引擎
"""

import re
from typing import Dict, List, Tuple, Optional


class CodeParser:
    """代码解析器"""

    LANGUAGE_SIGNATURES = {
        "python": {
            "extensions": [".py", ".pyw"],
            "keywords": ["def ", "import ", "from ", "class ", "if __name__", "print(", "self."],
            "shebang": r"python"
        },
        "javascript": {
            "extensions": [".js", ".jsx", ".mjs"],
            "keywords": ["function ", "const ", "let ", "var ", "=>", "require(", "module.exports"],
            "shebang": r"node"
        },
        "typescript": {
            "extensions": [".ts", ".tsx"],
            "keywords": ["interface ", "type ", "enum ", ": string", ": number", "as ", "implements"],
            "shebang": None
        },
        "java": {
            "extensions": [".java"],
            "keywords": ["public class", "private ", "protected ", "System.out", "@Override", "import java."],
            "shebang": None
        },
        "go": {
            "extensions": [".go"],
            "keywords": ["func ", "package ", "import (", "struct ", "interface ", "chan ", "goroutine"],
            "shebang": None
        },
        "cpp": {
            "extensions": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
            "keywords": ["#include", "std::", "class ", "public:", "template<", "namespace "],
            "shebang": None
        },
        "c": {
            "extensions": [".c", ".h"],
            "keywords": ["#include", "struct ", "typedef ", "malloc(", "printf(", "void*"],
            "shebang": None
        },
        "rust": {
            "extensions": [".rs"],
            "keywords": ["fn ", "let ", "mut ", "impl ", "struct ", "enum ", "match ", "Result<"],
            "shebang": None
        },
        "sql": {
            "extensions": [".sql"],
            "keywords": ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "FROM ", "WHERE ", "JOIN ", "CREATE TABLE"],
            "shebang": None
        },
        "shell": {
            "extensions": [".sh", ".bash", ".zsh"],
            "keywords": ["#!/bin/bash", "#!/bin/sh", "echo ", "if [", "for ", "while ", "function "],
            "shebang": r"bash|sh|zsh"
        },
    }

    def parse(self, code: str, filename: Optional[str] = None) -> Dict:
        """
        主解析入口
        code: 代码文本
        filename: 文件名（可选，用于识别语言）
        """
        if not code or not code.strip():
            return {"status": "failed", "error": "未检测到有效代码", "language": None}

        # 1. 识别语言
        language = self._detect_language(code, filename)

        # 2. 清洗代码
        cleaned = self._clean_code(code)

        # 3. 分段
        segments = self._split_segments(cleaned, language)

        # 4. 提取元数据
        metadata = self._extract_metadata(cleaned, language)

        return {
            "status": "success",
            "language": language,
            "total_lines": len(code.split("\n")),
            "segments": segments,
            "metadata": metadata,
            "raw_code": cleaned,
            "warnings": []
        }

    def _detect_language(self, code: str, filename: Optional[str]) -> str:
        """识别编程语言"""
        # 优先根据文件名
        if filename:
            ext = filename.lower()
            for lang, sig in self.LANGUAGE_SIGNATURES.items():
                if any(ext.endswith(e) for e in sig["extensions"]):
                    return lang

        # 根据代码特征
        scores = {}
        code_sample = code[:2000].lower()

        for lang, sig in self.LANGUAGE_SIGNATURES.items():
            score = 0
            for kw in sig["keywords"]:
                if kw.lower() in code_sample:
                    score += 1
            if sig["shebang"] and re.search(sig["shebang"], code_sample):
                score += 3
            scores[lang] = score

        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best

        return "unknown"

    def _clean_code(self, code: str) -> str:
        """清洗代码"""
        # 统一换行符
        code = code.replace("\r\n", "\n").replace("\r", "\n")
        # 去除尾部空行
        code = code.rstrip()
        return code

    def _split_segments(self, code: str, language: str) -> List[Dict]:
        """按函数/类分段"""
        segments = []
        lines = code.split("\n")

        if language == "python":
            segments = self._split_python(code, lines)
        elif language in ["javascript", "typescript"]:
            segments = self._split_js_ts(code, lines)
        elif language == "java":
            segments = self._split_java(code, lines)
        elif language == "go":
            segments = self._split_go(code, lines)
        elif language in ["cpp", "c"]:
            segments = self._split_cpp(code, lines)
        elif language == "rust":
            segments = self._split_rust(code, lines)
        elif language == "sql":
            segments = self._split_sql(code, lines)
        else:
            # 通用分段：按空行分段
            segments = self._split_generic(code, lines)

        return segments

    def _split_python(self, code: str, lines: List[str]) -> List[Dict]:
        """Python分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 函数定义
            if re.match(r"^def\s+\w+", stripped):
                if current["lines"]:
                    segments.append(current)
                current = {"type": "function", "name": re.search(r"def\s+(\w+)", stripped).group(1),
                          "start": i, "lines": [line]}
            # 类定义
            elif re.match(r"^class\s+\w+", stripped):
                if current["lines"]:
                    segments.append(current)
                current = {"type": "class", "name": re.search(r"class\s+(\w+)", stripped).group(1),
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_js_ts(self, code: str, lines: List[str]) -> List[Dict]:
        """JS/TS分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 函数定义
            if re.match(r"^(function|const|let|var)\s+\w+.*[=:].*function|\(.*\)\s*=>", stripped):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"(?:function|const|let|var)\s+(\w+)", stripped)
                current = {"type": "function", "name": name_match.group(1) if name_match else "anonymous",
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_java(self, code: str, lines: List[str]) -> List[Dict]:
        """Java分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^(public|private|protected)?\s*(static)?\s*\w+.*\(", stripped):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"\s+(\w+)\s*\(", stripped)
                current = {"type": "method", "name": name_match.group(1) if name_match else "unknown",
                          "start": i, "lines": [line]}
            elif re.match(r"^class\s+\w+", stripped):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"class\s+(\w+)", stripped)
                current = {"type": "class", "name": name_match.group(1) if name_match else "unknown",
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_go(self, code: str, lines: List[str]) -> List[Dict]:
        """Go分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^func\s+\w+", stripped):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"func\s+(?:\([^)]+\)\s*)?(\w+)", stripped)
                current = {"type": "function", "name": name_match.group(1) if name_match else "unknown",
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_cpp(self, code: str, lines: List[str]) -> List[Dict]:
        """C/C++分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^\w+.*\(.*\)\s*\{", stripped) and not stripped.startswith("if") and not stripped.startswith("for"):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"(\w+)\s*\(", stripped)
                current = {"type": "function", "name": name_match.group(1) if name_match else "unknown",
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_rust(self, code: str, lines: List[str]) -> List[Dict]:
        """Rust分段"""
        segments = []
        current = {"type": "global", "name": "global", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^fn\s+\w+", stripped):
                if current["lines"]:
                    segments.append(current)
                name_match = re.search(r"fn\s+(\w+)", stripped)
                current = {"type": "function", "name": name_match.group(1) if name_match else "unknown",
                          "start": i, "lines": [line]}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_sql(self, code: str, lines: List[str]) -> List[Dict]:
        """SQL分段"""
        segments = []
        current = {"type": "statement", "name": "query", "start": 0, "lines": []}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.endswith(";"):
                current["lines"].append(line)
                segments.append(current)
                current = {"type": "statement", "name": "query", "start": i + 1, "lines": []}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _split_generic(self, code: str, lines: List[str]) -> List[Dict]:
        """通用分段"""
        segments = []
        current = {"type": "block", "name": "block_0", "start": 0, "lines": []}
        block_idx = 0

        for i, line in enumerate(lines):
            if line.strip() == "":
                if current["lines"]:
                    segments.append(current)
                    block_idx += 1
                    current = {"type": "block", "name": f"block_{block_idx}", "start": i + 1, "lines": []}
            else:
                current["lines"].append(line)

        if current["lines"]:
            segments.append(current)

        return segments

    def _extract_metadata(self, code: str, language: str) -> Dict:
        """提取代码元数据"""
        metadata = {
            "imports": [],
            "functions_count": 0,
            "classes_count": 0,
            "lines_of_code": 0,
            "comment_ratio": 0.0
        }

        lines = code.split("\n")
        comment_lines = 0
        code_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                comment_lines += 1
            else:
                code_lines += 1

        metadata["lines_of_code"] = code_lines
        if code_lines + comment_lines > 0:
            metadata["comment_ratio"] = round(comment_lines / (code_lines + comment_lines), 2)

        # 提取导入
        if language == "python":
            metadata["imports"] = re.findall(r"^(?:import|from)\s+(\w+)", code, re.MULTILINE)
        elif language in ["javascript", "typescript"]:
            metadata["imports"] = re.findall(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", code)
        elif language == "java":
            metadata["imports"] = re.findall(r"import\s+([\w.]+);", code)
        elif language == "go":
            metadata["imports"] = re.findall(r'"([^"]+)"', code)

        # 统计函数和类
        metadata["functions_count"] = len(re.findall(r"\bdef\s+\w+|\bfunc\s+\w+|\bfunction\s+\w+|\bfn\s+\w+", code))
        metadata["classes_count"] = len(re.findall(r"\bclass\s+\w+|\bstruct\s+\w+|\binterface\s+\w+", code))

        return metadata


# 对外入口
def parse_code(code: str, filename: Optional[str] = None) -> Dict:
    parser = CodeParser()
    return parser.parse(code, filename)
