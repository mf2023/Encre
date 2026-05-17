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

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from yim.backend import create_backend
from yim.backends.base import BaseBackend
from yim.compact.engine import YmiCompactEngine
from yim.config import YmiConfig
from yim.evolution.config import EvolutionConfig
from yim.logging_config import get_logger
from yim.prompts.base import YmiPromptTemplate

logger = get_logger(__name__)
from yim.recovery import ErrorRecoveryEngine, RetryableExecutor
from yim.safety import YmiSafetyEngine
from yim.utils.tokens import count_message_tokens
from yim.session import YmiSession
from yim.telemetry import YmiTelemetry
from yim.tools.registry import ToolRegistry
from yim.hooks.system import YmiHookSystem
from yim.memdir.system import YmiMemorySystem
from yim.skills.registry import YmiSkillRegistry
from yim.utils.types import (
    AgentEvent,
    BackendError,
    BackendFinish,
    BackendText,
    BackendThinking,
    BackendToolCall,
    BackendToolCallDelta,
    Finish,
    TextDelta,
    ThinkingDelta,
    ToolResult,
    create_finish,
    create_permission_request,
    create_text_delta,
    create_thinking_delta,
    create_tool_call_delta,
    create_tool_call_end,
    create_tool_call_start,
    create_tool_progress,
    create_tool_result,
)


