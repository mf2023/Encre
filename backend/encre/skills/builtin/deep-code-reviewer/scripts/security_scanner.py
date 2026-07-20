#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Security Scanner Engine
安全漏洞扫描引擎
"""

import re
from typing import Dict, List


class SecurityScanner:
    """安全扫描器"""

    def __init__(self):
        # 敏感信息模式
        self.secret_patterns = {
            "api_key": [
                r"api[_-]?key\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{16,})['\"]",
                r"apikey\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{16,})['\"]",
            ],
            "password": [
                r"password\s*[=:]\s*['\"]([^'\"]{4,})['\"]",
                r"passwd\s*[=:]\s*['\"]([^'\"]{4,})['\"]",
                r"pwd\s*[=:]\s*['\"]([^'\"]{4,})['\"]",
            ],
            "token": [
                r"token\s*[=:]\s*['\"]([a-zA-Z0-9_\-\.]{20,})['\"]",
                r"access_token\s*[=:]\s*['\"]([a-zA-Z0-9_\-\.]{20,})['\"]",
                r"bearer\s+([a-zA-Z0-9_\-\.]{20,})",
            ],
            "private_key": [
                r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
                r"private[_-]?key\s*[=:]\s*['\"]([^'\"]{20,})['\"]",
            ],
            "aws_key": [
                r"AKIA[0-9A-Z]{16}",
            ],
            "github_token": [
                r"ghp_[a-zA-Z0-9]{36}",
            ],
        }

    def scan(self, code: str, language: str) -> List[Dict]:
        """执行安全扫描"""
        issues = []

        # SQL注入
        issues.extend(self._check_sql_injection(code, language))

        # 命令注入
        issues.extend(self._check_command_injection(code, language))

        # XSS
        issues.extend(self._check_xss(code, language))

        # 敏感信息硬编码
        issues.extend(self._check_hardcoded_secrets(code))

        # 不安全的反序列化
        issues.extend(self._check_unsafe_deserialization(code, language))

        # 路径遍历
        issues.extend(self._check_path_traversal(code, language))

        # 弱加密
        issues.extend(self._check_weak_crypto(code, language))

        # 日志泄露
        issues.extend(self._check_log_leak(code, language))

        # CORS配置
        issues.extend(self._check_cors(code, language))

        return issues

    def _check_sql_injection(self, code: str, language: str) -> List[Dict]:
        """检查SQL注入"""
        issues = []

        # 字符串拼接SQL模式
        patterns = [
            r"['\"].*SELECT\s+.*FROM\s+.*['\"]\s*\+",
            r"['\"].*INSERT\s+INTO\s+.*['\"]\s*\+",
            r"['\"].*UPDATE\s+.*SET\s+.*['\"]\s*\+",
            r"['\"].*DELETE\s+FROM\s+.*['\"]\s*\+",
            r"\.format\s*\(.*SELECT|INSERT|UPDATE|DELETE",
            r"f['\"].*SELECT\s+.*FROM\s+.*{.*}.*['\"]",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "SQL注入",
                    "severity": "阻断",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "检测到SQL字符串拼接，存在SQL注入风险",
                    "fix": "使用参数化查询或ORM，禁止字符串拼接SQL",
                    "example": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"
                })

        return issues

    def _check_command_injection(self, code: str, language: str) -> List[Dict]:
        """检查命令注入"""
        issues = []

        dangerous_funcs = {
            "python": ["os.system", "os.popen", "subprocess.call", "subprocess.Popen", "eval", "exec"],
            "javascript": ["eval", "Function", "exec", "child_process.exec", "child_process.spawn"],
            "java": ["Runtime.exec", "ProcessBuilder"],
            "go": ["os/exec.Command", "syscall.Exec"],
        }

        funcs = dangerous_funcs.get(language, ["eval", "exec", "system"])
        for func in funcs:
            pattern = rf"\b{re.escape(func)}\s*\("
            for match in re.finditer(pattern, code):
                line_num = code[:match.start()].count("\n") + 1
                # 检查是否包含用户输入变量
                line_end = code.find("\n", match.end())
                line_content = code[match.start():line_end if line_end > 0 else len(code)]
                if any(var in line_content for var in ["req", "request", "input", "param", "args", "argv"]):
                    issues.append({
                        "rule": "命令注入",
                        "severity": "阻断",
                        "line": line_num,
                        "code": line_content[:80],
                        "description": f"检测到{func}调用且包含用户输入，存在命令注入风险",
                        "fix": "使用参数列表代替字符串拼接，或对输入做白名单校验",
                        "example": "subprocess.run(['ls', '-la', safe_path], check=True)"
                    })

        return issues

    def _check_xss(self, code: str, language: str) -> List[Dict]:
        """检查XSS"""
        issues = []

        if language in ["javascript", "typescript"]:
            # 直接innerHTML赋值
            patterns = [
                r"\.innerHTML\s*=\s*[^;]+",
                r"document\.write\s*\([^)]+",
                r"\.html\s*\([^)]+",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "XSS",
                        "severity": "阻断",
                        "line": line_num,
                        "code": match.group(0)[:80],
                        "description": "检测到直接操作HTML内容且未转义，存在XSS风险",
                        "fix": "使用textContent代替innerHTML，或使用DOMPurify等库做输入净化",
                        "example": "element.textContent = userInput  // 或使用 DOMPurify.sanitize()"
                    })

        elif language == "python":
            # Flask/Django模板中未转义
            patterns = [
                r"return\s+render_template_string\s*\([^)]+",
                r"Markup\s*\([^)]+",
                r"\.format\s*\(.*['\"]<.*>.*['\"]",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, code):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "XSS",
                        "severity": "阻断",
                        "line": line_num,
                        "code": match.group(0)[:80],
                        "description": "检测到模板渲染中可能包含未转义的用户输入",
                        "fix": "使用模板引擎的自动转义功能，禁止手动拼接HTML",
                        "example": "return render_template('page.html', data=escape(user_input))"
                    })

        return issues

    def _check_hardcoded_secrets(self, code: str) -> List[Dict]:
        """检查硬编码敏感信息"""
        issues = []

        for secret_type, patterns in self.secret_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.IGNORECASE):
                    line_num = code[:match.start()].count("\n") + 1
                    matched_text = match.group(0)
                    # 排除示例/测试用的假密钥
                    if any(fake in matched_text.lower() for fake in ["example", "test", "demo", "placeholder", "your_", "xxx", "changeme"]):
                        continue

                    issues.append({
                        "rule": "敏感信息硬编码",
                        "severity": "严重",
                        "line": line_num,
                        "code": matched_text[:60] + "...",
                        "description": f"检测到硬编码的{secret_type}，存在泄露风险",
                        "fix": "使用环境变量或密钥管理服务（如AWS Secrets Manager、HashiCorp Vault）",
                        "example": f"{secret_type.upper()} = os.environ.get('{secret_type.upper()}_KEY')"
                    })

        return issues

    def _check_unsafe_deserialization(self, code: str, language: str) -> List[Dict]:
        """检查不安全的反序列化"""
        issues = []

        dangerous = {
            "python": [("pickle.loads", "pickle反序列化"), ("yaml.load", "yaml反序列化"), ("eval(", "eval执行")],
            "javascript": [("JSON.parse", "JSON解析（注意原型链污染）")],
            "java": [("ObjectInputStream", "Java反序列化")],
        }

        funcs = dangerous.get(language, [])
        for func, desc in funcs:
            for match in re.finditer(rf"\b{re.escape(func)}\s*\(", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "不安全的反序列化",
                    "severity": "严重",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": f"检测到{desc}，可能执行恶意代码",
                    "fix": "使用安全的替代方案（如json.loads、yaml.safe_load），或对输入做签名验证",
                    "example": "data = json.loads(raw)  # 或 yaml.safe_load(raw)"
                })

        return issues

    def _check_path_traversal(self, code: str, language: str) -> List[Dict]:
        """检查路径遍历"""
        issues = []

        patterns = [
            r"open\s*\([^)]*\+",
            r"with\s+open\s*\([^)]*\+",
            r"\.readFile\s*\([^)]*\+",
            r"\.sendFile\s*\([^)]*\+",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "路径遍历",
                    "severity": "严重",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "检测到文件路径拼接，存在路径遍历风险",
                    "fix": "使用pathlib.Path.resolve()或os.path.realpath()校验路径，限制访问目录",
                    "example": "safe_path = os.path.realpath(os.path.join(BASE_DIR, filename))"
                })

        return issues

    def _check_weak_crypto(self, code: str, language: str) -> List[Dict]:
        """检查弱加密"""
        issues = []

        weak_algos = ["md5", "sha1", "DES", "RC4", "ECB"]
        for algo in weak_algos:
            for match in re.finditer(rf"\b{algo}\b", code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "弱加密算法",
                    "severity": "严重",
                    "line": line_num,
                    "code": match.group(0),
                    "description": f"检测到已不安全的算法{algo}，存在碰撞或破解风险",
                    "fix": "使用SHA-256/SHA-3、AES-GCM、Argon2等现代算法",
                    "example": "hashlib.sha256(data.encode()).hexdigest()"
                })

        return issues

    def _check_log_leak(self, code: str, language: str) -> List[Dict]:
        """检查日志泄露敏感信息"""
        issues = []

        patterns = [
            r"(log|logger|print|console\.log|fmt\.Print).*(password|token|secret|key|credit|ssn|身份证|手机号)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "日志泄露敏感信息",
                    "severity": "严重",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "检测到日志中可能打印敏感信息",
                    "fix": "日志中只记录脱敏后的信息或标识符，绝不打印密码/Token/身份证号",
                    "example": "logger.info('User login: %s', mask_phone(user.phone))"
                })

        return issues

    def _check_cors(self, code: str, language: str) -> List[Dict]:
        """检查CORS配置"""
        issues = []

        if language in ["python", "javascript"]:
            # Access-Control-Allow-Origin: * 且允许Credentials
            if "*" in code and ("credentials" in code.lower() or "withCredentials" in code):
                for match in re.finditer(r"Access-Control-Allow-Origin.*\*", code):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "CORS配置过宽",
                        "severity": "中等",
                        "line": line_num,
                        "code": match.group(0),
                        "description": "CORS允许任意来源且允许携带凭证，存在CSRF风险",
                        "fix": "限制允许的Origin列表，或使用SameSite Cookie",
                        "example": "CORS(app, origins=['https://example.com'])"
                    })

        return issues


# 对外入口
def scan_security(code: str, language: str) -> List[Dict]:
    scanner = SecurityScanner()
    return scanner.scan(code, language)
