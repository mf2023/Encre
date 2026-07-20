import sys
import json
import re
import os

def check_dangerous_code(code):
    dangerous_patterns = {
        "command_injection": {
            "patterns": [
                r'(?:subprocess|Popen|os\.system|os\.popen|commands\.|sh\.|shell\s*=)',
                r'(?:\\$|%\\(\\)|`.*`|\|.*\|)',
                r'(?:subprocess\.|subprocess\s*\()'
            ],
            "severity": "high",
            "description": "Potential command injection vulnerability - code may execute system commands"
        },
        "code_execution": {
            "patterns": [
                r'(?:exec\(|eval\(|compile\(|execfile\()',
                r'(?:__import__\(|importlib\.import_module\()',
                r'(?:exec\s*\(.*\)|eval\s*\(.*\))'
            ],
            "severity": "high",
            "description": "Potential code injection - code may execute arbitrary Python code"
        },
        "file_access": {
            "patterns": [
                r'(?:open\(|file\(|os\.open|io\.open)',
                r'(?:os\.path|os\.chdir|os\.listdir|os\.walk)',
                r'(?:with\s+open\s*\()'
            ],
            "severity": "medium",
            "description": "Potential file system access - code may read/write files"
        },
        "network_access": {
            "patterns": [
                r'(?:requests\.|urllib\.|http\.|socket\.|ftplib\.|smtplib\.|email\.|ssl\.)',
                r'(?:http://|https://|ftp://|tcp://|udp://)',
                r'(?:connect\(|bind\(|listen\(|accept\()'
            ],
            "severity": "medium",
            "description": "Potential network access - code may communicate over network"
        },
        "system_access": {
            "patterns": [
                r'(?:os\.chmod|os\.chown|os\.mkdir|os\.rmdir|os\.remove|os\.unlink)',
                r'(?:shutil\.|kill\(|signal\.|process\.|pid\b)',
                r'(?:sys\.exit|sys\.modules|sys\.path)'
            ],
            "severity": "medium",
            "description": "Potential system access - code may modify system state"
        },
        "sensitive_data": {
            "patterns": [
                r'(?:password|secret|key|token|apikey|credential)',
                r'(?:api[_-]?key|secret[_-]?key|access[_-]?token)',
                r'(?:AWS_ACCESS_KEY|GOOGLE_API_KEY|OPENAI_API_KEY)'
            ],
            "severity": "medium",
            "description": "Potential sensitive data exposure - code may contain secrets"
        },
        "runtime_modification": {
            "patterns": [
                r'(?:__globals__|__locals__|__dict__|__bases__|__class__)',
                r'(?:type\(|object\(|classmethod|staticmethod|property\()'
            ],
            "severity": "medium",
            "description": "Potential runtime modification - code may modify Python runtime"
        },
        "threading": {
            "patterns": [
                r'(?:threading\.|multiprocessing\.|concurrent\.)',
                r'(?:Thread\(|Process\(|Pool\(|Executor\()'
            ],
            "severity": "low",
            "description": "Potential threading - code may use concurrency"
        }
    }
    
    issues = []
    for issue_type, config in dangerous_patterns.items():
        for pattern in config["patterns"]:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                issues.append({
                    "type": issue_type,
                    "severity": config["severity"],
                    "description": config["description"],
                    "matches": list(set(matches))
                })
    
    return issues

def analyze_code_complexity(code):
    lines = code.split('\n')
    return {
        "total_lines": len(lines),
        "empty_lines": sum(1 for line in lines if line.strip() == ''),
        "comment_lines": sum(1 for line in lines if line.strip().startswith(('#', '//', '/*', '*'))),
        "code_lines": len(lines) - sum(1 for line in lines if line.strip() == '' or line.strip().startswith(('#', '//', '/*', '*'))),
        "function_count": len(re.findall(r'\bdef\s+\w+\s*\(', code)),
        "class_count": len(re.findall(r'\bclass\s+\w+', code)),
        "import_count": len(re.findall(r'\bimport\s+\w+|\bfrom\s+\w+\s+import', code))
    }

def analyze_code_style(code):
    issues = []
    if len(code) > 5000:
        issues.append({"type": "code_length", "severity": "medium", "message": "Code exceeds 5000 characters"})
    
    lines = code.split('\n')
    for i, line in enumerate(lines):
        if len(line) > 120:
            issues.append({"type": "line_length", "severity": "low", "message": f"Line {i+1} exceeds 120 characters"})
    
    return issues

def analyze_code(code, language):
    result = {
        "language": language,
        "analysis": {
            "safety": {},
            "complexity": {},
            "style": {},
            "summary": {}
        }
    }
    
    dangerous_issues = check_dangerous_code(code)
    complexity = analyze_code_complexity(code)
    style_issues = analyze_code_style(code)
    
    result["analysis"]["safety"] = {
        "issues": dangerous_issues,
        "total_issues": len(dangerous_issues),
        "high_severity_count": sum(1 for issue in dangerous_issues if issue["severity"] == "high"),
        "medium_severity_count": sum(1 for issue in dangerous_issues if issue["severity"] == "medium"),
        "low_severity_count": sum(1 for issue in dangerous_issues if issue["severity"] == "low"),
        "checked_patterns": ["command_injection", "code_execution", "file_access", "network_access", "system_access", "sensitive_data", "runtime_modification", "threading"],
        "recommendations": []
    }
    
    if len(dangerous_issues) == 0:
        result["analysis"]["safety"]["recommendations"].append("Code passes safety analysis")
        result["analysis"]["safety"]["recommendations"].append("Manual execution recommended in controlled environment")
    else:
        result["analysis"]["safety"]["recommendations"].append("Code contains potential security risks")
        result["analysis"]["safety"]["recommendations"].append("Review security issues before execution")
        result["analysis"]["safety"]["recommendations"].append("Do not execute untrusted code")
    
    result["analysis"]["complexity"] = complexity
    result["analysis"]["style"] = {
        "issues": style_issues,
        "total_issues": len(style_issues)
    }
    
    total_issues = len(dangerous_issues) + len(style_issues)
    if total_issues == 0:
        result["analysis"]["summary"]["rating"] = "A"
        result["analysis"]["summary"]["score"] = 100
    elif total_issues <= 2:
        result["analysis"]["summary"]["rating"] = "B"
        result["analysis"]["summary"]["score"] = 85
    elif total_issues <= 5:
        result["analysis"]["summary"]["rating"] = "C"
        result["analysis"]["summary"]["score"] = 70
    else:
        result["analysis"]["summary"]["rating"] = "D"
        result["analysis"]["summary"]["score"] = 50
    
    result["analysis"]["summary"]["is_safe_for_execution"] = len([i for i in dangerous_issues if i["severity"] == "high"]) == 0
    result["analysis"]["summary"]["recommendation"] = "Manual execution recommended" if result["analysis"]["summary"]["is_safe_for_execution"] else "Do not execute - contains high severity issues"
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: python execute_code.py <code content or file path> <language>"
        }, ensure_ascii=False))
        sys.exit(1)
    
    code_input = sys.argv[1]
    language = sys.argv[2].lower()
    
    if os.path.isfile(code_input):
        try:
            with open(code_input, 'r', encoding='utf-8') as f:
                code = f.read()
        except Exception as e:
            print(json.dumps({"error": f"Failed to read file: {str(e)}"}, ensure_ascii=False))
            sys.exit(1)
    else:
        code = code_input
    
    result = analyze_code(code, language)
    print(json.dumps(result, ensure_ascii=False, indent=2))
