First off, thank you for considering contributing to encre! It's people like you that make encre such a great tool.

This document provides guidelines and instructions for contributing to the encre project. By participating, you are expected to uphold this code and help us maintain a welcoming and productive community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Pull Requests](#pull-requests)
- [Development Guidelines](#development-guidelines)
  - [Setting Up Development Environment](#setting-up-development-environment)
  - [Building the Project](#building-the-project)
  - [Running Tests](#running-tests)
  - [Code Style](#code-style)
  - [Commit Messages](#commit-messages)
- [Project Structure](#project-structure)
- [Community](#community)
- [License](#license)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

- Make sure you have a [GitHub account](https://github.com/signup/free)
- Fork the repository on GitHub
- Set up your development environment (see [Development Guidelines](#development-guidelines))
- Familiarize yourself with the [project structure](#project-structure)

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [existing issues](https://github.com/mf2023/Encre/issues) to see if the problem has already been reported. When you are creating a bug report, please include as many details as possible:

#### Before Submitting a Bug Report

- **Check the documentation** for information that might help
- **Check if the bug has already been reported** by searching on GitHub under [Issues](https://github.com/mf2023/Encre/issues)
- **Determine which component the problem should be reported in** (Python framework, Rust native core, or Electron desktop)

#### How to Submit a Good Bug Report

Bugs are tracked as [GitHub issues](https://github.com/mf2023/Encre/issues). Create an issue and provide the following information:

- **Use a clear and descriptive title** for the issue to identify the problem
- **Describe the exact steps to reproduce the problem** in as many details as possible
- **Provide specific examples to demonstrate the steps**. Include links to files or GitHub projects, or copy/pasteable snippets
- **Describe the behavior you observed** and why it's a problem
- **Explain which behavior you expected to see instead and why**
- **Include code samples and screenshots** which show you demonstrating the problem

**Example:**

```markdown
**Description:**
EncreAgent crashes when using the web_search tool with empty query string

**Steps to Reproduce:**
1. Create a EncreAgent instance
2. Run agent with prompt containing empty web search
3. Observe the crash

**Expected Behavior:**
Graceful error handling with informative message

**Actual Behavior:**
```
KeyError: 'query'
```

**Environment:**
- OS: Ubuntu 24.04
- Python Version: 3.12
- encre Version: 0.1.5-pre.1
- Backend: openai/gpt-4o
```

### Suggesting Enhancements

Enhancement suggestions are tracked as [GitHub issues](https://github.com/mf2023/Encre/issues). When creating an enhancement suggestion, please include:

- **Use a clear and descriptive title** for the issue to identify the suggestion
- **Provide a step-by-step description of the suggested enhancement** in as many details as possible
- **Provide specific examples to demonstrate the enhancement**
- **Explain why this enhancement would be useful** to most encre users
- **List some other AI agent frameworks where this enhancement exists**

### Pull Requests

1. Fork the repo and create your branch from `master`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code follows the style guidelines
6. Issue that pull request!

#### Pull Request Process

1. Update the [CHANGELOG.md](CHANGELOG.md) with details of changes if applicable
2. Update the [README.md](README.md) with details of changes to the interface if applicable
3. The PR will be merged once you have the sign-off of at least one maintainer

## Development Guidelines

### Setting Up Development Environment

#### Prerequisites

- **Python** (3.11+): [Install Python](https://www.python.org/downloads/)
- **Node.js** (18+ for desktop application): [Install Node.js](https://nodejs.org/)
- **Rust** (1.65+ for native extension, optional): [Install Rust](https://www.rust-lang.org/tools/install)
- **Platforms**: Linux (x64, arm64), macOS (x64, arm64), Windows (x64)

#### Windows-Specific Requirements

For the desktop application on Windows:
- Visual Studio 2022 with "Desktop development with C++" workload (for node-pty)
- Or install via: `npm install --global windows-build-tools`

#### Clone the Repository

```bash
git clone https://github.com/mf2023/Encre.git
cd encre
```

#### Install Python Dependencies

```bash
# Install core dependencies (editable mode)
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"

# Install optional backends as needed
pip install -e ".[anthropic]"       # Anthropic Claude backend
pip install -e ".[ollama]"           # Ollama local backend

# Install Rust native extension (requires Rust toolchain)
pip install -e ".[native]"
```

#### Install Desktop Dependencies

```bash
cd desktop
npm install
```

### Building the Project

#### Build Python Wheel

```bash
pip install build
python -m build
```

#### Build Rust Native Extension

```bash
cd crates
cargo build --release
```

#### Build Desktop Application

```bash
cd desktop
npm run build        # Bundle TypeScript with esbuild
npm start            # Build + launch Electron
npm run dist         # Build + package for distribution
```

### Running Tests

#### Python Tests

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/test_agent.py -v

# Run with coverage
pytest --cov=encre tests/
```

#### Rust Tests

```bash
# Run all tests
cargo test

# Run tests in a specific crate
cargo test -p encre-core
cargo test -p encre-py
```

#### Desktop Type Check

```bash
cd desktop
npm run typecheck
```

### Code Style

#### Python Code Style

We use **ruff** for linting and formatting, and **mypy** for type checking:

```bash
# Lint
ruff check .

# Auto-fix
ruff check --fix .

# Type check
mypy encre
```

#### Rust Code Style

We follow the official [Rust Style Guide](https://doc.rust-lang.org/style-guide/) and use `rustfmt` for formatting:

```bash
# Format code
cargo fmt

# Lint
cargo clippy --all-features
```

#### Documentation

- All public APIs must have documentation comments
- Use `cargo doc` to generate Rust documentation
- Documentation should include examples where appropriate

### Commit Messages

This project uses **date-based commit messages** in the format `YYYY.MM.DD`:

```
2026.05.31
```

#### Format

- Use the **current date** in `YYYY.MM.DD` format
- No additional description
- No body or footer

#### Examples

```bash
# Good
git commit -m "2026.05.31"

# Bad - don't use conventional commits or descriptions
git commit -m "feat(agent): add streaming support"
git commit -m "fix bug in tool execution"
```

#### Why Date-Based?

- **Simple**: No need to think about commit message format
- **Clear timeline**: Easy to see when changes were made
- **Consistent**: All commits follow the same pattern
- **Changelog**: Detailed changes are tracked in [CHANGELOG.md](CHANGELOG.md)

#### Tracking Changes

Since commit messages are minimal, detailed change information is maintained in:

- **[CHANGELOG.md](CHANGELOG.md)**: Version history and release notes
- **GitHub Issues/PRs**: Detailed discussion and context
- **Code comments**: Inline documentation for complex changes

## Project Structure

```
encre/
├── agent.py                  # Agent entry point
├── config.py                 # Global configuration
├── pyproject.toml            # Python build & dependencies
├── Cargo.toml                # Rust workspace root
├── __init__.py               # Public API surface
├── native.py                 # Rust native bridge
│
├── encre/                      # Python agent framework
│   ├── agent.py              # EncreAgent — public API
│   ├── loop.py               # EncreLoop — execution loop
│   ├── session.py            # EncreSession — conversation state
│   ├── safety.py             # EncreSafetyEngine — permission modes
│   ├── backends/             # 31 LLM providers
│   ├── tools/builtin/        # 35 built-in tools
│   ├── tools/mcp.py          # MCP client
│   ├── hooks/                # EncreHookSystem
│   ├── memdir/               # Persistent memory system
│   ├── skills/               # Skill registry (11 bundled)
│   ├── swarm/                # Multi-agent system
│   ├── task/                 # Task manager & executor
│   ├── server/               # WebSocket server + admin API
│   ├── channels/             # Transport layer
│   ├── compact/              # Context compaction
│   ├── lsp/                  # LSP client
│   ├── codebase/             # Code indexer (BM25 + dep graph)
│   ├── computer/             # Desktop & browser automation
│   ├── notebook/             # Interactive Python kernel
│   ├── sandbox/              # Docker container sandbox
│   └── utils/                # IDs, token counting, types
│
├── crates/                   # Rust workspace
│   ├── encre-core/             # Native core (fs, search, diff, etc.)
│   └── encre-py/               # PyO3 bindings → encre._native
│
├── desktop/                  # Electron desktop application
│   ├── main.ts               # Electron main process
│   ├── preload.ts            # Context bridge
│   ├── build.js              # esbuild configuration
│   ├── package.json          # Node.js dependencies
│   └── renderer/             # Frontend (HTML, CSS, TypeScript)
│
└── tests/                    # Python test suite
```

## Community

### Communication Channels

- **Gitee Issues** (Primary): Bug reports, feature requests, and general discussion - https://gitee.com/dunimd/encre/issues
- **GitHub Issues** (Mirror): Alternative access - https://github.com/mf2023/Encre/issues
- **GitHub Discussions**: For questions and community interaction

### Repositories

- **Gitee** (Primary): https://gitee.com/dunimd/encre.git
- **GitHub** (Mirror): https://github.com/mf2023/Encre.git

### Recognition

Contributors will be recognized in our [CHANGELOG.md](CHANGELOG.md) and release notes.

## License

By contributing to encre, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

---

Thank you for contributing to encre! 🎉