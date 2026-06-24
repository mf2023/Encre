#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
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



import asyncio
import types
from contextvars import ContextVar
from typing import Any

from encre.logging_config import get_logger
from encre.tools.base import build_tool

logger = get_logger(__name__)

MAX_SUB_AGENT_DEPTH = 1

_current_loop: ContextVar[Any] = ContextVar("encre_agent_current_loop", default=None)

_parent_loop: Any = None


def set_parent_loop(loop: Any) -> None:
    global _parent_loop
    _parent_loop = loop


def set_active_loop(loop: Any) -> Any:
    return _current_loop.set(loop)


def reset_active_loop(token: Any) -> None:
    _current_loop.reset(token)


def _resolve_loop() -> Any:
    ctx_loop = _current_loop.get()
    if ctx_loop is not None:
        return ctx_loop
    return _parent_loop


def _build_agents_list() -> str:
    """Build a formatted string listing available sub-agents for the tool description."""
    loop = _resolve_loop()
    if loop is None:
        return ""
    sub_agents = getattr(loop.config, "sub_agents", [])
    if not sub_agents:
        return ""
    lines = ["Available sub-agents:"]
    for sa in sub_agents:
        policy = getattr(sa, "tool_policy", "all")
        suffix = ""
        if policy == "readonly":
            suffix = " [read-only]"
        elif policy == "no_writes":
            suffix = " [no writes]"
        lines.append(f"  - {sa.name}: {sa.description}{suffix}")
    lines.append(
        "\nYou can run multiple sub-agents in parallel by passing a `tasks` "
        "array -- each entry has the same shape as the single-task fields."
    )
    return "\n".join(lines)


def _resolve_sub_agent_config(agent_name: str) -> Any:
    """Find a sub-agent by name in the active loop's sub_agents list.

    Returns the matching ``SubAgentConfig`` or ``None`` if not found.
    """
    loop = _resolve_loop()
    if loop is None:
        return None
    sub_agents = getattr(loop.config, "sub_agents", [])
    for sa in sub_agents:
        if sa.name == agent_name:
            return sa
    return None


def _enforce_tool_policy(tool_name: str) -> str | None:
    """Return an error string if the current sub-agent's tool policy
    forbids ``tool_name``; return ``None`` when the call is allowed.

    The policy comes from the active loop's ``config.current_tool_policy``
    attribute.  This is set by the parent loop before delegating to a
    sub-agent (see ``loop._run_sub_agent``) and travels with the
    sub-agent's own ``EncreConfig`` so the pre-tool hook can see it
    regardless of which loop is currently active.
    """
    loop = _resolve_loop()
    if loop is None:
        return None
    policy = getattr(loop.config, "current_tool_policy", "all")
    # Hard-fence FIRST: any sub-agent (depth > 0) must NOT spawn further
    # sub-agents.  This is checked before the policy short-circuit so
    # even an "all"-policy sub-agent cannot call the agent tool.  The
    # depth check is the only layer that reliably stops an LLM from
    # re-trying on a soft error.
    if tool_name == "agent" and getattr(loop, "sub_agent_depth", 0) > 0:
        return (
            "Sub-agents are forbidden from spawning further sub-agents. "
            "The runtime only allows one level of delegation. Complete the "
            "assigned task with your own tools and return the result."
        )
    if not isinstance(policy, str) or policy == "all":
        return None
    write_tools = {"file_write", "file_edit", "write_file", "writeFile", "apply_patch"}
    if policy == "readonly" and tool_name in write_tools:
        return f"Tool {tool_name} is forbidden in readonly sub-agent policy."
    if policy == "readonly" and tool_name in ("docker", "deploy", "workflow",
                                              "cron_create", "cron_delete",
                                              "cron_list", "task_create",
                                              "task_update", "agent"):
        return f"Tool {tool_name} is forbidden in readonly sub-agent policy."
    if policy == "no_writes" and tool_name in write_tools:
        return f"Tool {tool_name} is forbidden in no_writes sub-agent policy."
    if policy == "no_writes" and tool_name in ("docker", "deploy", "workflow", "agent"):
        return f"Tool {tool_name} is forbidden in no_writes sub-agent policy."
    # bash policy is enforced by the safety engine based on the
    # ``dangerous_command_patterns`` list -- we do not duplicate that
    # check here. The safety engine already returns PermissionAsk or
    # PermissionDeny for write-shaped bash commands.
    return None


