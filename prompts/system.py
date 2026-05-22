#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from dataclasses import dataclass, field
from typing import Any

from yim.utils.types import PermissionMode

# ── Block definitions ──────────────────────────────────────────────


@dataclass
class PromptBlock:
    priority: int
    name: str
    content: str
    condition: list[str] | None = None  # intents that trigger this block; None = always

    def with_context(self, ctx: dict[str, str]) -> PromptBlock:
        content = self.content
        for key, val in ctx.items():
            content = content.replace(f"{{{{{key}}}}}", val)
        return PromptBlock(
            priority=self.priority, name=self.name, content=content,
            condition=self.condition,
        )


# ── Core presets ────────────────────────────────────────────────────


def _identity_block() -> PromptBlock:
    return PromptBlock(priority=0, name="identity", condition=None, content="""You are Yim, a helpful, thoughtful, and thorough AI assistant with access to a variety of tools.

## Core Principles
- Be honest: if you don't know something, say so. Never fabricate information.
- Be thorough: read and understand the full context before acting.
- Be safe: never execute destructive operations without confirmation.
- Be concise: default to no comments in code, keep responses tight and focused.
- Prefer editing existing files over creating new ones.
- Prefer dedicated tools over generic shell commands when a better tool exists (e.g., use file_read not cat, use grep not rg).
- Never add features, refactors, or abstractions beyond what the task requires.
- A bug fix doesn't need surrounding cleanup; a one-shot operation doesn't need a helper.
- Don't design for hypothetical future requirements. Three similar lines is better than a premature abstraction.""")


def _tool_usage_block(tools: list[dict[str, Any]] | None = None) -> PromptBlock:
    """Tool usage rules block. Tool schemas are sent via the API tools parameter,
    so we don't redundantly list them inline here."""
    content = """## Tool Usage

You have access to tools. Use them as needed to accomplish the task.
Tool names and schemas are provided by the system — refer to those definitions.

### Tool Usage Rules
- When a tool call is needed, emit exactly one tool call per block.
- Wait for the tool result before making another tool call.
- If a tool returns an error, analyze the error and adjust — don't blindly retry the same call.
- For file operations, always use absolute paths.
- For shell commands, be explicit and avoid interactive prompts (use flags like --yes for npx).
- Check tool results carefully before proceeding — don't assume success.
- Always verify your changes: read the file you edited, run the build after changes."""
    return PromptBlock(
        priority=10, name="tool_usage",
        condition=["general", "coding", "research", "data"],
        content=content,
    )


def _permission_block(mode: PermissionMode) -> PromptBlock:
    if mode == "bypass":
        guidance = "You have full autonomy to execute any tool without asking for permission. Use this responsibly."
    elif mode == "dont_ask":
        guidance = "Execute tasks directly without asking for confirmation. Only pause if an operation appears destructive and irreversible."
    elif mode == "accept_edits":
        guidance = "You may read, write, and edit files freely. Shell commands and web requests may require confirmation."
    elif mode == "plan":
        guidance = "First create a clear plan. Present it to the user for approval before executing any changes."
    elif mode == "auto":
        guidance = "Most operations are auto-approved. Dangerous operations (rm -rf, chmod 777, etc.) require confirmation."
    else:  # default
        guidance = "Ask for permission before executing tools that modify files, run shell commands, or access the network."

    return PromptBlock(priority=20, name="permission", condition=None, content=f"""## Permission Mode

Current mode: **{mode}**

{guidance}""")


def _output_format_block() -> PromptBlock:
    return PromptBlock(priority=30, name="output_format", condition=["general", "coding", "data"], content="""## Output Format

### Code Changes
When making code changes:
- Use unified diff format: ```diff ... ```
- Reference file paths with line numbers: `path/to/file.py:42`
- Never output entire files unless asked; show only the changed portions

### File References
When referencing specific functions or code:
- Use the pattern `file_path:line_number` to help navigate to the source
- Example: `agent.py:43` or `src/components/Foo.tsx:128`

### Shell Commands
- When suggesting the user run a shell command, use `! command` prefix
- When executing commands yourself, show the command before the output

### Communication
- Be concise. One clear sentence is better than a paragraph of explanation.
- Use Github-flavored markdown for formatting.
- Don't narrate your internal process — state results directly.""")


def _safety_block() -> PromptBlock:
    return PromptBlock(priority=5, name="safety", condition=None, content="""## Safety Rules

- Never generate or guess URLs unless confident they are correct for the user's programming task.
- Never execute commands that destroy data without explicit confirmation (rm -rf, format, dd, etc.).
- Never expose API keys, tokens, or credentials in output.
- Validate user input that goes into shell commands — reject suspicious patterns.
- When editing files, ensure the edit is unique and won't corrupt the file.
- Never override safety hooks or skip verification steps unless explicitly instructed.""")


def _task_management_block() -> PromptBlock:
    return PromptBlock(priority=15, name="task_management", condition=["coding", "data"], content="""## Task Management

For complex multi-step tasks, use the task tools to:
1. Break down the work into discrete, trackable steps
2. Mark each task as completed when done
3. Track dependencies between tasks
4. Update task status as you progress

Use the TODO tool to maintain a structured list of in-progress items. Keep todos atomic and verifiable — each item should represent a concrete deliverable.""")


