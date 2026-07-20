import re
import sys
import json
import os

SENSITIVE_PATTERNS = {
    'password': [
        r'password\s*[=:]\s*["\']?\w+["\']?',
        r'pwd\s*[=:]\s*["\']?\w+["\']?',
        r'secret\s*[=:]\s*["\']?\w+["\']?',
        r'token\s*[=:]\s*["\']?\w+["\']?',
        r'api[_-]?key\s*[=:]\s*["\']?\w+["\']?'
    ],
    'sql_injection': [
        r'["\'].*SELECT.*FROM.*["\']',
        r'["\'].*INSERT INTO.*["\']',
        r'["\'].*UPDATE.*SET.*["\']',
        r'["\'].*DELETE FROM.*["\']',
        r'execute\s*\(\s*["\'].*["\']',
        r'query\s*\(\s*["\'].*["\']'
    ],
    'xss': [
        r'document\.write\s*\(',
        r'innerHTML\s*[=]',
        r'outerHTML\s*[=]',
        r'eval\s*\(',
        r'setTimeout\s*\(\s*["\']',
        r'setInterval\s*\(\s*["\']'
    ],
    'path_traversal': [
        r'\.\./',
        r'\.\.\\',
        r'/etc/passwd',
        r'/var/log/'
    ],
    'command_injection': [
        r'subprocess\.Popen\s*\(',
        r'os\.system\s*\(',
        r'os\.popen\s*\(',
        r'subprocess\.call\s*\(',
        r'eval\s*\(',
        r'exec\s*\('
    ],
    'hardcoded_secrets': [
        r'["\']?[a-zA-Z0-9]{32,}["\']?',
        r'["\']?[a-zA-Z0-9]{20,}["\']?',
        r'["\']?AKIA[A-Z0-9]{16}["\']?'
    ]
}

def scan_code(code):
    findings = {
        'critical': [],
        'high': [],
        'medium': [],
        'low': [],
        'info': []
    }
    
    for category, patterns in SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            for match in matches:
                finding = {
                    'category': category,
                    'pattern': pattern,
                    'match': match,
                    'line': find_line_number(code, match)
                }
                
                if category in ['password', 'hardcoded_secrets']:
                    findings['critical'].append(finding)
                elif category in ['sql_injection', 'command_injection']:
                    findings['high'].append(finding)
                elif category in ['xss', 'path_traversal']:
                    findings['medium'].append(finding)
                else:
                    findings['low'].append(finding)
    
    findings['info'].append({
        'message': f'Scan completed, found {sum(len(v) for v in findings.values())} potential security issues',
        'scan_time': '2026-07-16'
    })
    
    return findings

def find_line_number(code, match):
    lines = code.split('\n')
    for i, line in enumerate(lines, 1):
        if match in line:
            return i
    return None

def calculate_security_score(findings):
    score = 100
    
    score -= len(findings['critical']) * 20
    score -= len(findings['high']) * 10
    score -= len(findings['medium']) * 5
    score -= len(findings['low']) * 2
    
    return max(0, min(100, score))

def generate_security_report(findings):
    report = {
        'findings': findings,
        'security_score': calculate_security_score(findings),
        'summary': generate_summary(findings),
        'recommendations': generate_recommendations(findings)
    }
    
    return report

def generate_summary(findings):
    summary = []
    
    if findings['critical']:
        summary.append(f'Found {len(findings["critical"])} critical security issues')
    if findings['high']:
        summary.append(f'Found {len(findings["high"])} high severity security issues')
    if findings['medium']:
        summary.append(f'Found {len(findings["medium"])} medium severity security issues')
    if findings['low']:
        summary.append(f'Found {len(findings["low"])} low severity security issues')
    
    if not any([findings['critical'], findings['high'], findings['medium'], findings['low']]):
        summary.append('No obvious security issues found')
    
    return summary

def generate_recommendations(findings):
    recommendations = []
    
    if findings['critical']:
        recommendations.append('[URGENT] Found hardcoded secrets or passwords, please remove immediately and use environment variables')
    
    if findings['high']:
        recommendations.append('[IMPORTANT] Found SQL injection or command injection risks, please use parameterized queries')
    
    if findings['medium']:
        recommendations.append('[WARNING] Found XSS or path traversal risks, please implement input validation and escaping')
    
    if findings['low']:
        recommendations.append('[SUGGESTION] Found potential security concerns, please conduct code review')
    
    recommendations.append('Consider using environment variables for sensitive configuration')
    recommendations.append('Consider implementing strict input validation and filtering')
    recommendations.append('Consider using ORM framework to prevent SQL injection')
    recommendations.append('Consider implementing HTML escaping for output content')
    
    return recommendations

def audit_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    findings = scan_code(code)
    report = generate_security_report(findings)
    
    return report

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(json.dumps({'error': 'Please provide code file path'}))
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(json.dumps({'error': 'File does not exist'}))
        sys.exit(1)
    
    report = audit_file(file_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