async def _run_one_sub_agent(
    parent_loop: Any,
    prompt: str,
    agent_name: str,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Run a single sub-agent. Used both by the legacy single-task path
    and by the parallel ``tasks`` path.

    When ``agent_name`` is non-empty, it is resolved against the parent's
    ``config.sub_agents`` list to obtain the ``tool_policy`` and
    ``system_prompt``.  This ensures Explore runs readonly, Plan runs
    no-writes, and general-purpose runs unrestricted.
    """
    logger.info("[agent] agent_name=%s | prompt_len=%d", agent_name, len(prompt))
    logger.info("[agent] prompt=%.300s", prompt)
    # Resolve agent_name -> tool_policy + system_prompt
    tool_policy = "all"
    system_prompt = ""
    if agent_name and parent_loop is not None:
        sub_agents = getattr(parent_loop.config, "sub_agents", [])
        for sa in sub_agents:
            if sa.name == agent_name:
                tool_policy = getattr(sa, "tool_policy", "all")
                system_prompt = getattr(sa, "system_prompt", "")
                break
    if parent_loop is not None and parent_loop.sub_agent_depth >= MAX_SUB_AGENT_DEPTH:
        return {"content": "Error: Maximum sub-agent recursion depth reached", "messages": []}
    if parent_loop is not None:
        sub_result = await parent_loop._run_sub_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            max_turns=0,
            tool_policy=tool_policy,
            progress_callback=progress_callback,
        )
        if isinstance(sub_result, dict):
            return sub_result
        return {"content": str(sub_result), "messages": []}
    from encre.config import EncreConfig
    from encre.loop import EncreLoop
    from encre.session import EncreSession
    config = EncreConfig()
    session = EncreSession(config)
    loop = EncreLoop(config, session)
    sub_result = await loop._run_sub_agent(
        prompt, system_prompt=system_prompt, tool_policy=tool_policy,
        progress_callback=progress_callback,
    )
    if isinstance(sub_result, dict):
        return sub_result
    return {"content": str(sub_result), "messages": []}


async def _agent_execute(**kwargs: Any) -> Any:
    """Spawn one or more sub-agents.

    Two calling shapes are supported:

    1. **Single task (legacy / Claude-Code-style)**: pass ``prompt``
       and optionally ``agent_name``. A single sub-agent runs and its
       result is returned as ``{"content": ..., "messages": [...]}``.

    2. **Parallel tasks (Claude Code ``tasks`` parameter)**: pass
       ``tasks`` as a list of ``{"prompt": ..., "agent_name": ...}``
       objects. Each task runs concurrently via ``asyncio.gather`` and
       the results are returned as a list, in the same order. The
       parent sees a single tool result that aggregates the parallel
       outcomes -- matching Claude Code's "fire off three Explore agents
       in parallel" UX.
    """
    progress_callback = kwargs.get("progress_callback")
    parent_loop = _resolve_loop()

    tasks = kwargs.get("tasks")
    if tasks:
        if not isinstance(tasks, list):
            return {"content": "Error: 'tasks' must be an array of {prompt, agent_name} objects.", "messages": []}
        # Build coroutines for each task
        async def _runner(t: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(t, dict):
                return {"content": "Error: each task must be a dict", "messages": []}
            return await _run_one_sub_agent(
                parent_loop,
                t.get("prompt", ""),
                t.get("agent_name", ""),
                progress_callback=None,
            )
        coros = [_runner(t) for t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        # Normalize exceptions
        out: list[dict[str, Any]] = []
        for idx, r in enumerate(results):
            if isinstance(r, BaseException):
                out.append({"content": f"Sub-agent {idx} failed: {type(r).__name__}: {r}", "messages": []})
            else:
                out.append(r)
        # Format the aggregated result so the parent can read each
        # sub-agent's outcome cleanly.
        lines = [f"Parallel sub-agent results ({len(out)} tasks):"]
        for idx, r in enumerate(out):
            content = r.get("content", "") if isinstance(r, dict) else str(r)
            t = tasks[idx] if idx < len(tasks) and isinstance(tasks[idx], dict) else {}
            name = t.get("agent_name", "") or "default"
            lines.append(f"\n--- Task {idx + 1} ({name}) ---\n{content}")
        return {"content": "\n".join(lines), "messages": [], "sub_results": out}

    return await _run_one_sub_agent(
        parent_loop,
        kwargs.get("prompt", ""),
        kwargs.get("agent_name", ""),
        progress_callback=progress_callback,
    )


EncreAgentTool = build_tool(
    name="agent",
    description="Spawn one or more sub-agents for parallel fan-out ONLY. This is NOT a default "
                "way to get work done -- most tasks should be handled directly with your own tools. "
                "Use it only when a goal cleanly splits into independent workstreams that can run "
                "concurrently and be merged afterwards. Pass a `tasks` array to run multiple "
                "sub-agents in parallel (asyncio.gather); the results are aggregated into a single "
                "response. Be specific in each prompt -- it is the complete instruction for the "
                "sub-agent. Do NOT call this tool from a sub-agent (no nested agent calls) -- if "
                "you are already a delegated sub-agent, complete the assigned task with your own "
                "tools and return a final answer.",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The full task instruction for the sub-agent. "
                               "The sub-agent runs as an independent session with "
                               "all tools and capabilities available. Required for "
                               "single-task mode; ignored when `tasks` is provided.",
            },
            "agent_name": {
                "type": "string",
                "description": "Optional sub-agent name. Built-ins include Explore "
                               "(read-only), Plan (no writes), general-purpose (full), "
                               "coder, researcher, critic, architect, planner.",
            },
            "tasks": {
                "type": "array",
                "description": "Run multiple sub-agents in parallel. Each entry is "
                               "an object with the same `prompt` and `agent_name` "
                               "fields as the single-task form. The parent receives a "
                               "single aggregated result containing all sub-agent "
                               "outcomes in the order they were submitted.",
                "items": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "agent_name": {"type": "string"},
                    },
                    "required": ["prompt"],
                },
            },
        },
    },
    execute=_agent_execute,
    intents=["general", "coding", "system"],
    semantic_type="orchestrate",
    cost_level="high",
    retryability="manual",
    safe_fallback="If delegation is not clearly splitting independent work, continue in the main thread and summarize the next concrete step.",
)


def _agent_to_openai_format(self) -> dict[str, Any]:
    agents_block = _build_agents_list()
    description = self.description
    if agents_block:
        description += f"\n\n{agents_block}"
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": description,
            "parameters": self.input_schema,
        },
    }


def _agent_to_anthropic_format(self) -> dict[str, Any]:
    agents_block = _build_agents_list()
    description = self.description
    if agents_block:
        description += f"\n\n{agents_block}"
    return {
        "name": self.name,
        "description": description,
        "input_schema": self.input_schema,
    }


# Monkey-patch the format methods to include dynamic agents list
EncreAgentTool.to_openai_format = types.MethodType(_agent_to_openai_format, EncreAgentTool)
EncreAgentTool.to_anthropic_format = types.MethodType(_agent_to_anthropic_format, EncreAgentTool)