class YmiLoop:
    def __init__(
        self,
        config: YmiConfig,
        session: YmiSession,
        tool_registry: ToolRegistry | None = None,
        hook_system: YmiHookSystem | None = None,
        safety: YmiSafetyEngine | None = None,
        memory_system: YmiMemorySystem | None = None,
        skill_registry: YmiSkillRegistry | None = None,
        telemetry: YmiTelemetry | None = None,
        evolution: EvolutionConfig | None = None,
        recovery: ErrorRecoveryEngine | None = None,
    ) -> None:
        self.config = config
        self.session = session
        self.tool_registry = tool_registry or ToolRegistry()
        self.hook_system = hook_system or YmiHookSystem()
        self.memory_system = memory_system
        self.skill_registry = skill_registry
        self.telemetry = telemetry or YmiTelemetry(enabled=False)
        evo = evolution or EvolutionConfig.create_default()
        self.learner = evo.learner
        self.optimizer = evo.optimizer
        self.reflex = evo.reflex
        self.meta = evo.meta
        self.recovery_engine = recovery or ErrorRecoveryEngine()
        self.backend: BaseBackend | None = create_backend(
            config.backend_type,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            **config.backend_kwargs,
        )
        self.safety = safety or YmiSafetyEngine(config)
        self.compact_engine = YmiCompactEngine()
        self.prompt_builder = YmiPromptTemplate()
        self._permission_event: asyncio.Event | None = None
        self._permission_decision: bool = False
        self._pending_tool_name: str = ""

    async def aclose(self) -> None:
        """Release backend resources (httpx clients, model memory, etc.)."""
        if self.backend is not None:
            try:
                await self.backend.aclose()
            except Exception as e:
                logger.warning(f"Error closing backend: {e}", extra={"backend": type(self.backend).__name__})

    def resolve_permission(self, decision: bool) -> None:
        """Called by the agent owner to approve or deny a pending permission request."""
        self._permission_decision = decision
        if self._permission_event is not None:
            self._permission_event.set()

    async def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if self.backend is None:
            yield create_finish("error", error="No backend configured. Send a 'configure' message first.")
            return
        if system_prompt is None:
            tools = None
            if self.backend.supports_tool_calling():
                tools = self.tool_registry.get_openai_tools()
            system_prompt = self.prompt_builder.build_system_prompt(
                self.config.permission_mode,
                tools=tools,
            )

        if not self.session.messages:
            self.session.add_message("system", system_prompt)
            self.session.add_message("user", prompt)
        else:
            # Avoid duplicate if WS handler already added the same user message for early persist
            last = self.session.messages[-1]
            if last.get("role") != "user" or last.get("content") != prompt:
                self.session.add_message("user", prompt)

        await self.hook_system.emit_session_start()
        while not self.session.is_max_turns_reached():
            turn_start = time.time()
            turn_events = 0
            await self.hook_system.emit_turn_start(self.session.turn_count)
            self.session.checkpoint(f"turn_{self.session.turn_count}")
            await self.hook_system.emit_checkpoint(f"turn_{self.session.turn_count}")
            if await self.compact_engine.should_compact(
                self.session.messages, self.backend.context_window_size()
            ):
                old_count = len(self.session.messages)
                est_tokens = count_message_tokens(self.session.messages)
                await self.hook_system.emit_pre_compact(old_count, est_tokens)
                self.session.messages = await self.compact_engine.compact(
                    self.session.messages, self.backend.context_window_size()
                )
                await self.hook_system.emit_post_compact(old_count, len(self.session.messages))

            tools = None
            if self.backend.supports_tool_calling():
                tools = self.tool_registry.get_openai_tools()

            # Inject evolution guidance (skip first turn)
            if self.session.turn_count > 0:
                guidance_parts: list[str] = []
                learner_hint = self.learner.get_guidance("__any__", prompt[:300])
                if not learner_hint:
                    learner_hint = ""  # no guidance yet
                reflex_hint = self.reflex.get_improvement_context()
                meta_hint = self.meta.get_self_awareness_context()
                for hint in [learner_hint, reflex_hint, meta_hint]:
                    if hint:
                        guidance_parts.append(hint)
                if guidance_parts:
                    guidance_msg = "\n\n".join(guidance_parts)
                    self.session.add_message("user", f"[SYSTEM GUIDANCE]\n{guidance_msg}")

            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_call_buffers: dict[int, dict[str, Any]] = {}

            pre_model = await self.hook_system.emit_pre_model_request(
                self.session.messages, tools
            )
            backend_messages = self.session.messages
            backend_tools = tools
            if pre_model and pre_model.get("modified_input"):
                mi = pre_model["modified_input"]
                backend_messages = mi.get("messages", self.session.messages)
                backend_tools = mi.get("tools", tools)

            response_text = ""
            _backend_usage: dict[str, Any] | None = None
            async for event in self.backend.chat(
                messages=backend_messages,
                tools=backend_tools,
                max_tokens=self.config.max_tokens,
                enable_caching=self.config.enable_prompt_caching and self.backend.supports_prompt_caching(),
            ):
                if isinstance(event, BackendText):
                    text_parts.append(event.text)
                    yield create_text_delta(event.text)
                    turn_events += 1

                elif isinstance(event, BackendThinking):
                    thinking_parts.append(event.text)
                    yield create_thinking_delta(event.text)
                    turn_events += 1

                elif isinstance(event, BackendToolCallDelta):
                    idx = event.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                    buf = tool_call_buffers[idx]
                    if event.key == "name":
                        buf["name"] += event.value
                    elif event.key == "arguments":
                        buf["arguments"] += event.value
                    yield create_tool_call_delta(
                        id=buf["id"] or f"call_{idx}",
                        key=event.key,
                        value=event.value,
                    )
                    turn_events += 1

                elif isinstance(event, BackendToolCall):
                    # Update existing buffer entry (from deltas) if present;
                    # otherwise create a new one.
                    found = False
                    for existing_idx, buf in tool_call_buffers.items():
                        if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):
                            buf["id"] = event.id or buf["id"]
                            buf["name"] = event.name
                            buf["arguments"] = event.arguments
                            found = True
                            break
                    if not found:
                        idx = len(tool_call_buffers)
                        tool_call_buffers[idx] = {
                            "id": event.id,
                            "name": event.name,
                            "arguments": event.arguments,
                        }

                elif isinstance(event, BackendFinish):
                    # Capture token usage from the backend
                    if event.usage:
                        _backend_usage = event.usage

                elif isinstance(event, BackendError):
                    await self.hook_system.emit_error(
                        Exception(event.error),
                        "backend_error"
                    )
                    await self.hook_system.emit_backend_error(
                        event.error, self.config.backend_type
                    )
                    await self.hook_system.emit_session_end()
                    yield create_finish("error")
                    return

            # Post-model hook
            response_text = "".join(text_parts)
            await self.hook_system.emit_post_model_response(
                response_text, len(tool_call_buffers)
            )

            if text_parts and not tool_call_buffers:
                full_text = "".join(text_parts)
                txt_kwargs: dict[str, Any] = {}
                if thinking_parts:
                    txt_kwargs["reasoning_content"] = "".join(thinking_parts)
                if _backend_usage:
                    txt_kwargs["usage"] = _backend_usage
                self.session.add_message("assistant", full_text, **txt_kwargs)
                await self.hook_system.emit_session_end()
                yield create_finish("stop", usage=_backend_usage)
                return

            if not tool_call_buffers:
                await self.hook_system.emit_session_end()
                yield create_finish("stop", usage=_backend_usage)
                return

            assistant_content = "".join(text_parts) if text_parts else ""

            # Build OpenAI-format tool_calls from buffers
            assistant_tool_calls: list[dict[str, Any]] = []
            for idx in sorted(tool_call_buffers.keys()):
                tc = tool_call_buffers[idx]
                assistant_tool_calls.append({
                    "id": tc["id"] or f"call_{idx}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                })

            msg_kwargs: dict[str, Any] = {}
            if assistant_tool_calls:
                msg_kwargs["tool_calls"] = assistant_tool_calls
            if _backend_usage:
                msg_kwargs["usage"] = _backend_usage
            if thinking_parts:
                msg_kwargs["reasoning_content"] = "".join(thinking_parts)
            self.session.add_message("assistant", assistant_content or None, **msg_kwargs)

            # ── Prepare tool calls: parse args, resolve tools, categorize ──
            prepared: list[dict[str, Any]] = []
            for idx in sorted(tool_call_buffers.keys()):
                tc = tool_call_buffers[idx]
                yield create_tool_call_start(name=tc["name"], id=tc["id"])
                turn_events += 1

                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                    err_msg = f"Error: Invalid JSON arguments: {tc['arguments']}"
                    yield create_tool_result(id=tc["id"], content=err_msg, is_error=True)
                    self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=tc["name"], latency_ms=0, success=False, error_message=err_msg,
                    )
                    yield create_tool_call_end(id=tc["id"])
                    turn_events += 1
                    prepared.append({"id": tc["id"], "name": tc["name"], "args": args,
                                     "tool": None, "skip": True, "error": err_msg})
                    continue

                tool = self.tool_registry.get(tc["name"])
                if tool is None:
                    err_msg = f"Error: Unknown tool: {tc['name']}"
                    yield create_tool_result(id=tc["id"], content=err_msg, is_error=True)
                    self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=tc["name"], latency_ms=0, success=False, error_message=err_msg,
                    )
                    yield create_tool_call_end(id=tc["id"])
                    turn_events += 1
                    prepared.append({"id": tc["id"], "name": tc["name"], "args": args,
                                     "tool": None, "skip": True, "error": err_msg})
                    continue

                is_safe = tool.is_concurrency_safe(args)
                prepared.append({
                    "id": tc["id"], "name": tc["name"], "args": args,
                    "tool": tool, "skip": False, "safe": is_safe,
                })

            # ── Permission & hooks for all tools (sequential — these may need user input) ──
            for p in prepared:
                if p["skip"]:
                    continue
                permission = await self.safety.check_tool_permission(p["name"], p["args"])
                if permission.behavior == "ask":
                    await self.hook_system.emit_permission_request(
                        p["name"], f"Tool {p['name']} requires permission"
                    )
                    yield create_permission_request(
                        tool_name=p["name"],
                        reason=f"Tool {p['name']} requires permission",
                    )
                    self._pending_tool_name = p["name"]
                    self._permission_event = asyncio.Event()
                    self._permission_decision = False
                    try:
                        await asyncio.wait_for(self._permission_event.wait(), timeout=120.0)
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Permission request timed out for tool '{p['name']}' after 120s",
                            extra={"tool_name": p["name"]},
                        )
                    self._permission_event = None
                    await self.hook_system.emit_permission_response(
                        p["name"], self._permission_decision
                    )
                    if not self._permission_decision:
                        err_msg = "Permission denied by user."
                        yield create_tool_result(id=p["id"], content=err_msg, is_error=True)
                        self.session.add_tool_result(p["id"], err_msg, is_error=True)
                        turn_events += 1
                        self.telemetry.record_tool_call(
                            tool_name=p["name"], latency_ms=0,
                            success=False, error_message=err_msg,
                        )
                        yield create_tool_call_end(id=p["id"])
                        turn_events += 1
                        p["skip"] = True
                        p["error"] = err_msg
                        continue

                pre_hook = await self.hook_system.emit_pre_tool(p["name"], p["args"])
                if pre_hook and pre_hook.get("block"):
                    block_reason = pre_hook.get("block_reason") or f"Blocked by hook: {p['name']}"
                    yield create_tool_progress(id=p["id"], tool_name=p["name"], status="blocked")
                    yield create_tool_result(id=p["id"], content=block_reason, is_error=True)
                    self.session.add_tool_result(p["id"], block_reason, is_error=True)
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=0,
                        success=False, error_message=block_reason,
                    )
                    yield create_tool_call_end(id=p["id"])
                    turn_events += 1
                    p["skip"] = True
                    p["error"] = block_reason
                    continue
                if pre_hook and pre_hook.get("modified_input"):
                    p["args"] = pre_hook["modified_input"]

            # ── Split into safe (concurrent) and unsafe (sequential) groups ──
            safe_tools = [p for p in prepared if not p.get("skip") and p.get("safe")]
            unsafe_tools = [p for p in prepared if not p.get("skip") and not p.get("safe")]

            # ── Execute safe tools in parallel ──
            if safe_tools:
                # Emit progress for all safe tools upfront
                for p in safe_tools:
                    yield create_tool_progress(id=p["id"], tool_name=p["name"], status="running")

                async def _execute_safe(p: dict[str, Any]) -> dict[str, Any]:
                    tool_start = time.time()
                    tool_error = False
                    executor = RetryableExecutor(self.recovery_engine)
                    state = await executor.execute(
                        tool_name=p["name"],
                        tool_args=p["args"],
                        execute_fn=lambda args: p["tool"].execute(**args),
                    )
                    if state.succeeded:
                        result = state.final_result
                        result = self.safety.validate_tool_output(p["name"], result)
                    else:
                        result = state.final_result
                        tool_error = True
                    extra = await self.hook_system.emit_post_tool(p["name"], p["args"], result)
                    if extra:
                        result = result + "\n" + extra
                    p["result"] = result
                    p["is_error"] = tool_error
                    p["recovery_history"] = list(state.recovery_history)
                    p["latency_ms"] = (time.time() - tool_start) * 1000
                    return p

                safe_tasks = [_execute_safe(p) for p in safe_tools]
                completed = await asyncio.gather(*safe_tasks, return_exceptions=True)
                for item in completed:
                    if isinstance(item, BaseException):
                        continue
                    p = item
                    yield create_tool_result(id=p["id"], content=p["result"], is_error=p["is_error"])
                    self.session.add_tool_result(p["id"], p["result"], is_error=p["is_error"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=p["latency_ms"],
                        success=not p["is_error"],
                        error_message=p["result"] if p["is_error"] else "",
                    )
                    if p["is_error"]:
                        self.learner.record_error(
                            tool_name=p["name"], error_type="execution_error",
                            context=json.dumps(p["args"])[:600], correction="",
                        )
                    else:
                        self.learner.record_success(
                            tool_name=p["name"], intent=prompt[:300], params=p["args"],
                            outcome=p["result"][:500], latency_ms=p["latency_ms"],
                        )
                        if p.get("recovery_history"):
                            correction = ErrorRecoveryEngine.infer_correction_from_history(p["recovery_history"], p["name"])
                            self.learner.record_correction(
                                tool_name=p["name"],
                                error_context=json.dumps(p["args"])[:600],
                                correction=correction,
                            )
                    self.optimizer.record_outcome(
                        tool_name=p["name"], params=p["args"],
                        success=not p["is_error"], latency_ms=p["latency_ms"],
                    )
                    yield create_tool_call_end(id=p["id"])
                    turn_events += 1

            # ── Execute unsafe tools sequentially ──
            for p in unsafe_tools:
                tool_start = time.time()
                yield create_tool_progress(id=p["id"], tool_name=p["name"], status="running")

                tool_error = False
                executor = RetryableExecutor(self.recovery_engine)
                state = await executor.execute(
                    tool_name=p["name"],
                    tool_args=p["args"],
                    execute_fn=lambda args: p["tool"].execute(**args),
                )
                if state.succeeded:
                    result = state.final_result
                    result = self.safety.validate_tool_output(p["name"], result)
                    if state.recovery_history:
                        correction = ErrorRecoveryEngine.infer_correction(state)
                        self.learner.record_correction(
                            tool_name=p["name"],
                            error_context=json.dumps(p["args"])[:600],
                            correction=correction,
                        )
                else:
                    result = state.final_result
                    tool_error = True

                extra = await self.hook_system.emit_post_tool(p["name"], p["args"], result)
                if extra:
                    result = result + "\n" + extra

                yield create_tool_result(id=p["id"], content=result, is_error=tool_error)
                self.session.add_tool_result(p["id"], result, is_error=tool_error)
                turn_events += 1

                tool_latency = (time.time() - tool_start) * 1000
                self.telemetry.record_tool_call(
                    tool_name=p["name"], latency_ms=tool_latency,
                    success=not tool_error,
                    error_message=result if tool_error else "",
                )
                if tool_error:
                    self.learner.record_error(
                        tool_name=p["name"], error_type="execution_error",
                        context=json.dumps(p["args"])[:600], correction="",
                    )
                else:
                    self.learner.record_success(
                        tool_name=p["name"], intent=prompt[:300], params=p["args"],
                        outcome=result[:500], latency_ms=tool_latency,
                    )
                self.optimizer.record_outcome(
                    tool_name=p["name"], params=p["args"],
                    success=not tool_error, latency_ms=tool_latency,
                )
                yield create_tool_call_end(id=p["id"])
                turn_events += 1

            self.session.turn_count += 1
            turn_latency = (time.time() - turn_start) * 1000
            self.telemetry.record_turn(
                turn_number=self.session.turn_count,
                event_count=turn_events,
                latency_ms=turn_latency,
            )

            # Evolution: reflex + meta-cognition
            tool_outcomes: list[dict[str, Any]] = [
                {"tool_name": tc["name"], "is_error": False}
                for tc in tool_call_buffers.values()
            ]
            reflection = self.reflex.reflect(
                turn_number=self.session.turn_count,
                tool_results=tool_outcomes,
                turn_latency_ms=turn_latency,
            )
            self.meta.assess_turn(
                prompt=prompt,
                tool_results=tool_outcomes,
            )

            await self.hook_system.emit_turn_end(self.session.turn_count)

        await self.hook_system.emit_session_end()
        yield create_finish("max_tokens")

    async def _run_sub_agent(self, prompt: str, tool_names: list[str]) -> str:
        from yim.config import YmiConfig
        from yim.loop import YmiLoop
        from yim.session import YmiSession

        sub_config = YmiConfig(
            model=self.config.model,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            max_tokens=self.config.max_tokens,
            max_turns=10,
            permission_mode="bypass",
        )
        sub_session = YmiSession(sub_config)
        sub_loop = YmiLoop(sub_config, sub_session, self.tool_registry)

        result_parts: list[str] = []
        async for event in sub_loop.run(prompt):
            if isinstance(event, TextDelta):
                result_parts.append(event.text)
            elif isinstance(event, ToolResult):
                result_parts.append(f"\n[Tool {event.id}: {event.content[:200]}]")
            elif isinstance(event, Finish):
                if event.reason == "error":
                    return "Error: Sub-agent failed"

        return "".join(result_parts) or "No output from sub-agent"