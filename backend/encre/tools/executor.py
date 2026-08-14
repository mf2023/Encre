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

"""Tool execution pipeline extracted from EncreLoop._run_impl.

Encapsulates all tool call processing: building assistant messages,
preparing tool calls, permission checking, gating, execution, and
post-result processing (artifacts, references, telemetry).
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from typing import TYPE_CHECKING, Any

from encre.loop import (
    _WRITE_TOOL_NAMES,
    _apply_result_budget,
    _args_summary,
    _ensure_plan_items,
    _extract_apply_patch_paths,
    _extract_diff_text,
    _extract_file_path,
    _extract_ref_summary,
    _infer_tool_semantics,
    _is_reference_tool,
    _permission_reason,
    _tool_retry_allowed,
    build_verify_instruction,
)
from encre.recovery import RetryableExecutor
from encre.sandbox.types import SandboxResult
from encre.tools.streaming_executor import AbortController, StreamingToolExecutor, TrackedTool
from encre.utils.types import (
    AgentEvent,
    Artifact,
    PermissionAllow,
    PermissionAsk,
    PermissionDeny,
    PlanUpdate,
    Reference,
    create_permission_request,
    create_question_request,
    create_tool_call_end,
    create_tool_call_start,
    create_tool_progress,
    create_tool_result,
)

if TYPE_CHECKING:
    from encre._loop import EncreLoop

logger = logging.getLogger(__name__)

_MAX_TOOL_CONCURRENCY = max(
    1,
    int(__import__("os").environ.get("ENCRE_MAX_TOOL_USE_CONCURRENCY", "10") or "10"),
)

# ── Tool partitioning ───────────────────────────────────────────────────
# Groups tool calls into optimal execution batches:
#   - Consecutive read-only / concurrency-safe tools → parallel batch
#   - Write tools (not concurrency-safe) → isolated singletons
# This mirrors Claude Code's partitionToolCalls() strategy.

def partition_tool_calls(
    tools: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Partition tool calls into optimal execution groups.

    Yields a list of lists.  Each inner list is either:
    - A *batch* of consecutive concurrency-safe tools (run in parallel), or
    - A singleton non-concurrency-safe tool (runs alone).

    Within each batch, if one tool errors, the entire batch is cancelled
    so sibling tools don't waste resources on invalidated context.
    """
    if not tools:
        return []

    groups: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []

    for p in tools:
        safe = p.get("safe", False)
        if safe:
            current_batch.append(p)
        else:
            if current_batch:
                groups.append(current_batch)
                current_batch = []
            groups.append([p])

    if current_batch:
        groups.append(current_batch)

    return groups


# ── Prompt-injection defense ────────────────────────────────────────────
# Wraps tool results from high-risk sources in a delimiter so the model
# can distinguish external content from its own reasoning.
# Mirrors Hermes' <untrusted_tool_result> wrapping strategy.

_UNTRUSTED_TOOL_RESULT_TOOLS: frozenset[str] = frozenset({
    "web_search", "web_fetch", "browser", "computer_use",
    "vlm_computer_use", "read", "pdf", "spreadsheet",
    "document", "media", "media_api", "rest_client",
})

_UNTRUSTED_DELIMITER_OPEN = "<untrusted_tool_result>"
_UNTRUSTED_DELIMITER_CLOSE = "</untrusted_tool_result>"


def _wrap_untrusted_result(tool_name: str, content: str) -> str:
    """Wrap tool output in untrusted-result delimiters, defanging embedded tokens.

    High-risk tools (web, MCP, browser, etc.) produce content from external
    sources that may contain prompt-injection payloads.  Wrapping them in a
    structured delimiter lets the model distinguish them from system / user
    instructions.  Embedded delimiter tokens are defanged to prevent nested
    delimiter attacks.
    """
    from encre.errors import _NEUTRALIZE_DELIMITERS
    safe = _NEUTRALIZE_DELIMITERS(content)
    return (
        f"{_UNTRUSTED_DELIMITER_OPEN} source=\"{tool_name}\"\n"
        f"{safe}\n"
        f"{_UNTRUSTED_DELIMITER_CLOSE}"
    )


def _format_container_sandbox_result(
    sb_result: SandboxResult,
    command: str,
    cwd: str,
) -> str:
    return json.dumps(
        {
            "success": sb_result.exit_code == 0,
            "exit_code": sb_result.exit_code,
            "stdout": sb_result.stdout,
            "stderr": sb_result.stderr,
            "timed_out": sb_result.timed_out,
            "killed": sb_result.killed,
            "sandbox_violation": sb_result.sandbox_violation,
            "output_truncated": sb_result.output_truncated,
            "duration_ms": sb_result.duration_ms,
            "command": command,
            "cwd": cwd,
        },
        ensure_ascii=False,
    )