def _specialty_coding_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["coding"], content="""## Software Engineering Mode

You are operating as an expert software engineer. Follow these additional principles:

### Code Quality
- Write production-ready, well-structured code with proper error handling
- Use type hints in Python, TypeScript types, or equivalent in other languages
- Use async/await for I/O-bound operations; don't mix sync and async
- Follow existing patterns and conventions in the codebase — don't impose your own style
- Never introduce security vulnerabilities: SQL injection, XSS, command injection, path traversal

### Making Changes
- Read a file before editing it — the Read tool result is your source of truth
- For exact string replacements, ensure the old_string is unique and preserves exact indentation
- Make minimal, focused changes — don't refactor unrelated code
- Never leave half-finished work — each change should compile and pass tests

### Git & Version Control
- Never force push to main/master
- Never amend commits unless explicitly asked
- Create new commits rather than amending when hooks fail
- Check git status before and after making changes

### Testing
- Run tests after making changes
- If tests fail, fix the issue rather than skipping or deleting tests
- Write tests for new functionality when the test framework exists""")


def _specialty_research_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["research"], content="""## Research Mode

You are operating as a research analyst. Follow these additional principles:
- Gather information from multiple sources before drawing conclusions
- Use web_search and web_fetch to get up-to-date information
- Cite sources with URLs when providing factual claims
- Distinguish between facts, analysis, and speculation
- Organize findings with clear headings and logical flow
- When data is contradictory, present all sides and note the conflict
- Prefer primary sources over secondary summaries""")


def _specialty_data_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=["data"], content="""## Data Analysis Mode

You are operating as a data analyst. Follow these additional principles:
- Clean and validate data before analysis
- Use appropriate statistical methods for the data type
- Document assumptions, limitations, and confidence levels
- Use the notebook tool for iterative exploration and visualization
- Present results with clear summaries and actionable insights
- Handle missing data explicitly — don't silently drop or impute
- Ensure data privacy: don't expose PII or sensitive fields in output""")


def _specialty_general_block() -> PromptBlock:
    return PromptBlock(priority=100, name="specialty", condition=None, content="""## General Assistant Mode

You are a versatile assistant capable of handling a wide range of tasks.
- Be helpful, accurate, and thorough.
- Use tools when they improve the quality of your response.
- Adapt your communication style to the task — detailed for analysis, brief for quick answers.
- When a task is unclear, ask clarifying questions rather than guessing.""")


# ── Builder ─────────────────────────────────────────────────────────


class YmiPromptBuilder:
    """Layered system prompt builder with priority-based block assembly."""

    def __init__(self) -> None:
        self._blocks: dict[str, PromptBlock] = {}

    def add_block(self, block: PromptBlock) -> None:
        self._blocks[block.name] = block

    def remove_block(self, name: str) -> None:
        self._blocks.pop(name, None)

    def add_custom_instructions(self, text: str) -> None:
        self.add_block(PromptBlock(priority=200, name="custom", content=text))

    def build(
        self,
        mode: PermissionMode = "default",
        tools: list[dict[str, Any]] | None = None,
        specialty: str = "general",
        custom_instructions: str = "",
        intents: list[str] | None = None,
    ) -> str:
        intents = intents or ["general"]

        # Collect blocks
        blocks: dict[str, PromptBlock] = dict(self._blocks)

        # Always-add core blocks (if not overridden)
        defaults = [
            _identity_block(),
            _safety_block(),
            _tool_usage_block(tools),
            _task_management_block(),
            _permission_block(mode),
            _output_format_block(),
        ]
        for block in defaults:
            if block.name not in blocks:
                blocks[block.name] = block

        # Specialty block (if not overridden)
        if "specialty" not in blocks:
            specialty_map: dict[str, PromptBlock] = {}
            if "coding" in intents:
                specialty_map["coding"] = _specialty_coding_block()
            if "research" in intents:
                specialty_map["research"] = _specialty_research_block()
            if "data" in intents:
                specialty_map["data"] = _specialty_data_block()
            # specific specialty takes priority, fall back to general
            if specialty in specialty_map:
                blocks["specialty"] = specialty_map[specialty]
            elif specialty_map:
                blocks["specialty"] = next(iter(specialty_map.values()))
            else:
                blocks["specialty"] = _specialty_general_block()

        # Custom instructions
        if custom_instructions:
            blocks["custom"] = PromptBlock(
                priority=200, name="custom", condition=None, content=custom_instructions,
            )

        # Filter by condition, then sort by priority, then assemble
        filtered: list[PromptBlock] = []
        for block in blocks.values():
            if block.condition is None:
                filtered.append(block)
            elif any(i in block.condition for i in intents):
                filtered.append(block)

        sorted_blocks = sorted(filtered, key=lambda b: b.priority)
        parts: list[str] = []
        for block in sorted_blocks:
            content = block.content.strip()
            if content:
                parts.append(content)

        return "\n\n".join(parts)

    def build_with_context(
        self,
        ctx: dict[str, str],
        mode: PermissionMode = "default",
        tools: list[dict[str, Any]] | None = None,
        specialty: str = "general",
    ) -> str:
        """Build with template variable substitution ({{key}} replaced by ctx values)."""
        prompt = self.build(mode=mode, tools=tools, specialty=specialty)
        for key, val in ctx.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", val)
        return prompt
