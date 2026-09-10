---
name: tool-lint_format
description: "Run a linter and/or formatter on the workspace and return a structured JSON report. Supports ruff (Python), eslint + prettier (JavaScript/TypeScript), and cargo fmt + cargo clippy (Rust). Use this instead of invoking ruff/eslint/cargo directly via bash -- it auto-detects the toolchain from project files, parses diagnostics into structured per-file/line/column entries, and handles window-hiding for desktop sessions. Mode 'check' reports diagnostics without writing to disk; 'fix' runs linter auto-fixers (ruff check --fix, eslint --fix, cargo clippy --fix, cargo fmt); 'format' runs the formatter (ruff format / prettier --write / cargo fmt). TIP: Run mode='check' first to see diagnostics before applying fixes; scope with 'paths' to keep it fast. AVOID: Running mode='fix' or 'format' across the whole workspace blindly -- review the check report first."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# lint_format

Run a linter and/or formatter on the workspace and return a structured JSON report. Supports ruff (Python), eslint + prettier (JavaScript/TypeScript), and cargo fmt + cargo clippy (Rust). Use this instead of invoking ruff/eslint/cargo directly via bash -- it auto-detects the toolchain from project files, parses diagnostics into structured per-file/line/column entries, and handles window-hiding for desktop sessions. Mode 'check' reports diagnostics without writing to disk; 'fix' runs linter auto-fixers (ruff check --fix, eslint --fix, cargo clippy --fix, cargo fmt); 'format' runs the formatter (ruff format / prettier --write / cargo fmt). TIP: Run mode='check' first to see diagnostics before applying fixes; scope with 'paths' to keep it fast. AVOID: Running mode='fix' or 'format' across the whole workspace blindly -- review the check report first.
