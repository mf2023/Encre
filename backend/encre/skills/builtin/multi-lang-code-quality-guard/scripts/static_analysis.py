import subprocess
import sys
import os
import json
import re

def run_pylint(code_path):
    try:
        result = subprocess.run(
            ['pylint', code_path, '--output-format=json'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return parse_pylint_text(result.stdout)
        return []
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

def parse_pylint_text(text):
    issues = []
    for line in text.split('\n'):
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 4:
                issues.append({
                    'line': int(parts[1].strip()) if parts[1].strip().isdigit() else None,
                    'column': int(parts[2].strip()) if parts[2].strip().isdigit() else None,
                    'message': parts[3].strip()
                })
    return issues

def run_flake8(code_path):
    try:
        result = subprocess.run(
            ['flake8', code_path, '--format=json'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return parse_flake8_text(result.stdout)
        return []
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

def parse_flake8_text(text):
    issues = []
    pattern = re.compile(r'(.+):(\d+):(\d+): (\w+) (.+)')
    for line in text.split('\n'):
        match = pattern.match(line)
        if match:
            issues.append({
                'line': int(match.group(2)),
                'column': int(match.group(3)),
                'code': match.group(4),
                'message': match.group(5)
            })
    return issues

def calculate_code_metrics(code):
    lines = code.split('\n')
    total_lines = len(lines)
    code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('#'))
    comment_lines = sum(1 for line in lines if line.strip().startswith('#'))
    blank_lines = sum(1 for line in lines if not line.strip())
    
    functions = len(re.findall(r'\bdef\s+\w+\s*\(', code))
    classes = len(re.findall(r'\bclass\s+\w+\s*[:{]', code))
    docstrings = len(re.findall(r'""".*?"""', code, re.DOTALL))
    
    return {
        'total_lines': total_lines,
        'code_lines': code_lines,
        'comment_lines': comment_lines,
        'blank_lines': blank_lines,
        'functions': functions,
        'classes': classes,
        'docstrings': docstrings,
        'comment_ratio': round(comment_lines / max(code_lines, 1) * 100, 1) if code_lines > 0 else 0
    }

def analyze_code(code_path):
    with open(code_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    pylint_issues = run_pylint(code_path)
    flake8_issues = run_flake8(code_path)
    
    metrics = calculate_code_metrics(code)
    
    all_issues = []
    for issue in pylint_issues:
        all_issues.append({
            'type': 'pylint',
            'line': issue.get('line'),
            'message': issue.get('message', '')
        })
    
    for issue in flake8_issues:
        all_issues.append({
            'type': 'flake8',
            'line': issue.get('line'),
            'code': issue.get('code', ''),
            'message': issue.get('message', '')
        })
    
    score = calculate_quality_score(all_issues, metrics)
    
    return {
        'metrics': metrics,
        'pylint_issues': pylint_issues,
        'flake8_issues': flake8_issues,
        'all_issues': all_issues,
        'quality_score': score,
        'recommendations': generate_recommendations(all_issues, metrics)
    }

def calculate_quality_score(issues, metrics):
    score = 100
    
    score -= len(issues) * 2
    
    if metrics['comment_ratio'] < 5:
        score -= 10
    elif metrics['comment_ratio'] < 10:
        score -= 5
    
    if metrics['docstrings'] == 0 and (metrics['functions'] > 0 or metrics['classes'] > 0):
        score -= 10
    
    for issue in issues:
        if 'error' in issue.get('message', '').lower():
            score -= 5
        elif 'warning' in issue.get('message', '').lower():
            score -= 2
    
    return max(0, min(100, score))

def generate_recommendations(issues, metrics):
    recommendations = []
    
    if metrics['comment_ratio'] < 10:
        recommendations.append('Consider adding more code comments to improve readability')
    
    if metrics['docstrings'] == 0 and (metrics['functions'] > 0 or metrics['classes'] > 0):
        recommendations.append('Consider adding docstrings for functions and classes')
    
    error_count = sum(1 for issue in issues if 'error' in issue.get('message', '').lower())
    if error_count > 0:
        recommendations.append(f'Found {error_count} errors, recommend fixing first')
    
    warning_count = sum(1 for issue in issues if 'warning' in issue.get('message', '').lower())
    if warning_count > 5:
        recommendations.append(f'Found {warning_count} warnings, recommend reviewing each')
    
    if not issues:
        recommendations.append('Code quality is good, keep up the good work')
    
    return recommendations

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(json.dumps({'error': 'Please provide code file path'}))
        sys.exit(1)
    
    code_path = sys.argv[1]
    
    if not os.path.exists(code_path):
        print(json.dumps({'error': 'File does not exist'}))
        sys.exit(1)
    
    result = analyze_code(code_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
