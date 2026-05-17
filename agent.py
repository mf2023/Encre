#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
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

from typing import Any, AsyncGenerator

from yim.config import YmiConfig
from yim.evolution.config import EvolutionConfig
from yim.hooks.system import YmiHookSystem
from yim.loop import YmiLoop
from yim.memdir.system import YmiMemorySystem
from yim.plugins.registry import PluginRegistry
from yim.recovery import ErrorRecoveryEngine
from yim.safety import YmiSafetyEngine
from yim.session import YmiSession
from yim.skills.registry import YmiSkillRegistry
from yim.skills.bundled import create_bundled_skills
from yim.telemetry import YmiTelemetry
from yim.tools.registry import ToolRegistry
from yim.utils.types import AgentEvent


class YmiAgent:
    def __init__(
        self,
        config: YmiConfig | None = None,
        tool_registry: ToolRegistry | None = None,
        hook_system: YmiHookSystem | None = None,
        memory_system: YmiMemorySystem | None = None,
        skill_registry: YmiSkillRegistry | None = None,
        safety: YmiSafetyEngine | None = None,
        recovery: ErrorRecoveryEngine | None = None,
        plugin_registry: PluginRegistry | None = None,
    ) -> None:
        self.config = config or YmiConfig()
        self.tool_registry = tool_registry or ToolRegistry()
        self.hook_system = hook_system or YmiHookSystem()
        if memory_system is not None:
            self.memory_system = memory_system
        else:
            from yim.config import get_data_dir
            self.memory_system = YmiMemorySystem(str(get_data_dir() / "memory"))
        self.safety = safety or YmiSafetyEngine(self.config)
        self.recovery = recovery or ErrorRecoveryEngine()
        self.session = YmiSession(self.config)
        self.telemetry = YmiTelemetry(enabled=self.config.telemetry_enabled)
        self.evolution = EvolutionConfig.create_default()
        self.plugin_registry = plugin_registry or PluginRegistry()
        self.skill_registry = skill_registry
        if self.skill_registry is None:
            self.skill_registry = YmiSkillRegistry()
            create_bundled_skills(self.skill_registry)
        self.loop = YmiLoop(
            self.config, self.session, self.tool_registry,
            self.hook_system, self.safety,
            self.memory_system, self.skill_registry,
            self.telemetry,
            evolution=self.evolution,
            recovery=self.recovery,
        )
        self._wire_tools()
        self._load_plugins()

    async def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        async for event in self.loop.run(prompt, system_prompt):
            yield event

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
        from yim.backend import create_backend as _cb
        self.loop.backend = _cb(
            self.config.backend_type,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            **self.config.backend_kwargs,
        )

    def load_plugins(self, discover: bool = True) -> int:
        """Load and activate all plugins. Returns count of activated plugins.

        If discover=True, scans entry points and plugin directories first.
        """
        if discover:
            self.plugin_registry.discover_all()
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
        for name, backend_cls in self.plugin_registry.get_all_backends().items():
            from yim.backend import create_backend as _cb
            # Plugin backends are registered by name for later use

        return self.plugin_registry.active_count

    def _load_plugins(self) -> None:
        """Auto-load plugins during agent initialization."""
        self.load_plugins(discover=True)

    def _wire_tools(self) -> None:
        """Wire parent loop reference to tools that need it."""
        from yim.tools.builtin.agent import YmiAgentTool
        YmiAgentTool.set_parent_loop(self.loop)

    def set_scheduler(self, scheduler: Any) -> None:
        """Wire a scheduler instance to cron tools."""
        from yim.tools.builtin.cron_create import YmiCronCreateTool
        from yim.tools.builtin.cron_delete import YmiCronDeleteTool
        from yim.tools.builtin.cron_list import YmiCronListTool
        YmiCronCreateTool.set_scheduler(scheduler)
        YmiCronDeleteTool.set_scheduler(scheduler)
        YmiCronListTool.set_scheduler(scheduler)

    def reset(self) -> None:
        self.session = YmiSession(self.config)
        self.telemetry.reset()
        self.evolution = EvolutionConfig.create_default()
        self.loop = YmiLoop(
            self.config, self.session, self.tool_registry,
            self.hook_system, self.safety,
            self.memory_system, self.skill_registry,
            self.telemetry,
            evolution=self.evolution,
            recovery=self.recovery,
        )
        self._wire_tools()
        self._load_plugins()

    async def aclose(self) -> None:
        """Release all resources held by this agent.

        Closes the backend (httpx clients, model memory), clears session state,
        and flushes telemetry.
        """
        # Close the agent loop (which closes the backend)
        try:
            await self.loop.aclose()
        except Exception:
            pass

        # Flush telemetry
        if self.telemetry is not None:
            try:
                self.telemetry.flush()
            except Exception:
                pass

        # Clear session
        if self.session is not None:
            self.session.messages.clear()

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
    ) -> "YmiGoalLoop":
        """Create a goal-driven autonomous loop for this agent.

        Usage:
            result = await agent.goal(
                "Implement login", "JWT tokens work, tests pass"
            ).execute()
        """
        from yim.goal import YmiGoalLoop
        return YmiGoalLoop(
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
    ) -> "YmiSwarmSession":
        """Create a multi-agent swarm session for this agent.

        Decomposes the goal, assigns roles, and executes in parallel with
        shared blackboard and optional reviewer gates.

        Usage:
            result = await agent.swarm(
                "Build a full-stack TODO app with auth"
            ).execute()
        """
        from yim.swarm.session import YmiSwarmSession
        return YmiSwarmSession(
            self,
            goal=goal,
            max_concurrent=max_concurrent,
            enable_reviewer=enable_reviewer,
            timeout_seconds=timeout_seconds,
        )
