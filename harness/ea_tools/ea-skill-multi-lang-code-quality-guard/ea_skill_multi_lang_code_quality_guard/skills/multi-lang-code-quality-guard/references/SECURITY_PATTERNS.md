# Security Patterns Reference

## Common Security Vulnerabilities

### SQL Injection
- **Risk Level**: High
- **Description**: User input is directly concatenated into SQL statements without validation
- **Example**: `query = f"SELECT * FROM users WHERE id = {user_id}"`
- **Fix**: Use parameterized queries or ORM frameworks

### XSS Attack
- **Risk Level**: Medium
- **Description**: User input is directly output to HTML pages without escaping
- **Example**: `document.write(user_input)`
- **Fix**: Use HTML escaping functions

### Path Traversal
- **Risk Level**: Medium
- **Description**: User input contains path traversal characters like `../`
- **Example**: `open(f"/data/{user_input}")`
- **Fix**: Validate and normalize paths

### Command Injection
- **Risk Level**: High
- **Description**: User input is directly passed to system commands
- **Example**: `os.system(f"ping {user_input}")`
- **Fix**: Use subprocess and avoid shell=True

## Secure Coding Best Practices

### Input Validation
- Validate all user input for type and format
- Use whitelist validation, not blacklist
- Limit input length

### Output Escaping
- Use `html.escape()` for HTML output
- Use `json.dumps()` for JSON output
- Use `urllib.parse.quote()` for URL parameters

### Sensitive Data Handling
- Never hardcode passwords or keys
- Use environment variables for sensitive configuration
- Don't log sensitive information

### Dependency Security
- Regularly update third-party libraries
- Use `pip-audit` to check for vulnerabilities
- Only install necessary dependencies

## Code Review Checklist

- [ ] Are parameterized queries used?
- [ ] Is user input validated?
- [ ] Is output properly escaped?
- [ ] Are there any hardcoded secrets?
- [ ] Is secure random number generation used?
- [ ] Are file operations path-validated?
- [ ] Are file upload types and sizes restricted?
- [ ] Are appropriate timeouts set?
