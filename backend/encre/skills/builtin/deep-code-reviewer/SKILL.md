---
name: deep-code-reviewer
description: Intelligent code review assistant. Invoked when the user needs "code review", "Code Review", "check code quality", "see if this code has issues", "code optimization suggestions", "does this code have bugs", "is this code safe", "are there performance issues", "refactoring suggestions", "PR Review", "review code logic", "code style check", "find code defects", "code security issues", "how to improve this code". Supports Python, JavaScript/TypeScript, Java, Go, C/C++, Rust, SQL and other languages. Has semantic review capabilities to detect logic bugs, performance traps, security issues, readability anti-patterns, and architecture design problems. Highly robust, runs stably with syntax-error code, large files, mixed languages, encoding issues - no crashes, no loss of critical issues.
version: "1.0.0"
---

# Code Review Assistant

## Triggers

This skill **must** be used when the user encounters any of the following scenarios:

- Mentions "code review", "Code Review", "review this code", "look at this code"
- Mentions "does this code have bugs", "is there a problem with this code", "find code defects"
- Mentions "code optimization", "how to improve this", "refactoring suggestions", "code improvement"
- Mentions "performance issues", "is this code slow", "performance bottlenecks", "SQL optimization"
- Mentions "security issues", "is this code safe", "injection risk", "XSS", "SQL injection"
- Mentions "code style", "style check", "naming issues", "readability"
- Mentions "logic bugs", "null pointer", "race condition", "deadlock", "memory leak"
- Pastes a code snippet and asks for analysis
- Mentions "PR Review", "review this PR", "look at this commit"
- Mentions "architecture issues", "design patterns", "coupling", "maintainability"

## Core Capabilities

1. **Multi-language support**: Python, JavaScript/TypeScript, Java, Go, C/C++, Rust, SQL, Shell/Bash
2. **Semantic review**: Goes beyond format and syntax - deep checks for logic bugs, business logic contradictions, missed edge cases
3. **Performance trap detection**: Time complexity analysis, N+1 queries, memory leaks, infinite loops, blocking operations
4. **Security vulnerability scanning**: SQL injection, XSS, command injection, hardcoded sensitive info, unsafe deserialization
5. **Readability anti-patterns**: Magic numbers, overly long functions, excessive nesting, inconsistent naming, comments that don't match code
6. **Architecture design assessment**: Coupling, single responsibility, duplicate code, design pattern misuse, extensibility risks
7. **Fix suggestion generation**: Each issue gets a specific fix with code + explanation + risk level

## Procedure

### Phase 1: Code Ingestion & Parsing

Read `scripts/code_parser.py` as reference for parsing logic.

1. **Identify input type**:
   - User pastes code snippet -> process directly
   - User uploads a code file -> identify language by extension
   - User sends a code screenshot -> OCR extraction (mark confidence)
   - User provides Git diff / PR link -> extract changed content

2. **Language identification**:
   - By file extension: .py/.js/.ts/.java/.go/.cpp/.c/.rs/.sql/.sh
   - No extension -> auto-infer from code features (e.g., `def` at start -> Python, `func` -> Go)
   - Mixed-language files (e.g., HTML with embedded JS) -> process in segments, label language per segment

3. **Code cleaning & segmentation**:
   - Remove excess blank lines, normalize line endings
   - Segment by function/class/method, build line-number mapping table
   - Extract comments, string constants, import statements

4. **Robustness safeguards**:
   - Code has syntax errors and cannot parse -> mark "syntax error location", skip that segment and continue reviewing others, do not crash
   - Code too long (>1000 lines) -> auto-chunk, review chunk by chunk then aggregate results
   - Encoding issues (mixed UTF-8 and GBK) -> try multiple encoding parsers, fall back to raw bytes + suggestion if all fail
   - Unknown programming language -> perform basic review based on general code patterns (e.g., check hardcoded passwords, comment quality), mark "language not supported, basic check only"
   - Empty file / no code -> immediately return "no valid code detected"

### Phase 2: Semantic Analysis

Read `scripts/semantic_analyzer.py` as reference for analysis logic.

Run the following review dimensions for each code segment:

#### Dimension 1: Logic Bugs

| Check Item | Detection Logic | Severity |
|-----------|----------------|----------|
| Null pointer / None reference | Variable used without initialization, accessing property without null check | Critical |
| Array/list out of bounds | Loop condition error, index not validated against length | Critical |
| Division by zero | Divisor not validated before division/modulo | Critical |
| Infinite loop | Loop condition always true, missing exit condition | Critical |
| Resource not released | File/connection/lock not closed, no with/try-finally | Medium |
| Race condition | Shared variables in multithreading without lock protection, non-atomic operations | Critical |
| Missing edge case | Not handling empty input, single element, max values, etc. | Medium |
| Type error | No type checking in dynamic languages, forced conversion without validation in strongly-typed languages | Medium |

#### Dimension 2: Performance Traps

Read `scripts/performance_analyzer.py` as reference for performance analysis logic.

