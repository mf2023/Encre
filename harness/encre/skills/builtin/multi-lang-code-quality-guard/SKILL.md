---
name: multi-lang-code-quality-guard
description: Input natural language functional requirements, generate multi-language code (Python/Java/JS/Go/Rust/C++), automatically generate unit test cases, perform static analysis and security audit, analyze code safety and complexity, and output comprehensive quality report; applicable for student homework checking, developer code review, code quality assurance scenarios; trigger words: code review, check code quality, security audit, generate code, code testing, code optimization, code detection, code validation, generate test cases, code safety analysis
---

# Multi-Language Code Quality Guard

## Function Description

This tool implements a complete "code generation - safety analysis - static analysis - security audit - optimization" pipeline:
1. Generate multi-language code based on user requirements (Python/Java/JavaScript/Go/Rust/C++)
2. Automatically generate unit test cases
3. Perform comprehensive safety analysis to detect dangerous patterns
4. Perform code complexity and style analysis
5. Perform static code analysis (pylint/flake8) for all languages
6. Execute security audit (sensitive information, vulnerability scanning)
7. Provide code refactoring suggestions
8. Output comprehensive quality report

## Competition Topic

- Category: II. Intelligent Analysis and Decision Making
- Covered Topic: Code Intelligent Assistance and Quality Assurance

## Core Capabilities

1. **Multi-language Code Generation**: Generate Python/Java/JavaScript/Go/Rust/C++ code based on natural language requirements
2. **Unit Test Generation**: Automatically extract function signatures, generate unit test cases
3. **Safety Analysis**: Static detection of dangerous patterns (command injection, eval, file/network/system access, threading)
4. **Complexity Analysis**: Analyze code complexity metrics including lines of code, function count, class count
5. **Static Analysis**: Integrate pylint/flake8, output code quality score
6. **Security Audit**: Detect SQL injection, XSS, command injection, sensitive information leakage and other vulnerabilities
7. **Refactoring Suggestions**: Identify code structure issues, provide optimization suggestions

## Standard Workflow

```
User Requirement → Code Generation → Unit Test Generation → Safety Analysis → Complexity Analysis → Static Analysis → Security Audit → Quality Report
```

### Step-by-step Explanation

1. **Receive Requirement**: User inputs natural language functional requirement, optionally specifying programming language
2. **Code Generation**: Generate complete code in the target language, save as temporary file
3. **Unit Test Generation**: Call `scripts/test_generator.py` to extract functions and generate test cases
4. **Safety Analysis**: Call `scripts/execute_code.py` to perform comprehensive static safety analysis, detect dangerous patterns (command injection, eval, file/network/system access, threading)
5. **Complexity Analysis**: Analyze code complexity metrics (lines of code, function count, class count, import count)
6. **Static Analysis**: Call `scripts/static_analysis.py` for pylint/flake8 checking
7. **Security Audit**: Call `scripts/security_audit.py` for security scanning
8. **Refactoring Analysis**: Call `scripts/code_refactor.py` to analyze code structure
9. **Generate Report**: Summarize all detection results, output comprehensive quality report

## Tool Calling Specifications

### execute_code.py
- **Purpose**: Perform comprehensive static safety analysis, detect dangerous code patterns, analyze code complexity and style
- **Analysis Features**: 
  - Safety analysis: detect 8 categories of dangerous patterns (command injection, code execution, file access, network access, system access, sensitive data, runtime modification, threading)
  - Complexity analysis: lines of code, function count, class count, import count
  - Style analysis: code length, line length checking
  - Risk rating: A/B/C/D rating based on detected issues
- **Supported Languages**: All languages (Python/Java/JavaScript/Go/Rust/C++)
- **Usage**: `python scripts/execute_code.py <code content or file path> <language>`
- **Input**: Code string or file path, optional language parameter (python/java/javascript/go/rust/cpp)
- **Output**: JSON formatted static analysis report
- **Return Fields**:
  - `analysis.safety.issues`: List of detected security issues with severity and description
  - `analysis.safety.total_issues`: Total number of security issues
  - `analysis.safety.high_severity_count`: Number of high severity issues
  - `analysis.safety.medium_severity_count`: Number of medium severity issues
  - `analysis.safety.low_severity_count`: Number of low severity issues
  - `analysis.safety.checked_patterns`: List of checked dangerous pattern categories
  - `analysis.safety.recommendations`: Safety recommendations
  - `analysis.complexity`: Code complexity metrics
  - `analysis.style.issues`: Style issues
  - `analysis.summary.rating`: Overall rating (A/B/C/D)
  - `analysis.summary.score`: Overall score (0-100)
  - `analysis.summary.is_safe_for_execution`: Whether code is safe for manual execution
  - `analysis.summary.recommendation`: Execution recommendation
  - `language`: Programming language used

