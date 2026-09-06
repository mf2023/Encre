#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Security Scanner Engine
瀹夊叏婕忔礊鎵弿寮曟搸
"""

import re
from typing import Dict, List


class SecurityScanner:
    """Security scanner engine that detects common vulnerability patterns.

    Engineering design: Regex-based pattern matching across multiple
    vulnerability categories (injection, XSS, hardcoded secrets, etc.)
    without requiring AST analysis, making it language-agnostic at the
    detection layer while still respecting per-language patterns.
    """

    def __init__(self):
        # Define regex patterns for detecting hardcoded sensitive information

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
        """Run all security checks and return list of findings.

        Args:
            code: Source code to scan.
            language: Programming language (affects which checks are active).
        """
        issues = []

        # Check for SQL injection via string concatenation
        issues.extend(self._check_sql_injection(code, language))
        # Check for command injection via user-controlled input
        issues.extend(self._check_command_injection(code, language))
        # Check for cross-site scripting vectors
        issues.extend(self._check_xss(code, language))
        # Check for hardcoded secrets and credentials
        issues.extend(self._check_hardcoded_secrets(code))
        # Check for unsafe deserialization
        issues.extend(self._check_unsafe_deserialization(code, language))
        # Check for path traversal vulnerabilities
        issues.extend(self._check_path_traversal(code, language))
        # Check for weak cryptographic algorithms
        issues.extend(self._check_weak_crypto(code, language))
        # Check for sensitive data in log statements
        issues.extend(self._check_log_leak(code, language))
        # Check for overly permissive CORS configuration
        issues.extend(self._check_cors(code, language))

        return issues

    def _check_sql_injection(self, code: str, language: str) -> List[Dict]:
        """妫€鏌QL娉ㄥ叆"""
        issues = []

        # Detect string-concatenated SQL patterns

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
                    "rule": "SQL娉ㄥ叆",
                    "severity": "闃绘柇",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "妫€娴嬪埌SQL瀛楃涓叉嫾鎺ワ紝瀛樺湪SQL娉ㄥ叆椋庨櫓",
                    "fix": "浣跨敤鍙傛暟鍖栨煡璇㈡垨ORM锛岀姝㈠瓧绗︿覆鎷兼帴SQL",
                    "example": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"
                })

        return issues

    def _check_command_injection(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ュ懡浠ゆ敞鍏?""
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
                # Only flag if user input variables are present in the call
                line_end = code.find("\n", match.end())
                line_content = code[match.start():line_end if line_end > 0 else len(code)]
                if any(var in line_content for var in ["req", "request", "input", "param", "args", "argv"]):
                    issues.append({
                        "rule": "鍛戒护娉ㄥ叆",
                        "severity": "闃绘柇",
                        "line": line_num,
                        "code": line_content[:80],
                        "description": f"妫€娴嬪埌{func}璋冪敤涓斿寘鍚敤鎴疯緭鍏ワ紝瀛樺湪鍛戒护娉ㄥ叆椋庨櫓",
                        "fix": "浣跨敤鍙傛暟鍒楄〃浠ｆ浛瀛楃涓叉嫾鎺ワ紝鎴栧杈撳叆鍋氱櫧鍚嶅崟鏍￠獙",
                        "example": "subprocess.run(['ls', '-la', safe_path], check=True)"
                    })

        return issues

    def _check_xss(self, code: str, language: str) -> List[Dict]:
        """妫€鏌SS"""
        issues = []

        if language in ["javascript", "typescript"]:
            # Detect direct innerHTML assignment in JS/TS

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
                        "severity": "闃绘柇",
                        "line": line_num,
                        "code": match.group(0)[:80],
                        "description": "妫€娴嬪埌鐩存帴鎿嶄綔HTML鍐呭涓旀湭杞箟锛屽瓨鍦╔SS椋庨櫓",
                        "fix": "浣跨敤textContent浠ｆ浛innerHTML锛屾垨浣跨敤DOMPurify绛夊簱鍋氳緭鍏ュ噣鍖?,
                        "example": "element.textContent = userInput  // 鎴栦娇鐢?DOMPurify.sanitize()"
                    })

        elif language == "python":
            # Flask/Django template injection patterns
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
                        "severity": "闃绘柇",
                        "line": line_num,
                        "code": match.group(0)[:80],
                        "description": "妫€娴嬪埌妯℃澘娓叉煋涓彲鑳藉寘鍚湭杞箟鐨勭敤鎴疯緭鍏?,
                        "fix": "浣跨敤妯℃澘寮曟搸鐨勮嚜鍔ㄨ浆涔夊姛鑳斤紝绂佹鎵嬪姩鎷兼帴HTML",
                        "example": "return render_template('page.html', data=escape(user_input))"
                    })

        return issues

    def _check_hardcoded_secrets(self, code: str) -> List[Dict]:
        """妫€鏌ョ‖缂栫爜鏁忔劅淇℃伅"""
        issues = []

        for secret_type, patterns in self.secret_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.IGNORECASE):
                    line_num = code[:match.start()].count("\n") + 1
                    matched_text = match.group(0)
                    # Skip example/demo placeholders to reduce false positives
                    if any(fake in matched_text.lower() for fake in ["example", "test", "demo", "placeholder", "your_", "xxx", "changeme"]):
                        continue

                    issues.append({
                        "rule": "鏁忔劅淇℃伅纭紪鐮?,
                        "severity": "涓ラ噸",
                        "line": line_num,
                        "code": matched_text[:60] + "...",
                        "description": f"妫€娴嬪埌纭紪鐮佺殑{secret_type}锛屽瓨鍦ㄦ硠闇查闄?,
                        "fix": "浣跨敤鐜鍙橀噺鎴栧瘑閽ョ鐞嗘湇鍔★紙濡侫WS Secrets Manager銆丠ashiCorp Vault锛?,
                        "example": f"{secret_type.upper()} = os.environ.get('{secret_type.upper()}_KEY')"
                    })

        return issues

    def _check_unsafe_deserialization(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ヤ笉瀹夊叏鐨勫弽搴忓垪鍖?""
        issues = []

        dangerous = {
            "python": [("pickle.loads", "pickle鍙嶅簭鍒楀寲"), ("yaml.load", "yaml鍙嶅簭鍒楀寲"), ("eval(", "eval鎵ц")],
            "javascript": [("JSON.parse", "JSON瑙ｆ瀽锛堟敞鎰忓師鍨嬮摼姹℃煋锛?)],
            "java": [("ObjectInputStream", "Java鍙嶅簭鍒楀寲")],
        }

        funcs = dangerous.get(language, [])
        for func, desc in funcs:
            for match in re.finditer(rf"\b{re.escape(func)}\s*\(", code):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "涓嶅畨鍏ㄧ殑鍙嶅簭鍒楀寲",
                    "severity": "涓ラ噸",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": f"妫€娴嬪埌{desc}锛屽彲鑳芥墽琛屾伓鎰忎唬鐮?,
                    "fix": "浣跨敤瀹夊叏鐨勬浛浠ｆ柟妗堬紙濡俲son.loads銆亂aml.safe_load锛夛紝鎴栧杈撳叆鍋氱鍚嶉獙璇?,
                    "example": "data = json.loads(raw)  # 鎴?yaml.safe_load(raw)"
                })

        return issues

    def _check_path_traversal(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ヨ矾寰勯亶鍘?""
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
                    "rule": "璺緞閬嶅巻",
                    "severity": "涓ラ噸",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "妫€娴嬪埌鏂囦欢璺緞鎷兼帴锛屽瓨鍦ㄨ矾寰勯亶鍘嗛闄?,
                    "fix": "浣跨敤pathlib.Path.resolve()鎴杘s.path.realpath()鏍￠獙璺緞锛岄檺鍒惰闂洰褰?,
                    "example": "safe_path = os.path.realpath(os.path.join(BASE_DIR, filename))"
                })

        return issues

    def _check_weak_crypto(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ュ急鍔犲瘑"""
        issues = []

        weak_algos = ["md5", "sha1", "DES", "RC4", "ECB"]
        for algo in weak_algos:
            for match in re.finditer(rf"\b{algo}\b", code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "寮卞姞瀵嗙畻娉?,
                    "severity": "涓ラ噸",
                    "line": line_num,
                    "code": match.group(0),
                    "description": f"妫€娴嬪埌宸蹭笉瀹夊叏鐨勭畻娉晎algo}锛屽瓨鍦ㄧ鎾炴垨鐮磋В椋庨櫓",
                    "fix": "浣跨敤SHA-256/SHA-3銆丄ES-GCM銆丄rgon2绛夌幇浠ｇ畻娉?,
                    "example": "hashlib.sha256(data.encode()).hexdigest()"
                })

        return issues

    def _check_log_leak(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ユ棩蹇楁硠闇叉晱鎰熶俊鎭?""
        issues = []

        patterns = [
            r"(log|logger|print|console\.log|fmt\.Print).*(password|token|secret|key|credit|ssn|韬唤璇亅鎵嬫満鍙?",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "rule": "鏃ュ織娉勯湶鏁忔劅淇℃伅",
                    "severity": "涓ラ噸",
                    "line": line_num,
                    "code": match.group(0)[:80],
                    "description": "妫€娴嬪埌鏃ュ織涓彲鑳芥墦鍗版晱鎰熶俊鎭?,
                    "fix": "鏃ュ織涓彧璁板綍鑴辨晱鍚庣殑淇℃伅鎴栨爣璇嗙锛岀粷涓嶆墦鍗板瘑鐮?Token/韬唤璇佸彿",
                    "example": "logger.info('User login: %s', mask_phone(user.phone))"
                })

        return issues

    def _check_cors(self, code: str, language: str) -> List[Dict]:
        """妫€鏌ORS閰嶇疆"""
        issues = []

        if language in ["python", "javascript"]:
            # Access-Control-Allow-Origin: * Credentials
            if "*" in code and ("credentials" in code.lower() or "withCredentials" in code):
                for match in re.finditer(r"Access-Control-Allow-Origin.*\*", code):
                    line_num = code[:match.start()].count("\n") + 1
                    issues.append({
                        "rule": "CORS閰嶇疆杩囧",
                        "severity": "涓瓑",
                        "line": line_num,
                        "code": match.group(0),
                        "description": "CORS鍏佽浠绘剰鏉ユ簮涓斿厑璁告惡甯﹀嚟璇侊紝瀛樺湪CSRF椋庨櫓",
                        "fix": "闄愬埗鍏佽鐨凮rigin鍒楄〃锛屾垨浣跨敤SameSite Cookie",
                        "example": "CORS(app, origins=['https://example.com'])"
                    })

        return issues


# Public factory function for security scanning
def scan_security(code: str, language: str) -> List[Dict]:
    scanner = SecurityScanner()
    return scanner.scan(code, language)
