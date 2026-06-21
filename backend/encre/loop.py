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
import json
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from encre.backend import create_backend
from encre.backends.base import BaseBackend
from encre.compact.engine import CompactEngine
from encre.config import EncreConfig
from encre.evolution.config import EvolutionConfig
from encre.logging_config import get_logger
from encre.prompts.base import EncrePromptTemplate
from encre.prompts.classifier import classify_intents

logger = get_logger(__name__)
import builtins  # noqa: E402
import contextlib  # noqa: E402

from encre.codebase.document_manager import EncreDocumentManager  # noqa: E402
from encre.codebase.indexer import EncreCodeIndex  # noqa: E402
from encre.feedback.learner import EncreFeedbackLearner  # noqa: E402
from encre.git.repo import EncreGitRepo  # noqa: E402
from encre.hooks.system import EncreHookSystem  # noqa: E402
from encre.memdir.system import EncreMemorySystem  # noqa: E402
from encre.profile.system import EncreProfileSystem  # noqa: E402
from encre.recovery import ErrorRecoveryEngine, RetryableExecutor  # noqa: E402
from encre.rollback import EncreRollbackGit  # noqa: E402
from encre.rules.loader import RulesLoader  # noqa: E402
from encre.safety import EncreSafetyEngine  # noqa: E402
from encre.session import EncreSession  # noqa: E402
from encre.skills.registry import EncreSkillRegistry  # noqa: E402
from encre.soul.system import EncreSoulSystem  # noqa: E402
from encre.telemetry import EncreTelemetry  # noqa: E402
from encre.thinking.config import resolve_thinking_config  # noqa: E402
from encre.tools.discovery import ToolDiscovery  # noqa: E402
from encre.tools.registry import ToolRegistry  # noqa: E402
from encre.tracing import (  # noqa: E402  # noqa: E501
    maybe_get_tracer,
    setup_tracing,
    trace_llm_call,
    trace_tool_call,
)
from encre.utils.tokens import count_message_tokens  # noqa: E402
from encre.utils.types import (  # noqa: E402
    AgentEvent,
    Artifact,
    BackendError,
    BackendEvent,
    BackendFinish,
    BackendText,
    BackendThinking,
    BackendToolCall,
    BackendToolCallDelta,
    CompactNotification,
    Finish,
    PlanModeChanged,
    PlanProposal,
    PlanUpdate,
    Reference,
    TextDelta,
    ThinkingDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
    WorkflowCompletedEvent,
    WorkflowStartedEvent,
    WorkflowTaskEvent,
    create_assistant_boundary,
    create_finish,
    create_permission_request,
    create_plan_mode_changed,
    create_plan_proposal,
    create_plan_resolved,
    create_question_request,
    create_text_delta,
    create_thinking_delta,
    create_tool_call_delta,
    create_tool_call_end,
    create_tool_call_start,
    create_tool_progress,
    create_tool_result,
)

_WRITE_TOOL_NAMES = {"file_write", "file_edit", "write_file", "writeFile", "apply_patch"}
_PROMPT_CACHE_TTL_SECONDS = 30.0


def _apply_result_budget(
    result: str,
    tool: Any,
    max_chars: int = 100_000,
) -> str:
    """Truncate a tool result if it exceeds the tool's size budget.

    Each tool can declare ``max_result_size_chars``.  The default is
    100 000 characters (≈ 25 000 tokens).  Results beyond that are
    truncated with a count of removed characters.
    """
    budget = getattr(tool, "max_result_size_chars", max_chars) or max_chars
    if len(result) > budget:
        excess = len(result) - budget
        return result[:budget] + f"\n... (truncated {excess} characters)"
    return result


def _extract_file_path(tool_name: str, result: str) -> str | None:
    if tool_name not in _WRITE_TOOL_NAMES:
        return None

    if tool_name == "apply_patch":
        # Result format: "{summary}\n{json}"
        import json as _json
        try:
            json_part = result.split("\n", 1)[1] if "\n" in result else result
            data = _json.loads(json_part)
            files = data.get("files", []) if isinstance(data, dict) else []
            if files:
                fp = files[0].get("new_path") or files[0].get("old_path", "")
                if fp and os.path.isabs(fp) and os.path.exists(fp):
                    return fp
        except (_json.JSONDecodeError, IndexError, KeyError):
            pass
        return None

    for pattern in [
        r"Successfully wrote \d+ characters to (.+)",
        r"Applied \d+ edit\(s\) to (.+?)\.\s*\n",  # file_edit -- \n forces lazy match past file extension periods  # noqa: E501
        r"Wrote .+ to (.+)",
    ]:
        m = re.search(pattern, result, re.IGNORECASE)
        if m:
            path = m.group(1).strip()
            if os.path.isabs(path) and os.path.exists(path):
                return path
    return None


def _extract_diff_text(tool_name: str, result: str) -> str:
    """Extract the unified diff block from a tool result string."""
    m = re.search(r"```diff\n(.+?)\n```", result, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def _args_summary(args: dict[str, Any]) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:600]
    except Exception:
        return str(args)[:600]


def _permission_reason(tool_name: str) -> str:
    return f"Tool {tool_name} requires permission"


def _extract_apply_patch_paths(result: str) -> list[str]:
    """Extract all successful file paths from an apply_patch result JSON."""
    import json as _json
    try:
        json_part = result.split("\n", 1)[1] if "\n" in result else result
        data = _json.loads(json_part)
        files = data.get("files", []) if isinstance(data, dict) else []
        paths = []
        for f in files:
            if f.get("status") != "ok":
                continue
            fp = f.get("new_path") or f.get("old_path", "")
            if fp and os.path.isabs(fp) and os.path.exists(fp):
                paths.append(fp)
        return paths
    except (_json.JSONDecodeError, IndexError, KeyError):
        return []


def _is_reference_tool(tool_name: str) -> bool:
    """Only memory and MCP tools generate sidebar references."""
    return tool_name.startswith("mcp__") or tool_name.startswith("memory_")


def _extract_ref_summary(tool_name: str, args: dict[str, Any], result: str) -> str:
    """Generate a human-readable summary of a tool invocation for the references panel."""
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) >= 3:
            server = parts[1]
            inner = parts[2]
            sub = args.get("tool_name") or args.get("name") or inner
            return f"MCP {server}: {sub}"
        return f"MCP: {tool_name}"

    name = tool_name.lower()

    if name in ("memory_create", "memory_update"):
        fn = args.get("filename", "") or args.get("name", "")
        return f"Memory: {fn}" if fn else f"Memory: {tool_name}"

    if name == "memory_read":
        fn = args.get("filename", "") or args.get("name", "")
        return f"Read memory: {fn}" if fn else "Read memory"

    if name == "memory_delete":
        fn = args.get("filename", "") or args.get("name", "")
        return f"Deleted memory: {fn}" if fn else "Deleted memory"

    if name == "memory_search":
        q = args.get("query", "")
        return f"Searched memory: {q[:60]}" if q else "Searched memory"

    if name == "memory_profile":
        field = args.get("field", "")
        val = args.get("value", "")
        return f"Profile: {field} = {val[:40]}" if field else "Profile updated"

    if name == "web_search":
        q = args.get("query", "")
        return f"Web search: {q[:80]}" if q else "Web search"

    if name == "web_fetch":
        url = args.get("url", "")
        return f"Fetched: {url[:80]}" if url else "Web fetch"

    if name == "agent":
        task = args.get("goal") or args.get("task") or args.get("name", "")
        return f"Sub-agent: {task[:80]}" if task else "Sub-agent"

    if name in ("bash", "execute", "shell", "run"):
        cmd = args.get("command", "") or args.get("cmd", "")
        return f"Shell: {cmd[:80].strip()}" if cmd else "Shell command"

    if name == "database":
        q = args.get("query", "")
        return f"DB query: {q[:60]}" if q else "Database"

    if name == "git":
        cmd_args = args.get("args", [])
        if isinstance(cmd_args, list):
            cmd_str = " ".join(str(a) for a in cmd_args)
        else:
            cmd_str = str(cmd_args)
        return f"Git: {cmd_str[:80]}" if cmd_str else "Git"

    if name == "browser":
        url = args.get("url", "")
        return f"Browser: {url[:80]}" if url else "Browser"

    if name == "cron_create":
        label = args.get("label", "") or args.get("name", "")
        return f"Scheduled: {label[:60]}" if label else "Cron created"

    if name == "notebook":
        path = args.get("path", "") or args.get("notebook_path", "")
        return f"Notebook: {path[:60]}" if path else "Notebook"

    if name == "workflow":
        wf = args.get("name") or args.get("workflow_name", "")
        return f"Workflow: {wf[:60]}" if wf else "Workflow"

    if name == "docker":
        cmd_args = args.get("args", [])
        if isinstance(cmd_args, list):
            cmd_str = " ".join(str(a) for a in cmd_args)[:80]
        else:
            cmd_str = str(cmd_args)[:80]
        return f"Docker: {cmd_str}" if cmd_str else "Docker"

    # Fallback: extract from result first line
    first_line = (result or "").split("\n")[0].strip()
    if first_line and not first_line.startswith("Error"):
        return first_line[:120]

    return tool_name


_PLAN_STATUS_MAP = {
    "pending": "pending",
    "in_progress": "active",
    "completed": "done",
}


def _ensure_plan_items(tool_name: str, args: dict[str, Any]) -> list[dict[str, Any]] | None:
    if tool_name != "todo":
        return None
    todos = args.get("todos")
    if not todos or not isinstance(todos, list):
        return None
    items: list[dict[str, Any]] = []
    for i, todo in enumerate(todos):
        content = todo.get("content", "")
        if not content:
            continue
        status = _PLAN_STATUS_MAP.get(todo.get("status", "pending"), "pending")
        items.append({
            "id": f"plan-{i}",
            "text": content,
            "status": status,
        })
    return items if items else None