### test_generator.py
- **Purpose**: Automatically extract function signatures, generate unit test cases
- **Usage**: `python scripts/test_generator.py <code file path> <language>`
- **Input**: Code file path, optional language parameter (python/java/javascript/go/rust/cpp)
- **Output**: JSON formatted test generation result (tests are not automatically executed)
- **Return Fields**:
  - `test_file.test_file_path`: Generated test file path
  - `test_file.functions`: Extracted function list
  - `test_file.test_cases`: Generated test case list
  - `test_result.message`: Information about test execution status
  - `test_result.test_file_path`: Path to generated test file
  - `test_result.run_command`: Command to manually run tests

### static_analysis.py
- **Purpose**: Static code analysis, detect code style issues
- **Usage**: `python scripts/static_analysis.py <code file path>`
- **Input**: Code file path
- **Output**: JSON formatted analysis result
- **Return Fields**:
  - `metrics`: Code metrics (lines, functions, comment ratio, etc.)
  - `pylint_issues`: pylint detection results
  - `flake8_issues`: flake8 detection results
  - `quality_score`: Code quality score
  - `recommendations`: Improvement suggestions

### security_audit.py
- **Purpose**: Security audit, detect security vulnerabilities
- **Usage**: `python scripts/security_audit.py <code file path>`
- **Input**: Code file path
- **Output**: JSON formatted security report
- **Return Fields**:
  - `findings.critical/high/medium/low`: Security issues by severity
  - `security_score`: Security score
  - `summary`: Security issue summary
  - `recommendations`: Security improvement suggestions

### code_refactor.py
- **Purpose**: Code structure analysis, provide refactoring suggestions
- **Usage**: `python scripts/code_refactor.py <code file path>`
- **Input**: Code file path
- **Output**: JSON formatted refactoring analysis report
- **Return Fields**:
  - `structure`: Code structure (functions, classes, imports)
  - `refactor_opportunities`: Refactoring opportunities
  - `summary`: Analysis summary
  - `recommendations`: Refactoring suggestions

## Input Validation Rules

1. **Requirement Description**: Must contain clear functional description, supports specifying programming language (Python/Java/JavaScript/Go/Rust/C++)
2. **Code File**: Must be valid source code file, supports Python/Java/JavaScript/Go/Rust/C++
3. **Security**: Must not contain sensitive information (passwords, keys, etc.)
4. **Resource Limits**: Analysis timeout is 30 seconds, code size limit is 5000 lines
5. **Test Generation**: Only generates test cases for code containing function definitions

## Edge Case Handling

1. **Unclear Requirements**: Prompt user to supplement key information (programming language, input/output, functional details)
2. **Code Analysis Issues**: Automatically analyze detected issues, provide fix suggestions
3. **Security Issues Found**: Mark severity level, provide fix plan, recommend manual review before execution
4. **Complex Requirements**: Split requirements into multiple modules, generate and verify separately
5. **User Feedback**: Support users to provide modification suggestions, perform multi-round iterative optimization

## Quality Report Format

The generated quality report includes the following sections:

```
┌─────────────────────────────────────────────┐
│ Code Quality Assurance Report               │
├─────────────────────────────────────────────┤
│ 1. Basic Information                        │
│    - Language: Python/Java/JS/Go/Rust/C++   │
│    - Lines of Code: xxx                     │
│    - Functions: xxx                         │
├─────────────────────────────────────────────┤
│ 2. Unit Test Results                        │
│    - Test File: xxx_test.py                 │
│    - Test Cases: xxx                        │
│    - Passed: xxx                            │
│    - Failed: xxx                            │
│    - Score: xxx/100                         │
├─────────────────────────────────────────────┤
│ 3. Execution Verification                   │
│    - Status: Success/Failed                 │
│    - Output: xxx                            │
│    - Error: xxx (if any)                    │
│    - Score: xxx/100                         │
├─────────────────────────────────────────────┤
│ 4. Static Analysis                          │
│    - pylint Issues: xxx                     │
│    - flake8 Issues: xxx                     │
│    - Code Metrics: xxx                      │
│    - Score: xxx/100                         │
├─────────────────────────────────────────────┤
│ 5. Security Audit                           │
│    - Critical: xxx                          │
│    - High: xxx                              │
│    - Medium: xxx                            │
│    - Score: xxx/100                         │
├─────────────────────────────────────────────┤
│ 6. Refactoring Suggestions                  │
│    - Long Functions: xxx                    │
│    - High Complexity: xxx                   │
│    - Improvements: xxx                      │
├─────────────────────────────────────────────┤
│ 7. Overall Score                            │
│    - Total Score: xxx/100                   │
│    - Rating: A/B/C/D                        │
│    - Recommendations: xxx                   │
└─────────────────────────────────────────────┘
```

