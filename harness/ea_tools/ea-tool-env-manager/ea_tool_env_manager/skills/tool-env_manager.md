---
name: tool-env_manager
description: "Read and modify environment variables and config files. The 'process' scope mutates the current process environment (get/set/delete/list); the 'file' scope persists changes to a .env file. The 'load' action imports variables from .env, JSON, YAML, or TOML files into the process environment, and 'save' exports the current environment to a file in env, JSON, or YAML format. Use this instead of bash `export`/`set`/`unset` and hand-editing .env files -- it handles multiple formats, preserves comments on file writes, and keeps config changes auditable. TIP: Use scope='file' with action='set' to update a specific key in an existing .env without rewriting unrelated lines. AVOID: Storing secrets in plain .env files committed to version control -- prefer environment variables or a secrets manager."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# env_manager

Read and modify environment variables and config files. The 'process' scope mutates the current process environment (get/set/delete/list); the 'file' scope persists changes to a .env file. The 'load' action imports variables from .env, JSON, YAML, or TOML files into the process environment, and 'save' exports the current environment to a file in env, JSON, or YAML format. Use this instead of bash `export`/`set`/`unset` and hand-editing .env files -- it handles multiple formats, preserves comments on file writes, and keeps config changes auditable. TIP: Use scope='file' with action='set' to update a specific key in an existing .env without rewriting unrelated lines. AVOID: Storing secrets in plain .env files committed to version control -- prefer environment variables or a secrets manager.
