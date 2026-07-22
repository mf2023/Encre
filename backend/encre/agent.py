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

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from encre.goal import EncreGoalLoop
    from encre.swarm.session import EncreSwarmSession

from encre.channels.slash_commands import (
    EncreCommandRegistry,
    load_project_commands,
    load_user_commands,
)
from encre.codebase.indexer import EncreCodeIndex
from encre.config import EncreConfig, SubAgentConfig
from encre.evolution.config import EvolutionConfig
from encre.feedback.learner import EncreFeedbackLearner
from encre.hooks.file_loader import load_project_hooks
from encre.hooks.system import EncreHookSystem
from encre.loop import EncreLoop
from encre.memdir.system import EncreMemorySystem
from encre.plugins.registry import PluginRegistry
from encre.profile.system import EncreProfileSystem
from encre.recovery import ErrorRecoveryEngine
from encre.safety import EncreSafetyEngine
from encre.session import EncreSession
from encre.skills.bundled import create_bundled_skills
from encre.skills.registry import EncreSkillRegistry, parse_yaml_frontmatter
from encre.soul.system import EncreSoulSystem
from encre.telemetry import EncreTelemetry
from encre.tools.defaults import register_default_tools
from encre.tools.registry import ToolRegistry
from encre.utils.types import AgentEvent, ToolCallStart, ToolProgress

logger = logging.getLogger(__name__)

_BUNDLED_SKILLS_LOADED = False
_USER_SKILLS_LOADED_DIRS: set[str] = set()
_PROJECT_SKILLS_LOADED_DIRS: set[str] = set()
_PROJECT_SUB_AGENT_LOADED_DIRS: set[str] = set()
_PLUGINS_DISCOVERED = False
_SHARED_SKILL_REGISTRY: EncreSkillRegistry | None = None
_SHARED_PLUGIN_REGISTRY: PluginRegistry | None = None

# Project-level skill directories scanned under the active workspace.
# The first existing directory wins per workspace; later directories are
# merged so users can mix our native (.encre/skills) and Claude Code
# (.claude/skills) layouts side by side.
_PROJECT_SKILLS_CANDIDATE_DIRS: tuple[str, ...] = (
    ".encre/skills",
    ".claude/skills",
)

# Project-level sub-agent directories scanned under the active workspace.
# Native (.encre/agents), Claude Code (.claude/agents) and Codex
# (.codex/agents) layouts are merged side by side.
_PROJECT_SUB_AGENT_CANDIDATE_DIRS: tuple[str, ...] = (
    ".encre/agents",
    ".claude/agents",
    ".codex/agents",
)


def _ensure_bundled_skills_loaded(registry: EncreSkillRegistry) -> None:
    global _BUNDLED_SKILLS_LOADED
    if _BUNDLED_SKILLS_LOADED and registry.list_all():
        return
    create_bundled_skills(registry)
    # Load static built-in skills (one SKILL.md per sub-directory).  These are
    # pure markdown - adding a built-in skill is just dropping a folder.
    from encre.skills.builtin import builtin_skills_dir
    from encre.skills.types import SkillSource
    registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)
    _BUNDLED_SKILLS_LOADED = True


def _ensure_user_skills_loaded(registry: EncreSkillRegistry, skills_dir: str) -> None:
    global _USER_SKILLS_LOADED_DIRS
    if skills_dir in _USER_SKILLS_LOADED_DIRS:
        return
    from encre.skills.types import SkillSource
    registry.load_from_dir(skills_dir, source=SkillSource.USER)
    _USER_SKILLS_LOADED_DIRS.add(skills_dir)


def _ensure_project_skills_loaded(
    registry: EncreSkillRegistry, workspace_path: str
) -> None:
    """Load project-level skills from the active workspace.

    Scans well-known directories (``.encre/skills`` and ``.claude/skills``)
    and reuses :meth:`EncreSkillRegistry.load_from_dir` with
    :class:`SkillSource.PROJECT` so the standard priority/override logic
    in the registry decides which copy of a same-named skill wins.
    """
    global _PROJECT_SKILLS_LOADED_DIRS
    if not workspace_path:
        return
    from encre.skills.types import SkillSource

    for rel in _PROJECT_SKILLS_CANDIDATE_DIRS:
        full = os.path.join(workspace_path, rel)
        if full in _PROJECT_SKILLS_LOADED_DIRS:
            continue
        if not os.path.isdir(full):
            continue
        try:
            registry.load_from_dir(full, source=SkillSource.PROJECT)
            _PROJECT_SKILLS_LOADED_DIRS.add(full)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load project skills from %s: %s", full, e)