## Usage Example

### Example: Generate Python Calculator Code and Verify

**User Input:**
```
Write a Python program that implements a simple calculator with addition, subtraction, multiplication, and division
```

**Analysis Flow:**

1. Generate code and save as `calculator.py`
2. Call `test_generator.py` to generate unit tests
3. Call `execute_code.py` for static safety analysis
4. Call `static_analysis.py` for static checking
5. Call `security_audit.py` for security audit
6. Call `code_refactor.py` to analyze code structure
7. Output comprehensive quality report

**Quality Report Output:**
```
┌─────────────────────────────────────────────┐
│ Code Quality Assurance Report               │
├─────────────────────────────────────────────┤
│ 1. Basic Information                        │
│    - Language: Python                       │
│    - Lines of Code: 45                      │
│    - Functions: 5                           │
├─────────────────────────────────────────────┤
│ 2. Unit Test Results                        │
│    - Test File: calculator_test.py          │
│    - Test Cases: 5                          │
│    - Passed: 5                              │
│    - Failed: 0                              │
│    - Score: 95/100                          │
├─────────────────────────────────────────────┤
│ 3. Execution Verification                   │
│    - Status: Success                        │
│    - Output: Calculator works correctly     │
│    - Score: 85/100                          │
├─────────────────────────────────────────────┤
│ 4. Static Analysis                          │
│    - pylint Issues: 2 (warnings)            │
│    - flake8 Issues: 1 (format)              │
│    - Comment Ratio: 15%                     │
│    - Score: 78/100                          │
├─────────────────────────────────────────────┤
│ 5. Security Audit                           │
│    - Critical: 0                            │
│    - High: 0                                │
│    - Medium: 0                              │
│    - Score: 100/100                         │
├─────────────────────────────────────────────┤
│ 6. Refactoring Suggestions                  │
│    - Long Functions: 0                      │
│    - High Complexity: 0                     │
│    - Improvements: Add type annotations     │
├─────────────────────────────────────────────┤
│ 7. Overall Score                            │
│    - Total Score: 89/100                    │
│    - Rating: B                              │
│    - Recommendations: Fix pylint warnings,  │
│      add type annotations                   │
└─────────────────────────────────────────────┘
```

## Differentiation Value

Core differences between this Skill and ordinary code generation:

1. **Multi-language Support**: Supports six mainstream programming languages (Python/Java/JavaScript/Go/Rust/C++)
2. **Unit Test Generation**: Automatically extracts function signatures, generates comprehensive test cases
3. **Safety Analysis**: Detects 8 categories of dangerous code patterns and potential security risks through static analysis
4. **Multi-dimensional Quality Detection**: Static analysis + security audit + safety analysis + complexity analysis + structure analysis, covering all dimensions of code quality
5. **Security Audit Capability**: Detects SQL injection, XSS, command injection and other common vulnerabilities
6. **Complexity Analysis**: Provides code complexity metrics including lines of code, function count, class count, import count
7. **Quantifiable Quality Score**: Outputs quantifiable quality metrics and risk ratings (A/B/C/D)

## Quality Assurance

1. **Code Correctness**: Ensure generated code has correct logic and is runnable
2. **Security**: Detect and block dangerous code, do not output sensitive information
3. **Standardization**: Follow coding standards, ensure consistent code formatting
4. **Completeness**: Cover multiple dimensions of code quality

## Notes

1. Do not output sensitive information (passwords, keys, personal information, etc.)
2. This tool performs static analysis only and does not execute user code
3. Safety analysis detects 8 categories of dangerous patterns (command injection, code execution, file/network/system access, sensitive data, runtime modification, threading)
4. Generated code follows coding standards of the target language
5. For complex requirements, provide step-by-step implementation suggestions
6. Users should manually review and execute generated code in a controlled environment
7. Code is not automatically executed; safety analysis provides recommendations for manual execution