class ToolPipeline:
    """Orchestrates the entire tool execution lifecycle for one turn.

    Takes a reference to the parent EncreLoop and accesses its subsystems
    (tool_registry, session, safety, hooks, telemetry, learner, etc.)
    through that reference.

    Supports configurable tool-level timeout, global retry policy,
    and execution middleware chains for pre/post tool processing.
    """

    def __init__(
        self,
        loop: EncreLoop,
        tool_timeout: float | None = None,
    ) -> None:
        """Initialize the tool execution pipeline.

        Args:
            loop: Reference to the parent EncreLoop for accessing subsystems.
            tool_timeout: Optional per-tool execution timeout in seconds.
        """
        self._loop = loop
        self._tool_timeout = tool_timeout
        self._pre_middlewares: list[Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]]] = []
        self._post_middlewares: list[Callable[[str, dict[str, Any], str], Awaitable[str]]] = []

    def add_pre_middleware(
        self,
        fn: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]],
    ) -> None:
        """Register a pre-execution middleware.

        Receives (tool_name, args). Return modified args, or None to block.
        """
        self._pre_middlewares.append(fn)

    def add_post_middleware(
        self,
        fn: Callable[[str, dict[str, Any], str], Awaitable[str]],
    ) -> None:
        """Register a post-execution middleware.

        Receives (tool_name, args, result). Return the (possibly modified) result.
        """
        self._post_middlewares.append(fn)

    # ── Public entry point ───────────────────────────────────────────────

    async def execute_tools(
        self,
        tool_call_buffers: dict[int, dict[str, Any]],
        text_parts: list[str],
        thinking_parts: list[str],
        backend_usage: dict[str, Any] | None,
        turn_count: int,
        prompt: str,
        ctx_msgs: list[dict[str, Any]],
        context_msgs: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        streamed_results: dict[str, dict[str, Any]] | None,
        extra_text: list[str],
        extra_thinking: list[str],
        extra_buffers: dict[int, dict[str, Any]],
        tool_seen: bool,
        in_extra: bool,
        yolo_context: str,
        prefetch_tasks: list[Any],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the full tool pipeline for one turn.

        Yields AgentEvents for streaming UIs and mutates the session.
        """
        loop = self._loop
        turn_events = 0

        assistant_content = "".join(text_parts) if text_parts else ""

        # ── Build assistant message ──────────────────────────────────────
        assistant_tool_calls: list[dict[str, Any]] = []
        for idx in sorted(tool_call_buffers.keys()):
            tc = tool_call_buffers[idx]
            client_id = f"call_{turn_count}_{idx}"
            protocol_id = tc["id"] or client_id
            tc["id"] = protocol_id
            entry: dict[str, Any] = {
                "id": protocol_id,
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            }
            if client_id != entry["id"]:
                entry["_client_id"] = client_id
            assistant_tool_calls.append(entry)

        msg_kwargs: dict[str, Any] = {}
        if assistant_tool_calls:
            msg_kwargs["tool_calls"] = assistant_tool_calls
        if backend_usage:
            msg_kwargs["usage"] = backend_usage
        if thinking_parts:
            msg_kwargs["reasoning_content"] = "".join(thinking_parts)
        segs = []
        if thinking_parts:
            segs.append({"kind": "thinking", "text": "".join(thinking_parts)})
        if assistant_content:
            segs.append({"kind": "text", "text": assistant_content})
        for tc in assistant_tool_calls:
            segs.append({"kind": "tool", "tool_id": tc["id"]})
        if segs:
            msg_kwargs["segments"] = segs
        loop.session.add_message("assistant", assistant_content or None, **msg_kwargs)

        # ── Prepare tool calls ───────────────────────────────────────────
        prepared = await self._prepare_tool_calls(tool_call_buffers, turn_count)
        async for event in self._yield_prepared_tool_calls(prepared):
            yield event
            turn_events += 1

        # Tag pre-executed tools
        if streamed_results:
            for p in prepared:
                if p["client_id"] in streamed_results:
                    p["pre_executed"] = True

        loop._infer_task_stage(prompt, prepared)
        loop._set_task_stage(loop._infer_task_stage(prompt, prepared), reason="tool preparation")
        loop._refresh_working_set(prompt, prepared)

        # ── Permission checks ────────────────────────────────────────────
        perm_map = await self._check_permissions(prepared, yolo_context)

        # ── Per-tool gating ──────────────────────────────────────────────
        skip_prepared = set()
        async for event in self._gate_tools(prepared, perm_map, prefetch_tasks):
            if isinstance(event, _SkipTool):
                skip_prepared.add(event.client_id)
                turn_events += event.count
            else:
                yield event
                turn_events += 1

        # Remove skipped tools
        prepared = [p for p in prepared if p["client_id"] not in skip_prepared]

        # ── Emit pre-executed streaming results ──────────────────────────
        if streamed_results:
            async for event in self._emit_streamed_results(prepared, streamed_results, prompt):
                yield event
                turn_events += 1

        # ── Execute tools via StreamingToolExecutor ────────────────────
        exec_tools = [p for p in prepared if not p.get("skip")]
        self._capture_file_snapshots(exec_tools)

        if exec_tools:
            async for event in self._execute_via_streaming_executor(exec_tools, prompt):
                yield event
                turn_events += 1

        # ── Intra-turn split handling ────────────────────────────────────
        self._last_prepared = prepared
        if in_extra and (extra_text or extra_thinking or extra_buffers):
            async for event in self._handle_intra_turn_split(
                extra_text, extra_thinking, extra_buffers,
                turn_count, prompt, yolo_context, prefetch_tasks,
            ):
                yield event
                turn_events += 1

    # ── Internal methods ─────────────────────────────────────────────────

    async def _prepare_tool_calls(
        self,
        tool_call_buffers: dict[int, dict[str, Any]],
        turn_count: int,
    ) -> list[dict[str, Any]]:
        """Parse tool call arguments and resolve tool objects."""
        loop = self._loop
        prepared: list[dict[str, Any]] = []
        for idx in sorted(tool_call_buffers.keys()):
            tc = tool_call_buffers[idx]
            client_id = f"call_{turn_count}_{idx}"

            raw_args = tc["arguments"]
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str) and raw_args.strip():
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                    prepared.append({
                        "id": tc["id"], "client_id": client_id,
                        "name": tc["name"], "args": args,
                        "tool": None, "skip": True,
                        "error": f"Invalid JSON arguments: {raw_args[:200]}",
                    })
                    continue
            else:
                args = {}

            tool = loop.tool_registry.get(tc["name"])
            if tool is None:
                prepared.append({
                    "id": tc["id"], "client_id": client_id,
                    "name": tc["name"], "args": args,
                    "tool": None, "skip": True,
                    "error": f"Unknown tool: {tc['name']}",
                })
                continue

            is_safe = tool.is_concurrency_safe(args)
            semantics = _infer_tool_semantics(tc["name"], tool)
            loop.session.metadata.setdefault("tool_semantics", {})[tc["name"]] = semantics
            prepared.append({
                "id": tc["id"], "client_id": client_id,
                "name": tc["name"], "args": args,
                "tool": tool, "skip": False, "safe": is_safe,
                "args_summary": _args_summary(args),
                "semantics": semantics,
            })
        return prepared

    async def _yield_prepared_tool_calls(
        self,
        prepared: list[dict[str, Any]],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Yield tool_call_start events for prepared tools."""
        for p in prepared:
            if p.get("skip"):
                continue
            yield create_tool_call_start(name=p["name"], id=p["client_id"])

    async def _check_permissions(
        self,
        prepared: list[dict[str, Any]],
        yolo_context: str,
    ) -> dict[str, Any]:
        """Parallel permission checks for all tools."""
        loop = self._loop
        futures: dict[str, asyncio.Task[Any]] = {}
        for p in prepared:
            if p.get("skip") or p.get("pre_executed"):
                continue
            cid = p["client_id"]
            tool_obj = p.get("tool")
            if tool_obj and tool_obj.is_readonly(p["args"]):
                continue
            if loop.config.permission_mode == "auto":
                futures[cid] = asyncio.create_task(
                    loop.safety.check_yolo_permission(
                        p["name"], p["args"],
                        conversation_context=yolo_context,
                        tool=tool_obj,
                    ),
                    name=f"perm_{cid}",
                )
            else:
                futures[cid] = asyncio.create_task(
                    loop.safety.check_tool_permission(p["name"], p["args"]),
                    name=f"perm_{cid}",
                )
        if futures:
            results = await asyncio.gather(*futures.values(), return_exceptions=True)
            perm_map: dict[str, Any] = {}
            for (cid, _task), result in zip(futures.items(), results):
                if isinstance(result, BaseException):
                    perm_map[cid] = PermissionAllow()
                else:
                    perm_map[cid] = result
            return perm_map
        return {}

    async def _gate_tools(
        self,
        prepared: list[dict[str, Any]],
        perm_map: dict[str, Any],
        prefetch_tasks: list[Any],
    ) -> AsyncGenerator[AgentEvent | _SkipTool, None]:
        """Per-tool gating: retry guard, permission deny/ask, hooks, plan mode."""
        loop = self._loop
        for p in prepared:
            if loop._cancelled():
                break
            if p.get("skip") or p.get("pre_executed"):
                continue
            if not _tool_retry_allowed(p, loop._recent_tool_names):
                retry_msg = (
                    "Blocked repeated high-risk tool retry. "
                    + p.get("semantics", {}).get("safe_fallback", "Gather more context before retrying.")
                )
                yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="blocked")
                yield create_tool_result(id=p["client_id"], content=retry_msg, is_error=True)
                loop.session.add_tool_result(p["id"], retry_msg, is_error=True, client_id=p["client_id"])
                loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=0, success=False, error_message=retry_msg)
                loop._error_tool_names.add(p["name"])
                yield create_tool_call_end(id=p["client_id"])
                yield _SkipTool(client_id=p["client_id"], count=3)
                continue

            permission = perm_map.get(p["client_id"])
            if permission is None:
                permission = PermissionAllow()

            # is_destructive escalation: in guarded modes, destructive tools
            # that were auto-allowed still prompt the user.  This fills the
            # gap where the Rust engine only knows about bash patterns, not
            # about tools like file_write, deploy, git_tool, etc.
            tool_obj = p.get("tool")

            # Immune-path hard deny: sensitive paths (.git/, .claude/, .ssh/,
            # shell-init files) are refused even in bypass mode.  Unlike the
            # destructive escalation below, this guard is NOT exempted by
            # permission_mode -- it fires in bypass/auto/plan/spec too.  Only
            # applies to destructive operations so reads of .git/HEAD survive.
            immune_hit = loop.safety.check_immune_path(p["name"], p["args"])
            if immune_hit and isinstance(permission, (PermissionAllow, PermissionAsk)):
                is_destructive_op = (
                    bool(tool_obj)
                    and callable(getattr(tool_obj, "is_destructive", None))
                    and bool(tool_obj.is_destructive(p["args"]))
                )
                if not is_destructive_op and p["name"] in {
                    "file_write", "write_file", "file_edit", "edit_file",
                    "file_delete", "delete_file", "apply_patch", "patch",
                    "bash", "shell", "execute", "git_tool", "git",
                    "mv", "cp", "rm", "sed", "tee",
                }:
                    is_destructive_op = True
                if is_destructive_op:
                    permission = PermissionDeny(
                        reason=(
                            f"Refused: target path '{immune_hit}' is immune "
                            f"(system-sensitive: .git/.claude/.ssh/shell-init). "
                            f"Cannot be modified, even in bypass mode."
                        )
                    )

            if (isinstance(permission, PermissionAllow) and tool_obj
                    and tool_obj.is_destructive(p["args"])
                    and getattr(loop.config, "permission_mode", "default")
                    not in ("bypass", "auto", "plan", "spec")):
                permission = PermissionAsk(
                    reason=f"Destructive operation: {p['name']}. Confirm to proceed."
                )

            if permission.behavior == "deny":
                deny_reason = getattr(permission, "reason", "") or _permission_reason(p["name"]) or "Permission denied."
                yield create_tool_result(id=p["client_id"], content=deny_reason, is_error=True)
                loop.session.add_tool_result(p["id"], deny_reason, is_error=True, client_id=p["client_id"])
                loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=0, success=False, error_message=deny_reason)
                loop._error_tool_names.add(p["name"])
                yield create_tool_call_end(id=p["client_id"])
                yield _SkipTool(client_id=p["client_id"], count=2)
                continue

            if permission.behavior == "ask":
                permission_reason = getattr(permission, "reason", "") or _permission_reason(p["name"])
                await loop.hook_system.emit_permission_request(p["name"], permission_reason)
                yield create_permission_request(tool_name=p["name"], reason=permission_reason)
                allowed = await loop._permission.request_permission(p["name"])
                await loop.hook_system.emit_permission_response(p["name"], allowed)
                if not allowed:
                    err_msg = "Permission denied by user."
                    yield create_tool_result(id=p["client_id"], content=err_msg, is_error=True)
                    loop.session.add_tool_result(p["id"], err_msg, is_error=True, client_id=p["client_id"])
                    loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=0, success=False, error_message=err_msg)
                    yield create_tool_call_end(id=p["client_id"])
                    yield _SkipTool(client_id=p["client_id"], count=2)
                    continue

            pre_hook = await loop.hook_system.emit_pre_tool(p["name"], p["args"])
            if pre_hook and pre_hook.get("block"):
                block_reason = pre_hook.get("block_reason") or f"Blocked by hook: {p['name']}"
                yield create_tool_result(id=p["client_id"], content=block_reason, is_error=True)
                loop.session.add_tool_result(p["id"], block_reason, is_error=True, client_id=p["client_id"])
                loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=0, success=False, error_message=block_reason)
                loop._error_tool_names.add(p["name"])
                yield create_tool_call_end(id=p["client_id"])
                yield _SkipTool(client_id=p["client_id"], count=2)
                continue
            if pre_hook and pre_hook.get("modified_input"):
                p["args"] = pre_hook["modified_input"]

            if loop.plan_mode_active:
                proposal_emitted = False
                async for event in loop._intercept_plan_mode(
                    p["name"], p["args"], p["id"], p["client_id"],
                ):
                    proposal_emitted = True
                    yield event
                if proposal_emitted and not loop._plan_decision:
                    if loop._plan_decision_timed_out:
                        plan_err = ("Plan approval timed out with no decision. "
                                    "Proceed carefully, or present a smaller, clearer proposal.")
                    else:
                        plan_err = "Plan rejected by user. Adjust your plan and try a different approach."
                    yield create_tool_result(id=p["client_id"], content=plan_err, is_error=True)
                    loop.session.add_tool_result(p["id"], plan_err, is_error=True, client_id=p["client_id"])
                    loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=0, success=False, error_message=plan_err)
                    yield create_tool_call_end(id=p["client_id"])
                    yield _SkipTool(client_id=p["client_id"], count=2)
                    continue

            if p["name"] == "question":
                args = p["args"]
                questions_list: list[dict[str, Any]] = []
                questions_raw = args.get("questions")
                if isinstance(questions_raw, str):
                    with contextlib.suppress(Exception):
                        questions_raw = json.loads(questions_raw)
                if questions_raw and isinstance(questions_raw, list):
                    for q in questions_raw:
                        if isinstance(q, dict):
                            text = (q.get("question") or "").strip()
                            if text:
                                item: dict[str, Any] = {"question": text}
                                if q.get("details"):
                                    item["details"] = str(q["details"]).strip()
                                if q.get("options") and isinstance(q["options"], list):
                                    item["options"] = [str(o) for o in q["options"]]
                                questions_list.append(item)
                q_text = (args.get("question") or "").strip()
                if q_text:
                    item: dict[str, Any] = {"question": q_text}
                    if args.get("details"):
                        item["details"] = str(args["details"]).strip()
                    if args.get("options") and isinstance(args["options"], list):
                        item["options"] = [str(o) for o in args["options"]]
                    questions_list.append(item)
                yield create_question_request(
                    tool_call_id=p["client_id"], questions=questions_list,
                )
                yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")
                loop._question_event = asyncio.Event()
                loop._question_answers = ""
                try:
                    await asyncio.wait_for(loop._question_event.wait(), timeout=300.0)
                except TimeoutError:
                    loop._question_answers = "Error: Question timed out."
                loop._question_event = None
                result = loop._question_answers
                yield create_tool_result(id=p["client_id"], content=result)
                loop.session.add_tool_result(p["id"], result, client_id=p["client_id"])
                loop.telemetry.record_tool_call(
                    tool_name=p["name"], latency_ms=0, success=True,
                )
                yield create_tool_call_end(id=p["client_id"])
                p["skip"] = True
                p["result"] = result
                continue

    async def _emit_streamed_results(
        self,
        prepared: list[dict[str, Any]],
        streamed_results: dict[str, dict[str, Any]],
        prompt: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Emit cached results from pre-executed streaming tools."""
        loop = self._loop
        for p in list(prepared):
            if p.get("pre_executed") and p["client_id"] in streamed_results:
                sr = streamed_results[p["client_id"]]
                p["result"] = sr.get("content", "")
                p["is_error"] = sr.get("is_error", False)
                p["latency_ms"] = sr.get("elapsed_ms", 0)
                p["recovery_history"] = []
                p["result"] = _apply_result_budget(
                    p["result"], p["tool"],
                    context_ratio=loop._last_context_ratio,
                    session_id=loop.session.id or "",
                    tool_name=p.get("name", ""),
                )
                yield create_tool_result(id=p["client_id"], content=p["result"], is_error=p["is_error"])
                loop.session.add_tool_result(p["id"], p["result"], is_error=p["is_error"], client_id=p["client_id"])
                loop.telemetry.record_tool_call(tool_name=p["name"], latency_ms=p["latency_ms"], success=not p["is_error"], error_message=p["result"] if p["is_error"] else "")
                yield create_tool_call_end(id=p["client_id"])
                prepared.remove(p)

    def _capture_file_snapshots(
        self,
        tools: list[dict[str, Any]],
    ) -> None:
        """Capture file snapshots before write operations."""
        loop = self._loop
        for p in tools:
            name = p["name"]
            args = p["args"]
            if name not in _WRITE_TOOL_NAMES:
                continue
            fp = args.get("file_path", "")
            if not fp and name in ("file_edit",):
                fp = args.get("file_path", "")
            if name == "apply_patch":
                for fd in args.get("files", []):
                    if isinstance(fd, dict):
                        old_p = fd.get("old_path") or ""
                        new_p = fd.get("new_path") or ""
                        if old_p:
                            loop.session.capture_file_snapshot(old_p)
                        if new_p and new_p != old_p:
                            loop.session.capture_file_snapshot(new_p)
                continue
            if fp:
                loop.session.capture_file_snapshot(fp)

    async def _execute_single_tool(
        self,
        p: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Execute one tool and return the result dict.

        Applies pre/post middlewares, tool-level timeout, and
        the configured retry policy.
        """
        loop = self._loop
        tool_start = time.time()

        # ── Pre-execution middlewares ──
        args = p["args"]
        for mw in self._pre_middlewares:
            modified = await mw(p["name"], args)
            if modified is None:
                p["result"] = f"Blocked by middleware: {p['name']}"
                p["is_error"] = True
                p["latency_ms"] = (time.time() - tool_start) * 1000
                return p
            args = modified
        p["args"] = args

        tool_error = False
        try:
            async def _do_execute() -> str:
                """Execute the tool, routing bash through sandbox if enabled."""
                if (p["name"] == "bash"
                    and loop.safety.sandbox_enabled
                    and loop.safety.require_container_sandbox("bash")):
                    command = p["args"].get("command", "")
                    timeout = p["args"].get("timeout", 120)
                    cwd = p["args"].get("cwd", "")
                    sb_result = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: loop.safety.execute_in_sandbox(command, timeout),
                    )
                    r = _format_container_sandbox_result(sb_result, command, cwd)
                    if sb_result.exit_code != 0:
                        nonlocal tool_error
                        tool_error = True
                    return r

                executor = RetryableExecutor(loop.recovery_engine)
                state = await executor.execute(
                    tool_name=p["name"],
                    tool_args=p["args"],
                    execute_fn=lambda a, p=p, sid=loop.session.session_id: p["tool"].execute(**{**a, "_session_id": sid}),
                )
                if state.succeeded:
                    r = state.final_result
                    if isinstance(r, dict):
                        r = str(r.get("content", ""))
                    r = loop.safety.validate_tool_output(p["name"], r)
                else:
                    r = state.final_result
                    if isinstance(r, dict):
                        r = str(r.get("content", ""))
                    tool_error = True
                return r

            if self._tool_timeout is not None:
                result = await asyncio.wait_for(_do_execute(), timeout=self._tool_timeout)
            else:
                result = await _do_execute()

            extra = await loop.hook_system.emit_post_tool(p["name"], p["args"], result)
            if extra:
                result = result + "\n" + extra

        except TimeoutError:
            result = f"Tool execution timed out after {self._tool_timeout}s: {p['name']}"
            tool_error = True
        except Exception:
            raise

        # ── Post-execution middlewares ──
        for mw in self._post_middlewares:
            result = await mw(p["name"], p["args"], result)

        p["result"] = result
        p["is_error"] = tool_error
        p["latency_ms"] = (time.time() - tool_start) * 1000
        return p

    def _emit_single_result(
        self,
        p: dict[str, Any],
        prompt: str,
    ) -> Generator[AgentEvent, None, None]:
        """Emit result events for one tool (telemetry, artifacts, etc.)."""
        loop = self._loop
        p["result"] = _apply_result_budget(
            p["result"], p["tool"],
            context_ratio=loop._last_context_ratio,
            session_id=loop.session.id or "",
            tool_name=p.get("name", ""),
        )

        if not p["is_error"] and p["name"] in _WRITE_TOOL_NAMES:
            fp = _extract_file_path(p["name"], p["result"])
            if fp:
                p["result"] += "\n\n" + build_verify_instruction(fp)

        if p["is_error"]:
            hint = loop._get_recovery_hint(p["name"], p["result"])
            if hint:
                p["result"] += f"\n\n[RECOVERY] {hint}"

        # Prompt-injection defense: wrap results from high-risk sources
        # (web, browser, MCP, etc.) in untrusted-result delimiters so the
        # model can distinguish external content from its own instructions.
        if not p["is_error"] and p["name"] in _UNTRUSTED_TOOL_RESULT_TOOLS:
            p["result"] = _wrap_untrusted_result(p["name"], p["result"])

        yield create_tool_result(
            id=p["client_id"],
            content=p["result"],
            is_error=p["is_error"],
            sub_agent_messages=p.get("sub_agent_messages"),
            sub_agent_session_id=p.get("sub_agent_session_id"),
        )
        loop.session.add_tool_result(
            p["id"], p["result"], is_error=p["is_error"],
            sub_agent_messages=p.get("sub_agent_messages"),
            sub_agent_session_id=p.get("sub_agent_session_id"),
            client_id=p["client_id"],
        )
        loop.telemetry.record_tool_call(
            tool_name=p["name"], latency_ms=p["latency_ms"],
            success=not p["is_error"],
            error_message=p["result"] if p["is_error"] else "",
        )

        if p["is_error"]:
            loop._error_tool_names.add(p["name"])
            loop.learner.record_error(
                tool_name=p["name"], error_type="execution_error",
                context=p["args_summary"], correction="",
            )
            if loop.feedback is not None:
                loop.feedback.record_correction(
                    tool_name=p["name"], error_type="execution_error",
                    error_context=p["args_summary"],
                    user_correction=p["result"][:400],
                )
        else:
            loop._error_tool_names.discard(p["name"])
            loop.learner.record_success(
                tool_name=p["name"], intent=prompt[:300], params=p["args"],
                outcome=p["result"][:500], latency_ms=p["latency_ms"],
            )

        loop.optimizer.record_outcome(
            tool_name=p["name"], params=p["args"],
            success=not p["is_error"], latency_ms=p["latency_ms"],
        )
        yield create_tool_call_end(id=p["client_id"])

        if not p["is_error"]:
            fp = _extract_file_path(p["name"], p["result"])
            if fp:
                if p["name"] == "apply_patch":
                    for ap_path in _extract_apply_patch_paths(p["result"]):
                        entry = loop.session.add_artifact(ap_path, p["name"], diff_text="")
                        yield Artifact(artifact=entry)
                else:
                    diff_text = _extract_diff_text(p["name"], p["result"])
                    entry = loop.session.add_artifact(fp, p["name"], diff_text=diff_text)
                    yield Artifact(artifact=entry)
            else:
                if _is_reference_tool(p["name"]):
                    summary = _extract_ref_summary(p["name"], p.get("args", {}), p["result"])
                    if summary is not None:
                        entry = loop.session.add_reference(p["name"], summary, icon="")
                        yield Reference(reference=entry)
                for sub_ref in (p.get("sub_agent_references") or []):
                    if isinstance(sub_ref, dict) and _is_reference_tool(sub_ref.get("tool", "")):
                        ref_entry = loop.session.add_reference(
                            sub_ref.get("tool", ""),
                            sub_ref.get("summary", ""),
                            icon=sub_ref.get("icon", ""),
                        )
                        yield Reference(reference=ref_entry)

            plan_items = _ensure_plan_items(p["name"], p["args"])
            if plan_items:
                yield PlanUpdate(plan_items=plan_items)
                loop.session.plan_items = plan_items

    async def _execute_via_streaming_executor(
        self,
        tools: list[dict[str, Any]],
        prompt: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute all tools via StreamingToolExecutor.

        Handles normal tools, agent sub-agents, and workflow tools with
        lifecycle management, concurrent execution, ordered result emission,
        and sibling error cascading.
        """
        loop = self._loop
        tool_map = {p["client_id"]: p for p in tools}

        async def _exec_fn(tracked: TrackedTool) -> None:
            """Execute a single tracked tool (agent, workflow, or regular)."""
            p = tool_map[tracked.client_id]

            tracked.pending_progress.append(
                create_tool_progress(id=tracked.client_id, tool_name=tracked.name, status="running")
            )

            if p["name"] == "agent":
                await self._exec_agent_tracked(tracked, p, loop)
            elif p["name"] == "workflow":
                await self._exec_workflow_tracked(tracked, p, loop)
            else:
                result_p = await self._execute_single_tool(p, prompt)
                tracked.result_content = result_p.get("result", "")
                tracked.is_error = result_p.get("is_error", False)
                tracked.latency_ms = result_p.get("latency_ms", 0.0)
                tracked.sub_agent_messages = result_p.get("sub_agent_messages")
                tracked.sub_agent_session_id = result_p.get("sub_agent_session_id")

            tracked.results.extend(self._emit_single_result(p, prompt))

        def _emit_fn(tracked: TrackedTool) -> Generator[AgentEvent, None, None]:
            """Emit buffered results for a tracked tool."""
            yield from tracked.results

        abort_controller = AbortController()
        groups = partition_tool_calls(tools)

        for group in groups:
            # If the abort controller was triggered by a previous batch,
            # cancel all remaining tools immediately.
            if abort_controller.reason:
                for p in group:
                    yield create_tool_result(
                        id=p["client_id"],
                        content=f"Tool execution was cancelled: {abort_controller.reason}",
                        is_error=True,
                    )
                continue

            executor = StreamingToolExecutor(
                execute_fn=_exec_fn,
                emit_fn=_emit_fn,
                concurrency=min(_MAX_TOOL_CONCURRENCY, len(group)),
                tool_registry=loop.tool_registry if hasattr(loop, "tool_registry") else None,
                abort_controller=abort_controller,
            )

            for p in group:
                tracked = TrackedTool(
                    id=p["id"],
                    name=p["name"],
                    args=p["args"],
                    client_id=p["client_id"],
                    is_concurrency_safe=p.get("safe", False),
                )
                executor.add_tool(tracked)

            async for event in executor.get_remaining_results():
                yield event

    async def _exec_agent_tracked(
        self,
        tracked: TrackedTool,
        p: dict[str, Any],
        loop: EncreLoop,
    ) -> None:
        """Execute an agent tool via the tracked executor with progress reporting."""
        progress_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _agent_progress(messages, pq=progress_queue):
            """Forward agent progress messages to the progress queue."""
            await pq.put(messages)

        agent_args = dict(p["args"])
        agent_args["progress_callback"] = _agent_progress

        async def _run_agent(p=p, aa=agent_args, pq=progress_queue):
            """Execute the agent tool and signal completion via the queue."""
            try:
                return await p["tool"].execute(**aa)
            finally:
                await pq.put(None)

        agent_task = asyncio.create_task(_run_agent())
        sub_agent_messages = None
        sub_agent_session_id = None
        sub_agent_references = []

        while True:
            live = await progress_queue.get()
            if live is None:
                break
            tracked.pending_progress.append(
                create_tool_progress(
                    id=tracked.client_id, tool_name=tracked.name,
                    status="running", sub_agent_messages=live,
                )
            )

        result_obj = await agent_task
        if isinstance(result_obj, dict):
            sub_agent_messages = result_obj.get("messages")
            sub_agent_session_id = result_obj.get("session_id")
            sub_agent_references = result_obj.get("references", [])
            if sub_agent_messages:
                tracked.pending_progress.append(
                    create_tool_progress(
                        id=tracked.client_id, tool_name=tracked.name,
                        status="running", sub_agent_messages=sub_agent_messages,
                    )
                )
            result = str(result_obj.get("content", ""))
        else:
            result = str(result_obj)

        result = loop.safety.validate_tool_output(p["name"], result)

        p["result"] = result
        p["is_error"] = False
        p["latency_ms"] = 0
        p["sub_agent_messages"] = sub_agent_messages
        p["sub_agent_session_id"] = sub_agent_session_id
        p["sub_agent_references"] = sub_agent_references
        tracked.result_content = result
        tracked.sub_agent_messages = sub_agent_messages
        tracked.sub_agent_session_id = sub_agent_session_id

    async def _exec_workflow_tracked(
        self,
        tracked: TrackedTool,
        p: dict[str, Any],
        loop: EncreLoop,
    ) -> None:
        """Execute a workflow tool via the tracked executor with progress reporting."""
        progress_queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _wf_progress(messages, pq=progress_queue):
            """Forward workflow progress messages to the progress queue."""
            await pq.put(messages)

        wf_args = dict(p["args"])
        wf_args["progress_callback"] = _wf_progress

        async def _run_wf(p=p, wa=wf_args, pq=progress_queue):
            """Execute the workflow tool and signal completion via the queue."""
            try:
                return await p["tool"].execute(**wa)
            finally:
                await pq.put(None)

        wf_task = asyncio.create_task(_run_wf())
        sub_agent_messages = None

        while True:
            live = await progress_queue.get()
            if live is None:
                break
            for msg in live if isinstance(live, list) else [live]:
                if isinstance(msg, dict) and msg.get("role") == "workflow":
                    wf_type = msg.get("type", "")
                    if wf_type == "workflow_started":
                        tracked.pending_progress.append(
                            create_tool_progress(
                                id=tracked.client_id, tool_name=tracked.name,
                                status="running",
                                sub_agent_messages=[{
                                    "role": "workflow", "type": "workflow_started",
                                    "workflow_id": msg.get("workflow_id", ""),
                                    "goal": msg.get("goal", ""),
                                    "total_tasks": msg.get("total_tasks", 0),
                                    "task_ids": msg.get("task_ids", []),
                                }],
                            )
                        )
                    elif wf_type == "workflow_task":
                        tracked.pending_progress.append(
                            create_tool_progress(
                                id=tracked.client_id, tool_name=tracked.name,
                                status="running",
                                sub_agent_messages=[{
                                    "role": "workflow", "type": "workflow_task",
                                    "workflow_id": msg.get("workflow_id", ""),
                                    "task_id": msg.get("task_id", ""),
                                    "task_name": msg.get("task_name", ""),
                                    "status": msg.get("status", "running"),
                                }],
                            )
                        )
                    elif wf_type == "workflow_completed":
                        tracked.pending_progress.append(
                            create_tool_progress(
                                id=tracked.client_id, tool_name=tracked.name,
                                status="running",
                                sub_agent_messages=[{
                                    "role": "workflow", "type": "workflow_completed",
                                    "workflow_id": msg.get("workflow_id", ""),
                                    "goal": msg.get("goal", ""),
                                    "success": msg.get("success", True),
                                    "completed_count": msg.get("completed_count", 0),
                                    "failed_count": msg.get("failed_count", 0),
                                    "skipped_count": msg.get("skipped_count", 0),
                                    "total_duration": msg.get("total_duration", 0.0),
                                }],
                            )
                        )
                else:
                    sub_msgs = [msg] if not isinstance(live, list) else live
                    tracked.pending_progress.append(
                        create_tool_progress(
                            id=tracked.client_id, tool_name=tracked.name,
                            status="running", sub_agent_messages=sub_msgs,
                        )
                    )

        result_obj = await wf_task
        if isinstance(result_obj, dict):
            sub_agent_messages = result_obj.get("messages")
            result = str(result_obj.get("content", ""))
        else:
            result = str(result_obj)

        result = loop.safety.validate_tool_output(p["name"], result)

        p["result"] = result
        p["is_error"] = False
        p["latency_ms"] = 0
        p["sub_agent_messages"] = sub_agent_messages
        tracked.result_content = result
        tracked.sub_agent_messages = sub_agent_messages

    async def _handle_intra_turn_split(
        self,
        extra_text: list[str],
        extra_thinking: list[str],
        extra_buffers: dict[int, dict[str, Any]],
        turn_count: int,
        prompt: str,
        yolo_context: str,
        prefetch_tasks: list[Any],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Handle intra-turn split: merge post-tool content and execute
        secondary tools."""
        loop = self._loop

        # Merge extra content into existing assistant message
        for i in range(len(loop.session.messages) - 1, -1, -1):
            msg = loop.session.messages[i]
            if msg.get("role") == "assistant":
                if extra_text:
                    existing = msg.get("content") or ""
                    extra = "".join(extra_text)
                    msg["content"] = (existing + "\n\n" + extra) if existing else extra
                if extra_buffers:
                    extra_tc = []
                    for idx in sorted(extra_buffers.keys()):
                        tc = extra_buffers[idx]
                        extra_tc.append({
                            "id": tc["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        })
                    existing_tc = msg.get("tool_calls", [])
                    msg["tool_calls"] = existing_tc + extra_tc
                if extra_thinking:
                    existing_r = msg.get("reasoning_content", "") or ""
                    msg["reasoning_content"] = existing_r + "".join(extra_thinking)
                extra_segs = []
                if extra_thinking:
                    extra_segs.append({"kind": "thinking", "text": "".join(extra_thinking)})
                if extra_text:
                    extra_segs.append({"kind": "text", "text": "".join(extra_text)})
                for etc in (extra_tc if extra_buffers else []):
                    extra_segs.append({"kind": "tool", "tool_id": etc["id"]})
                if extra_segs:
                    existing_segs = msg.get("segments", [])
                    msg["segments"] = existing_segs + extra_segs
                loop.session.mark_messages_dirty()
                break

        # Prepare secondary tool calls
        extra_prepared = await self._prepare_tool_calls(extra_buffers, turn_count)
        async for event in self._yield_prepared_tool_calls(extra_prepared):
            yield event

        if loop._cancelled():
            return

        # Permission for secondary tools
        extra_yolo_ctx = yolo_context if loop.config.permission_mode == "auto" else ""
        perm_map = await self._check_permissions(extra_prepared, extra_yolo_ctx)

        skip_extra = set()
        async for event in self._gate_tools(extra_prepared, perm_map, prefetch_tasks):
            if isinstance(event, _SkipTool):
                skip_extra.add(event.client_id)
            else:
                yield event

        extra_prepared = [p for p in extra_prepared if p["client_id"] not in skip_extra]

        # Execute secondary tools via StreamingToolExecutor
        if extra_prepared:
            self._capture_file_snapshots(extra_prepared)
            async for event in self._execute_via_streaming_executor(extra_prepared, prompt):
                yield event


class _SkipTool:
    """Internal marker to signal a tool was skipped (denied / blocked)."""
    def __init__(self, client_id: str, count: int = 1) -> None:
        """Initialize skip marker.

        Args:
            client_id: The tool call's client-side identifier.
            count: Number of events yielded by this skip.
        """
        self.client_id = client_id
        self.count = count

    def __repr__(self) -> str:
        return f"_SkipTool(client_id={self.client_id!r}, count={self.count})"