| Check Item | Detection Logic | Severity |
|-----------|----------------|----------|
| Time complexity explosion | Nested loops, recursion without memoization, O(n^2) or higher algorithms | Medium |
| N+1 queries | ORM queries one by one in a loop, no join/preload | Critical |
| Memory leak | Accumulating large lists in loops, closures capturing large objects, cache not cleaned | Critical |
| String concatenation | Repeated string concatenation in loops (Python/Java, etc.) | Minor |
| Blocking I/O | Synchronous requests, sleep on critical path, no async | Medium |
| Redundant computation | Recomputing invariants inside loops, not extracting constants | Minor |
| Slow SQL queries | Queries without index, full table scan, select *, large offset | Critical |

#### Dimension 3: Security Issues

Read `scripts/security_scanner.py` as reference for security scanning logic.

| Check Item | Detection Logic | Severity |
|-----------|----------------|----------|
| SQL injection | String concatenation in SQL, no parameterized queries | Blocker |
| Command injection | User input directly concatenated into os.system/subprocess | Blocker |
| XSS | User input directly output to HTML, no escaping | Blocker |
| Hardcoded sensitive info | Passwords/API Keys/Tokens written directly in code | Critical |
| Unsafe deserialization | pickle.loads, yaml.load(unsafe), eval | Critical |
| Path traversal | User input used directly as file path, no validation | Critical |
| Weak encryption | Using MD5/SHA1, hardcoded keys, ECB mode | Critical |
| Logging sensitive info | Printing passwords/tokens/ID numbers in logs | Critical |
| Overly permissive CORS | Access-Control-Allow-Origin: * + allowed Credentials | Medium |
| Dependency vulnerabilities | Using libraries with known vulnerable versions (based on common CVE patterns) | Medium |

#### Dimension 4: Readability Anti-patterns

| Check Item | Detection Logic | Severity |
|-----------|----------------|----------|
| Magic numbers | Bare numbers in code without comments (not 0/1/-1) | Minor |
| Overly long functions | Functions over 50 lines (Python) / 80 lines (Java/C++) | Minor |
| Excessive nesting | If/for/while nesting over 4 levels | Minor |
| Inconsistent naming | Same variable named differently in different places, mixed camelCase and snake_case | Minor |
| Comments not matching code | Comment description inconsistent with actual code behavior | Medium |
| Dead code | Unused variables/imports/functions, unreachable branches | Minor |
| Complex expressions | Multiple logical operators in one line, nested ternaries | Minor |

#### Dimension 5: Architecture Design Issues

| Check Item | Detection Logic | Severity |
|-----------|----------------|----------|
| Duplicate code | Similar logic blocks appearing 3+ times | Medium |
| God class/function | One class/function doing too much, too many dependencies | Medium |
| Tight coupling | Direct instantiation of concrete classes, cross-layer calls | Medium |
| Violation of single responsibility | Function/class not having a single responsibility, mixing business logic and technical details | Medium |
| Design pattern misuse | Unnecessary singleton, over-abstraction, pattern for pattern's sake | Minor |
| Extensibility risk | Hardcoded branches, missing abstract interfaces, changes requiring modifications in many places | Medium |

### Phase 3: Severity Scoring

Each issue is graded by the following criteria:

| Level | Definition | Handling Requirement |
|-------|-----------|---------------------|
| **Blocker** | Security vulnerability, bug that would cause production incidents | Must fix immediately, cannot merge |
| **Critical** | Logic error, performance bottleneck, resource leak | Must fix, blocks release |
| **Medium** | Missing edge case, architecture issue, readability | Suggest fix, does not block but needs follow-up |
| **Minor** | Style issue, magic number, slight redundancy | Suggest fix, can be cleaned up later |

**Code Health Score**:
```
health_score = 100 - (blocker * 30 + critical * 15 + warning * 5 + minor * 1)
>=90 Excellent | >=75 Good | >=60 Passing | <60 Needs refactoring
```

### Phase 4: Fix Suggestion Generation

For each issue, the following must be provided:

1. **Problem description**: One-sentence explanation of the issue
2. **Risk explanation**: Why this is a problem, what happens if not fixed
3. **Specific location**: Line number + code snippet (highlight the problematic part)
4. **Fix code**: Directly replaceable fixed code
5. **Fix explanation**: Explain the fix approach
6. **Reference link**: Related best practices documentation (if available)

**Fix code example format**:
```python
# Original code (line 42)
user_input = request.GET["id"]
query = "SELECT * FROM users WHERE id = " + user_input  # Blocker: SQL injection

# After fix
user_input = request.GET.get("id", "")
if not user_input.isdigit():
    return HttpResponseBadRequest("Invalid id")
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_input,))  # Using parameterized query
```

### Phase 5: Report Output

Use `templates/review_report.md` as the output template.

