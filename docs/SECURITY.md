The encre project takes security seriously. This document outlines our security policy, including supported versions, how to report vulnerabilities, and our disclosure process.

## Supported Versions

The following versions of encre are currently supported with security updates:

| Version | Supported          | Status                |
| ------- | ------------------ | --------------------- |
| 0.1.x   | :white_check_mark: | Current stable series |
| < 0.1.0 | :x:                | No longer supported   |

We provide security updates for the latest minor version in each major version series. Users are encouraged to upgrade to the latest version to receive security patches.

## Reporting a Vulnerability

If you discover a security vulnerability in encre, please report it to us as soon as possible. We appreciate your efforts to responsibly disclose your findings.

### How to Report

**Please do not report security vulnerabilities through public GitHub issues or Gitee issues.**

Instead, please report security vulnerabilities via:

📧 **Email**: dunimd@outlook.com

For general questions and non-security issues, please use:
- **Gitee Issues** (Primary): https://gitee.com/dunimd/encre/issues
- **GitHub Issues** (Mirror): https://github.com/mf2023/Encre/issues

Please include the following information in your report:

- **Description**: A clear and concise description of the vulnerability
- **Impact**: What kind of vulnerability is it and what impact could it have
- **Affected Versions**: Which versions of encre are affected
- **Steps to Reproduce**: Detailed steps to reproduce the vulnerability
- **Proof of Concept**: If possible, include a proof-of-concept or exploit code (especially for tool injection, prompt injection, or sandbox escape)
- **Suggested Fix**: If you have suggestions for how to fix the vulnerability
- **Your Contact Information**: How we can reach you for clarifications (optional)

### What to Expect

When you submit a security report, you can expect the following:

1. **Acknowledgment**: We will acknowledge receipt of your report within 48 hours
2. **Initial Assessment**: We will provide an initial assessment within 5 business days
3. **Investigation**: We will investigate the vulnerability and determine its impact
4. **Fix Development**: If confirmed, we will work on a fix and may reach out for additional information
5. **Disclosure**: We will coordinate with you on the disclosure timeline

### Response Time

Our target response times are:

| Severity | Initial Response | Fix Timeline |
|----------|-----------------|--------------|
| Critical | 24 hours | 7 days |
| High | 48 hours | 14 days |
| Medium | 5 business days | 30 days |
| Low | 10 business days | 60 days |

## Security Considerations

### Tool Execution Safety

encre provides 35 built-in tools that can execute code and access the filesystem. Security measures include:

#### Permission Modes (6 levels)
- **bypass**: No permission checks (development only)
- **dont_ask**: Automatically allow all tool calls
- **accept_edits**: Auto-allow file edits, ask for other actions
- **plan**: Require approval for all disruptive operations
- **auto**: Heuristic-based permission decisions via safety classifier
- **default**: Always ask for user confirmation before executing tools

#### Dangerous Command Detection
- Shell command pattern analysis detects potentially harmful operations
- Commands like `rm -rf /`, `dd if=/dev/zero`, `:(){ :\|:& };:` are blocked by default
- Configurable allow/block lists for command patterns

#### Sandboxed Execution (Docker)
- Optional Docker container sandbox with seccomp profiles
- Restricts system calls available to executed commands
- Isolates file system access within the container

### SSRF Protection

- DNS resolution validation before connection establishment
- CIDR blocklist for private/internal IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, etc.)
- Prevents Server-Side Request Forgery via web fetch and web search tools

### API Key and Credential Security

- API keys stored in environment variables or encrypted configuration
- AES-256-GCM encryption for sensitive data at rest
- The `crypto.py` module provides secure encryption/decryption
- Credentials are never logged or exposed in tool outputs by default

### Prompt Injection Defense

- encre uses a multi-layered system prompt architecture
- Safety classifiers can detect injection attempts
- Tool input validation sanitizes parameters
- The auto classifier uses the LLM itself to evaluate permission requests

### Memory & Data Privacy

- Persistent memory stored as local `.md` files in memdir
- No default telemetry or data collection
- All data remains local unless explicitly sent to an LLM API
- Memory aging/pruning prevents unbounded data accumulation
- Encryption available for sensitive memory data

### Desktop Application Security

- Context isolation enabled in Electron (`contextIsolation: true`)
- Preload script provides minimal, audited API surface
- Node.js integration disabled in renderer process
- Content Security Policy headers enforced
- Encrypted cookie store for browser automation (AES-256-GCM)

### LSP Client Security

- LSP client communicates only with locally started language servers
- No remote LSP server connections
- Language server processes are managed and terminated by encre

### Codebase Indexer

- All indexing is local (no remote code analysis)
- File access limited to the workspace directory
- Sensitive file patterns (.env, \*.key, etc.) excluded from indexing

## Security Best Practices

When using encre in your applications:

### 1. Keep Dependencies Updated

Regularly update encre and its dependencies to receive security patches:

```bash
# Update Python dependencies
pip install --upgrade encre
pip list --outdated

# Update Rust dependencies
cargo update
cargo audit  # Use cargo-audit to check for known vulnerabilities

# Update desktop dependencies
cd desktop
npm audit
npm update
```

### 2. Use Appropriate Permission Mode

Choose the appropriate tool permission mode for your use case:

```python
# Maximum security - always ask
agent = EncreAgent(..., tool_permission_mode="default")

# Automated with heuristic checks
agent = EncreAgent(..., tool_permission_mode="auto")

# Development only - no checks
agent = EncreAgent(..., tool_permission_mode="bypass")
```

