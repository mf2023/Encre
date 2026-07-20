#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
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

from __future__ import annotations

"""Module: builtin/manage.py

Manage tool — the "god tool" that lets the model dynamically install new tools,
sub-agents, skills, and MCP servers at runtime. All changes take effect
immediately and are available on the very next turn.
"""

import json
from typing import Any

from encre.tools.base import build_tool
from encre.tools.builtin.find_tool import _resolve_loop


async def _manage_execute(**kwargs: Any) -> str:
    action = (kwargs.get("action") or "").strip()
    if not action:
        return (
            "Error: 'action' is required. "
            "Choose: install_tool, install_agent, install_skill, install_mcp"
        )

    loop = _resolve_loop()
    if loop is None:
        return "Error: manage requires a parent loop reference."

    if action == "install_tool":
        return await _install_tool(loop, kwargs)
    elif action == "install_agent":
        return await _install_agent(loop, kwargs)
    elif action == "install_skill":
        return await _install_skill(loop, kwargs)
    elif action == "install_mcp":
        return await _install_mcp(loop, kwargs)
    else:
        return (
            f"Error: unknown action '{action}'. "
            "Choose: install_tool, install_agent, install_skill, install_mcp"
        )


def _ensure_unlocked(loop: Any, session_id: str, name: str) -> None:
    """Auto-unlock a newly installed tool so it's immediately available."""
    discovery = getattr(loop, "discovery", None)
    if discovery is not None:
        discovery.unlock(session_id, [name])