**Required fields**:
- `status`: success / partial_success / failed
- `summary`: Code health score, total issue count, core conclusion (2-3 sentences)
- `language_detected`: Detected programming language
- `issue_summary`: Issue count by severity level
- `critical_issues`: Blocker/critical issue list (with line numbers, descriptions, fix code)
- `warnings`: Medium issue list
- `minor_issues`: Minor issue list
- `positive_findings`: Strengths in the code (if any, encourage positive feedback)
- `overall_suggestions`: Overall architecture/design suggestions
- `next_actions`: Next steps (fix priority ordering)

**Output format requirements**:
1. Start with **core conclusion** (one-sentence summary of code quality)
2. Show **code health score card**
3. List **blocker/critical issues** (red, must fix immediately)
4. List **medium issues** (yellow, suggest fixing)
5. List **minor issues** (gray, can clean up later)
6. Provide **fix code** (each critical issue gets directly usable fix code)
7. Give **overall suggestions** (architecture-level improvement directions)
8. Give **positive feedback** (code highlights, avoid being only critical)

## Input/Output Examples

Refer to `examples/input-code-snippet.md` and `examples/output-review-report.md` for typical input/output.

### Example Conversation Flow

**User**: Check if this Python code has issues, it's a user registration endpoint.

**AI (after loading this Skill)**:
1. Parse code -> identified as Python, Flask framework, user registration endpoint, ~80 lines
2. Semantic analysis:
   - Blocker: Line 23 directly concatenates SQL, SQL injection present
   - Critical: Line 31 stores password in plaintext, not using bcrypt
   - Critical: Line 45 returns full exception stack trace, may leak sensitive info
   - Medium: Line 12 no email format validation
   - Medium: Line 56 file operation without `with`, possible resource leak
   - Minor: Line 8 magic number 3600 (should be defined as constant SESSION_TIMEOUT)
3. Score: Code health 58 points (needs refactoring)
4. Output report:
   - Core conclusion: 1 blocker-level security vulnerability and 2 critical issues found, not recommended for direct deployment
   - Fix code: SQL injection fix (parameterized query), password encryption fix, exception handling fix
   - Overall suggestions: Recommend introducing ORM framework, unified exception handling middleware, add input validation layer
   - Positive feedback: Clean code structure, organized routes using blueprints, comprehensive logging

## Robustness Guarantees (Must Follow)

1. **Never crash**:
   - Code has syntax errors -> mark syntax error location, skip that segment, continue reviewing others
   - Code too long (>1000 lines) -> auto-chunk (500 lines per chunk), review chunk by chunk then aggregate
   - Unknown programming language -> perform basic check based on general patterns (hardcoded passwords, comment quality), mark "language not supported, basic check only"
   - Code contains binary/garbled content -> filter non-text portions, continue processing identifiable text
   - Empty input / non-code content -> return "no valid code detected, please provide a code snippet"

2. **Graceful degradation**:
   - A rule fails to execute -> skip that rule, report "some rules not executed", do not block the overall flow
   - A code segment cannot be parsed -> mark "segment parsing failed", continue processing other segments
   - Missing context (e.g., only a function snippet provided) -> perform limited analysis based on the snippet, mark "missing context, recommend providing the full file"

3. **Sensitive information protection**:
   - Detect hardcoded password/API Key -> display as `sk-************xxxx` in the report
   - Real domain names/IPs in code -> display as `example.com` / `x.x.x.x`
   - Never execute user-provided code (static analysis only, no runtime)

4. **Result validation**:
   - Fix suggestions must be syntactically correct (if Python fix suggestion, must be valid Python code)
   - Fix suggestions must not introduce new issues (e.g., fixing SQL injection must not introduce XSS)
   - Line number annotations must be accurate and correspond to the actual code
   - Severity level judgments must be reasonable (cannot mark a style issue as blocker)

5. **Fairness**:
   - Do not lower scores based on programming language preference (e.g., do not deduct extra points for PHP)
   - Use different standards for legacy code and new technology code (e.g., do not force type annotations for Python 2 code)

## Known Limitations

- Static analysis cannot detect issues only found at runtime (e.g., bugs triggered by specific input, concurrent race condition timing)
- Limited detection capability for highly business-related logic errors (e.g., "should use addition instead of multiplication"), mainly detects general patterns
- Code screenshot OCR accuracy is affected by image quality, handwriting/low resolution may cause recognition errors
- Parsing may be inaccurate for code using non-standard syntax or experimental language features
- This skill does not perform dynamic execution or fuzz testing, only based on static pattern matching and semantic analysis

## Supporting File References

- `scripts/code_parser.py` - Code parsing and language identification engine
- `scripts/semantic_analyzer.py` - Semantic analysis engine (logic bugs, readability, architecture)
- `scripts/performance_analyzer.py` - Performance trap detection engine
- `scripts/security_scanner.py` - Security vulnerability scanning engine
- `scripts/report_generator.py` - Review report generator
- `templates/review_report.md` - Code review report output template
- `examples/input-code-snippet.md` - Code input example
- `examples/output-review-report.md` - Review report output example
