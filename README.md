Based on the code map provided, I can see this is a comprehensive AI agent framework called "Yim" (也迷). Let me create a detailed README.md for this project.

# Yim (也迷)

[English](README.md) | [中文](README_zh.md)

Yim is a powerful, modular AI agent framework written in Python with Rust extensions for performance-critical operations. It provides a flexible architecture for building AI-powered applications with support for multiple LLM backends, tool systems, memory management, and multi-agent orchestration.

## Features

### 🤖 Multi-Backend Support
- **OpenAI** - GPT-4.1, GPT-4o, O3, O4-mini models
- **Anthropic** - Claude Sonnet, Opus, Haiku with thinking and prompt caching
- **DeepSeek** - DeepSeek V4 with reasoning support
- **Google** - Gemini 2.5 Pro with grounding support
- **Groq** - Fast inference with Llama models
- **Ollama** - Local LLM support
- **Local** - Device inference with Qwen models
- **AWS Bedrock** - Cloud deployment support
- **Failover & Router** - Automatic backend switching and cost-based routing

### 🛠️ Built-in Tools
- **File Operations** - Read, write, edit files with precision
- **Bash Execution** - Safe command execution with security analysis
- **Git Integration** - Repository operations and diff handling
- **Web Fetch/Search** - Internet access tools
- **Code Intelligence** - LSP integration for code analysis
- **Browser Automation** - Playwright-based web automation
- **Notebook Support** - Jupyter kernel integration
- **Task Management** - Create and track tasks
- **Cron Scheduling** - Time-based job execution

### 🧠 Advanced Capabilities
- **Memory System** - Semantic memory with consolidation and search
- **Skills Framework** - Composable agent behaviors
- **Plugin System** - Extensible architecture
- **Safety Engine** - Command analysis and sandboxing
- **Auto-Safety Classifier** - ML-based permission decisions
- **Error Recovery** - Automatic retry and fallback strategies
- **Evolution Learning** - Self-improvement from success/error patterns
- **Meta-Cognition** - Self-awareness and delegation decisions
- **Swarm Mode** - Multi-agent collaboration with consensus
- **Goal Execution** - Autonomous goal-seeking with evaluation
- **Context Compression** - Efficient token budget management

### 🖥️ Desktop Application
- Modern Electron-based UI
- Real-time streaming responses
- Session management with rollback
- Theme customization
- Model selection

### ⚡ Rust Core (yim-core)
- High-performance diff computation
- SIMD-accelerated search
- Token counting
- Sandboxed execution
- Landlock security sandboxing
- LSP protocol support

## Installation

```bash
# Install from source
pip install -e .

# Or install with all dependencies
pip install -e ".[all]"

# Build Rust extensions
pip install maturin
maturin develop --release
```

## Quick Start

```python
import asyncio
from yim import YmiAgent

async def main():
    agent = YmiAgent(
        model="claude-sonnet-4-20250514",
        backend_type="anthropic",
    )
    
    async for event in agent.run("List files in the current directory"):
        print(event)

asyncio.run(main())
```

### Using with Tools

```python
from yim import YmiAgent
from yim.tools.registry import ToolRegistry
from yim.tools.builtin import YmiBashTool, YmiFileReadTool

# Create agent with tools
agent = YmiAgent()
agent.tool_registry.register(YmiBashTool())
agent.tool_registry.register(YmiFileReadTool())

async for event in agent.run_with_tools(
    "Read the contents of README.md",
    tools=agent.tool_registry.all()
):
    print(event)
```

### Goal Execution

```python
agent = YmiAgent()

# Define a goal with success criteria
goal_loop = agent.goal(
    description="Fix all type errors in the project",
    success_criteria="Running mypy returns no errors",
    max_attempts=10
)

result = await goal_loop.execute()
print(f"Goal status: {result.status}")
```

### Swarm Multi-Agent

```python
agent = YmiAgent()

# Spawn multiple agents to collaborate
swarm = agent.swarm(
    goal="Build a web scraper",
    max_concurrent=5,
    enable_reviewer=True
)

result = await swarm.execute()
```

## Configuration

Yim can be configured via YAML, TOML, or Python:

```yaml
# yim.yaml
model: gpt-4.1
backend_type: openai
api_key: $OPENAI_API_KEY
max_turns: 50
permission_mode: ask
sandbox_enabled: true
```

## Architecture

```
yim/
├── agent.py          # Main agent implementation
├── loop.py           # Agent loop execution
├── session.py        # Session management
├── config.py         # Configuration handling
├── safety.py         # Safety engine
├── backends/         # LLM backend implementations
├── tools/            # Tool implementations
├── skills/           # Skill system
├── plugins/          # Plugin framework
├── swarm/            # Multi-agent orchestration
├── goal.py           # Goal execution
├── compact/          # Context compression
├── memdir/           # Memory system
├── evolution/        # Learning system
├── desktop/          # Electron desktop app
└── crates/          # Rust core (yim-core)
```

## Security

Yim includes multiple security layers:
- **Bash Command Analysis** - Detects dangerous commands
- **SSRF Protection** - Prevents server-side request forgery
- **Landlock Sandbox** - Linux kernel security sandboxing
- **Container Sandboxing** - Docker-based command isolation
- **Auto-Safety Classifier** - ML-based permission decisions

## Development

```bash
# Run tests
pytest

# Run specific test file
pytest tests/test_agent.py -v

# Type checking
mypy yim/

# Format code
ruff format .
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

---

For more examples and documentation, visit the [project repository](https://gitee.com/dunimd/yim).