import re
import sys
import os
import json

def extract_functions(code, language='python'):
    functions = []
    
    if language == 'python':
        pattern = r'\bdef\s+(\w+)\s*\(([^)]*)\)\s*:'
        matches = re.findall(pattern, code)
        for func_name, params in matches:
            func_code = extract_function_body(code, func_name, 'python')
            functions.append({
                'name': func_name,
                'params': [p.strip() for p in params.split(',') if p.strip()],
                'body': func_code,
                'return_type': infer_return_type(func_code)
            })
    
    elif language == 'java':
        pattern = r'(public|private|protected)\s+(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{?'
        matches = re.findall(pattern, code)
        for modifier, return_type, func_name, params in matches:
            if return_type not in ['class', 'interface', 'enum']:
                functions.append({
                    'name': func_name,
                    'params': parse_java_params(params),
                    'return_type': return_type,
                    'body': ''
                })
    
    elif language == 'javascript':
        pattern = r'function\s+(\w+)\s*\(([^)]*)\)\s*\{?'
        matches = re.findall(pattern, code)
        for func_name, params in matches:
            functions.append({
                'name': func_name,
                'params': [p.strip() for p in params.split(',') if p.strip()],
                'return_type': 'any',
                'body': ''
            })
        
        arrow_pattern = r'(\w+)\s*=\s*\(([^)]*)\)\s*=>'
        matches = re.findall(arrow_pattern, code)
        for func_name, params in matches:
            functions.append({
                'name': func_name,
                'params': [p.strip() for p in params.split(',') if p.strip()],
                'return_type': 'any',
                'body': ''
            })
    
    elif language == 'go':
        pattern = r'func\s+(\w+)\s*\(([^)]*)\)\s*(\w+)?\s*\{?'
        matches = re.findall(pattern, code)
        for func_name, params, return_type in matches:
            functions.append({
                'name': func_name,
                'params': parse_go_params(params),
                'return_type': return_type if return_type else 'void',
                'body': ''
            })
    
    elif language == 'cpp':
        pattern = r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{?'
        matches = re.findall(pattern, code)
        for return_type, func_name, params in matches:
            if return_type not in ['class', 'struct', 'enum']:
                functions.append({
                    'name': func_name,
                    'params': parse_cpp_params(params),
                    'return_type': return_type,
                    'body': ''
                })
    
    elif language == 'rust':
        pattern = r'fn\s+(\w+)\s*\(([^)]*)\)\s*->?\s*(\w+)?\s*\{?'
        matches = re.findall(pattern, code)
        for func_name, params, return_type in matches:
            functions.append({
                'name': func_name,
                'params': parse_rust_params(params),
                'return_type': return_type if return_type else '()',
                'body': ''
            })
    
    return functions

def extract_function_body(code, func_name, language):
    lines = code.split('\n')
    start_line = None
    
    if language == 'python':
        for i, line in enumerate(lines):
            if re.match(r'\bdef\s+' + func_name + r'\s*\(', line):
                start_line = i
                break
    
    if start_line is None:
        return ''
    
    if language == 'python':
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
    
    return ''

def infer_return_type(func_body):
    if 'return' in func_body:
        if 'return True' in func_body or 'return False' in func_body:
            return 'bool'
        elif 'return ' in func_body:
            return 'any'
    return 'void'

def parse_java_params(params_str):
    params = []
    if not params_str.strip():
        return params
    for param in params_str.split(','):
        param = param.strip()
        if param:
            parts = param.split()
            if len(parts) >= 2:
                params.append({'type': parts[0], 'name': parts[1]})
    return params

def parse_go_params(params_str):
    params = []
    if not params_str.strip():
        return params
    for param in params_str.split(','):
        param = param.strip()
        if param:
            parts = param.split()
            if len(parts) >= 2:
                params.append({'type': parts[1], 'name': parts[0]})
    return params

def parse_cpp_params(params_str):
    params = []
    if not params_str.strip():
        return params
    for param in params_str.split(','):
        param = param.strip()
        if param:
            parts = param.split()
            if len(parts) >= 2:
                params.append({'type': parts[0], 'name': parts[1]})
    return params

def parse_rust_params(params_str):
    params = []
    if not params_str.strip():
        return params
    for param in params_str.split(','):
        param = param.strip()
        if param:
            parts = param.split(':')
            if len(parts) >= 2:
                params.append({'name': parts[0].strip(), 'type': parts[1].strip()})
    return params

def generate_test_cases(functions, language='python'):
    test_cases = []
    
    for func in functions:
        if func['name'].startswith('_'):
            continue
        
        cases = generate_test_case_for_function(func, language)
        test_cases.extend(cases)
    
    return test_cases

def generate_test_case_for_function(func, language):
    cases = []
    
    if language == 'python':
        cases.append(generate_python_test_case(func))
    
    elif language == 'java':
        cases.append(generate_java_test_case(func))
    
    elif language == 'javascript':
        cases.append(generate_javascript_test_case(func))
    
    elif language == 'go':
        cases.append(generate_go_test_case(func))
    
    elif language == 'cpp':
        cases.append(generate_cpp_test_case(func))
    
    elif language == 'rust':
        cases.append(generate_rust_test_case(func))
    
    return cases

def generate_python_test_case(func):
    test_name = f"test_{func['name']}"
    param_names = func['params']
    
    normal_args = []
    zero_args = []
    for param_name in param_names:
        if is_list_parameter(func['body'], param_name):
            normal_args.append('[1, 2, 3]')
            zero_args.append('[0, 0, 0]')
        elif is_string_parameter(func['body'], param_name):
            normal_args.append('"test"')
            zero_args.append('""')
        elif is_dict_parameter(func['body'], param_name):
            normal_args.append("{'key': 'value'}")
            zero_args.append('{}')
        else:
            normal_args.append('1')
            zero_args.append('0')
    
    empty_test = generate_empty_test(func, param_names)
    
    if param_names:
        test_code = f"""def {test_name}():
    # Test normal case
    result = module.{func['name']}({', '.join(normal_args)})
    assert result is not None, "Function return value should not be None"
    
    # Test boundary case
    result = module.{func['name']}({', '.join(zero_args)})
    assert result is not None, "Function should handle zero value input"
    
    # Test empty input (if applicable)
    {empty_test}
    
    print(f"{test_name} passed")
"""
    else:
        test_code = f"""def {test_name}():
    # Test function execution
    result = module.{func['name']}()
    assert result is not None, "Function return value should not be None"
    print(f"{test_name} passed")
"""
    
    return {'name': test_name, 'code': test_code}

def is_list_parameter(func_body, param_name):
    patterns = [
        rf'{param_name}\.',
        rf'len\({param_name}\)',
        rf'{param_name}\[',
        rf'for .+ in {param_name}'
    ]
    for pattern in patterns:
        if re.search(pattern, func_body):
            return True
    return False

def is_string_parameter(func_body, param_name):
    patterns = [
        rf'{param_name}\.strip',
        rf'{param_name}\.split',
        rf'{param_name}\.join',
        rf'{param_name}\.upper',
        rf'{param_name}\.lower'
    ]
    for pattern in patterns:
        if re.search(pattern, func_body):
            return True
    return False

def is_dict_parameter(func_body, param_name):
    patterns = [
        rf'{param_name}\[',
        rf'{param_name}\.get',
        rf'{param_name}\.keys',
        rf'{param_name}\.values'
    ]
    for pattern in patterns:
        if re.search(pattern, func_body):
            return True
    return False

def generate_empty_test(func, param_names):
    empty_args = []
    for param_name in param_names:
        if is_list_parameter(func['body'], param_name):
            empty_args.append('[]')
        elif is_string_parameter(func['body'], param_name):
            empty_args.append('""')
        elif is_dict_parameter(func['body'], param_name):
            empty_args.append('{}')
        else:
            return ''
    
    if empty_args:
        return f"""result = module.{func['name']}({', '.join(empty_args)})
    assert result is not None, "Function should handle empty input"
"""
    return ''

def generate_java_test_case(func):
    test_name = f"test{func['name'].capitalize()}"
    param_types = [p['type'] for p in func['params']]
    
    test_code = f"""@Test
public void {test_name}() {{
    // Test normal case
    {func['return_type']} result = {func['name']}({generate_java_args(param_types)});
    assertNotNull(result);
    
    // Test boundary case
    {func['return_type']} result2 = {func['name']}({generate_java_zero_args(param_types)});
    assertNotNull(result2);
    
    System.out.println("{test_name} passed");
}}
"""
    return {'name': test_name, 'code': test_code}

def generate_java_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('1')
        elif p_type == 'String':
            args.append('"test"')
        elif p_type == 'boolean':
            args.append('true')
        elif p_type == 'double':
            args.append('1.0')
        else:
            args.append('null')
    return ', '.join(args)

def generate_java_zero_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('0')
        elif p_type == 'String':
            args.append('""')
        elif p_type == 'boolean':
            args.append('false')
        elif p_type == 'double':
            args.append('0.0')
        else:
            args.append('null')
    return ', '.join(args)

def generate_javascript_test_case(func):
    test_name = f"test_{func['name']}"
    param_count = len(func['params'])
    
    test_code = f"""function {test_name}() {{
    // Test normal case
    const result = {func['name']}({', '.join(['1'] * param_count)});
    console.assert(result !== undefined, "Function return value should not be undefined");
    
    // Test boundary case
    const result2 = {func['name']}({', '.join(['0'] * param_count)});
    console.assert(result2 !== undefined, "Function should handle zero value input");
    
    console.log("{test_name} passed");
}}

{test_name}();
"""
    return {'name': test_name, 'code': test_code}

def generate_go_test_case(func):
    test_name = f"Test{func['name'].capitalize()}"
    param_types = [p['type'] for p in func['params']]
    
    test_code = f"""func {test_name}(t *testing.T) {{
    // Test normal case
    result := {func['name']}({generate_go_args(param_types)})
    if result == nil {{
        t.Error("Function return value should not be nil")
    }}
    
    // Test boundary case
    result2 := {func['name']}({generate_go_zero_args(param_types)})
    if result2 == nil {{
        t.Error("Function should handle zero value input")
    }}
    
    t.Log("{test_name} passed")
}}
"""
    return {'name': test_name, 'code': test_code}

def generate_go_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('1')
        elif p_type == 'string':
            args.append('"test"')
        elif p_type == 'bool':
            args.append('true')
        elif p_type == 'float64':
            args.append('1.0')
        else:
            args.append('nil')
    return ', '.join(args)

def generate_go_zero_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('0')
        elif p_type == 'string':
            args.append('""')
        elif p_type == 'bool':
            args.append('false')
        elif p_type == 'float64':
            args.append('0.0')
        else:
            args.append('nil')
    return ', '.join(args)

def generate_cpp_test_case(func):
    test_name = f"test_{func['name']}"
    param_types = [p['type'] for p in func['params']]
    
    test_code = f"""void {test_name}() {{
    // Test normal case
    {func['return_type']} result = {func['name']}({generate_cpp_args(param_types)});
    assert(result != NULL);
    
    // Test boundary case
    {func['return_type']} result2 = {func['name']}({generate_cpp_zero_args(param_types)});
    assert(result2 != NULL);
    
    std::cout << "{test_name} passed" << std::endl;
}}
"""
    return {'name': test_name, 'code': test_code}

def generate_cpp_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('1')
        elif p_type == 'std::string':
            args.append('"test"')
        elif p_type == 'bool':
            args.append('true')
        elif p_type == 'double':
            args.append('1.0')
        else:
            args.append('NULL')
    return ', '.join(args)

def generate_cpp_zero_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'int':
            args.append('0')
        elif p_type == 'std::string':
            args.append('""')
        elif p_type == 'bool':
            args.append('false')
        elif p_type == 'double':
            args.append('0.0')
        else:
            args.append('NULL')
    return ', '.join(args)

def generate_rust_test_case(func):
    test_name = f"test_{func['name']}"
    param_types = [p['type'] for p in func['params']]
    
    test_code = f"""#[test]
fn {test_name}() {{
    // Test normal case
    let result = {func['name']}({generate_rust_args(param_types)});
    assert!(result.is_some());
    
    // Test boundary case
    let result2 = {func['name']}({generate_rust_zero_args(param_types)});
    assert!(result2.is_some());
    
    println!("{test_name} passed");
}}
"""
    return {'name': test_name, 'code': test_code}

def generate_rust_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'i32' or p_type == 'i64':
            args.append('1')
        elif p_type == 'String':
            args.append('"test".to_string()')
        elif p_type == 'bool':
            args.append('true')
        elif p_type == 'f64':
            args.append('1.0')
        else:
            args.append('None')
    return ', '.join(args)

def generate_rust_zero_args(param_types):
    args = []
    for p_type in param_types:
        if p_type == 'i32' or p_type == 'i64':
            args.append('0')
        elif p_type == 'String':
            args.append('"".to_string()')
        elif p_type == 'bool':
            args.append('false')
        elif p_type == 'f64':
            args.append('0.0')
        else:
            args.append('None')
    return ', '.join(args)

def generate_test_file(code_path, language='python'):
    with open(code_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    functions = extract_functions(code, language)
    test_cases = generate_test_cases(functions, language)
    
    test_code = generate_test_file_content(test_cases, language, code_path)
    
    test_file_path = generate_test_file_path(code_path, language)
    
    with open(test_file_path, 'w', encoding='utf-8') as f:
        f.write(test_code)
    
    return {
        'test_file_path': test_file_path,
        'functions': [f['name'] for f in functions],
        'test_cases': [tc['name'] for tc in test_cases],
        'test_code': test_code
    }

def generate_test_file_content(test_cases, language, code_path):
    file_name = os.path.basename(code_path)
    
    if language == 'python':
        return f'''"""Automatically generated unit test file"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import tested module
module_name = os.path.splitext("{file_name}")[0]
module = __import__(module_name)

{''.join(tc['code'] for tc in test_cases)}

if __name__ == "__main__":
    {', '.join(tc['name'] + '()' for tc in test_cases)}
    print("All tests passed")
'''
    
    elif language == 'java':
        return f"""import static org.junit.Assert.*;
import org.junit.Test;

public class Test{file_name.replace('.java', '')} {{
{''.join(tc['code'] for tc in test_cases)}
}}
"""
    
    elif language == 'javascript':
        return f"""/**
 * Automatically generated unit test file
 * Dependencies: mocha or run directly
 */

const code = require('./{file_name}');

{''.join(tc['code'] for tc in test_cases)}
"""
    
    elif language == 'go':
        return f"""package main

import (
    "testing"
)

{''.join(tc['code'] for tc in test_cases)}
"""
    
    elif language == 'cpp':
        return f"""#include <iostream>
#include <cassert>
#include "{file_name}"

{''.join(tc['code'] for tc in test_cases)}

int main() {{
    {', '.join(tc['name'] + '()' for tc in test_cases)}
    std::cout << "All tests passed" << std::endl;
    return 0;
}}
"""
    
    elif language == 'rust':
        return f"""use std::option::Option;

{''.join(tc['code'] for tc in test_cases)}
"""
    
    return ''

def generate_test_file_path(code_path, language):
    base_name = os.path.splitext(code_path)[0]
    
    if language == 'python':
        return f"{base_name}_test.py"
    elif language == 'java':
        return f"Test{os.path.basename(base_name)}.java"
    elif language == 'javascript':
        return f"{base_name}_test.js"
    elif language == 'go':
        return f"{base_name}_test.go"
    elif language == 'cpp':
        return f"{base_name}_test.cpp"
    elif language == 'rust':
        return f"{base_name}_test.rs"
    
    return f"{base_name}_test.py"

def run_tests(test_file_path, language='python'):
    import subprocess
    
    result = {
        'success': False,
        'output': '',
        'error': '',
        'passed': 0,
        'failed': 0,
        'total': 0
    }
    
    try:
        if language == 'python':
            proc = subprocess.run(
                [sys.executable, test_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                text=True
            )
        elif language == 'javascript':
            proc = subprocess.run(
                ['node', test_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                text=True
            )
        elif language == 'go':
            proc = subprocess.run(
                ['go', 'test', '-v', test_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                text=True
            )
        else:
            result['error'] = f'Unsupported test language: {language}'
            return result
        
        result['output'] = proc.stdout.strip()
        result['error'] = proc.stderr.strip()
        
        if proc.returncode == 0:
            result['success'] = True
            result['passed'] = count_test_passes(result['output'])
            result['total'] = result['passed']
        else:
            result['failed'] = count_test_failures(result['error'])
            result['passed'] = count_test_passes(result['output'])
            result['total'] = result['passed'] + result['failed']
        
    except subprocess.TimeoutExpired:
        result['error'] = 'Test execution timeout'
    except FileNotFoundError as e:
        result['error'] = f'Runtime not found: {e.filename}'
    except Exception as e:
        result['error'] = str(e)
    
    return result

def count_test_passes(output):
    return output.count('passed') + output.count('PASS') + output.count('passed')

def count_test_failures(error):
    return error.count('FAIL') + error.count('failed') + error.count('Error')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Please provide code file path'}))
        sys.exit(1)
    
    language = 'python'
    if len(sys.argv) >= 3:
        language = sys.argv[2]
    
    code_path = sys.argv[1]
    
    if not os.path.exists(code_path):
        print(json.dumps({'error': 'File does not exist'}))
        sys.exit(1)
    
    result = generate_test_file(code_path, language)
    
    output = {
        'test_file': result,
        'test_result': {
            'success': False,
            'message': 'Tests are not automatically executed. Please manually run the generated test file.',
            'test_file_path': result['test_file_path'],
            'run_command': f'python {result["test_file_path"]}' if language == 'python' else f'{language} {result["test_file_path"]}'
        }
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2))