### 3. Enable Sandbox for Untrusted Code

```python
from encre import EncreAgent

agent = EncreAgent(
    ...,
    sandbox_enabled=True,
    sandbox_image="encre-sandbox:latest",
)
```

### 4. Securely Manage API Keys

```bash
# Use environment variables (recommended)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Or use encrypted config
python -c "from encre import encrypt_config; encrypt_config('config.yaml')"
```

### 5. Validate Tool Output

Tool outputs are validated before being sent back to the LLM. Custom output validation can be added via hooks:

```python
from encre.hooks import EncreHookSystem

hooks = EncreHookSystem()
@hooks.on_post_tool
async def validate_output(event):
    if "sensitive_data" in event.result:
        return {"block": True, "reason": "Output contains sensitive data"}
```

### 6. Monitor and Log

Enable audit logging for security events:

```python
from encre import EncreAgent

agent = EncreAgent(
    ...,
    log_level="INFO",
    audit_log="audit.log",
)
```

### 7. Secure Deployment

- Run encre with least privilege (non-root user)
- Use container security best practices when using Docker sandbox
- Implement network segmentation for multi-agent deployments
- Regular security audits of tool configurations

## Known Security Limitations

### Current Limitations

1. **Prompt Injection**: Like all LLM applications, encre is susceptible to prompt injection attacks. The safety classifier provides mitigation but cannot guarantee complete protection.

2. **Tool Output to LLM**: Tool execution results are sent to the LLM provider. Avoid including sensitive information in tool outputs when using external LLM APIs.

3. **Browser Automation**: The browser automation tool (Playwright) runs in the local environment. Ensure proper access controls are in place.

4. **Rust Native Extension**: The `encre._native` module provides fast file I/O and shell execution. The sandbox should be enabled when running untrusted commands.

### Security Considerations for Production

- Review the configurable tool allow/block lists in your deployment
- Implement proper network security (firewalls, VPCs) for multi-agent setups
- Use secrets management systems for API keys (e.g., HashiCorp Vault)
- Enable audit logging for all tool executions
- Consider running the desktop application in a restricted environment

## Security Updates

Security updates will be announced through:

- GitHub Security Advisories
- GitHub Releases (with security fix notes)
- CHANGELOG.md (with security-related changes marked)

## Vulnerability Disclosure Policy

### Our Commitment

- We will acknowledge receipt of vulnerability reports within 48 hours
- We will provide regular updates on our progress
- We will credit researchers who responsibly disclose vulnerabilities (unless they prefer to remain anonymous)
- We will not take legal action against researchers who follow this policy

### Disclosure Timeline

1. **Day 0**: Vulnerability reported
2. **Day 1-2**: Acknowledgment and initial assessment
3. **Day 3-14**: Investigation and fix development
4. **Day 15-30**: Testing and validation
5. **Day 30+**: Coordinated disclosure

We aim to disclose vulnerabilities within 90 days of the initial report, or sooner if a fix is available.

### Public Disclosure

We will publicly disclose vulnerabilities after:

- A fix has been developed and tested
- Affected users have had reasonable time to update
- The vulnerability has been assigned a CVE identifier (if applicable)

## Security-Related Configuration

### Environment Variables

| Variable | Description | Security Impact |
|----------|-------------|-----------------|
| `ENCRE_LOG_LEVEL` | Logging level | May expose sensitive data if set to `DEBUG` or `TRACE` |
| `ENCRE_TOOL_PERMISSION_MODE` | Default permission mode | Affects tool execution security (see above) |
| `ENCRE_SANDBOX_ENABLED` | Enable Docker sandbox | Disabling reduces security for shell execution |
| `OPENAI_API_KEY` | OpenAI API key | Protect this credential |
| `ANTHROPIC_API_KEY` | Anthropic API key | Protect this credential |

### Configuration Options

Review security-related configuration options in:

- `EncreSafetyEngine` - Permission mode and dangerous command patterns
- `EncreSandbox` - Docker sandbox configuration (seccomp, memory limits)
- `EncreSSRFValidator` - SSRF protection settings
- `EncreCrypto` - Encryption configuration

## Third-Party Security Audits

We welcome third-party security audits. If you are conducting a security audit of encre:

1. Please follow responsible disclosure practices
2. Contact us in advance if you plan to publish findings
3. We appreciate receiving a copy of the audit report

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP LLM Top 10](https://genai.owasp.org/)
- [Rust Security Guidelines](https://doc.rust-lang.org/nomicon/)
- [Cargo Audit](https://github.com/RustSec/cargo-audit)
- [Python Security Best Practices](https://cheatsheetseries.owasp.org/cheatsheets/Python_Security_Cheat_Sheet.html)

## Contact

For security-related inquiries:

- **Email**: dunimd@outlook.com
- **GPG Key**: [Available upon request]

For general questions and non-security issues, please use:

- **Gitee Issues** (Primary): https://gitee.com/dunimd/encre/issues
- **GitHub Issues** (Mirror): https://github.com/mf2023/Encre/issues
- **GitHub Discussions**: https://github.com/mf2023/Encre/discussions

## Acknowledgments

We thank the following security researchers who have responsibly disclosed vulnerabilities:

*This list will be updated as vulnerabilities are reported and fixed.*

---

**Last Updated**: 2026-05-31

**Version**: 1.0