class EncreLoop:
    def __init__(
        self,
        config: EncreConfig,
        session: EncreSession,
        tool_registry: ToolRegistry | None = None,
        hook_system: EncreHookSystem | None = None,
        safety: EncreSafetyEngine | None = None,
        memory_system: EncreMemorySystem | None = None,
        profile_system: EncreProfileSystem | None = None,
        soul_system: EncreSoulSystem | None = None,
        skill_registry: EncreSkillRegistry | None = None,
        telemetry: EncreTelemetry | None = None,
        evolution: EvolutionConfig | None = None,
        recovery: ErrorRecoveryEngine | None = None,
        feedback: EncreFeedbackLearner | None = None,
        code_index: EncreCodeIndex | None = None,
        sub_agent_depth: int = 0,
    ) -> None:
        self.config = config
        self.session = session
        self.tool_registry = tool_registry or ToolRegistry()
        self.discovery = ToolDiscovery(self.tool_registry)
        self.hook_system = hook_system or EncreHookSystem()
        self.memory_system = memory_system
        self.profile_system = profile_system
        self.soul_system = soul_system
        self.skill_registry = skill_registry
        self.telemetry = telemetry or EncreTelemetry(enabled=False)
        # Initialise OpenTelemetry tracer from config (no-op when disabled
        # or when opentelemetry-api is not installed).
        setup_tracing(
            enabled=config.tracing_enabled,
            service_name=config.tracing_service_name,
            endpoint=config.tracing_endpoint,
        )
        self._tracer = maybe_get_tracer()
        self.sub_agent_depth = sub_agent_depth
        evo = evolution or EvolutionConfig.create_default()
        self.learner = evo.learner
        self.optimizer = evo.optimizer
        self.reflex = evo.reflex
        self.meta = evo.meta
        self.recovery_engine = recovery or ErrorRecoveryEngine()
        self.feedback = feedback
        self._code_index: EncreCodeIndex | None = code_index
        self._pending_code_scan: EncreCodeIndex | None = None

        # Auto-resolve thinking config based on model if not explicitly set
        self._thinking_config = config.thinking_config
        if self._thinking_config is None:
            self._thinking_config = resolve_thinking_config(
                None, config.model, backend_type=config.backend_type
            )
        self.backend: BaseBackend | None = create_backend(
            config.backend_type,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            **config.backend_kwargs,
        )
        self.safety = safety or EncreSafetyEngine(config)
        self.compact_engine = CompactEngine()
        self.prompt_builder = EncrePromptTemplate()
        self.rollback = EncreRollbackGit()
        self._permission_event: asyncio.Event | None = None
        self._permission_decision: bool = False
        self._pending_tool_name: str = ""
        self._question_event: asyncio.Event | None = None
        self._question_answers: str = ""
        self._cancel_event = asyncio.Event()
        # Active sub-agent loops spawned by THIS loop.  When the user hits
        # the Stop button on the parent, we cancel every child here so a
        # single click terminates the entire agent tree immediately,
        # not just the top-level loop.
        self._child_loops: set[Any] = set()
        # Plan-mode state. When ``plan_mode_active`` is True, write-class
        # tools (``file_write``/``file_edit``/``apply_patch``) are NOT
        # executed directly.  Instead the loop builds a preview
        # (diff/command summary), emits a ``PlanProposal`` event, and
        # waits for the user to approve or reject via
        # ``approve_plan``/``reject_plan`` before continuing.  This
        # gives desktop UI a real "plan-first" workflow that matches
        # Claude Code's plan mode.
        self.plan_mode_active: bool = False
        self._plan_event: asyncio.Event | None = None
        self._plan_decision: bool = False
        self._plan_proposals: dict[str, dict[str, Any]] = {}
        self._rules_loader = RulesLoader()
        self._recent_tool_names: list[tuple[str, ...]] = []  # tool_name:args_sig signatures
        self._error_tool_names: set[str] = set()
        self._document_manager: EncreDocumentManager | None = None
        self._document_manager_data_dir: str | None = None
        self._workspace_info_cache: tuple[str, float, tuple[str, str, str]] | None = None
        self._memory_prompt_cache: tuple[str, float, str] | None = None
        self._soul_prompt_cache: tuple[str, float, str] | None = None
        self._document_prompt_cache: tuple[str, float, str] | None = None
        self._codebase_context_cache: tuple[tuple[str, int, int], float, str] | None = None
        self._profile_prompt_cache: tuple[str, str, float, str] | None = None
        self._rules_prompt_cache: tuple[tuple[str, bool, bool], float, str] | None = None
        self._sanitized_branches: set[str] = set()
        # Background compaction task -- runs in parallel to avoid blocking the main loop
        self._compact_task: asyncio.Task[None] | None = None
        # Pending compact notification to yield at next turn start
        self._compact_notification: CompactNotification | None = None

    def _cache_fresh(self, built_at: float, ttl: float = _PROMPT_CACHE_TTL_SECONDS) -> bool:
        return (time.time() - built_at) < ttl

    async def aclose(self) -> None:
        """Release backend resources (httpx clients, model memory, etc.)."""
        if self.backend is not None:
            try:
                await self.backend.aclose()
            except Exception as e:
                logger.warning(f"Error closing backend: {e}", extra={"backend": type(self.backend).__name__})  # noqa: E501

    def resolve_permission(self, decision: bool) -> None:
        """Called by the agent owner to approve or deny a pending permission request."""
        self._permission_decision = decision
        if self._pending_tool_name and self.safety is not None:
            # Persist the verdict so future invocations of the same tool
            # don't have to ask again.  Done before signalling the event
            # to make the policy update visible to any concurrent reader.
            try:
                self.safety.record_permission_decision(
                    self._pending_tool_name, decision
                )
            except Exception as _e:
                logger.debug("record_permission_decision failed: %s", _e)
        if self._permission_event is not None:
            self._permission_event.set()

    def resolve_question(self, answers: str) -> None:
        """Called when the user answers a pending question."""
        self._question_answers = answers
        if self._question_event is not None:
            self._question_event.set()

    # ── Plan mode API ───────────────────────────────────────────────
    #
    # Plan mode intercepts write-class tools and turns them into
    # ``PlanProposal`` events that the desktop UI renders as inline
    # diffs / previews with explicit accept / reject buttons.  This
    # makes the agent a true "plan first" workflow: it proposes the
    # change, the user inspects it, and only then does the tool run.

    def enter_plan_mode(self, reason: str = "") -> PlanModeChanged:
        """Switch the loop into plan mode.

        Subsequent write-class tools will be intercepted and emitted
        as ``PlanProposal`` events until ``exit_plan_mode`` is called.
        """
        self.plan_mode_active = True
        return create_plan_mode_changed(True, reason=reason)

    def exit_plan_mode(self, reason: str = "") -> PlanModeChanged:
        """Leave plan mode. Pending proposals remain in the queue."""
        self.plan_mode_active = False
        # Wake any waiters so the loop can decide what to do with the
        # remaining queued proposals.
        if self._plan_event is not None:
            self._plan_event.set()
        return create_plan_mode_changed(False, reason=reason)

    def approve_plan(self, proposal_id: str = "") -> None:
        """Approve a pending plan proposal.

        ``proposal_id`` may be empty -- an empty id is treated as
        "approve whatever is currently waiting".  This matches the
        Claude Code UX where the user clicks a single Approve button
        on the most recent pending proposal.
        """
        self._plan_decision = True
        if proposal_id:
            entry = self._plan_proposals.get(proposal_id)
            if entry is not None:
                entry["approved"] = True
        if self._plan_event is not None:
            self._plan_event.set()

    def reject_plan(self, proposal_id: str = "") -> None:
        """Reject a pending plan proposal. The underlying tool is NOT
        executed and a synthetic error result is fed back to the
        model so it can adjust its plan."""
        self._plan_decision = False
        if proposal_id:
            entry = self._plan_proposals.get(proposal_id)
            if entry is not None:
                entry["approved"] = False
        if self._plan_event is not None:
            self._plan_event.set()

    def get_pending_proposals(self) -> list[dict[str, Any]]:
        """Return a snapshot of all queued plan proposals.

        Used by the desktop UI to repopulate the plan panel after a
        reconnect, and by tests to assert plan-mode behavior without
        consuming the events.
        """
        return [dict(v) for v in self._plan_proposals.values()]

    def _build_plan_proposal(
        self,
        proposal_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> PlanProposal | None:
        """Compute a preview for a write-class tool without executing it.

        Returns ``None`` when the tool has no previewable form (e.g.
        ``bash`` commands the model has already phrased, or unknown
        tools).  In that case the caller falls back to a generic
        description so the user can still approve / reject.
        """
        preview = ""
        diff_text = ""
        file_path = ""
        original = ""
        proposed = ""
        added = 0
        removed = 0
        risk = "low"

        if tool_name in ("file_write", "write_file", "writeFile"):
            file_path = str(tool_args.get("file_path", "") or "")
            proposed = str(tool_args.get("content", "") or "")
            try:
                from encre.native import compute_diff as _native_diff
                from encre.native import read_file as _native_read
                try:
                    original = _native_read(file_path, 0, 0) if file_path else ""
                except Exception:
                    original = ""
                if file_path or proposed:
                    diff_text = _native_diff(original or "", proposed or "")
                    added = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))  # noqa: E501
                    removed = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))  # noqa: E501
            except Exception:
                diff_text = ""
            preview = (
                f"Create/overwrite {file_path or '(new file)'} "
                f"(+{added} -{removed}, {len(proposed)} chars)"
            )
            risk = "medium" if file_path and original else "low"
        elif tool_name in ("file_edit",):
            file_path = str(tool_args.get("file_path", "") or "")
            try:
                from encre.native import compute_diff as _native_diff
                from encre.native import read_file as _native_read
                try:
                    original = _native_read(file_path, 0, 0) if file_path else ""
                except Exception:
                    original = ""
                edits = tool_args.get("edits")
                if isinstance(edits, list) and edits:
                    content = original
                    for e in edits:
                        if not isinstance(e, dict):
                            continue
                        old_s = str(e.get("old_str", "") or "")
                        new_s = str(e.get("new_str", "") or "")
                        if old_s and old_s in content:
                            content = content.replace(old_s, new_s, 1)
                    proposed = content
                else:
                    old_s = str(tool_args.get("old_str", "") or "")
                    new_s = str(tool_args.get("new_str", "") or "")
                    proposed = (
                        original.replace(old_s, new_s, 1) if old_s and old_s in original else original  # noqa: E501
                    )
                if file_path or original or proposed:
                    diff_text = _native_diff(original or "", proposed or "")
                    added = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))  # noqa: E501
                    removed = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))  # noqa: E501
            except Exception:
                diff_text = ""
            preview = (
                f"Edit {file_path or '(file)'} (+{added} -{removed})"
            )
            risk = "medium"
        elif tool_name == "apply_patch":
            patch = str(tool_args.get("patch", "") or "")
            file_hints: list[str] = []
            for ln in patch.splitlines():
                if ln.startswith("+++ "):
                    p = ln[4:].strip()
                    if p and p != "/dev/null":
                        file_hints.append(p.lstrip("b/"))
            file_path = ", ".join(file_hints[:3])
            diff_text = patch[:4000]
            added = sum(1 for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))  # noqa: E501
            removed = sum(1 for ln in patch.splitlines() if ln.startswith("-") and not ln.startswith("---"))  # noqa: E501
            preview = (
                f"Apply patch to {file_path or '(multi-file)'} "
                f"(+{added} -{removed})"
            )
            risk = "medium" if len(file_hints) > 1 else "low"
        elif tool_name == "bash":
            command = str(tool_args.get("command", "") or "")
            preview = f"Run shell command: {command[:200]}"
            risk = "high"
        else:
            preview = f"Execute {tool_name}"

        return create_plan_proposal(
            proposal_id=proposal_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_args=dict(tool_args),
            preview=preview,
            diff_text=diff_text,
            file_path=file_path,
            original=original,
            proposed=proposed,
            added=added,
            removed=removed,
            risk=risk,
        )

    async def _await_plan_decision(
        self,
        proposal: PlanProposal,
        timeout: float = 300.0,
    ) -> bool:
        """Emit a ``PlanProposal`` event and block until the user decides.

        Returns ``True`` when the user approved the proposal and the
        underlying tool may execute; ``False`` when the user rejected
        it (or the call timed out, or the loop was cancelled).
        """
        self._plan_proposals[proposal.proposal_id] = {
            "proposal_id": proposal.proposal_id,
            "tool_call_id": proposal.tool_call_id,
            "tool_name": proposal.tool_name,
            "tool_args": proposal.tool_args,
            "preview": proposal.preview,
            "risk": proposal.risk,
            "approved": False,
        }
        self._plan_event = asyncio.Event()
        self._plan_decision = False
        try:
            await asyncio.wait_for(self._plan_event.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                f"Plan proposal '{proposal.proposal_id}' timed out after {timeout}s -- auto-rejecting",  # noqa: E501
            )
            self._plan_decision = False
        self._plan_event = None
        decision = self._plan_decision
        self._plan_proposals.pop(proposal.proposal_id, None)
        return decision

    async def _intercept_plan_mode(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str,
        client_id: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """If plan mode is on, intercept the call and yield a proposal.

        Returns nothing (empty generator) when the call should proceed
        normally.  When intercepted, the generator yields a
        ``PlanProposal`` event and (after the user resolves) a
        ``PlanResolved`` event.  Callers that want to know whether the
        tool was approved should track ``self._plan_decision``
        immediately after iterating this helper.
        """
        interceptable = tool_name in _WRITE_TOOL_NAMES or tool_name == "bash"
        if not self.plan_mode_active or not interceptable:
            return
        proposal_id = f"plan-{uuid.uuid4().hex[:12]}"
        proposal = self._build_plan_proposal(
            proposal_id, tool_call_id, tool_name, tool_args,
        )
        if proposal is None:
            return
        yield proposal
        approved = await self._await_plan_decision(proposal)
        yield create_plan_resolved(proposal.proposal_id, tool_call_id, approved)

    async def _chat_with_timeout(
        self,
        gen: AsyncGenerator[BackendEvent, None],
        timeout: float = 120.0,
    ) -> AsyncGenerator[BackendEvent, None]:
        """Iterate ``gen`` with a per-iteration timeout so a hanging API call
        (wrong key, no network, overloaded provider) surfaces an error instead
        of freezing the UI indefinitely."""
        try:
            while True:
                try:
                    event = await asyncio.wait_for(gen.__anext__(), timeout=timeout)
                    yield event
                except StopAsyncIteration:
                    return
        except TimeoutError:
            logger.error("[run] backend.chat() timed out after %.0fs -- check API key / network", timeout)  # noqa: E501
            yield BackendError(f"API request timed out after {timeout}s")
        except Exception:
            raise

    def cancel(self) -> None:
        """Signal the agent loop to stop at the next checkpoint.

        Also cancels any active sub-agent loops spawned by this loop so a
        single Stop click terminates the entire agent tree.
        """
        self._cancel_event.set()
        # Snapshot to avoid mutation-during-iteration: a child cancel may
        # synchronously trigger cleanup that touches ``_child_loops``.
        for child in list(self._child_loops):
            try:
                child.cancel()
            except Exception:
                logger.warning("[cancel] failed to cancel child loop", exc_info=True)
        # Allow sanitize to re-run on the next turn so any incomplete
        # assistant+tool_calls message (from an interrupted tool execution)
        # is cleaned up before the backend sees it, preventing 400 errors.
        self._sanitized_branches.clear()

    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    _SKILL_PATTERN = re.compile(r"^/(\S+)(?:\s+(.*))?", re.DOTALL)

    async def _activate_skills(self, prompt: str) -> tuple[str, str]:
        """Detect /skill-name invocations in prompt.

        Returns (skill_prompt, stripped_prompt). skill_prompt is "" if no skills matched.
        """
        if not self.skill_registry:
            return "", prompt
        parts: list[str] = []
        remaining = prompt
        while True:
            m = self._SKILL_PATTERN.match(remaining)
            if not m:
                break
            skill_name = m.group(1)
            args = (m.group(2) or "").strip() or None
            skill = self.skill_registry.lookup(skill_name)
            if skill is None:
                break
            skill_prompt = await self.skill_registry.activate(skill_name, args)
            if not skill_prompt.startswith("Error: "):
                parts.append(skill_prompt)
            end = m.end()
            remaining = remaining[end:].strip()
        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n", remaining
        return "", prompt

    def _workspace_info(self) -> tuple[str, str, str]:
        """Return (workspace_root, workspace_name, project_summary) for the prompt builder.

        Returns ("", "", "") when not running inside a workspace.
        """
        ws_path = getattr(self.config, "workspace", "") or ""
        if not ws_path or not os.path.isdir(ws_path):
            self._workspace_info_cache = None
            return "", "", ""
        cache_key = ws_path
        if (
            self._workspace_info_cache is not None
            and self._workspace_info_cache[0] == cache_key
            and self._cache_fresh(self._workspace_info_cache[1])
        ):
            return self._workspace_info_cache[2]

        ws_name = os.path.basename(ws_path)

        # Load workspace config overrides from .encre/config.json
        yim_dir = os.path.join(ws_path, ".encre")
        ws_config_path = os.path.join(yim_dir, "config.json")
        ws_config: dict[str, Any] = {}
        if os.path.isfile(ws_config_path):
            try:
                with open(ws_config_path, encoding="utf-8") as f:
                    ws_config = json.load(f)
            except Exception:
                pass

        summary_lines: list[str] = []

        custom_prompt = ws_config.get("system_prompt", "")
        if custom_prompt:
            summary_lines.append("Project-specific instructions:")
            summary_lines.append(custom_prompt)
            summary_lines.append("")

        # Top-level directory contents
        try:
            visible: list[tuple[str, bool]] = []
            with os.scandir(ws_path) as entries:
                for entry in entries:
                    name = entry.name
                    if name.startswith(".") and name != ".encre":
                        continue
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    visible.append((name, is_dir))
            visible.sort(key=lambda item: (not item[1], item[0]))
            if visible:
                summary_lines.append("Top-level entries:")
                for name, is_dir in visible[:
                    40]:
                    prefix = "/" if is_dir else " "
                    summary_lines.append(f"  {prefix}{name}")
                if len(visible) > 40:
                    summary_lines.append(f"  ... and {len(visible) - 40} more entries")
        except Exception:
            pass

        # Git state
        try:
            git_repo = EncreGitRepo(ws_path)
            if git_repo.is_in_repo():
                state = git_repo.get_state()
                summary_lines.append("")
                summary_lines.append("Git status:")
                summary_lines.append(f"  branch: {state.branch}")
                summary_lines.append(f"  clean: {'yes' if state.is_clean else 'no'}")
                if state.changed_files:
                    summary_lines.append(f"  changed: {', '.join(state.changed_files[:20])}")
                if state.untracked_files:
                    summary_lines.append(f"  untracked: {', '.join(state.untracked_files[:10])}")
        except Exception:
            pass

        result = (ws_path, ws_name, "\n".join(summary_lines))
        self._workspace_info_cache = (cache_key, time.time(), result)
        return result

    def _build_workspace_context(self) -> str:
        """Deprecated -- workspace context is now produced by _workspace_info()
        and consumed by EncrePromptBuilder. Kept for backward compatibility with
        external callers; returns an empty string in the new pipeline."""
        return ""

    def _build_directory_tree(self, ws_path: str, max_depth: int = 4, max_entries: int = 200) -> str:
        """Quickly walk the workspace directory tree without reading file contents.
        Returns a compact tree representation so the model has at least the
        project structure on the very first turn, even before the full index
        is built.  Skips ``.git``, ``node_modules`` and other noisy dirs."""
        skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv",
                     "target", "build", "dist", ".tox", ".eggs",
                     ".mypy_cache", ".pytest_cache", ".ruff_cache",
                     ".svn", ".hg", ".idea", ".vscode"}
        skip_ext = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe"}
        lines: list[str] = []
        total_files = 0
        try:
            for root, dirs, files in os.walk(ws_path):
                # Skip hidden dirs and noisy dirs
                dirs[:] = [d for d in dirs
                           if not d.startswith(".") and d not in skip_dirs]
                rel = os.path.relpath(root, ws_path)
                if rel == ".":
                    rel = ""
                depth = rel.count(os.sep) + 1 if rel else 0
                if depth > max_depth:
                    continue
                indent = "  " * depth
                if depth == 0:
                    lines.append("📁 workspace/")
                else:
                    basename = os.path.basename(root)
                    lines.append(f"{indent}📁 {basename}/")
                for fname in sorted(files):
                    if fname.startswith("."):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in skip_ext:
                        continue
                    if len(lines) >= max_entries:
                        break
                    lines.append(f"{indent}  📄 {fname}")
                    total_files += 1
                if len(lines) >= max_entries:
                    lines.append(f"  ... (truncated at {max_entries} entries)")
                    break
        except (OSError, PermissionError):
            pass
        if not lines:
            return ""
        header = (
            f"## Workspace Structure\n"
            f"{total_files} files shown (tree depth ≤{max_depth}). "
            f"Index is still building — full file contents coming soon.\n"
            f"```\n" + "\n".join(lines) + "\n```"
        )
        return header

    def _build_codebase_context_sync(self, ws_path: str, idx: Any) -> str:
        """Synchronous version of ``_build_codebase_context()`` for use in
        ``inject_code_index()`` where we're already holding a ready index."""
        try:
            modules = idx.list_all_modules()
            total = len(modules)
            if total == 0:
                return ""
            by_lang: dict[str, int] = {}
            for mod in modules:
                lang = getattr(mod, "language", None) or "other"
                by_lang[lang] = by_lang.get(lang, 0) + 1
            lang_items = sorted(by_lang.items(), key=lambda x: (-x[1], x[0]))
            lines = ["## Codebase Index",
                     f"Indexed {total} source files in the workspace.",
                     "Use `codebase_search` to find relevant code, or "
                     "`codebase_context` to view a specific file's details."]
            if lang_items:
                lines.append("Language breakdown: " +
                             ", ".join(f"{lang}: {count}" for lang, count in lang_items))
            return "\n".join(lines)
        except Exception:
            return ""

    def inject_code_index(self, idx: Any) -> None:
        """Inject a fully-built code index from the background IndexManager.
        Called from ws.py when the subprocess-based index finishes building.
        The index is stored so ``_build_codebase_context()`` can use it
        without blocking the conversation on a full re-scan.

        Real-time injection: if a system message with a placeholder already
        exists in the session, replace it immediately so the very next model
        response within the same turn sees the real codebase context."""
        self._code_index = idx
        self._codebase_context_cache = None
        # Real-time injection: replace any codebase placeholder in the system
        # message with real data, so the very next model response within the
        # same turn sees the actual file counts and language breakdown.
        ws_path = getattr(idx, "workspace", "")
        if ws_path and self.session.messages:
            new_ctx = self._build_codebase_context_sync(ws_path, idx)
            if new_ctx:
                for m in self.session.messages:
                    if m.get("role") == "system":
                        old = m.get("content", "")
                        # Replace codebase-related block at any stage
                        if "## Codebase Index" in old:
                            # Already has real data (re-index) — skip
                            pass
                        elif "## Workspace Structure" in old or \
                             "Codebase index is still being built" in old:
                            m["content"] = old + "\n\n" + new_ctx
                            self.session.mark_messages_dirty()
                            logger.info(
                                "[codebase] real-time injected into system msg workspace=%s",
                                ws_path,
                            )
                        break
        logger.info("[codebase] injected ready index workspace=%s",
                    getattr(idx, "workspace", "?"))

    async def _build_codebase_context(self) -> str:
        """Build codebase context from the workspace index when available.

        The index is built by a **subprocess** (via ``IndexManager``) so this
        method never runs ``scan()`` or ``scan_incremental()`` in the main
        process.  It simply loads whatever the subprocess has already written
        to disk.  If the index is not yet ready, a short placeholder is
        returned instead of blocking the message pipeline.
        """
        ws_path = getattr(self.config, "workspace", "") or ""
        if not ws_path or not os.path.isdir(ws_path):
            return ""

        loop = asyncio.get_running_loop()

        # Lazy-init code index for this workspace
        if self._code_index is None or getattr(self._code_index, "workspace", "") != ws_path:
            _t0 = time.time()
            try:
                idx = await loop.run_in_executor(None, EncreCodeIndex, ws_path)
                self._code_index = idx
                if not idx._indexed:
                    logger.info("[codebase] index not ready yet for workspace=%s", ws_path)
                    # Return directory tree immediately without waiting for full index
                    return self._build_directory_tree(ws_path)
                logger.info("[codebase] cache=hit workspace=%s (%.2fs)", ws_path, time.time() - _t0)
            except Exception:
                # Fallback: directory tree even if index load fails
                return self._build_directory_tree(ws_path)
        elif not self._code_index._indexed:
            return self._build_directory_tree(ws_path)

        if self._code_index is None:
            return ""

        modules = self._code_index.list_all_modules()
        total = len(modules)
        if total == 0:
            return ""

        by_lang: dict[str, int] = {}
        for mod in modules:
            lang = mod.language or "other"
            by_lang[lang] = by_lang.get(lang, 0) + 1
        lang_summary_items = tuple(sorted(by_lang.items(), key=lambda x: (-x[1], x[0])))
        cache_key = (ws_path, total, int(self._code_index._indexed), lang_summary_items)
        if (
            self._codebase_context_cache is not None
            and self._codebase_context_cache[0] == cache_key
            and self._cache_fresh(self._codebase_context_cache[1])
        ):
            return self._codebase_context_cache[2]

        lines: list[str] = []
        lines.append("## Codebase Index")
        lines.append(f"Indexed {total} source files in the workspace.")
        lines.append("Use `codebase_search` to find relevant code, or `codebase_context` to view a specific file's details.")  # noqa: E501

        # Quick top-level summary: count by language
        if lang_summary_items:
            lang_summary = ", ".join(f"{lang}: {count}" for lang, count in lang_summary_items)
            lines.append(f"Language breakdown: {lang_summary}")

        result = "\n".join(lines)
        self._codebase_context_cache = (cache_key, time.time(), result)
        return result

    def _build_document_context(self) -> str:
        from encre.config import get_data_dir

        try:
            data_dir = str(get_data_dir())
            index_path = os.path.join(data_dir, "documents", "index.json")
            try:
                st = os.stat(index_path)
                cache_key = f"{data_dir}:{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                cache_key = data_dir
            if (
                self._document_prompt_cache is not None
                and self._document_prompt_cache[0] == cache_key
                and self._cache_fresh(self._document_prompt_cache[1])
            ):
                return self._document_prompt_cache[2]

            if self._document_manager is None or self._document_manager_data_dir != data_dir:
                self._document_manager = EncreDocumentManager(data_dir)
                self._document_manager_data_dir = data_dir
            else:
                self._document_manager._load()
            prompt = self._document_manager.build_context()
            self._document_prompt_cache = (cache_key, time.time(), prompt)
            return prompt
        except Exception:
            return ""

    def _build_memory_prompt(self) -> str:
        if self.memory_system is None:
            return ""

        memory_dir = self.memory_system.get_memory_path()
        cache_key = memory_dir
        if (
            self._memory_prompt_cache is not None
            and self._memory_prompt_cache[0] == cache_key
            and self._cache_fresh(self._memory_prompt_cache[1])
        ):
            return self._memory_prompt_cache[2]

        prompt = self.memory_system.build_prompt()
        self._memory_prompt_cache = (cache_key, time.time(), prompt)
        return prompt

    def _build_soul_prompt(self) -> str:
        if self.soul_system is None:
            return ""

        soul_dir = self.soul_system.get_soul_dir()
        cache_key = soul_dir
        if (
            self._soul_prompt_cache is not None
            and self._soul_prompt_cache[0] == cache_key
            and self._cache_fresh(self._soul_prompt_cache[1])
        ):
            return self._soul_prompt_cache[2]

        prompt = self.soul_system.build_prompt()
        self._soul_prompt_cache = (cache_key, time.time(), prompt)
        return prompt

    def _refresh_profile_in_system(self) -> None:
        if self.profile_system is None:
            return
        if not self.session.messages or self.session.messages[0].get("role") != "system":
            return
        try:
            # Use the last user message as query for relevance matching
            query = ""
            for m in reversed(self.session.messages):
                if m.get("role") == "user":
                    query = m.get("content", "")
                    break
            fresh = self.profile_system.build_relevant_prompt(query=query, threshold=0.0)
            if not fresh:
                return
            content = self.session.messages[0].get("content", "")
            content = re.sub(
                r"\n+## User Profile.*?(?=\n+## |\Z)",
                "",
                content,
                count=1,
                flags=re.DOTALL,
            )
            content = content.rstrip() + "\n\n" + fresh
            self.session.messages[0]["content"] = content
            self.session.mark_messages_dirty()
        except Exception:
            pass

    def _build_profile_prompt(self, query: str) -> str:
        if self.profile_system is None:
            return ""
        cache_key = (getattr(self.profile_system, "_profile_path", ""), query)
        if (
            self._profile_prompt_cache is not None
            and self._profile_prompt_cache[0] == cache_key[0]
            and self._profile_prompt_cache[1] == cache_key[1]
            and self._cache_fresh(self._profile_prompt_cache[2])
        ):
            return self._profile_prompt_cache[3]
        prompt = self.profile_system.build_relevant_prompt(query=query, threshold=0.0)
        self._profile_prompt_cache = (cache_key[0], cache_key[1], time.time(), prompt)
        return prompt

    def _build_rules_prompt(self) -> str:
        ws_root = getattr(self.config, "workspace", "") or ""
        cache_key = (
            ws_root,
            bool(self.config.enable_project_rules),
            bool(self.config.enable_global_rules),
        )
        if (
            self._rules_prompt_cache is not None
            and self._rules_prompt_cache[0] == cache_key
            and self._cache_fresh(self._rules_prompt_cache[1])
        ):
            return self._rules_prompt_cache[2]
        prompt = self._rules_loader.build_rules_prompt(
            ws_root,
            enable_project=self.config.enable_project_rules,
            enable_global=self.config.enable_global_rules,
        )
        self._rules_prompt_cache = (cache_key, time.time(), prompt)
        return prompt

    async def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        custom_instructions: str = "",
        slash_command_mode: str = "",
        slash_commands: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if self.backend is None:
            logger.warning("Agent run requested but no backend configured")
            yield create_finish("error", error="No backend configured. Send a 'configure' message first.")  # noqa: E501
            return

        # Mark this loop as the active loop so context-aware tools (find_tool,
        # EncreAgentTool) see the correct discovery/registry/session even when
        # nested inside a sub-agent.
        from encre.tools.builtin.agent import (
            reset_active_loop as reset_agent_active_loop,
        )
        from encre.tools.builtin.agent import set_active_loop as set_agent_active_loop
        from encre.tools.builtin.bash import (
            reset_workspace as reset_bash_workspace,
        )
        from encre.tools.builtin.bash import set_workspace as set_bash_workspace
        from encre.tools.builtin.find_tool import reset_active_loop, set_active_loop
        _loop_token = set_active_loop(self)
        _agent_loop_token = set_agent_active_loop(self)
        # Inject the workspace path into the bash tool so the Rust
        # sandbox_execute can apply Landlock (Linux) or path isolation
        # (other platforms) automatically.
        _ws = getattr(self.config, "workspace", "") or ""
        _bash_ws_token = set_bash_workspace(_ws if _ws else None)
        try:
            async for ev in self._run_impl(
                prompt, system_prompt, custom_instructions,
                slash_command_mode=slash_command_mode,
                slash_commands=slash_commands,
            ):
                yield ev
        finally:
            reset_bash_workspace(_bash_ws_token)
            reset_active_loop(_loop_token)
            reset_agent_active_loop(_agent_loop_token)

    async def _run_impl(
        self,
        prompt: str,
        system_prompt: str | None = None,
        custom_instructions: str = "",
        slash_command_mode: str = "",
        slash_commands: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        # Log effective max_turns so we can diagnose unexpected session stops
        logger.info("[run] _run_impl start turn=%d max_turns=%d backend=%s model=%s",
                     self.session.turn_count, self.config.max_turns,
                     self.config.backend_type, self.config.model)
        # Main session: force unlimited turns so no config/workspace override
        # can cap it.  Sub-agents (depth > 0) keep their own max_turns so they
        # can still terminate naturally via text-only response.
        if self.sub_agent_depth == 0:
            self.config.max_turns = 0
        # Clear any stale cancel/pause state from a previous run so new
        # messages are not immediately rejected after a user cancellation.
        self._cancel_event.clear()
        self._recent_tool_names.clear()
        self._error_tool_names.clear()
        # Classify user intent for dynamic prompt assembly
        intents = classify_intents(prompt)

        # Activate any skills invoked via /skill-name syntax
        skill_prompt, prompt = await self._activate_skills(prompt)
        _t0 = time.time()
        tools = None
        if self.backend.supports_tool_calling():
            tools = self.discovery.get_active_tools_payload(self.session.id, fmt="openai")
        ws_root, ws_name, ws_summary = self._workspace_info()

        if system_prompt is None:
            # Cache the base system prompt by a content-hash key so we don't
            # rebuild it every turn when nothing changed.
            _cache_key = (
                self.config.permission_mode,
                self.config.slash_command_mode,
                self.session.id,
                tuple(t.get("function", {}).get("name", "") for t in tools) if tools else (),
                tuple(sorted(intents)),
                ws_root, ws_name, ws_summary,
                self.config.language_preference,
                self.config.language,
                custom_instructions,
                tuple(c.get("name", "") for c in (slash_commands or [])),
            )
            if (
                hasattr(self, "_sys_prompt_cache")
                and self._sys_prompt_cache_key == _cache_key
            ):
                system_prompt = self._sys_prompt_cache
            else:
                system_prompt = self.prompt_builder.build_system_prompt(
                    self.config.permission_mode,
                    tools=tools,
                    intents=intents,
                    workspace_root=ws_root,
                    workspace_name=ws_name,
                    project_summary=ws_summary,
                    language_preference=self.config.language_preference,
                    app_language=self.config.language,
                    custom_instructions=custom_instructions,
                    session_id=self.session.id,
                    slash_command_mode=slash_command_mode,
                    slash_commands=slash_commands,
                )
                self._sys_prompt_cache = system_prompt
                self._sys_prompt_cache_key = _cache_key
        elif slash_command_mode in ("plan", "spec"):
            # Custom system_prompt was provided (e.g., from an active agent).
            # Plan/spec mode requires mode-specific instructions -- build the
            # full mode-aware prompt and prepend the custom content so both
            # the custom prompt and the mode instructions are in effect.
            built = self.prompt_builder.build_system_prompt(
                self.config.permission_mode,
                tools=tools,
                intents=intents,
                workspace_root=ws_root,
                workspace_name=ws_name,
                project_summary=ws_summary,
                language_preference=self.config.language_preference,
                app_language=self.config.language,
                custom_instructions=custom_instructions,
                session_id=self.session.id,
                slash_command_mode=slash_command_mode,
                slash_commands=slash_commands,
            )
            system_prompt = system_prompt + "\n\n" + built

        # When a custom system_prompt was provided by a parent agent (not
        # None, not plan/spec mode), skip workspace context enrichment.
        # However, when no custom prompt was given (system_prompt was None),
        # the agent runs as a full session -- don't skip enrichments.
        _original_system_prompt_was_none = system_prompt is None
        _skip_enrichment = (
            system_prompt is not None
            and slash_command_mode not in ("plan", "spec")
            and not _original_system_prompt_was_none
        )

        # Inject codebase index context (multi-language code search + dependencies)
        if not _skip_enrichment:
            codebase_ctx = await self._build_codebase_context()
            if codebase_ctx:
                system_prompt = system_prompt + "\n\n" + codebase_ctx

        # Prepend skill prompt to system prompt
        if skill_prompt:
            system_prompt = skill_prompt + system_prompt

        if _skip_enrichment:
            # Sub-agent behavioral framework: essential blocks every agent
            # needs (tool protocol, safety, identity, output format) but
            # WITHOUT workspace-specific context that would distract from
            # the delegated task.
            from encre.prompts.loader import PromptLoader
            _loader = PromptLoader()
            _behavioral_parts: list[str] = []
            for _bname in ("identity", "safety", "tool_usage", "output_format"):
                try:
                    _bcontent = _loader.load(_bname)
                    if _bcontent:
                        _behavioral_parts.append(_bcontent)
                except Exception:
                    pass
            # Sub-agent identity and depth guard. When this loop is itself
            # a delegated sub-agent (depth > 0), tell the model that and
            # forbid further recursion. This blocks infinite agent-of-agent
            # chains and keeps sub-agents focused on the delegated task.
            if self.sub_agent_depth > 0:
                _behavioral_parts.append(
                    "## Sub-Agent Identity\n"
                    f"You are a delegated sub-agent (depth {self.sub_agent_depth}). "
                    "You were spawned by a parent agent to perform a specific task. "
                    "Your output is returned to the parent. Do NOT spawn further sub-agents -- "
                    "the runtime forbids two levels of nesting. Complete the assigned task with "
                    "the tools available and return a concise final answer. If you need to "
                    "parallelize work, return a list of sub-tasks to the parent instead."
                )
            # Language preference
            _lang_pref = self.config.language_preference or ""
            _app_lang = self.config.language or ""
            _resolved = _lang_pref if _lang_pref and _lang_pref != "auto" else _app_lang
            if _resolved == "zh":
                _behavioral_parts.append(
                    "IMPORTANT: You must always respond in Chinese (中文) "
                    "throughout the entire conversation."
                )
            elif _resolved == "en":
                _behavioral_parts.append(
                    "IMPORTANT: You must always respond in English "
                    "throughout the entire conversation."
                )
            if _behavioral_parts:
                system_prompt = system_prompt + "\n\n" + "\n\n".join(_behavioral_parts)
        else:
            # Inject persistent memory context (encrypted memories from disk)
            if self.memory_system is not None:
                try:
                    memory_prompt = self._build_memory_prompt()
                    if memory_prompt:
                        system_prompt = system_prompt + "\n\n" + memory_prompt
                except Exception:
                    pass

            # Inject relevant profile context -- only fields matching the user's query
            if self.profile_system is not None:
                try:
                    profile_prompt = self._build_profile_prompt(prompt)
                    if profile_prompt:
                        system_prompt = system_prompt + "\n\n" + profile_prompt
                except Exception:
                    pass

            # Inject agent soul / identity context (SOUL.md, IDENTITY.md, USER.md)
            if self.soul_system is not None:
                try:
                    soul_prompt = self._build_soul_prompt()
                    if soul_prompt:
                        system_prompt = system_prompt + "\n\n" + soul_prompt
                except Exception:
                    pass

            # Inject reference document context
            try:
                doc_prompt = self._build_document_context()
                if doc_prompt:
                    system_prompt = system_prompt + "\n\n" + doc_prompt
            except Exception:
                pass

            # Inject user rules (project-level + global)
            try:
                rules_prompt = self._build_rules_prompt()
                if rules_prompt:
                    from encre.prompts.loader import PromptLoader
                    _loader = PromptLoader()
                    rules_block = _loader.load_with_context("rules", rules_content=rules_prompt)
                    system_prompt = system_prompt + "\n\n" + rules_block
            except Exception:
                pass

        # Update system message on every run so prompt blocks match current intents
        has_system = any(
            m.get("role") == "system" and m.get("branch_id", self.session.active_branch_id) == self.session.active_branch_id  # noqa: E501
            for m in self.session.messages
        )
        if has_system:
            for i, m in enumerate(self.session.messages):
                if m.get("role") == "system" and m.get("branch_id", self.session.active_branch_id) == self.session.active_branch_id:  # noqa: E501
                    self.session.messages[i] = {"role": "system", "content": system_prompt, "branch_id": self.session.active_branch_id}  # noqa: E501
                    self.session.mark_messages_dirty()
                    break
        else:
            self.session.messages.insert(0, {"role": "system", "content": system_prompt, "branch_id": self.session.active_branch_id})  # noqa: E501
            self.session.mark_messages_dirty()

        # Add user prompt if not a duplicate of the last user message
        # in the active branch context (not just self.session.messages[-1],
        # which may be from a different branch during retry).
        ctx_msgs = self.session.get_context_messages()
        last_ctx_user = None
        for m in reversed(ctx_msgs):
            if m.get("role") == "user":
                last_ctx_user = m
                break
        if last_ctx_user is None or last_ctx_user.get("content") != prompt:
            if skill_prompt and last_ctx_user is not None:
                # Skill was activated -- don't add a duplicate with the stripped text.
                # Keep the original message content so the user sees what they typed.
                pass
            else:
                logger.info("[sub_agent] adding user message to session | prompt_len=%d | last_ctx_user_exists=%s",  # noqa: E501
                            len(prompt), last_ctx_user is not None)
                self.session.add_message("user", prompt)

        if time.time() - _t0 > 0.1:
            logger.info("[perf] prompt build %.1fs", time.time() - _t0)
        _t_hook = time.time()
        await self.hook_system.emit_session_start()
        logger.info("[run] emit_session_start done (%.2fs)", time.time() - _t_hook)
        _last_backend_usage: dict[str, Any] | None = None

        # Sanitize session messages on every run -- old sessions loaded from disk
        # may contain broken tool_call groups (from crashes) that cause 400 errors.
        # Only sanitize active branch context; other branches remain untouched.
        active_branch_id = self.session.active_branch_id
        if active_branch_id not in self._sanitized_branches:
            self.session.replace_branch_messages(active_branch_id, self.compact_engine.sanitize(ctx_msgs))  # noqa: E501
            self._sanitized_branches.add(active_branch_id)
            ctx_msgs = self.session.get_context_messages()

        while not self.session.is_max_turns_reached() and not self._cancelled():
            turn_start = time.time()
            turn_events = 0
            _t_ts = time.time()
            await self.hook_system.emit_turn_start(self.session.turn_count)
            logger.info("[run] emit_turn_start done turn=%d (%.2fs)", self.session.turn_count, time.time() - _t_ts)  # noqa: E501
            _t_ck = time.time()
            self.session.checkpoint(f"turn_{self.session.turn_count}")
            await self.hook_system.emit_checkpoint(f"turn_{self.session.turn_count}")
            logger.info("[run] emit_checkpoint done turn=%d (%.2fs)", self.session.turn_count, time.time() - _t_ck)  # noqa: E501
            # Emit compact notification if a background compact completed
            if self._compact_notification is not None:
                yield self._compact_notification
                self._compact_notification = None
            # Refresh context at the start of every turn so the model
            # sees its own assistant messages and tool results from
            # previous turns -- without this the context stays frozen on
            # the initial user message, causing repeated tool invocations.
            ctx_msgs = self.session.get_context_messages()
            context_msgs = ctx_msgs

            # ── Pre-API-call compaction (Claude Code style) ────────────
            # BEFORE the model sees the messages, check the token budget
            # against the model's actual context window.  This is pure
            # arithmetic -- no fixed turn count.  The compact agent uses
            # the SAME backend as the main loop to produce a structured
            # summary that preserves task intent, key decisions, files,
            # errors, and current state.
            window = self.backend.context_window_size()
            est_tokens = count_message_tokens(context_msgs)
            logger.info(
                "[run] turn=%d msgs=%d tokens=%dk/%dk (%.0f%%)",
                self.session.turn_count, len(context_msgs),
                est_tokens // 1000, window // 1000,
                100 * est_tokens / window if window else 0,
            )

            # Step 1: microcompact -- cheap cleanup of old tool results
            if self.compact_engine.should_microcompact(context_msgs, window):
                micro = await self.compact_engine.microcompact(context_msgs, window)
                if len(micro) != len(context_msgs):
                    self.session.replace_branch_messages(self.session.active_branch_id, micro)
                    ctx_msgs = self.session.get_context_messages()
                    context_msgs = ctx_msgs
                    est_tokens = count_message_tokens(context_msgs)
                    logger.info(
                        "[microcompact] done turn=%d msgs %d->%d tokens %dk",
                        self.session.turn_count, len(context_msgs),
                        len(micro), est_tokens // 1000,
                    )

            # Step 2: full compaction -- model-driven summarisation
            # Runs asynchronously in background; result applies to next turn
            if self.compact_engine.should_compact(context_msgs, window):
                if self._compact_task and not self._compact_task.done():
                    self._compact_task.cancel()
                logger.info(
                    "[compact] triggering turn=%d tokens=%dk window=%dk (async)",
                    self.session.turn_count, est_tokens // 1000, window // 1000,
                )

                async def _do_compact():
                    try:
                        self.session.set_compact_archive(context_msgs)
                        await self.hook_system.emit_pre_compact(len(context_msgs), est_tokens)
                        compacted = await self.compact_engine.compact(
                            context_msgs, backend=self.backend,
                            turn_count=self.session.turn_count,
                            system_prompt=system_prompt or "",
                            session_id=self.session.id or "",
                        )
                        if compacted is not None:
                            self.session.replace_branch_messages(self.session.active_branch_id, compacted)
                            new_tokens = count_message_tokens(compacted)
                            self._compact_notification = CompactNotification(
                                old_count=len(context_msgs),
                                new_count=len(compacted),
                                old_tokens=est_tokens,
                                new_tokens=new_tokens,
                            )
                            logger.info(
                                "[compact] bg done turn=%d msgs %d->%d tokens %dk->%dk",
                                self.session.turn_count, len(context_msgs),
                                len(compacted), est_tokens // 1000, new_tokens // 1000,
                            )
                    except asyncio.CancelledError:
                        logger.info("[compact] cancelled (new turn started)")
                    except Exception:
                        logger.warning(
                            "[compact] bg failed turn=%d -- circuit breaker or API error",
                            self.session.turn_count,
                        )

                self._compact_task = asyncio.create_task(_do_compact())

            tools = None
            if self.backend.supports_tool_calling():
                tools = self.discovery.get_active_tools_payload(self.session.id, fmt="openai")

            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_call_buffers: dict[int, dict[str, Any]] = {}
            _extra_thinking: list[str] = []
            _extra_text: list[str] = []
            _extra_buffers: dict[int, dict[str, Any]] = {}
            _tool_seen = False
            _in_extra = False

            _t_pm = time.time()
            pre_model = await self.hook_system.emit_pre_model_request(
                self.session.messages, tools
            )
            logger.info("[run] emit_pre_model_request done turn=%d (%.2fs)", self.session.turn_count, time.time() - _t_pm)  # noqa: E501

            backend_messages = list(ctx_msgs)
            backend_tools = tools
            if pre_model and pre_model.get("modified_input"):
                mi = pre_model["modified_input"]
                backend_messages = mi.get("messages", backend_messages)

            # Inject evolution guidance and feedback into backend messages only
            # (not into self.session.messages) so they don't appear as user input in the UI,
            # don't cause tool duplication on subsequent turns, and -- critically --
            # don't end the agent prematurely.  Guidance is merged into the LAST user
            # message rather than appended as a NEW user turn, because a separate turn
            # tricks the model into responding to the guidance as if it were a fresh
            # instruction, often producing a text-only summary that hits the `return`
            # at the text-only-exit points below, terminating the entire agent loop.
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

                def _merge_into_last_user(msgs: list[dict[str, Any]], suffix: str) -> None:
                    """Append `suffix` to the last user message content *in place*.
                    Creates a shallow copy of the target dict so the original session
                    messages are not mutated."""
                    for i in range(len(msgs) - 1, -1, -1):
                        if msgs[i].get("role") == "user":
                            msg = dict(msgs[i])
                            existing = (msg.get("content") or "")
                            msg["content"] = existing + "\n\n" + suffix
                            msgs[i] = msg
                            return

                if guidance_parts:
                    guidance_msg = "\n\n".join(guidance_parts)
                    _merge_into_last_user(backend_messages, f"[SYSTEM GUIDANCE]\n{guidance_msg}")

                if self.feedback is not None:
                    fb = self.feedback.get_relevant_feedback("__any__", prompt[:300])
                    if fb:
                        _merge_into_last_user(backend_messages, f"[PAST CORRECTIONS]\n{fb}")

            response_text = ""
            _backend_usage: dict[str, Any] | None = None
            _t_chat = time.time()

            logger.info("[run] calling backend.chat() turn=%d msgs=%d tools=%s",
                        self.session.turn_count, len(backend_messages),
                        bool(backend_tools))
            _chat_first_event = True
            _llm_span = trace_llm_call(
                self._tracer,
                self.config.model,
                str(backend_messages[0])[:200] if backend_messages else "",
            )
            _llm_span.set_attribute("llm.turn", self.session.turn_count)
            try:
                # Wrap the chat generator with a 120s timeout on the first event,
                # so a hanging API call (wrong key, no network, etc.) surfaces an
                # error rather than freezing the UI indefinitely.
                _chat_gen = self.backend.chat(
                    messages=backend_messages,
                    tools=backend_tools,
                    max_tokens=self.config.max_tokens,
                    enable_caching=self.config.enable_prompt_caching and self.backend.supports_prompt_caching(),  # noqa: E501
                )
                async for event in self._chat_with_timeout(_chat_gen, timeout=120.0):
                    if _chat_first_event:
                        logger.info("[run] backend.chat() first event after %.1fs turn=%d",
                                    time.time() - _t_chat, self.session.turn_count)
                        _chat_first_event = False
                    if isinstance(event, BackendText):
                        if _in_extra:
                            _extra_text.append(event.text)
                            yield create_text_delta(event.text)
                        elif _tool_seen:
                            _in_extra = True
                            yield create_assistant_boundary()
                            _extra_text.append(event.text)
                            yield create_text_delta(event.text)
                        else:
                            text_parts.append(event.text)
                            yield create_text_delta(event.text)
                        turn_events += 1

                    elif isinstance(event, BackendThinking):
                        if _tool_seen:
                            if not _in_extra:
                                _in_extra = True
                                yield create_assistant_boundary()
                            _extra_thinking.append(event.text)
                            yield create_thinking_delta(event.text)
                        else:
                            thinking_parts.append(event.text)
                            yield create_thinking_delta(event.text)
                        turn_events += 1

                    elif isinstance(event, BackendToolCallDelta):
                        _tool_seen = True
                        if _in_extra:
                            idx = event.index
                            # If this tool index was already being accumulated
                            # in tool_call_buffers before _in_extra, keep
                            # appending there instead of creating a duplicate
                            # in _extra_buffers.
                            if idx in tool_call_buffers:
                                buf = tool_call_buffers[idx]
                                if event.key == "name":
                                    buf["name"] += event.value
                                elif event.key == "arguments":
                                    buf["arguments"] += event.value
                            else:
                                if idx not in _extra_buffers:
                                    _extra_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                                buf = _extra_buffers[idx]
                                if event.key == "name":
                                    buf["name"] += event.value
                                elif event.key == "arguments":
                                    buf["arguments"] += event.value
                        else:
                            idx = event.index
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                            buf = tool_call_buffers[idx]
                            if event.key == "name":
                                buf["name"] += event.value
                            elif event.key == "arguments":
                                buf["arguments"] += event.value
                            yield create_tool_call_delta(
                                id=f"call_{self.session.turn_count}_{idx}",
                                key=event.key,
                                value=event.value,
                            )
                        turn_events += 1

                    elif isinstance(event, BackendToolCall):
                        _tool_seen = True
                        if _in_extra:
                            # Check if this tool already exists in tool_call_buffers
                            # (accumulated from deltas before _in_extra) and update
                            # in-place to avoid duplicates.
                            found = False
                            for _existing_idx, buf in tool_call_buffers.items():
                                if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):  # noqa: E501
                                    buf["id"] = event.id or buf["id"]
                                    buf["name"] = event.name
                                    buf["arguments"] = event.arguments
                                    found = True
                                    break
                            if not found:
                                for _existing_idx, buf in _extra_buffers.items():
                                    if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):  # noqa: E501
                                        buf["id"] = event.id or buf["id"]
                                        buf["name"] = event.name
                                        buf["arguments"] = event.arguments
                                        found = True
                                        break
                            if not found:
                                idx = len(_extra_buffers)
                                _extra_buffers[idx] = {
                                    "id": event.id,
                                    "name": event.name,
                                    "arguments": event.arguments,
                                }
                        else:
                            # Update existing buffer entry (from deltas) if present;
                            # otherwise create a new one.
                            found = False
                            for _existing_idx, buf in tool_call_buffers.items():
                                if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):  # noqa: E501
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
                            _last_backend_usage = event.usage

                    elif isinstance(event, BackendError):
                        await self.hook_system.emit_error(
                            Exception(event.error),
                            "backend_error"
                        )
                        await self.hook_system.emit_backend_error(
                            event.error, self.config.backend_type
                        )
                        # Raise so the generic except handler below catches this
                        # and continues the session instead of killing it.
                        raise RuntimeError(f"Backend error: {event.error}")

            except Exception as exc:
                logger.error("[run] backend.chat() raised exception after %.1fs turn=%d: %s",
                            time.time() - _t_chat, self.session.turn_count, exc)
                _llm_span.set_attribute("llm.error", str(exc))
                _llm_span.end()
                await self.hook_system.emit_error(exc, "backend_chat_exception")
                await self.hook_system.emit_backend_error(str(exc), type(self.backend).__name__ if self.backend else "unknown")  # noqa: E501
                # Don't end the session -- add the error to context so the model
                # sees it next turn and can retry or respond gracefully.
                err_msg = f"[Backend API Error]\n{type(exc).__name__}: {exc}"
                self.session.add_message("user", err_msg)
                logger.info("[run] added backend error to session on turn %d, continuing", self.session.turn_count)
                continue
            else:
                logger.info("[run] backend.chat() completed in %.1fs turn=%d events=%d",
                            time.time() - _t_chat, self.session.turn_count, turn_events)
                # Record token usage on the LLM span when the backend provided it
                if _backend_usage:
                    _llm_span.set_attribute("llm.token_count.prompt",
                                            _backend_usage.get("input_tokens", 0))
                    _llm_span.set_attribute("llm.token_count.completion",
                                            _backend_usage.get("output_tokens", 0))
                _llm_span.end()

            # Post-model hook
            response_text = "".join(text_parts)
            await self.hook_system.emit_post_model_response(
                response_text, len(tool_call_buffers)
            )

            if text_parts and not tool_call_buffers:
                full_text = "".join(text_parts)

                # Merge into the previous assistant that had tool_calls, so that
                # tool-calling turns don't create a second assistant message in
                # the session.  Scan backwards -- if we find an assistant with
                # tool_calls before any user message, it belongs to the same
                # logical response from the user's perspective.
                merged = False
                for i in range(len(self.session.messages) - 1, -1, -1):
                    m = self.session.messages[i]
                    if m.get("role") == "user":
                        break
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        existing = m.get("content") or ""
                        m["content"] = (existing + "\n\n" + full_text) if existing else full_text
                        if thinking_parts:
                            existing_r = m.get("reasoning_content", "") or ""
                            m["reasoning_content"] = existing_r + "".join(thinking_parts)
                        if _backend_usage:
                            m["usage"] = _backend_usage
                        # Preserve segment ordering
                        new_segs = []
                        if thinking_parts:
                            new_segs.append({"kind": "thinking", "text": "".join(thinking_parts)})
                        if full_text:
                            new_segs.append({"kind": "text", "text": full_text})
                        if new_segs:
                            existing_segs = m.get("segments", [])
                            m["segments"] = existing_segs + new_segs
                        self.session.mark_messages_dirty()
                        merged = True
                        break

                if not merged:
                    txt_kwargs: dict[str, Any] = {}
                    if thinking_parts:
                        txt_kwargs["reasoning_content"] = "".join(thinking_parts)
                    if _backend_usage:
                        txt_kwargs["usage"] = _backend_usage
                    segs = []
                    if thinking_parts:
                        segs.append({"kind": "thinking", "text": "".join(thinking_parts)})
                    if full_text:
                        segs.append({"kind": "text", "text": full_text})
                    if segs:
                        txt_kwargs["segments"] = segs
                    self.session.add_message("assistant", full_text, **txt_kwargs)

                await self.hook_system.emit_session_end()
                logger.debug("Agent finished (text-only response, %d chars)", len(full_text))
                yield create_finish("stop", usage=_backend_usage)
                # Main session: text-only ends this run. User sends next message.
                # Sub-agent: text-only completes the sub-agent task.
                return

            assistant_content = "".join(text_parts) if text_parts else ""

            # Build OpenAI-format tool_calls from buffers.
            # We also attach the synthetic client-facing id (used for
            # streaming events) under a non-protocol ``_client_id`` key
            # so the renderer can correlate tool_results delivered via
            # ``client_id`` (in tool_progress / tool_result events) with
            # the same tc after a session restore.  Without this, restore
            # uses the backend ``id`` (tc["id"]) and streaming updates use
            # the client_id — the two halves never meet, so
            # subAgentMessages never lands on the right tc.
            assistant_tool_calls: list[dict[str, Any]] = []
            for idx in sorted(tool_call_buffers.keys()):
                tc = tool_call_buffers[idx]
                client_id = f"call_{self.session.turn_count}_{idx}"
                entry: dict[str, Any] = {
                    "id": tc["id"] or f"call_{idx}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                # Only attach client_id when it differs from the
                # backend id (e.g. toolu_xxx) -- otherwise it would
                # be redundant and we keep the persisted shape slim.
                if client_id != entry["id"]:
                    entry["_client_id"] = client_id
                assistant_tool_calls.append(entry)

            msg_kwargs: dict[str, Any] = {}
            if assistant_tool_calls:
                msg_kwargs["tool_calls"] = assistant_tool_calls
            if _backend_usage:
                msg_kwargs["usage"] = _backend_usage
            if thinking_parts:
                msg_kwargs["reasoning_content"] = "".join(thinking_parts)
            # Build segments from streaming order
            segs = []
            if thinking_parts:
                segs.append({"kind": "thinking", "text": "".join(thinking_parts)})
            if assistant_content:
                segs.append({"kind": "text", "text": assistant_content})
            for tc in assistant_tool_calls:
                segs.append({"kind": "tool", "tool_id": tc["id"]})
            if segs:
                msg_kwargs["segments"] = segs
            self.session.add_message("assistant", assistant_content or None, **msg_kwargs)

            # ── Prepare tool calls: parse args, resolve tools, categorize ──
            # NOTE: client-facing events use a stable synthetic id ("call_{turn}_{idx}")
            # so they match the ids already emitted on tool_call_delta events.
            # Internal session/history/telemetry continues to use the real
            # backend id (tc["id"]). Without this split, the UI would create
            # one stub entry from the deltas (call_N) and a second entry from
            # tool_call_start (real id), rendering each tool call twice.
            prepared: list[dict[str, Any]] = []
            for idx in sorted(tool_call_buffers.keys()):
                tc = tool_call_buffers[idx]
                client_id = f"call_{self.session.turn_count}_{idx}"
                yield create_tool_call_start(name=tc["name"], id=client_id)
                turn_events += 1

                raw_args = tc["arguments"]
                if isinstance(raw_args, dict):
                    args = raw_args
                elif isinstance(raw_args, str) and raw_args.strip():
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                        err_msg = f"Error: Invalid JSON arguments: {raw_args[:200]}"
                        yield create_tool_result(id=client_id, content=err_msg, is_error=True)
                        self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                        turn_events += 1
                        self.telemetry.record_tool_call(
                            tool_name=tc["name"], latency_ms=0, success=False, error_message=err_msg,  # noqa: E501
                        )
                        yield create_tool_call_end(id=client_id)
                        turn_events += 1
                        prepared.append({"id": tc["id"], "client_id": client_id,
                                         "name": tc["name"], "args": args,
                                         "tool": None, "skip": True, "error": err_msg})
                        continue
                else:
                    args = {}

                tool = self.tool_registry.get(tc["name"])
                if tool is None:
                    err_msg = f"Error: Unknown tool: {tc['name']}"
                    yield create_tool_result(id=client_id, content=err_msg, is_error=True)
                    self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=tc["name"], latency_ms=0, success=False, error_message=err_msg,
                    )
                    yield create_tool_call_end(id=client_id)
                    turn_events += 1
                    prepared.append({"id": tc["id"], "client_id": client_id,
                                     "name": tc["name"], "args": args,
                                     "tool": None, "skip": True, "error": err_msg})
                    continue

                is_safe = tool.is_concurrency_safe(args)
                prepared.append({
                    "id": tc["id"], "client_id": client_id,
                    "name": tc["name"], "args": args,
                    "tool": tool, "skip": False, "safe": is_safe,
                    "args_summary": _args_summary(args),
                })

            # ── Permission & hooks for all tools (sequential -- these may need user input) ──
            if self._cancelled():
                break
            for p in prepared:
                if self._cancelled():
                    break
                if p["skip"]:
                    continue
                permission = await self.safety.check_tool_permission(p["name"], p["args"])
                if permission.behavior == "deny":
                    deny_reason = (
                        getattr(permission, "reason", "")
                        or _permission_reason(p["name"])
                        or "Permission denied by policy."
                    )
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="denied")
                    yield create_tool_result(id=p["client_id"], content=deny_reason, is_error=True)
                    self.session.add_tool_result(p["id"], deny_reason, is_error=True, client_id=p["client_id"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=0,
                        success=False, error_message=deny_reason,
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    p["skip"] = True
                    p["error"] = deny_reason
                    continue

                if permission.behavior == "ask":
                    # Prefer the reason supplied by the Rust permission
                    # engine (e.g. "Command matches dangerous pattern:
                    # \brm\s+.*-(?:[a-z]*r[a-z]*f|rf)\b").  Fall back
                    # to a generic message if the engine didn't supply
                    # one.
                    permission_reason = (
                        getattr(permission, "reason", "")
                        or _permission_reason(p["name"])
                    )
                    await self.hook_system.emit_permission_request(
                        p["name"], permission_reason
                    )
                    yield create_permission_request(
                        tool_name=p["name"],
                        reason=permission_reason,
                    )
                    self._pending_tool_name = p["name"]
                    self._permission_event = asyncio.Event()
                    self._permission_decision = False
                    permission_waiter = asyncio.create_task(self._permission_event.wait())
                    cancel_waiter = asyncio.create_task(self._cancel_event.wait())
                    try:
                        done, pending = await asyncio.wait(
                            [permission_waiter, cancel_waiter],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=120.0,
                        )
                        for t in pending:
                            t.cancel()
                        if cancel_waiter in done:
                            logger.info(
                                "Permission request cancelled for tool '%s'",
                                p["name"],
                            )
                    except Exception:
                        logger.warning(
                            "Permission request interrupted for tool '%s'",
                            p["name"],
                            exc_info=True,
                        )
                    self._permission_event = None
                    await self.hook_system.emit_permission_response(
                        p["name"], self._permission_decision
                    )
                    if not self._permission_decision:
                        err_msg = "Permission denied by user."
                        yield create_tool_result(id=p["client_id"], content=err_msg, is_error=True)
                        self.session.add_tool_result(p["id"], err_msg, is_error=True, client_id=p["client_id"])
                        turn_events += 1
                        self.telemetry.record_tool_call(
                            tool_name=p["name"], latency_ms=0,
                            success=False, error_message=err_msg,
                        )
                        yield create_tool_call_end(id=p["client_id"])
                        turn_events += 1
                        p["skip"] = True
                        p["error"] = err_msg
                        continue

                pre_hook = await self.hook_system.emit_pre_tool(p["name"], p["args"])
                if pre_hook and pre_hook.get("block"):
                    block_reason = pre_hook.get("block_reason") or f"Blocked by hook: {p['name']}"
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="blocked")  # noqa: E501
                    yield create_tool_result(id=p["client_id"], content=block_reason, is_error=True)
                    self.session.add_tool_result(p["id"], block_reason, is_error=True, client_id=p["client_id"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=0,
                        success=False, error_message=block_reason,
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    p["skip"] = True
                    p["error"] = block_reason
                    continue
                if pre_hook and pre_hook.get("modified_input"):
                    p["args"] = pre_hook["modified_input"]

                # ── Plan mode interception: propose before executing ──
                if self.plan_mode_active:
                    proposal_emitted = False
                    async for _event in self._intercept_plan_mode(
                        p["name"], p["args"], p["id"], p["client_id"],
                    ):
                        proposal_emitted = True
                        yield _event
                        turn_events += 1
                    if proposal_emitted and not self._plan_decision:
                        # User rejected the proposal -- feed a synthetic
                        # error result back to the model so it can
                        # adjust its plan without leaving the tool call
                        # hanging in the conversation.
                        plan_err = "Plan rejected by user. Adjust your plan and try a different approach."  # noqa: E501
                        yield create_tool_result(
                            id=p["client_id"],
                            content=plan_err,
                            is_error=True,
                        )
                        self.session.add_tool_result(p["id"], plan_err, is_error=True, client_id=p["client_id"])
                        turn_events += 1
                        self.telemetry.record_tool_call(
                            tool_name=p["name"], latency_ms=0,
                            success=False, error_message=plan_err,
                        )
                        yield create_tool_call_end(id=p["client_id"])
                        turn_events += 1
                        p["skip"] = True
                        p["error"] = plan_err
                        continue

                # ── Question tool: block until user answers ──
                if p["name"] == "question":
                    args = p["args"]
                    questions_list: list[dict[str, Any]] = []
                    questions_raw = args.get("questions")
                    if isinstance(questions_raw, str):
                        with contextlib.suppress(builtins.BaseException): questions_raw = json.loads(questions_raw)  # noqa: E501
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
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")  # noqa: E501
                    self._question_event = asyncio.Event()
                    self._question_answers = ""
                    try:
                        await asyncio.wait_for(self._question_event.wait(), timeout=300.0)
                    except TimeoutError:
                        self._question_answers = "Error: Question timed out."
                    self._question_event = None
                    result = self._question_answers
                    yield create_tool_result(id=p["client_id"], content=result)
                    self.session.add_tool_result(p["id"], result, client_id=p["client_id"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=0, success=True,
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    p["skip"] = True
                    p["result"] = result
                    continue

            # ── Split into safe (concurrent) and unsafe (sequential) groups ──
            safe_tools = [p for p in prepared if not p.get("skip") and p.get("safe")]
            unsafe_tools = [p for p in prepared if not p.get("skip") and not p.get("safe")]

            # ── Capture file snapshots before any tool writes to disk ──
            for p in safe_tools + unsafe_tools:
                name = p["name"]
                args = p["args"]
                if name in _WRITE_TOOL_NAMES:
                    # file_write, write_file, writeFile: file_path kwarg
                    fp = args.get("file_path", "")
                    # file_edit: file_path kwarg
                    if not fp and name in ("file_edit",):
                        fp = args.get("file_path", "")
                    # apply_patch: files list (capture both old and new paths)
                    if name == "apply_patch":
                        for fd in args.get("files", []):
                            if isinstance(fd, dict):
                                old_p = fd.get("old_path") or ""
                                new_p = fd.get("new_path") or ""
                                if old_p:
                                    self.session.capture_file_snapshot(old_p)
                                if new_p and new_p != old_p:
                                    self.session.capture_file_snapshot(new_p)
                        continue
                    if fp:
                        self.session.capture_file_snapshot(fp)
            # ── Execute safe tools in parallel ──
            if safe_tools:
                # Emit progress for all safe tools upfront
                for p in safe_tools:
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")  # noqa: E501

                async def _execute_safe(p: dict[str, Any]) -> dict[str, Any]:
                    tool_start = time.time()
                    tool_error = False
                    _span = trace_tool_call(self._tracer, p["name"], p["args"])
                    try:
                        executor = RetryableExecutor(self.recovery_engine)
                        state = await executor.execute(
                            tool_name=p["name"],
                            tool_args=p["args"],
                            execute_fn=lambda args: p["tool"].execute(**args),
                        )
                        if state.succeeded:
                            result = state.final_result
                            sub_agent_messages = None
                            sub_agent_references: list[dict[str, Any]] = []
                            if isinstance(result, dict):
                                sub_agent_messages = result.get("messages")
                                sub_agent_references = result.get("references", [])
                                result = str(result.get("content", ""))
                            result = self.safety.validate_tool_output(p["name"], result)
                        else:
                            result = state.final_result
                            sub_agent_messages = None
                            sub_agent_references = []
                            if isinstance(result, dict):
                                sub_agent_messages = result.get("messages")
                                result = str(result.get("content", ""))
                            tool_error = True
                        extra = await self.hook_system.emit_post_tool(p["name"], p["args"], result)
                        if extra:
                            result = result + "\n" + extra
                        _span.set_attribute("tool.success", not tool_error)
                        _span.set_attribute("tool.latency_ms", (time.time() - tool_start) * 1000)
                    except Exception as _exc:
                        _span.record_exception(_exc)
                        raise
                    finally:
                        _span.end()
                    p["result"] = result
                    p["sub_agent_messages"] = sub_agent_messages
                    p["sub_agent_references"] = sub_agent_references
                    p["is_error"] = tool_error
                    p["recovery_history"] = list(state.recovery_history)
                    p["latency_ms"] = (time.time() - tool_start) * 1000
                    return p

                safe_tasks = [_execute_safe(p) for p in safe_tools]
                completed = await asyncio.gather(*safe_tasks, return_exceptions=True)
                for idx, item in enumerate(completed):
                    if isinstance(item, BaseException):
                        p = safe_tools[idx]
                        err_msg = f"Tool execution crashed: {type(item).__name__}: {item}"
                        yield create_tool_result(id=p["client_id"], content=err_msg, is_error=True)
                        self.session.add_tool_result(p["id"], err_msg, is_error=True, client_id=p["client_id"])
                        turn_events += 1
                        self._error_tool_names.add(p["name"])
                        self.telemetry.record_tool_call(
                            tool_name=p["name"], latency_ms=0.0,
                            success=False, error_message=err_msg,
                        )
                        self.learner.record_error(
                            tool_name=p["name"], error_type="unhandled_exception",
                            context=p["args_summary"], correction="",
                        )
                        yield create_tool_call_end(id=p["client_id"])
                        turn_events += 1
                        continue
                    p = item
                    p["result"] = _apply_result_budget(p["result"], p["tool"])
                    # Auto-verify: append verification reminder for write tools
                    if not p["is_error"] and p["name"] in _WRITE_TOOL_NAMES:
                        fp = _extract_file_path(p["name"], p["result"])
                        if fp:
                            p["result"] += (
                                f"\n\n[VERIFY] Please verify the changes to `{fp}` "
                                f"are correct by reading the file."
                            )
                    yield create_tool_result(
                        id=p["client_id"],
                        content=p["result"],
                        is_error=p["is_error"],
                        sub_agent_messages=p.get("sub_agent_messages"),
                    )
                    self.session.add_tool_result(p["id"], p["result"], is_error=p["is_error"], sub_agent_messages=p.get("sub_agent_messages"), client_id=p["client_id"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=p["latency_ms"],
                        success=not p["is_error"],
                        error_message=p["result"] if p["is_error"] else "",
                    )
                    if p["is_error"]:
                        self._error_tool_names.add(p["name"])
                        self.learner.record_error(
                            tool_name=p["name"], error_type="execution_error",
                            context=p["args_summary"], correction="",
                        )
                        if self.feedback is not None:
                            self.feedback.record_correction(
                                tool_name=p["name"], error_type="execution_error",
                                error_context=p["args_summary"],
                                user_correction=p["result"][:400],
                            )
                    else:
                        self._error_tool_names.discard(p["name"])
                        self.learner.record_success(
                            tool_name=p["name"], intent=prompt[:300], params=p["args"],
                            outcome=p["result"][:500], latency_ms=p["latency_ms"],
                        )
                        if p.get("recovery_history"):
                            correction = ErrorRecoveryEngine.infer_correction_from_history(p["recovery_history"], p["name"])  # noqa: E501
                            self.learner.record_correction(
                                tool_name=p["name"],
                                error_context=p["args_summary"],
                                correction=correction,
                            )
                    self.optimizer.record_outcome(
                        tool_name=p["name"], params=p["args"],
                        success=not p["is_error"], latency_ms=p["latency_ms"],
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    if not p["is_error"]:
                        fp = _extract_file_path(p["name"], p["result"])
                        if fp:
                            if p["name"] == "apply_patch":
                                for ap_path in _extract_apply_patch_paths(p["result"]):
                                    entry = self.session.add_artifact(ap_path, p["name"], diff_text="")  # noqa: E501
                                    yield Artifact(artifact=entry)
                            else:
                                diff_text = _extract_diff_text(p["name"], p["result"])
                                entry = self.session.add_artifact(fp, p["name"], diff_text=diff_text)  # noqa: E501
                                yield Artifact(artifact=entry)
                        else:
                            # Non-file tool -> record as reference
                            if _is_reference_tool(p["name"]):
                                summary = _extract_ref_summary(p["name"], p.get("args", {}), p["result"])  # noqa: E501
                                ref_icon = ""
                                entry = self.session.add_reference(p["name"], summary, icon=ref_icon)  # noqa: E501
                                yield Reference(reference=entry)
                            # Forward references from sub-agents (agent / workflow tools)
                            for sub_ref in (p.get("sub_agent_references") or []):
                                if isinstance(sub_ref, dict) and _is_reference_tool(sub_ref.get("tool", "")):
                                    ref_entry = self.session.add_reference(
                                        sub_ref.get("tool", ""),
                                        sub_ref.get("summary", ""),
                                        icon=sub_ref.get("icon", ""),
                                    )
                                    yield Reference(reference=ref_entry)
                        plan_items = _ensure_plan_items(p["name"], p["args"])
                        if plan_items:
                            yield PlanUpdate(plan_items=plan_items)
                            self.session.plan_items = plan_items

            # ── Execute unsafe tools sequentially ──
            for p in unsafe_tools:
                tool_start = time.time()
                yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")

                tool_error = False
                sub_agent_messages = None
                sub_agent_session_id = None
                sub_agent_references: list[dict[str, Any]] = []
                try:
                    if p["name"] == "agent":
                        progress_queue: asyncio.Queue[list[dict[str, Any]] | None] = asyncio.Queue()

                        async def _sub_agent_progress(messages: list[dict[str, Any]]) -> None:
                            nonlocal sub_agent_messages
                            sub_agent_messages = messages
                            await progress_queue.put(messages)

                        agent_args = dict(p["args"])
                        agent_args["progress_callback"] = _sub_agent_progress

                        async def _run_agent_tool() -> Any:
                            try:
                                return await p["tool"].execute(**agent_args)
                            finally:
                                await progress_queue.put(None)

                        agent_task = asyncio.create_task(_run_agent_tool())
                        while True:
                            live_messages = await progress_queue.get()
                            if live_messages is None:
                                break
                            yield create_tool_progress(
                                id=p["client_id"],
                                tool_name=p["name"],
                                status="running",
                                sub_agent_messages=live_messages,
                            )
                        result_obj = await agent_task
                        if isinstance(result_obj, dict):
                            sub_agent_messages = result_obj.get("messages")
                            sub_agent_session_id = result_obj.get("session_id")
                            sub_agent_references = result_obj.get("references", [])
                            if sub_agent_messages:
                                yield create_tool_progress(
                                    id=p["client_id"],
                                    tool_name=p["name"],
                                    status="running",
                                    sub_agent_messages=sub_agent_messages,
                                )
                            result = str(result_obj.get("content", ""))
                        else:
                            result = str(result_obj)
                        result = self.safety.validate_tool_output(p["name"], result)
                    elif p["name"] == "workflow":
                        progress_queue: asyncio.Queue[list[dict[str, Any]] | None] = asyncio.Queue()

                        async def _wf_progress(messages: list[dict[str, Any]]) -> None:
                            await progress_queue.put(messages)

                        wf_args = dict(p["args"])
                        wf_args["progress_callback"] = _wf_progress

                        async def _run_wf_tool() -> Any:
                            try:
                                return await p["tool"].execute(**wf_args)
                            finally:
                                await progress_queue.put(None)

                        wf_task = asyncio.create_task(_run_wf_tool())
                        while True:
                            live_messages = await progress_queue.get()
                            if live_messages is None:
                                break
                            for msg in live_messages:
                                if isinstance(msg, dict) and msg.get("role") == "workflow":
                                    wf_type = msg.get("type", "")
                                    if wf_type == "workflow_started":
                                        yield WorkflowStartedEvent(
                                            workflow_id=msg.get("workflow_id", ""),
                                            goal=msg.get("goal", ""),
                                            total_tasks=msg.get("total_tasks", 0),
                                            task_ids=msg.get("task_ids", []),
                                        )
                                    elif wf_type == "workflow_task":
                                        yield WorkflowTaskEvent(
                                            workflow_id=msg.get("workflow_id", ""),
                                            task_id=msg.get("task_id", ""),
                                            task_name=msg.get("task_name", ""),
                                            status=msg.get("status", "running"),
                                        )
                                    elif wf_type == "workflow_completed":
                                        yield WorkflowCompletedEvent(
                                            workflow_id=msg.get("workflow_id", ""),
                                            goal=msg.get("goal", ""),
                                            success=msg.get("success", True),
                                            completed_count=msg.get("completed_count", 0),
                                            failed_count=msg.get("failed_count", 0),
                                            skipped_count=msg.get("skipped_count", 0),
                                            total_duration=msg.get("total_duration", 0.0),
                                        )
                                else:
                                    sub_agent_messages = [live_messages] if not isinstance(live_messages, list) else live_messages  # noqa: E501
                                    yield create_tool_progress(
                                        id=p["client_id"],
                                        tool_name=p["name"],
                                        status="running",
                                        sub_agent_messages=sub_agent_messages,
                                    )
                        result_obj = await wf_task
                        sub_agent_messages = None
                        if isinstance(result_obj, dict):
                            sub_agent_messages = result_obj.get("messages")
                            result = str(result_obj.get("content", ""))
                        else:
                            result = str(result_obj)
                        result = self.safety.validate_tool_output(p["name"], result)
                    else:
                        executor = RetryableExecutor(self.recovery_engine)
                        state = await executor.execute(
                            tool_name=p["name"],
                            tool_args=p["args"],
                            execute_fn=lambda args: p["tool"].execute(**args),
                        )
                        if state.succeeded:
                            result = state.final_result
                            if isinstance(result, dict):
                                sub_agent_messages = result.get("messages")
                                result = str(result.get("content", ""))
                            result = self.safety.validate_tool_output(p["name"], result)
                            if state.recovery_history:
                                correction = ErrorRecoveryEngine.infer_correction(state)
                                self.learner.record_correction(
                                    tool_name=p["name"],
                                    error_context=p["args_summary"],
                                    correction=correction,
                                )
                        else:
                            result = state.final_result
                            if isinstance(result, dict):
                                sub_agent_messages = result.get("messages")
                                result = str(result.get("content", ""))
                            tool_error = True

                    extra = await self.hook_system.emit_post_tool(p["name"], p["args"], result)
                    if extra:
                        result = result + "\n" + extra
                except Exception as exc:
                    result = f"Tool execution crashed: {type(exc).__name__}: {exc}"
                    tool_error = True

                result = _apply_result_budget(result, p["tool"])
                yield create_tool_result(
                    id=p["client_id"],
                    content=result,
                    is_error=tool_error,
                    sub_agent_messages=sub_agent_messages,
                    sub_agent_session_id=sub_agent_session_id,
                )
                self.session.add_tool_result(
                    p["id"],
                    result,
                    is_error=tool_error,
                    sub_agent_messages=sub_agent_messages,
                    sub_agent_session_id=sub_agent_session_id,
                )
                turn_events += 1

                tool_latency = (time.time() - tool_start) * 1000
                self.telemetry.record_tool_call(
                    tool_name=p["name"], latency_ms=tool_latency,
                    success=not tool_error,
                    error_message=result if tool_error else "",
                )
                if tool_error:
                    self._error_tool_names.add(p["name"])
                    self.learner.record_error(
                        tool_name=p["name"], error_type="execution_error",
                        context=p["args_summary"], correction="",
                    )
                    if self.feedback is not None:
                        self.feedback.record_correction(
                            tool_name=p["name"], error_type="execution_error",
                            error_context=p["args_summary"],
                            user_correction=result[:400],
                        )
                else:
                    self._error_tool_names.discard(p["name"])
                    self.learner.record_success(
                        tool_name=p["name"], intent=prompt[:300], params=p["args"],
                        outcome=result[:500], latency_ms=tool_latency,
                    )
                self.optimizer.record_outcome(
                    tool_name=p["name"], params=p["args"],
                    success=not tool_error, latency_ms=tool_latency,
                )
                yield create_tool_call_end(id=p["client_id"])
                turn_events += 1
                if not tool_error:
                    fp = _extract_file_path(p["name"], result)
                    if fp:
                        if p["name"] == "apply_patch":
                            for ap_path in _extract_apply_patch_paths(result):
                                entry = self.session.add_artifact(ap_path, p["name"], diff_text="")
                                yield Artifact(artifact=entry)
                        else:
                            diff_text = _extract_diff_text(p["name"], result)
                            entry = self.session.add_artifact(fp, p["name"], diff_text=diff_text)
                            yield Artifact(artifact=entry)
                    else:
                        # Non-file tool -> record as reference
                        if _is_reference_tool(p["name"]):
                            summary = _extract_ref_summary(p["name"], p.get("args", {}), result)
                            entry = self.session.add_reference(p["name"], summary)
                            yield Reference(reference=entry)
                    # Forward references from sub-agents (agent tool)
                    for sub_ref in sub_agent_references:
                        if isinstance(sub_ref, dict) and _is_reference_tool(sub_ref.get("tool", "")):
                            ref_entry = self.session.add_reference(
                                sub_ref.get("tool", ""),
                                sub_ref.get("summary", ""),
                                icon=sub_ref.get("icon", ""),
                            )
                            yield Reference(reference=ref_entry)
                    plan_items = _ensure_plan_items(p["name"], p["args"])
                    if plan_items:
                        yield PlanUpdate(plan_items=plan_items)

            # ── Intra-turn split: merge post-tool content into existing assistant message ──
            # When the model produces thinking/text -> tool_calls -> more thinking/text
            # within the same backend.chat() call, the post-tool content is
            # buffered in _extra_* variables. Merge it into the existing assistant
            # message so the session doesn't get split into two messages for a
            # single model response.
            if _in_extra and (_extra_text or _extra_thinking or _extra_buffers):
                for i in range(len(self.session.messages) - 1, -1, -1):
                    if self.session.messages[i].get("role") == "assistant":
                        msg = self.session.messages[i]
                        if _extra_text:
                            existing = msg.get("content") or ""
                            extra = "".join(_extra_text)
                            msg["content"] = (existing + "\n\n" + extra) if existing else extra
                        if _extra_buffers:
                            extra_tc = []
                            for idx in sorted(_extra_buffers.keys()):
                                tc = _extra_buffers[idx]
                                extra_tc.append({
                                    "id": tc["id"] or f"call_{idx}",
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": tc["arguments"],
                                    },
                                })
                            existing_tc = msg.get("tool_calls", [])
                            msg["tool_calls"] = existing_tc + extra_tc
                        if _extra_thinking:
                            existing_r = msg.get("reasoning_content", "") or ""
                            extra_r = "".join(_extra_thinking)
                            msg["reasoning_content"] = existing_r + extra_r
                        # Preserve segment ordering for intra-turn extra content
                        extra_segs = []
                        if _extra_thinking:
                            extra_segs.append({"kind": "thinking", "text": "".join(_extra_thinking)})  # noqa: E501
                        if _extra_text:
                            extra_segs.append({"kind": "text", "text": "".join(_extra_text)})
                        for etc in (extra_tc if _extra_buffers else []):
                            extra_segs.append({"kind": "tool", "tool_id": etc["id"]})
                        if extra_segs:
                            existing_segs = msg.get("segments", [])
                            msg["segments"] = existing_segs + extra_segs
                        self.session.mark_messages_dirty()
                        break

                # Prepare secondary tool calls
                extra_prepared: list[dict[str, Any]] = []
                for idx in sorted(_extra_buffers.keys()):
                    tc = _extra_buffers[idx]
                    client_id = f"call_{self.session.turn_count}_extra_{idx}"
                    yield create_tool_call_start(name=tc["name"], id=client_id)
                    turn_events += 1

                    raw_args = tc["arguments"]
                    if isinstance(raw_args, dict):
                        args = raw_args
                    elif isinstance(raw_args, str) and raw_args.strip():
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                            err_msg = f"Error: Invalid JSON arguments: {raw_args[:200]}"
                            yield create_tool_result(id=client_id, content=err_msg, is_error=True)
                            self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                            turn_events += 1
                            yield create_tool_call_end(id=client_id)
                            turn_events += 1
                            continue
                    else:
                        args = {}

                    tool = self.tool_registry.get(tc["name"])
                    if tool is None:
                        err_msg = f"Error: Unknown tool: {tc['name']}"
                        yield create_tool_result(id=client_id, content=err_msg, is_error=True)
                        self.session.add_tool_result(tc["id"], err_msg, is_error=True)
                        turn_events += 1
                        yield create_tool_call_end(id=client_id)
                        turn_events += 1
                        continue

                    extra_prepared.append({
                        "id": tc["id"], "client_id": client_id,
                        "name": tc["name"], "args": args,
                        "tool": tool,
                        "args_summary": _args_summary(args),
                    })

                # Permission & hooks for secondary tools
                if not self._cancelled():
                    for p in extra_prepared:
                        if self._cancelled():
                            break
                        permission = await self.safety.check_tool_permission(p["name"], p["args"])
                        if permission.behavior == "deny":
                            deny_reason = (
                                getattr(permission, "reason", "")
                                or _permission_reason(p["name"])
                                or "Permission denied by policy."
                            )
                            yield create_tool_result(id=p["client_id"], content=deny_reason, is_error=True)  # noqa: E501
                            self.session.add_tool_result(p["id"], deny_reason, is_error=True, client_id=p["client_id"])
                            turn_events += 1
                            self.telemetry.record_tool_call(
                                tool_name=p["name"], latency_ms=0,
                                success=False, error_message=deny_reason,
                            )
                            yield create_tool_call_end(id=p["client_id"])
                            turn_events += 1
                            continue

                        if permission.behavior == "ask":
                            permission_reason = (
                                getattr(permission, "reason", "")
                                or _permission_reason(p["name"])
                            )
                            await self.hook_system.emit_permission_request(
                                p["name"], permission_reason
                            )
                            yield create_permission_request(
                                tool_name=p["name"],
                                reason=permission_reason,
                            )
                            self._pending_tool_name = p["name"]
                            self._permission_event = asyncio.Event()
                            self._permission_decision = False
                            permission_waiter = asyncio.create_task(self._permission_event.wait())
                            cancel_waiter = asyncio.create_task(self._cancel_event.wait())
                            try:
                                done, pending = await asyncio.wait(
                                    [permission_waiter, cancel_waiter],
                                    return_when=asyncio.FIRST_COMPLETED,
                                    timeout=120.0,
                                )
                                for t in pending:
                                    t.cancel()
                                if cancel_waiter in done:
                                    logger.info(
                                        "Permission request cancelled for tool '%s'",
                                        p["name"],
                                    )
                            except Exception:
                                logger.warning(
                                    "Permission request interrupted for tool '%s'",
                                    p["name"],
                                    exc_info=True,
                                )
                            self._permission_event = None
                            await self.hook_system.emit_permission_response(
                                p["name"], self._permission_decision
                            )
                            if not self._permission_decision:
                                err_msg = "Permission denied by user."
                                yield create_tool_result(id=p["client_id"], content=err_msg, is_error=True)  # noqa: E501
                                self.session.add_tool_result(p["id"], err_msg, is_error=True, client_id=p["client_id"])
                                turn_events += 1
                                self.telemetry.record_tool_call(
                                    tool_name=p["name"], latency_ms=0,
                                    success=False, error_message=err_msg,
                                )
                                yield create_tool_call_end(id=p["client_id"])
                                turn_events += 1
                                continue

                        pre_hook = await self.hook_system.emit_pre_tool(p["name"], p["args"])
                        if pre_hook and pre_hook.get("block"):
                            block_reason = pre_hook.get("block_reason") or f"Blocked by hook: {p['name']}"  # noqa: E501
                            yield create_tool_result(id=p["client_id"], content=block_reason, is_error=True)  # noqa: E501
                            self.session.add_tool_result(p["id"], block_reason, is_error=True, client_id=p["client_id"])
                            turn_events += 1
                            self.telemetry.record_tool_call(
                                tool_name=p["name"], latency_ms=0,
                                success=False, error_message=block_reason,
                            )
                            yield create_tool_call_end(id=p["client_id"])
                            turn_events += 1
                            continue
                        if pre_hook and pre_hook.get("modified_input"):
                            p["args"] = pre_hook["modified_input"]

                        # ── Plan mode interception for secondary tools ──
                        if self.plan_mode_active:
                            sec_proposal_emitted = False
                            async for _event in self._intercept_plan_mode(
                                p["name"], p["args"], p["id"], p["client_id"],
                            ):
                                sec_proposal_emitted = True
                                yield _event
                                turn_events += 1
                            if sec_proposal_emitted and not self._plan_decision:
                                plan_err = "Plan rejected by user. Adjust your plan and try a different approach."  # noqa: E501
                                yield create_tool_result(
                                    id=p["client_id"],
                                    content=plan_err,
                                    is_error=True,
                                )
                                self.session.add_tool_result(p["id"], plan_err, is_error=True, client_id=p["client_id"])
                                turn_events += 1
                                self.telemetry.record_tool_call(
                                    tool_name=p["name"], latency_ms=0,
                                    success=False, error_message=plan_err,
                                )
                                yield create_tool_call_end(id=p["client_id"])
                                turn_events += 1
                                continue

                # Execute secondary tools sequentially
                for p in extra_prepared:
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")  # noqa: E501
                    tool_start = time.time()
                    tool_error = False
                    try:
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
                                    error_context=p["args_summary"],
                                    correction=correction,
                                )
                        else:
                            result = state.final_result
                            tool_error = True
                        extra = await self.hook_system.emit_post_tool(p["name"], p["args"], result)
                        if extra:
                            result = result + "\n" + extra
                    except Exception as exc:
                        result = f"Tool execution crashed: {type(exc).__name__}: {exc}"
                        tool_error = True
                    result = _apply_result_budget(result, p["tool"])
                    yield create_tool_result(id=p["client_id"], content=result, is_error=tool_error)
                    self.session.add_tool_result(p["id"], result, is_error=tool_error, client_id=p["client_id"])
                    turn_events += 1
                    tool_latency = (time.time() - tool_start) * 1000
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=tool_latency,
                        success=not tool_error, error_message=result if tool_error else "",
                    )
                    if tool_error:
                        self._error_tool_names.add(p["name"])
                        self.learner.record_error(
                            tool_name=p["name"], error_type="execution_error",
                            context=p["args_summary"], correction="",
                        )
                        if self.feedback is not None:
                            self.feedback.record_correction(
                                tool_name=p["name"], error_type="execution_error",
                                error_context=p["args_summary"],
                                user_correction=result[:400],
                            )
                    else:
                        self._error_tool_names.discard(p["name"])
                        self.learner.record_success(
                            tool_name=p["name"], intent=prompt[:300], params=p["args"],
                            outcome=result[:500], latency_ms=tool_latency,
                        )
                    self.optimizer.record_outcome(
                        tool_name=p["name"], params=p["args"],
                        success=not tool_error, latency_ms=tool_latency,
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    if not tool_error:
                        fp = _extract_file_path(p["name"], result)
                        if fp:
                            if p["name"] == "apply_patch":
                                for ap_path in _extract_apply_patch_paths(result):
                                    entry = self.session.add_artifact(ap_path, p["name"], diff_text="")  # noqa: E501
                                    yield Artifact(artifact=entry)
                            else:
                                diff_text = _extract_diff_text(p["name"], result)
                                entry = self.session.add_artifact(fp, p["name"], diff_text=diff_text)  # noqa: E501
                                yield Artifact(artifact=entry)
                        plan_items = _ensure_plan_items(p["name"], p["args"])
                        if plan_items:
                            yield PlanUpdate(plan_items=plan_items)
                            self.session.plan_items = plan_items

            # Don't yield an assistant_boundary here -- doing so makes the frontend
            # split the response into separate bubbles after every tool-calling
            # turn.  All model output within a single user turn (including post-tool
            # follow-ups) stays in one assistant message on both session and UI.

            self.session.turn_count += 1
            turn_latency = (time.time() - turn_start) * 1000

            # ── Repetitive tool-call loop detection ─────────────────────
            # Detect when the model is genuinely stuck: same tool+args
            # across consecutive turns.  Different queries with the same
            # tool name (e.g. web_search with different queries) are fine.
            turn_sigs: list[str] = []
            for tc in assistant_tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_raw = func.get("arguments", "")
                args_key = (args_raw or "")[:80]
                turn_sigs.append(f"{name}:{args_key}")
            if turn_sigs:
                self._recent_tool_names.append(tuple(turn_sigs))
                if len(self._recent_tool_names) > 20:
                    self._recent_tool_names.pop(0)
                if len(self._recent_tool_names) >= 12 and not self._error_tool_names:
                    last12 = self._recent_tool_names[-12:]
                    if last12.count(last12[-1]) >= 12:
                        logger.warning(
                            "[run] repetitive tool-loop: %s turn=%d -- continuing session",
                            last12[-1], self.session.turn_count,
                        )
                        # Don't kill the session, just warn and let it continue.
                        # The model or user can decide to stop if needed.

            self.telemetry.record_turn(
                turn_number=self.session.turn_count,
                event_count=turn_events,
                latency_ms=turn_latency,
                token_usage=_backend_usage or {},
                model=self.config.model,
            )

            # Evolution: reflex + meta-cognition
            tool_outcomes: list[dict[str, Any]] = [
                {"tool_name": tc["name"], "is_error": False}
                for tc in tool_call_buffers.values()
            ]
            self.reflex.reflect(
                turn_number=self.session.turn_count,
                tool_results=tool_outcomes,
                turn_latency_ms=turn_latency,
            )
            self.meta.assess_turn(
                prompt=prompt,
                tool_results=tool_outcomes,
            )

            await self.hook_system.emit_turn_end(self.session.turn_count)
            self.rollback.commit(self.session, f"turn_{self.session.turn_count}")

        reason = "cancelled" if self._cancelled() else "max_tokens"
        logger.warning("[run] session ending turn=%d max_turns=%s reason=%s",
                       self.session.turn_count, self.config.max_turns, reason)
        await self.hook_system.emit_session_end()
        yield create_finish(
            reason,
            usage=_last_backend_usage,
        )

    async def _run_sub_agent(self, prompt: str,
                              system_prompt: str = "", max_turns: int = 0,
                              model: str = "", api_key: str = "",
                              base_url: str = "",
                              tool_policy: str = "all",
                              progress_callback: Any = None,
                              event_callback: Any = None) -> dict[str, Any]:
        """Run a sub-agent as a fully isolated session.

        The sub-agent is ALWAYS an EncreAgent spawned from this loop. The
        caller can observe execution through two hooks:

        * ``progress_callback(messages_snapshot)`` is awaited on every
          streaming event with the canonical session messages plus any
          uncommitted draft. Used by the chat UI to render live tokens.
        * ``event_callback(event)`` is awaited on every raw AgentEvent
          (TextDelta, ThinkingDelta, ToolCallStart, ToolProgress,
          ToolCallEnd, ToolResult, Finish) before it is folded into the
          draft. Used by callers that need to translate the event stream
          into a different transport (e.g. the automation scheduler's
          automation_stream_event protocol).

        Returns the standard sub-agent result dict:

            ``{"content": str, "messages": list[dict], "session_id": str}``

        The sub-agent's session is persisted under
        ``<data_dir>/sub_agents/<session_id>/`` and ``metadata["channel"]``
        is set to ``"sub_agent"`` so the sidebar session list can filter
        it out.
        """
        # Coerce None to "" at the boundary so downstream code (logging,
        # sub_agent.run, etc.) can rely on a string.  Some callers
        # (notably the automation scheduler) pass ``system_prompt=None``
        # to mean "let the sub-agent build its default system prompt",
        # which previously crashed the length-based logger here.
        if prompt is None:
            prompt = ""
        if system_prompt is None:
            system_prompt = ""

        logger.info("[sub_agent] _run_sub_agent | prompt_len=%d | sys_prompt_len=%d | tool_policy=%s",  # noqa: E501
                    len(prompt), len(system_prompt), tool_policy)
        logger.info("[sub_agent] prompt_text=%.300s", prompt)

        # Create a full EncreAgent (same as SessionManager.create_session / normal user flow).
        # Lazy-import to avoid circular dependency (agent.py imports EncreLoop from this module).
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.tools.builtin.agent import (
            _enforce_tool_policy as _agent_enforce_policy,
            MAX_SUB_AGENT_DEPTH,
        )
        from encre.tools.registry import ToolRegistry

        sub_config = EncreConfig(
            model=model or self.config.model,
            api_key=api_key or self.config.api_key,
            base_url=base_url or self.config.base_url,
            max_tokens=self.config.max_tokens,
            max_turns=max_turns,
            permission_mode="bypass",
            backend_type=self.config.backend_type,
            backend_kwargs=self.config.backend_kwargs,
        )
        # Clone tool registry (same as session_manager._clone_tool_registry)
        tool_registry = ToolRegistry()
        tool_registry._tools = dict(self.tool_registry._tools)

        sub_agent = EncreAgent(
            config=sub_config,
            tool_registry=tool_registry,
            memory_system=self.memory_system,
            profile_system=self.profile_system,
            soul_system=self.soul_system,
            skill_registry=self.skill_registry,
            hook_system=self.hook_system,
            safety=self.safety,
        )
        sub_agent.loop.sub_agent_depth = self.sub_agent_depth + 1
        # Hard-fence: when the sub-agent is itself a delegated sub-agent
        # (depth > 0), the runtime forbids further nesting. Remove the
        # ``agent`` tool from the sub-agent's tool registry so the model
        # cannot even see it -- this is the only way to stop a
        # recursion-looping LLM that keeps retrying on a soft error.
        if self.sub_agent_depth >= MAX_SUB_AGENT_DEPTH and "agent" in tool_registry._tools:
            try:
                del tool_registry._tools["agent"]
                logger.info("[sub_agent] depth=%d reached MAX=%d, removed 'agent' tool from sub-agent registry",
                            self.sub_agent_depth + 1, MAX_SUB_AGENT_DEPTH)
            except Exception:
                pass
        # Propagate the role-template's tool_policy onto the sub-agent's
        # own EncreConfig so the pre-tool enforcement hook (in
        # ``tools.builtin.agent``) can read it via the loop's
        # ``config.current_tool_policy`` field.  ``"all"`` is a no-op
        # (no tools are blocked) so we only inject when the policy is
        # actually restrictive.
        sub_agent.config.current_tool_policy = tool_policy

        if tool_policy in ("readonly", "no_writes"):
            def _policy_hook(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:  # noqa: ARG001  # noqa: E501
                # ``tool_input`` is part of the pre-tool hook signature
                # for future context-aware policies; current policy
                # decisions only depend on ``tool_name``.
                err = _agent_enforce_policy(tool_name)
                if err is not None:
                    return {"block": True, "block_reason": err}
                return None

            # Wrap the sub-agent loop's pre-tool hook to apply the policy.
            original_emit_pre_tool = sub_agent.loop.hook_system.emit_pre_tool

            async def _emit_pre_tool_with_policy(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:  # noqa: E501
                result = _policy_hook(tool_name, tool_input)
                if result is not None:
                    return result
                return await original_emit_pre_tool(tool_name, tool_input)

            sub_agent.loop.hook_system.emit_pre_tool = _emit_pre_tool_with_policy  # type: ignore[assignment]
        # Add the prompt as a user message, exactly like ws.py does for normal input
        sub_agent.add_message("user", prompt)

        # Give the sub-agent a proper session ID
        import uuid
        sub_agent.session.id = sub_agent.session.id or str(uuid.uuid4())
        saved_session_id = sub_agent.session.id
        sub_agent.session.metadata["channel"] = "sub_agent"

        def _save():
            try:
                from encre.config import get_data_dir
                # Save to sub_agents dir (NOT the main sessions dir) so
                # SessionManager._bootstrap_index_from_disk does NOT include
                # sub-agent sessions in the sidebar session list.
                _dir = get_data_dir() / "sub_agents" / saved_session_id
                _dir.mkdir(parents=True, exist_ok=True)
                sub_agent.session.save_to_dir(str(_dir))
            except Exception:
                logger.warning("[sub_agent] failed to persist session", exc_info=True)

        result_parts: list[str] = []
        text_buffer = ""
        sub_refs: list[dict[str, Any]] = []
        # "Draft" assistant state tracked from the streaming events. Once the
        # sub-agent's own loop commits a new assistant message into
        # sub_agent.session.messages, we drop the matching draft and rely on
        # the committed record. This guarantees the snapshot never contains
        # duplicate / out-of-order assistant turns.
        draft_content: list[str] = []
        draft_reasoning: list[str] = []
        draft_tool_calls: list[dict[str, Any]] = []
        draft_tool_id_to_idx: dict[str, int] = {}
        draft_segments: list[dict[str, Any]] = []
        last_seen_msg_count = 0
        last_seen_assistant_id: str | None = None

        def _has_uncommitted_draft() -> bool:
            return bool(
                draft_content
                or draft_reasoning
                or draft_tool_calls
                or draft_segments
            )

        def _reset_draft() -> None:
            draft_content.clear()
            draft_reasoning.clear()
            draft_tool_calls.clear()
            draft_tool_id_to_idx.clear()
            draft_segments.clear()

        def _draft_as_message() -> dict[str, Any]:
            return {
                "role": "assistant",
                "content": "".join(draft_content),
                "reasoning_content": "".join(draft_reasoning),
                "tool_calls": [dict(tc) for tc in draft_tool_calls],
                "segments": [dict(s) for s in draft_segments],
                "created_at": time.time(),
            }

        def _sync_draft_with_session() -> None:
            """Drop the draft when the sub-agent's loop has committed a
            matching (or superseding) assistant message into session.messages.
            """
            nonlocal last_seen_msg_count, last_seen_assistant_id
            msgs = sub_agent.session.messages
            current_count = len(msgs)
            current_assistant_id: str | None = None
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    current_assistant_id = str(m.get("id") or "")
                    break
            # Reset the draft whenever a new assistant message has been
            # committed since the last emit. The agent's loop appends the
            # assistant message to session.messages only AFTER the streaming
            # for that turn has finished, so a new id means "the previous
            # turn's draft is now committed; start fresh".
            if (
                current_assistant_id is not None
                and current_assistant_id != last_seen_assistant_id
            ):
                last_seen_msg_count = current_count
                last_seen_assistant_id = current_assistant_id
                _reset_draft()
            elif current_count != last_seen_msg_count:
                last_seen_msg_count = current_count

        def _build_snapshot() -> list[dict[str, Any]]:
            """Build the messages snapshot for progress callbacks.

            Prefers sub_agent.session.messages (canonical, committed history
            with full tool_call / tool_result structure). If a streaming turn
            is still in progress and has not yet been committed, appends the
            draft so the frontend sees live tokens.
            """
            _sync_draft_with_session()
            snapshot = [dict(m) for m in sub_agent.session.messages]
            if _has_uncommitted_draft():
                snapshot.append(_draft_as_message())
            return snapshot

        async def _emit_live() -> None:
            if progress_callback is not None:
                await progress_callback(_build_snapshot())

        def _flush_text_buffer() -> None:
            nonlocal text_buffer
            text = text_buffer.strip()
            if text:
                result_parts.append(f"### Assistant\n{text}\n")
            text_buffer = ""

        #   Run exactly like ws.py does: agent.run(prompt, system_prompt=None) -> full system prompt
        # build
        # Register the child loop on the parent so a single Stop click on
        # the parent terminates the entire agent tree (the parent's
        # ``cancel()`` walks ``_child_loops``).
        self._child_loops.add(sub_agent.loop)
        async for event in sub_agent.run(prompt=prompt, system_prompt=system_prompt or None):
            # Forward the raw event to an optional caller-side observer
            # (e.g. the automation scheduler) BEFORE folding it into the
            # draft. Callers that don't need raw events simply leave
            # ``event_callback=None``.
            if event_callback is not None:
                try:
                    await event_callback(event)
                except Exception:
                    logger.warning("[sub_agent] event_callback raised", exc_info=True)
            if isinstance(event, TextDelta):
                text_buffer += event.text
                draft_content.append(event.text)
                if draft_segments and draft_segments[-1].get("kind") == "text":
                    draft_segments[-1]["text"] = (
                        str(draft_segments[-1].get("text") or "") + event.text
                    )
                else:
                    draft_segments.append({"kind": "text", "text": event.text})
                await _emit_live()
            elif isinstance(event, ThinkingDelta):
                _flush_text_buffer()
                thought = event.text.strip()
                if thought:
                    result_parts.append(f"### Thought\n{thought}\n")
                    draft_reasoning.append(event.text)
                    if draft_segments and draft_segments[-1].get("kind") == "thinking":
                        draft_segments[-1]["text"] = (
                            str(draft_segments[-1].get("text") or "") + event.text
                        )
                    else:
                        draft_segments.append({"kind": "thinking", "text": event.text})
                    await _emit_live()
            elif isinstance(event, ToolCallStart):
                _flush_text_buffer()
                result_parts.append(f"### Tool Start\n- id: `{event.id}`\n- name: `{event.name}`\n")
                tc_dict = {
                    "id": event.id,
                    "type": "function",
                    "function": {"name": event.name, "arguments": "{}"},
                }
                draft_tool_calls.append(tc_dict)
                draft_tool_id_to_idx[event.id] = len(draft_tool_calls) - 1
                draft_segments.append({"kind": "tool", "tool_id": event.id})
                await _emit_live()
            elif isinstance(event, ToolProgress):
                _flush_text_buffer()
                result_parts.append(f"### Tool Progress\n- id: `{event.id}`\n- name: `{event.tool_name}`\n- status: `{event.status}`\n")  # noqa: E501
                # Forward nested sub-agent messages so the frontend sees
                # live progress from sub-sub-agents all the way up.
                if progress_callback is not None and event.sub_agent_messages:
                    try:
                        await progress_callback(event.sub_agent_messages)
                    except Exception:
                        pass
                else:
                    await _emit_live()
            elif isinstance(event, ToolCallEnd):
                _flush_text_buffer()
                result_parts.append(f"### Tool End\n- id: `{event.id}`\n")
                await _emit_live()
            elif isinstance(event, ToolResult):
                _flush_text_buffer()
                content = event.content.strip()
                if len(content) > 2000:
                    content = f"{content[:2000]}\n... (truncated)"
                result_parts.append(
                    f"### Tool Result\n- id: `{event.id}`\n- error: `{'yes' if event.is_error else 'no'}`\n\n```text\n{content}\n```\n"  # noqa: E501
                )
                # Tool results are already persisted into sub_agent.session.messages
                # by the sub-agent's own loop. The snapshot builder picks them up
                # directly so we do NOT maintain a separate live_messages list.
                await _emit_live()
            elif isinstance(event, Reference):
                if event.reference:
                    sub_refs.append(event.reference)
            elif isinstance(event, Finish):
                _flush_text_buffer()
                await _emit_live()
                if event.reason == "error":
                    _save()
                    return {
                        "content": "Error: Sub-agent failed",
                        "messages": sub_agent.session.messages,
                        "session_id": saved_session_id,
                        "references": sub_refs,
                    }

        # Always unregister the child from the parent's active set on
        # every exit path (normal, error, or exception).  We wrap the
        # final save + return in try/finally so cancellation / exceptions
        # also trigger the unregister.
        try:
            _save()
            # Extract the sub-agent's final response: prefer text content, fall back
            # to reasoning content, then to "Tool calls executed" if only tools ran.
            final_text = ""
            for msg in reversed(sub_agent.session.messages):
                if msg.get("role") != "assistant":
                    continue
                txt = str(msg.get("content") or "")
                if txt.strip():
                    final_text = txt
                    break
                # No text content -- check reasoning
                rsn = str(msg.get("reasoning_content") or "")
                if rsn.strip():
                    final_text = f"[Thinking]\n{rsn}"
                    break
                # No text or reasoning -- check tool calls
                tcs = msg.get("tool_calls") or []
                if tcs:
                    names = [tc.get("function", {}).get("name", "?") for tc in tcs]
                    final_text = f"[Tool calls executed: {', '.join(names)}]"
                    break
            logger.info("[sub_agent] done session_id=%s final_len=%d msgs=%d",
                         saved_session_id, len(final_text), len(sub_agent.session.messages))
            logger.info("[sub_agent] final_text=%.200s", final_text)
            return {
                "content": final_text or "No output from sub-agent",
                "messages": sub_agent.session.messages,
                "session_id": saved_session_id,
                "references": sub_refs,
            }
        finally:
            self._child_loops.discard(sub_agent.loop)
