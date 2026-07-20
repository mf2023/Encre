import re
import sys
import json
import os

def analyze_code_structure(code):
    structure = {
        'functions': [],
        'classes': [],
        'imports': [],
        'global_vars': [],
        'complexity': []
    }
    
    imports = re.findall(r'^(import|from)\s+(\w+)', code, re.MULTILINE)
    structure['imports'] = [f'{imp[0]} {imp[1]}' for imp in imports]
    
    functions = re.findall(r'\bdef\s+(\w+)\s*\(([^)]*)\)\s*:', code)
    for func_name, params in functions:
        func_code = extract_function_code(code, func_name)
        complexity = calculate_complexity(func_code)
        structure['functions'].append({
            'name': func_name,
            'params': params.strip(),
            'line_count': len(func_code.split('\n')),
            'complexity': complexity
        })
    
    classes = re.findall(r'\bclass\s+(\w+)\s*[:{]', code)
    for cls_name in classes:
        cls_code = extract_class_code(code, cls_name)
        structure['classes'].append({
            'name': cls_name,
            'line_count': len(cls_code.split('\n'))
        })
    
    global_vars = re.findall(r'^(\w+)\s*[=]', code, re.MULTILINE)
    structure['global_vars'] = list(set(global_vars) - set([f['name'] for f in structure['functions']]) - set(structure['classes']))
    
    return structure

def extract_function_code(code, func_name):
    lines = code.split('\n')
    start_line = None
    for i, line in enumerate(lines):
        if re.match(r'\bdef\s+' + func_name + r'\s*\(', line):
            start_line = i
            break
    
    if start_line is None:
        return ''
    
    indent_level = len(lines[start_line]) - len(lines[start_line].lstrip())
    func_lines = [lines[start_line]]
    
    for i in range(start_line + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            func_lines.append(line)
            continue
        
        current_indent = len(line) - len(line.lstrip())
        if current_indent > indent_level:
            func_lines.append(line)
        else:
            break
    
    return '\n'.join(func_lines)

def extract_class_code(code, cls_name):
    lines = code.split('\n')
    start_line = None
    for i, line in enumerate(lines):
        if re.match(r'\bclass\s+' + cls_name + r'\s*[:{]', line):
            start_line = i
            break
    
    if start_line is None:
        return ''
    
    indent_level = len(lines[start_line]) - len(lines[start_line].lstrip())
    cls_lines = [lines[start_line]]
    
    for i in range(start_line + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            cls_lines.append(line)
            continue
        
        current_indent = len(line) - len(line.lstrip())
        if current_indent > indent_level or (current_indent == indent_level and line.strip()):
            cls_lines.append(line)
        else:
            break
    
    return '\n'.join(cls_lines)

def calculate_complexity(code):
    complexity = 1
    
    complexity += code.count('if')
    complexity += code.count('elif')
    complexity += code.count('else')
    complexity += code.count('for')
    complexity += code.count('while')
    complexity += code.count('and')
    complexity += code.count('or')
    complexity += code.count('case')
    
    return complexity

def identify_refactor_opportunities(code):
    opportunities = {
        'long_functions': [],
        'high_complexity': [],
        'duplicate_code': [],
        'missing_docstrings': [],
        'naming_issues': [],
        'improvements': []
    }
    
    structure = analyze_code_structure(code)
    
    for func in structure['functions']:
        if func['line_count'] > 50:
            opportunities['long_functions'].append({
                'name': func['name'],
                'line_count': func['line_count'],
                'suggestion': 'Function is too long, consider splitting into multiple smaller functions'
            })
        
        if func['complexity'] > 10:
            opportunities['high_complexity'].append({
                'name': func['name'],
                'complexity': func['complexity'],
                'suggestion': 'Function complexity is high, consider simplifying logic or splitting'
            })
        
        if not has_docstring(extract_function_code(code, func['name'])):
            opportunities['missing_docstrings'].append({
                'name': func['name'],
                'suggestion': 'Consider adding docstring'
            })
        
        if not is_good_naming(func['name']):
            opportunities['naming_issues'].append({
                'name': func['name'],
                'suggestion': 'Consider using more descriptive function names'
            })
    
    if len(structure['global_vars']) > 5:
        opportunities['improvements'].append('Too many global variables, consider encapsulating as class attributes or using configuration objects')
    
    duplicate_blocks = find_duplicate_code(code)
    if duplicate_blocks:
        opportunities['duplicate_code'] = [
            {'location': f'line {block["line"]}', 'suggestion': 'Found duplicate code block, consider extracting as function'}
            for block in duplicate_blocks
        ]
    
    return opportunities

def has_docstring(func_code):
    lines = func_code.split('\n')
    if len(lines) > 1:
        second_line = lines[1].strip()
        return second_line.startswith('"""') or second_line.startswith("'''")
    return False

def is_good_naming(name):
    if len(name) < 3:
        return False
    if name.islower():
        return True
    return False

def find_duplicate_code(code, min_length=5):
    lines = code.split('\n')
    seen = {}
    duplicates = []
    
    for i in range(len(lines) - min_length + 1):
        block = '\n'.join(lines[i:i+min_length])
        if block.strip() and len(block.strip()) > 20:
            if block in seen:
                duplicates.append({'line': i + 1})
            else:
                seen[block] = i
    
    return duplicates

def generate_refactor_report(code_path):
    with open(code_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    structure = analyze_code_structure(code)
    opportunities = identify_refactor_opportunities(code)
    
    report = {
        'structure': structure,
        'refactor_opportunities': opportunities,
        'summary': generate_summary(structure, opportunities),
        'recommendations': generate_recommendations(opportunities)
    }
    
    return report

def generate_summary(structure, opportunities):
    summary = []
    
    summary.append(f'Code contains {len(structure["functions"])} functions, {len(structure["classes"])} classes')
    
    if opportunities['long_functions']:
        summary.append(f'{len(opportunities["long_functions"])} functions are too long')
    
    if opportunities['high_complexity']:
        summary.append(f'{len(opportunities["high_complexity"])} functions have high complexity')
    
    if opportunities['missing_docstrings']:
        summary.append(f'{len(opportunities["missing_docstrings"])} functions are missing docstrings')
    
    return summary

def generate_recommendations(opportunities):
    recommendations = []
    
    if opportunities['long_functions']:
        recommendations.append('Consider splitting long functions, each function should have a single responsibility')
    
    if opportunities['high_complexity']:
        recommendations.append('Consider reducing function complexity using early returns, strategy pattern, etc.')
    
    if opportunities['missing_docstrings']:
        recommendations.append('Consider adding docstrings for all public functions')
    
    if opportunities['duplicate_code']:
        recommendations.append('Consider extracting duplicate code into common functions')
    
    if opportunities['naming_issues']:
        recommendations.append('Consider using more descriptive naming, following PEP8 standards')
    
    if not any([opportunities['long_functions'], opportunities['high_complexity'], 
                opportunities['missing_docstrings'], opportunities['duplicate_code']]):
        recommendations.append('Code structure is good, keep up the good work')
    
    return recommendations

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(json.dumps({'error': 'Please provide code file path'}))
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(json.dumps({'error': 'File does not exist'}))
        sys.exit(1)
    
    report = generate_refactor_report(file_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