def _load_sub_agent_file(path: str) -> SubAgentConfig | None:
    """Parse a single project-level sub-agent definition file.

    Supports ``.json``, ``.yaml``/``.yml`` and ``.md`` (YAML frontmatter +
    body as ``system_prompt``). Returns ``None`` when the file is missing a
    valid ``name``.
    """
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        logger.debug("Could not read project sub-agent file %s: %s", path, e)
        return None

    data: dict[str, Any] = {}
    body = ""
    lower = path.lower()
    if lower.endswith(".json"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse project sub-agent JSON %s: %s", path, e)
            return None
    elif lower.endswith(".yaml") or lower.endswith(".yml"):
        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            logger.warning("Failed to parse project sub-agent YAML %s: %s", path, e)
            return None
    elif lower.endswith(".md"):
        metadata, body = parse_yaml_frontmatter(content)
        data = metadata
    else:
        return None

    if not isinstance(data, dict):
        return None

    name = str(data.get("name", "")).strip().lower().replace("_", "-")
    if not name:
        return None

    system_prompt = str(data.get("system_prompt") or data.get("prompt") or "").strip()
    if not system_prompt and body:
        system_prompt = body.strip()
    description = str(data.get("description", "")).strip()
    tool_policy = str(data.get("tool_policy") or data.get("policy") or "all").strip()
    hidden = bool(data.get("hidden", False))

    return SubAgentConfig(
        name=name,
        description=description,
        system_prompt=system_prompt,
        hidden=hidden,
        tool_policy=tool_policy,
    )


def _ensure_project_sub_agents_loaded(
    agent: EncreAgent, workspace_path: str
) -> None:
    """Load project-level sub-agents from the active workspace.

    Scans well-known directories (``.encre/agents``, ``.claude/agents`` and
    ``.codex/agents``) and merges valid definitions into
    ``agent.config.sub_agents``. Project-level entries override builtins or
    global-config entries with the same name, matching the
    project-overrides-global convention.
    """
    global _PROJECT_SUB_AGENT_LOADED_DIRS
    if not workspace_path:
        return

    for rel in _PROJECT_SUB_AGENT_CANDIDATE_DIRS:
        full = os.path.join(workspace_path, rel)
        if full in _PROJECT_SUB_AGENT_LOADED_DIRS:
            continue
        if not os.path.isdir(full):
            continue
        _PROJECT_SUB_AGENT_LOADED_DIRS.add(full)
        try:
            loaded: list[SubAgentConfig] = []
            seen: set[str] = set()
            for entry in sorted(os.listdir(full)):
                if entry.startswith("."):
                    continue
                file_path = os.path.join(full, entry)
                if not os.path.isfile(file_path):
                    continue
                sub_agent = _load_sub_agent_file(file_path)
                if sub_agent is None or sub_agent.name in seen:
                    continue
                loaded.append(sub_agent)
                seen.add(sub_agent.name)

            # Project entries override existing same-name agents.
            agent.config.sub_agents = [
                sa for sa in getattr(agent.config, "sub_agents", [])
                if sa.name not in seen
            ]
            agent.config.sub_agents.extend(loaded)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load project sub-agents from %s: %s", full, e)


def _get_shared_skill_registry() -> EncreSkillRegistry:
    global _SHARED_SKILL_REGISTRY
    if _SHARED_SKILL_REGISTRY is None:
        registry = EncreSkillRegistry()
        _ensure_bundled_skills_loaded(registry)
        from encre.config import get_data_dir
        _ensure_user_skills_loaded(registry, str(get_data_dir() / "skills"))
        _SHARED_SKILL_REGISTRY = registry
    return _SHARED_SKILL_REGISTRY


def _get_shared_plugin_registry() -> PluginRegistry:
    global _SHARED_PLUGIN_REGISTRY, _PLUGINS_DISCOVERED
    if _SHARED_PLUGIN_REGISTRY is None:
        _SHARED_PLUGIN_REGISTRY = PluginRegistry()
    if not _PLUGINS_DISCOVERED:
        _SHARED_PLUGIN_REGISTRY.discover_all()
        _PLUGINS_DISCOVERED = True
    return _SHARED_PLUGIN_REGISTRY


class EncreAgent:
    def __init__(
        self,
        config: EncreConfig | None = None,
        tool_registry: ToolRegistry | None = None,
        hook_system: EncreHookSystem | None = None,
        memory_system: EncreMemorySystem | None = None,
        profile_system: EncreProfileSystem | None = None,
        soul_system: EncreSoulSystem | None = None,
        skill_registry: EncreSkillRegistry | None = None,
        command_registry: EncreCommandRegistry | None = None,
        safety: EncreSafetyEngine | None = None,
        recovery: ErrorRecoveryEngine | None = None,
        plugin_registry: PluginRegistry | None = None,
        feedback: EncreFeedbackLearner | None = None,
        code_index: EncreCodeIndex | None = None,
    ) -> None:
        from encre.config import get_data_dir
        self.config = config or EncreConfig()
        self.tool_registry = tool_registry or ToolRegistry()
        if not self.tool_registry.list_tools():
            register_default_tools(self.tool_registry)
        self.hook_system = hook_system or EncreHookSystem()
        if memory_system is not None:
            self.memory_system = memory_system
        else:
            self.memory_system = EncreMemorySystem(str(get_data_dir() / "memory"))
        if profile_system is not None:
            self.profile_system = profile_system
        else:
            mem_dir = str(get_data_dir() / "memory")
            self.profile_system = EncreProfileSystem(mem_dir)
            self.profile_system.load()
        if soul_system is not None:
            self.soul_system = soul_system
        else:
            self.soul_system = EncreSoulSystem()
            self.soul_system.ensure_defaults()
            self.soul_system.load()
        self.safety = safety or EncreSafetyEngine(self.config)
        self.recovery = recovery or ErrorRecoveryEngine()
        self.feedback = feedback or EncreFeedbackLearner()
        self.code_index = code_index
        self.session = EncreSession(self.config)
        # Inject built-in sub-agents (hidden from settings UI)
        from encre.agents.builtin import get_builtin_sub_agents
        existing_names = {sa.name for sa in self.config.sub_agents}
        for builtin in get_builtin_sub_agents():
            if builtin.name not in existing_names:
                self.config.sub_agents.append(builtin)
        # Load project-level sub-agents for the active workspace. Project
        # entries override builtins/global-config entries with the same name.
        _ensure_project_sub_agents_loaded(self, self.config.workspace)
        self.telemetry = EncreTelemetry(enabled=self.config.telemetry_enabled)
        self.evolution = EvolutionConfig.create_default()
        self.plugin_registry = plugin_registry or _get_shared_plugin_registry()
        self.skill_registry = skill_registry or _get_shared_skill_registry()
        # Load project-level skills for the active workspace.  This is a
        # no-op when no workspace is configured or when neither
        # .encre/skills nor .claude/skills exists in the workspace root.
        _ensure_project_skills_loaded(self.skill_registry, self.config.workspace)
        # Slash commands follow the same project-discovery pattern as
        # skills: builtin commands stay registered, project-level
        # ``.encre/commands`` and ``.claude/commands`` files are layered
        # on top with priority-based merging.  User-level commands (home
        # directory + settings.json) are loaded first and persist across
        # workspace switches; project commands reload per workspace.
        self.command_registry = command_registry or EncreCommandRegistry()
        load_user_commands(self.command_registry)
        load_project_commands(self.config.workspace, self.command_registry)
        # Wire project-level hooks from ``.encre/hooks.yaml`` or
        # ``.claude/settings.json`` straight into the live hook system
        # so they fire alongside the in-process handlers.
        if self.config.workspace:
            try:
                load_project_hooks(self.hook_system, self.config.workspace)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to load project hooks: %s", e)
            # Apply OpenAI Codex CLI configuration (AGENTS.md chain,
            # ``agents.<name>``, ``skills.config``, ``approval_policy``,
            # ``mcp_servers``) onto Encre's existing subsystems.
            try:
                from encre.codex_compat import apply_codex_config
                apply_codex_config(self, self.config.workspace)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to apply Codex config: %s", e)
        self.loop = EncreLoop(
            self.config, self.session, self.tool_registry,
            self.hook_system, self.safety,
            self.memory_system,
            profile_system=self.profile_system,
            soul_system=self.soul_system,
            skill_registry=self.skill_registry,
            telemetry=self.telemetry,
            evolution=self.evolution,
            recovery=self.recovery,
            feedback=self.feedback,
            code_index=self.code_index,
        )
        self._wire_tools()
        self._load_plugins()
        # MCP lifecycle (lazy init on first run)
        self._mcp_tools: list[Any] = []
        self._mcp_initialized = False
        # Engine-install bridge: computer-use sessions call this when
        # the bundled chromium binary is missing; we yield the
        # resulting events to the agent's stream so the user (not the
        # LLM) sees the prompt.
        from encre.computer.engine_bridge import EngineRequester
        self._engine_requester = EngineRequester()
        self._install_engine_requester()
    def _install_engine_requester(self) -> None:
        """Propagate the engine-install requester to all tools that
        need it (computer_use, browser, etc.).  Idempotent.

        We import the module-level ``set_engine_requester`` function
        from each tool module and call it -- this sets the requester
        on the singleton session so that any subsequent browser /
        desktop action routes the install prompt through the requester
        instead of returning an error to the LLM.
        """
        for mod_name in ("computer_use", "browser"):
            try:
                mod = __import__(
                    f"encre.tools.builtin.{mod_name}",
                    fromlist=["set_engine_requester"],
                )
            except Exception:
                continue
            setter = getattr(mod, "set_engine_requester", None)
            if callable(setter):
                try:
                    setter(self._engine_requester)
                except Exception:  # pragma: no cover - defensive
                    logger.warning(
                        "set_engine_requester(%s) failed", mod_name,
                        exc_info=True,
                    )

    def set_engine_emit(self, emit: Any) -> None:
        """Install the immediate-emit hook on the engine requester.

        Called by the WebSocket router with a callable that
        serializes an :class:`EngineInstallRequest` and sends it
        over the wire.  After this is set, the requester will
        fire the event the moment a browser / desktop session
        asks for an install, *without* waiting for the agent's
        event loop to tick -- so the desktop dialog pops up
        promptly even when the loop is blocked on the tool call.
        """
        self._engine_requester.set_emit(emit)

    def resolve_engine_install(self, request_id: str, choice: str) -> bool:
        """Called by the WebSocket layer when the user picks an
        option from the desktop dialog.  Returns True if the
        request was found and resolved."""
        return self._engine_requester.resolve(request_id, choice)

    async def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        custom_instructions: str = "",
    ) -> AsyncGenerator[AgentEvent, None]:
        # Lazy-init MCP connections on first run
        if not self._mcp_initialized:
            await self._init_mcp()
            self._mcp_initialized = True
        tool_names: list[str] = []
        slash_commands = [cmd.to_dict() for cmd in self.command_registry.list_all()]
        async for event in self.loop.run(
            prompt, system_prompt, custom_instructions=custom_instructions,
            slash_command_mode=self.config.slash_command_mode,
            slash_commands=slash_commands,
        ):
            if isinstance(event, ToolCallStart):
                tool_names.append(event.name)
            elif isinstance(event, ToolProgress):
                tool_names.append(event.tool_name)
            # Forward every pending engine-install request before
            # we yield any other event from the tool, so the dialog
            # can pop up promptly and the tool's await on the
            # requester future resolves cleanly.
            async for req in self._engine_requester.drain():
                yield req
            yield event
        async for req in self._engine_requester.drain():
            yield req
        # Trigger async profile inference after session completes
        if hasattr(self, "profile_system") and self.profile_system is not None:
            try:
                import asyncio
                self._profile_inference_task = asyncio.create_task(
                    self.profile_system.infer_from_session(
                        self.session.messages, self.loop.backend
                    )
                )
            except Exception:
                pass

        # Feed tool usage pattern to learning engine for skill crystallization
        if tool_names and hasattr(self, "_learning_engine") and self._learning_engine is not None:
            with contextlib.suppress(Exception):
                await self._learning_engine.analyze_run(tool_names, prompt)

    async def run_with_tools(
        self,
        prompt: str,
        tools: list[Any],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        for tool in tools:
            self.tool_registry.register(tool)
        async for event in self.run(prompt, system_prompt):
            yield event

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        self.session.add_message(role, content, **kwargs)

    def rebuild_backend(self) -> None:
        """Recreate the loop's backend from current config.

        Call this after changing config.backend_type, config.api_key,
        config.base_url, or config.model so the backend instance matches
        the updated settings.
        """
        from encre.backend import create_backend as _cb
        active_model = self.config.get_active_model()
        thinking_config = active_model.thinking_config or self.config.thinking_config
        self.loop.backend = _cb(
            self.config.backend_type,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            models=self.config.models,
            thinking_config=thinking_config,
            **self.config.backend_kwargs,
        )

    def load_plugins(self, discover: bool = True) -> int:
        """Load and activate all plugins. Returns count of activated plugins.

        If discover=True, scans entry points and plugin directories first.
        """
        global _PLUGINS_DISCOVERED
        if discover:
            if self.plugin_registry is _SHARED_PLUGIN_REGISTRY:
                if not _PLUGINS_DISCOVERED:
                    self.plugin_registry.discover_all()
                    _PLUGINS_DISCOVERED = True
            elif not _PLUGINS_DISCOVERED:
                self.plugin_registry.discover_all()
                _PLUGINS_DISCOVERED = True
        self.plugin_registry.activate_all()

        # Inject plugin tools
        for tool in self.plugin_registry.get_all_tools():
            self.tool_registry.register(tool)

        # Inject plugin skills
        for skill in self.plugin_registry.get_all_skills():
            self.skill_registry.register(skill)

        # Inject plugin hooks
        for event_type, handlers in self.plugin_registry.get_all_hooks().items():
            for handler in handlers:
                self.hook_system.register_handler(event_type, handler)

        # Register plugin backends
        for _name, _backend_cls in self.plugin_registry.get_all_backends().items():
            pass
            # Plugin backends are registered by name for later use

        return self.plugin_registry.active_count

    def _load_plugins(self) -> None:
        """Auto-load plugins during agent initialization."""
        if getattr(self, "_plugins_loaded", False):
            return
        self.load_plugins(discover=True)
        self._plugins_loaded = True

    def _wire_tools(self) -> None:
        """Wire parent loop reference to tools that need it."""
        from encre.tools.builtin.agent import set_parent_loop as _agent_set_parent
        from encre.tools.builtin.codebase import set_parent_loop as _codebase_set_parent
        from encre.tools.builtin.find_tool import set_parent_loop as _find_set_parent
        _agent_set_parent(self.loop)
        _codebase_set_parent(self.loop)
        _find_set_parent(self.loop)

    # ------------------------------------------------------------------
    # MCP lifecycle
    # ------------------------------------------------------------------

    async def _init_mcp(self) -> None:
        """Connect configured MCP servers and register their tools."""
        from encre.tools.mcp import EncreMCPTool

        for server in self.config.mcp_servers:
            # Support both old (enabled) and new (disabled) field names
            enabled_old = server.get("enabled", True)
            disabled_new = server.get("disabled", False)
            if isinstance(enabled_old, bool):
                if not enabled_old:
                    continue
            elif disabled_new:
                continue

            # Support both old (transport) and new (type) field names
            transport = server.get("type") or server.get("transport", "stdio")
            command = server.get("command", "")
            args = server.get("args", [])
            # Support both old (server_url) and new (url) field names
            server_url = server.get("url") or server.get("server_url", "")
            env = server.get("env")
            cwd = server.get("cwd")
            # Support both old (http_timeout) and new (timeout) field names
            http_timeout = server.get("timeout") or server.get("http_timeout", 60.0)

            # Skip if no command for stdio or no URL for http
            if transport == "http":
                if not server_url:
                    continue
            elif not command:
                continue

            # Build full command with args
            full_command = command + " " + " ".join(str(a) for a in args) if args else command

            try:
                mcp_tool = EncreMCPTool(
                    command=full_command if transport == "stdio" else "",
                    server_url=server_url if transport == "http" else "",
                    env=env if env else None,
                    cwd=cwd or None,
                    http_timeout=float(http_timeout) if http_timeout else 60.0,
                )
                await mcp_tool.register_with(self.tool_registry, prefix="mcp__")
                self._mcp_tools.append(mcp_tool)
            except Exception:
                import logging
                logging.getLogger("encre.agent").exception(
                    "Failed to connect MCP server: %s", server.get("name", command)
                )

    async def _disconnect_mcp(self) -> None:
        """Disconnect all MCP servers and remove their tools from the registry."""
        # Remove discovered MCP tool entries from the registry
        mcp_keys = [k for k in self.tool_registry.list_tools() if k.startswith("mcp__")]
        for key in mcp_keys:
            self.tool_registry._tools.pop(key, None)

        # Disconnect MCP clients
        for mcp in self._mcp_tools:
            with contextlib.suppress(Exception):
                await mcp._disconnect()
        self._mcp_tools.clear()

    async def reconnect_mcp(self) -> None:
        """Disconnect old MCP connections and reconnect with current config."""
        await self._disconnect_mcp()
        await self._init_mcp()

    def set_scheduler(self, scheduler: Any) -> None:
        """Wire a scheduler instance to cron tools."""
        from encre.tools.builtin.cron_create import EncreCronCreateTool
        from encre.tools.builtin.cron_delete import EncreCronDeleteTool
        from encre.tools.builtin.cron_list import EncreCronListTool
        EncreCronCreateTool.set_scheduler(scheduler)
        EncreCronDeleteTool.set_scheduler(scheduler)
        EncreCronListTool.set_scheduler(scheduler)

    def reset(self) -> None:
        self.session = EncreSession(self.config)
        self.telemetry.reset()
        self.evolution = EvolutionConfig.create_default()
        self.loop = EncreLoop(
            self.config, self.session, self.tool_registry,
            self.hook_system, self.safety,
            self.memory_system,
            profile_system=self.profile_system,
            soul_system=self.soul_system,
            skill_registry=self.skill_registry,
            telemetry=self.telemetry,
            evolution=self.evolution,
            recovery=self.recovery,
            feedback=self.feedback,
            code_index=self.code_index,
        )
        self._wire_tools()
        self._plugins_loaded = False
        self._load_plugins()
        self._mcp_initialized = False

    async def aclose(self) -> None:
        """Release all resources held by this agent.

        Closes the backend (httpx clients, model memory), clears session state,
        flushes telemetry, and disconnects MCP servers.
        """
        # Disconnect MCP servers
        with contextlib.suppress(Exception):
            await self._disconnect_mcp()

        # Close the agent loop (which closes the backend)
        with contextlib.suppress(Exception):
            await self.loop.aclose()

        # Flush telemetry
        if self.telemetry is not None:
            with contextlib.suppress(Exception):
                self.telemetry.flush()

        # Clear session
        if self.session is not None:
            self.session.messages.clear()
            self.session.rebuild_runtime_caches()

    def activate_skill(self, name: str, args: str | None = None) -> str:
        return self.skill_registry.activate(name, args)

    def respond_permission(self, decision: bool) -> None:
        """Approve or deny the pending permission request from the current turn."""
        self.loop.resolve_permission(decision)

    def goal(
        self,
        description: str,
        success_criteria: str,
        max_attempts: int = 20,
        timeout_seconds: int = 3600,
    ) -> EncreGoalLoop:
        """Create a goal-driven autonomous loop for this agent.

        Usage:
            result = await agent.goal(
                "Implement login", "JWT tokens work, tests pass"
            ).execute()
        """
        from encre.goal import EncreGoalLoop
        return EncreGoalLoop(
            self,
            description=description,
            success_criteria=success_criteria,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )

    def swarm(
        self,
        goal: str,
        max_concurrent: int = 5,
        enable_reviewer: bool = True,
        timeout_seconds: float = 3600.0,
    ) -> EncreSwarmSession:
        """Create a multi-agent swarm session for this agent.

        Decomposes the goal, assigns roles, and executes in parallel with
        shared blackboard and optional reviewer gates.

        Usage:
            result = await agent.swarm(
                "Build a full-stack TODO app with auth"
            ).execute()
        """
        from encre.swarm.session import EncreSwarmSession
        return EncreSwarmSession(
            self,
            goal=goal,
            max_concurrent=max_concurrent,
            enable_reviewer=enable_reviewer,
            timeout_seconds=timeout_seconds,
        )