async def _install_tool(loop: Any, kwargs: dict[str, Any]) -> str:
    name = (kwargs.get("name") or "").strip()
    description = (kwargs.get("description") or "").strip()
    input_schema_raw = kwargs.get("input_schema")
    code = (kwargs.get("code") or "").strip()

    if not name or not description or not input_schema_raw or not code:
        return "Error: install_tool requires 'name', 'description', 'input_schema', and 'code'."

    if isinstance(input_schema_raw, str):
        try:
            input_schema = json.loads(input_schema_raw)
        except json.JSONDecodeError:
            return "Error: input_schema is not valid JSON."
    else:
        input_schema = input_schema_raw

    if not isinstance(input_schema, dict):
        return "Error: input_schema must be a JSON object (JSON Schema)."

    local_ns: dict[str, Any] = {"__import__": __import__}
    try:
        exec(code, local_ns)
    except Exception as e:
        return f"Error: failed to compile tool code: {e}"

    execute_fn = local_ns.get("execute")
    if execute_fn is None or not callable(execute_fn):
        return "Error: code must define an 'execute' async function."

    category = (kwargs.get("category") or "").strip() or None
    intents_raw = kwargs.get("intents")
    intents = None
    if intents_raw:
        if isinstance(intents_raw, list):
            intents = [str(i) for i in intents_raw]
        elif isinstance(intents_raw, str):
            intents = [s.strip() for s in intents_raw.split(",") if s.strip()]

    always_available = kwargs.get("always_available", False)
    if isinstance(always_available, str):
        always_available = always_available.lower() in ("true", "1", "yes")

    try:
        tool = build_tool(
            name=name,
            description=description,
            input_schema=input_schema,
            execute=execute_fn,
            category=category,
            intents=intents,
            always_available=always_available,
            source="model",
        )
        loop.tool_registry.register(tool)

        session_id = getattr(loop.session, "id", "default")
        _ensure_unlocked(loop, session_id, name)

        return json.dumps({
            "status": "installed",
            "name": name,
            "registered": True,
            "available_now": True,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: failed to register tool '{name}': {e}"


async def _install_agent(loop: Any, kwargs: dict[str, Any]) -> str:
    from encre.config import SubAgentConfig

    name = (kwargs.get("name") or "").strip()
    description = (kwargs.get("description") or "").strip()
    system_prompt = (kwargs.get("system_prompt") or "").strip()
    tool_policy = (kwargs.get("tool_policy") or "all").strip()

    if not name or not description:
        return "Error: install_agent requires 'name' and 'description'."

    if tool_policy not in ("all", "readonly", "no_writes"):
        return (
            f"Error: tool_policy must be 'all', 'readonly', or 'no_writes', "
            f"got '{tool_policy}'."
        )

    existing = [sa for sa in loop.config.sub_agents if sa.name == name]
    if existing:
        return json.dumps({
            "status": "already_exists",
            "name": name,
            "message": f"Agent '{name}' is already registered.",
        }, ensure_ascii=False, indent=2)

    try:
        sub_agent = SubAgentConfig(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tool_policy=tool_policy,
            source="model",
        )
        loop.config.sub_agents.append(sub_agent)
        return json.dumps({
            "status": "installed",
            "name": name,
            "tool_policy": tool_policy,
            "available_now": True,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: failed to register agent '{name}': {e}"


async def _install_skill(loop: Any, kwargs: dict[str, Any]) -> str:
    from encre.skills.types import BundledSkillDefinition, SkillSource

    name = (kwargs.get("name") or "").strip()
    description = (kwargs.get("description") or "").strip()
    body = (kwargs.get("body") or "").strip()
    aliases_raw = kwargs.get("aliases")

    if not name or not description or not body:
        return "Error: install_skill requires 'name', 'description', and 'body'."

    skill_registry = getattr(loop, "skill_registry", None)
    if skill_registry is None:
        return "Error: no skill_registry available on this loop."

    aliases = []
    if aliases_raw:
        if isinstance(aliases_raw, list):
            aliases = [str(a) for a in aliases_raw]
        elif isinstance(aliases_raw, str):
            aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

    existing = skill_registry.lookup(name)
    if existing is not None:
        return json.dumps({
            "status": "already_exists",
            "name": name,
        }, ensure_ascii=False, indent=2)

    try:
        async def _get_prompt(args: str | None, context: dict[str, Any]) -> str:
            return body

        skill = BundledSkillDefinition(
            name=name,
            description=description,
            get_prompt_for_command=_get_prompt,
            aliases=aliases,
            source=SkillSource.MANAGED,
            body=body,
        )
        skill_registry.register(skill)
        return json.dumps({
            "status": "installed",
            "name": name,
            "aliases": aliases,
            "available_now": True,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: failed to register skill '{name}': {e}"


async def _install_mcp(loop: Any, kwargs: dict[str, Any]) -> str:
    from encre.tools.mcp import EncreMCPTool

    name = (kwargs.get("name") or "").strip()
    command = (kwargs.get("command") or "").strip()
    url = (kwargs.get("url") or "").strip()
    args_raw = kwargs.get("args")

    if not name:
        return "Error: install_mcp requires 'name'."
    if not command and not url:
        return "Error: install_mcp requires 'command' (stdio) or 'url' (HTTP)."
    if command and url:
        return "Error: specify either 'command' (stdio) or 'url' (HTTP), not both."

    args = []
    if args_raw:
        if isinstance(args_raw, list):
            args = [str(a) for a in args_raw]
        elif isinstance(args_raw, str):
            args = [a.strip() for a in args_raw.split(" ") if a.strip()]

    env = kwargs.get("env")
    cwd = kwargs.get("cwd")

    try:
        mcp_tool = EncreMCPTool(
            command=f"{command} {' '.join(args)}" if command else "",
            server_url=url if url else "",
            env=env if env and isinstance(env, dict) else None,
            cwd=cwd,
            http_timeout=float(kwargs.get("timeout", 60.0)),
        )
        await mcp_tool.register_with(loop.tool_registry, prefix="mcp__")

        if not hasattr(loop, "_mcp_tools"):
            loop._mcp_tools = []
        loop._mcp_tools.append(mcp_tool)

        mcp_entry = {"name": name, "source": "model"}
        if command:
            mcp_entry["type"] = "stdio"
            mcp_entry["command"] = command
            if args:
                mcp_entry["args"] = args
        else:
            mcp_entry["type"] = "http"
            mcp_entry["url"] = url
        if env:
            mcp_entry["env"] = env
        if cwd:
            mcp_entry["cwd"] = cwd
        loop.config.mcp_servers.append(mcp_entry)

        return json.dumps({
            "status": "installed",
            "name": name,
            "transport": "stdio" if command else "http",
            "available_now": True,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: failed to connect MCP server '{name}': {e}"


EncreManageTool = build_tool(
    name="manage",
    description=(
        "God tool for dynamically managing the runtime: install new tools, "
        "register sub-agents, install skills, and connect MCP servers. "
        "All changes take effect immediately.\n\n"

        "Actions:\n"
        "  install_tool  - Create and register a brand new tool. "
        "Requires: name, description, input_schema (JSON Schema), "
        "code (Python async function body named `execute`). "
        "Optional: category, intents, always_available.\n"
        "  install_agent - Register a new named sub-agent. "
        "Requires: name, description. "
        "Optional: system_prompt, tool_policy (all/readonly/no_writes).\n"
        "  install_skill - Install a new skill. "
        "Requires: name, description, body (skill prompt text). "
        "Optional: aliases.\n"
        "  install_mcp   - Connect a new MCP server. "
        "Requires: name, and either command (stdio) or url (HTTP). "
        "Optional: args, env, cwd, timeout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["install_tool", "install_agent", "install_skill", "install_mcp"],
                "description": "What to manage.",
            },
            "name": {
                "type": "string",
                "description": "Name for the tool, agent, skill, or MCP server.",
            },
            "description": {
                "type": "string",
                "description": "Description (for tools, agents, skills).",
            },
            "input_schema": {
                "oneOf": [{"type": "object"}, {"type": "string"}],
                "description": "JSON Schema dict for a new tool's parameters. Required for install_tool.",
            },
            "code": {
                "type": "string",
                "description": "Python source defining an `async def execute(**kwargs)` function. Required for install_tool.",
            },
            "category": {
                "type": "string",
                "description": "Tool category label (for install_tool).",
            },
            "intents": {
                "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
                "description": "Intent tags (comma-separated string or array).",
            },
            "always_available": {
                "type": "boolean",
                "description": "If true, tool is always visible without discovery (default false).",
            },
            "system_prompt": {
                "type": "string",
                "description": "System prompt for the sub-agent (install_agent).",
            },
            "tool_policy": {
                "type": "string",
                "enum": ["all", "readonly", "no_writes"],
                "description": "Tool access policy for the sub-agent (install_agent).",
            },
            "body": {
                "type": "string",
                "description": "Skill prompt body content (for install_skill).",
            },
            "aliases": {
                "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
                "description": "Skill aliases (comma-separated string or array).",
            },
            "command": {
                "type": "string",
                "description": "Executable command for stdio MCP server (install_mcp).",
            },
            "url": {
                "type": "string",
                "description": "URL for HTTP MCP server (install_mcp).",
            },
            "args": {
                "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
                "description": "Command-line arguments for the MCP server (install_mcp).",
            },
            "env": {
                "type": "object",
                "description": "Environment variables for the MCP server (install_mcp).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the MCP server (install_mcp).",
            },
            "timeout": {
                "type": "number",
                "description": "Connection timeout in seconds for MCP server (install_mcp, default 60).",
            },
        },
        "required": ["action"],
    },
    execute=_manage_execute,
    intents=["general", "coding", "system"],
    category="meta",
    triggers=["install", "manage", "register", "deploy", "god", "create tool", "new tool"],
    always_available=True,
    is_concurrency_safe=lambda _: False,
    is_readonly=False,
    is_destructive=True,
)
