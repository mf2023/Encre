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

import asyncio
import builtins
import contextlib
import json
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from encre.backend import create_backend
from encre.backends.base import BaseBackend, format_backend_error
from encre.codebase.document_manager import EncreDocumentManager
from encre.codebase.indexer import EncreCodeIndex
from encre.compact.engine import CompactEngine
from encre.compact.pipeline import CompactionPipeline
from encre.config import EncreConfig
from encre.evolution.config import EvolutionConfig
from encre.feedback.learner import EncreFeedbackLearner
from encre.git.repo import EncreGitRepo
from encre.hooks.system import EncreHookSystem
from encre.logging_config import get_logger
from encre.memdir.system import EncreMemorySystem
from encre.profile.system import EncreProfileSystem
from encre.prompts.base import EncrePromptTemplate
from encre.prompts.classifier import classify_intents
from encre.recovery import ErrorRecoveryEngine, RetryableExecutor
from encre.loop_stability import (
    BudgetState,
    SteerQueue,
    WithheldError,
    _detect_requirement_change,
    build_empty_retry_message,
    build_grace_message,
    build_auto_continue_message,
    build_delegation_guidance,
    build_steer_injection,
    build_thinking_prefill,
    build_tombstone_messages,
    build_truncated_retry_message,
    check_interrupt,
    check_token_pressure,
    classify_error,
    is_empty_response,
    is_truncated_tool_call,
    repair_messages,
    should_post_tool_compact,
)
from encre.recovery_loop import (
    MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
    ESCALATED_MAX_TOKENS,
    build_fallback_system_message,
    build_max_tokens_recovery_message,
    build_slot_escalation_message,
    can_fallback,
    is_context_overflow,
    is_prompt_too_long_error,
    is_rate_limit_or_overload,
    is_withheld_max_output_tokens,
    yield_missing_tool_result_blocks,
)
from encre.rollback import EncreRollbackGit
from encre.tools.builtin._terminal_manager import TerminalSessionManager
from encre.rules.loader import RulesLoader
from encre.safety import EncreSafetyEngine
from encre.session import EncreSession
from encre.skills.registry import EncreSkillRegistry
from encre.soul.system import EncreSoulSystem
from encre.telemetry import EncreTelemetry
from encre.thinking.config import resolve_thinking_config
from encre.tools.discovery import ToolDiscovery
from encre.tools.registry import ToolRegistry
from encre.tracing import (
    maybe_get_tracer,
    setup_tracing,
    trace_llm_call,
    trace_tool_call,
)
from encre.utils.tokens import count_message_tokens, estimate_tokens
from encre.utils.types import (
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
    create_system_message,
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

from encre.loop_state.state import LoopState
from encre.loop_state.transition import TurnTransition
from encre.loop_error import ErrorOrchestrator, RecoveryAction, PostStreamAction
from encre.errors import classify_error_code, get_error_metadata, ErrorCode

logger = get_logger(__name__)

_WRITE_TOOL_NAMES = {"file_write", "file_edit", "write_file", "writeFile", "apply_patch"}
_PROMPT_CACHE_TTL_SECONDS = 30.0
_TASK_STAGES = ("discover", "plan", "execute", "verify", "report")
_STUCK_LOOP_THRESHOLD = 6
_SUMMARY_INTERVAL_TURNS = 3

# Max concurrency-safe tools executed in parallel per turn. Mirrors Claude
# Code's getMaxToolUseConcurrency() default of 10 (CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY).
# Overridable via the same-spirited ENCRE_MAX_TOOL_USE_CONCURRENCY env var.
_MAX_TOOL_CONCURRENCY = max(1, int(os.environ.get("ENCRE_MAX_TOOL_USE_CONCURRENCY", "10") or "10"))

# Master switch for Encre's self-modification "evolution" layer (learner/reflex/
# meta/advisor guidance injected into the request each turn, plus the post-turn
# evolution pipeline). Disabled to match Claude Code's clean execution cadence.
# Set ENCRE_EVOLUTION=1 to re-enable.
_EVOLUTION_ENABLED = os.environ.get("ENCRE_EVOLUTION", "0") == "1"
_WORKING_SET_ARTIFACT_LIMIT = 8
_WORKING_SET_REFERENCE_LIMIT = 8
_WORKING_SET_TOOL_LIMIT = 12

# ── Context overflow detection (reactive compact) ──────────────
_CONTEXT_OVERFLOW_PATTERN = re.compile(
    r"(?:context|overflow|too\s+large|too\s+long|prompt|input\s+length|max_tokens)", re.IGNORECASE
)

# ── Context overflow detection ────────────────────────────────────────
# Legacy local re-export of the authoritative impl in encre.recovery_loop.
# Used by this module for backward compatibility; new code should import
# is_context_overflow directly from encre.recovery_loop.
_is_context_overflow = is_context_overflow


def _spillover_dir(session_id: str) -> str | None:
    """Return the directory for spillover files for *session_id*, creating it.

    Spillover lets a tool result larger than the context budget keep its full
    content on disk (so the agent can retrieve it later) instead of losing it
    to truncation.  Returns None when the data dir is unavailable so callers
    fall back to plain truncation.
    """
    try:
        from encre.config import get_data_dir
        import pathlib
        d = get_data_dir() / "spillover" / (session_id or "default")
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
    except Exception:
        return None


def _apply_result_budget(
    result: str,
    tool: Any,
    max_chars: int = 100_000,
    context_ratio: float = 1.0,
    session_id: str = "",
    tool_name: str = "",
) -> str:
    """Truncate a tool result if it exceeds the tool's size budget.

    Each tool can declare ``max_result_size_chars``.  The default is
    100 000 characters (≈ 25 000 tokens).  Results beyond that are
    truncated with a count of removed characters.
    """
    budget = getattr(tool, "max_result_size_chars", max_chars) or max_chars
    if context_ratio < 0.5:
        # Context is nearly full: scale the budget down so the result leaves
        # more room, but never below a minimum usable preview size.
        scaled = int(budget * context_ratio)
        budget = max(500, min(budget, scaled))
    if len(result) <= budget:
        return result
    excess = len(result) - budget
    spillover_path = None
    if session_id:
        import hashlib
        spillover_dir = _spillover_dir(session_id)
        if spillover_dir:
            digest = hashlib.sha1(result.encode("utf-8", errors="replace")).hexdigest()[:16]
            label = (tool_name or "tool").replace("/", "_")[:32]
            fname = f"spillover_{label}_{digest}.txt"
            import os as _os
            fpath = _os.path.join(spillover_dir, fname)
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(result)
                spillover_path = fpath
            except Exception:
                spillover_path = None
    preview = result[:1000]
    if spillover_path:
        return (
            preview
            + f"\n... (truncated {excess} characters; full output saved to {spillover_path})"
        )
    return result[:budget] + f"\n... (truncated {excess} characters)"


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
        r"Applied \d+ edit\(s\) to (.+?)\.\s*\n",  # file_edit -- \n forces lazy match past file extension periods
        r"Wrote .+ to (.+)",
    ]:
        m = re.search(pattern, result, re.IGNORECASE)
        if m:
            path = m.group(1).strip()
            if os.path.isabs(path) and os.path.exists(path):
                return path
    return None


def _extract_diff_text(_tool_name: str, result: str) -> str:
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


def _turn_to_message_index(
    messages: list[dict[str, Any]], target_turn: int,
) -> int | None:
    """P1 helper: convert an absolute turn index to a message index.

    The loop tracks ``turn_count`` as the number of assistant turns so
    far; messages and turns are not 1:1.  This walks messages in order
    and returns the index of the *N*-th assistant message (or ``None``
    if the conversation has fewer turns than requested).
    """
    if target_turn <= 0:
        return 0
    seen = 0
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            seen += 1
            if seen == target_turn:
                return i
    return None


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


def _extract_write_target_paths(tool_name: str, args: dict[str, Any]) -> set[str]:
    """Return the normalised absolute file paths a write tool will modify.

    Used by the path-aware parallel grouping so two write tools touching
    *different* files can run concurrently (mirrors Hermes' ``_paths_overlap``
    check).  Returns an empty set for tools whose target paths cannot be
    statically determined (e.g. ``bash``), which keeps them sequential.
    """
    if tool_name not in _WRITE_TOOL_NAMES:
        return set()
    if tool_name == "apply_patch":
        paths: set[str] = set()
        for fd in (args.get("files") or []):
            if isinstance(fd, dict):
                for key in ("old_path", "new_path"):
                    p = fd.get(key) or ""
                    if p:
                        try:
                            paths.add(os.path.abspath(p))
                        except Exception:
                            paths.add(p)
        return paths
    fp = args.get("file_path") or args.get("path") or ""
    if not fp:
        return set()
    try:
        return {os.path.abspath(fp)}
    except Exception:
        return {fp}


def _split_writes_by_path_conflict(
    write_tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition write tools into (parallel-safe, sequential) by path overlap.

    A write tool is parallel-safe only when none of its target paths overlap
    with any other write tool's paths in the same turn.  Tools whose paths
    cannot be determined (empty set -- e.g. bash, or a write tool missing its
    path arg) are always sequential to avoid racing on an unknown file.
    """
    path_map: dict[int, set[str]] = {
        i: _extract_write_target_paths(p["name"], p.get("args", {}))
        for i, p in enumerate(write_tools)
    }
    parallel: list[dict[str, Any]] = []
    sequential: list[dict[str, Any]] = []
    for i, p in enumerate(write_tools):
        my_paths = path_map[i]
        if not my_paths:
            sequential.append(p)
            continue
        conflict = any(
            bool(my_paths & path_map[j])
            for j in range(len(write_tools))
            if j != i
        )
        (sequential if conflict else parallel).append(p)
    return parallel, sequential


async def _try_lsp_diagnostics(file_path: str) -> str:
    """Run LSP diagnostics on *file_path* and return a formatted summary.

    Returns an empty string when LSP is unavailable (no server started for
    this workspace, unsupported language, or any error) so the caller falls
    back to the generic VERIFY reminder.  Mirrors Hermes' pattern of piping
    real language-server diagnostics into write-tool results so the model
    sees type errors immediately without a separate tool call.
    """
    try:
        from encre.tools.builtin.lsp import _get_manager
        mgr = _get_manager()
        if not getattr(mgr, "_workspace", ""):
            return ""
        diags = await mgr.get_diagnostics(file_path)
        if not diags:
            return ""
        sev_name = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
        lines = [f"\n\n[LSP Diagnostics for {file_path}] ({len(diags)})"]
        for d in diags[:20]:
            sev = sev_name.get(d.severity, "Issue")
            raw_msg = (d.message or "").strip()
            msg = (raw_msg.splitlines()[0][:200] if raw_msg else "")
            loc = ""
            try:
                if d.range and d.range.start is not None:
                    loc = f" line {d.range.start.line}:{d.range.start.character}"
            except Exception:
                pass
            src = f" ({d.source})" if d.source else ""
            lines.append(f"  [{sev}]{loc}{src} {msg}")
        return "\n".join(lines)
    except Exception:
        return ""


def _is_reference_tool(tool_name: str) -> bool:
    """Memory, MCP, and web tools generate sidebar references."""
    name = tool_name.lower()
    if tool_name.startswith("mcp__") or name.startswith("memory_") or name.startswith("web_"):
        return True
    return False


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


def _infer_tool_semantics(tool_name: str, tool: Any) -> dict[str, str]:
    semantic_type = str(getattr(tool, "semantic_type", "") or "").strip().lower()
    cost_level = str(getattr(tool, "cost_level", "") or "").strip().lower()
    retryability = str(getattr(tool, "retryability", "") or "").strip().lower()
    safe_fallback = str(getattr(tool, "safe_fallback", "") or "").strip()
    lowered = tool_name.lower()

    if not semantic_type or semantic_type == "general":
        if lowered in _WRITE_TOOL_NAMES or "write" in lowered or "edit" in lowered or "patch" in lowered or "delete" in lowered:
            semantic_type = "write"
        elif "read" in lowered or "cat" in lowered or "view" in lowered:
            semantic_type = "read"
        elif "search" in lowered or "grep" in lowered or "glob" in lowered or "find" in lowered:
            semantic_type = "search"
        elif lowered in {"bash", "shell", "execute", "run"}:
            semantic_type = "exec"
        elif lowered.startswith("web_") or lowered in {"browser", "rest_client"}:
            semantic_type = "network"
        elif lowered in {"agent", "workflow"}:
            semantic_type = "orchestrate"
        else:
            semantic_type = "general"

    if not cost_level:
        if semantic_type in {"search", "read"}:
            cost_level = "low"
        elif semantic_type in {"write", "exec", "network", "orchestrate"}:
            cost_level = "high"
        else:
            cost_level = "medium"

    if not retryability:
        if semantic_type in {"search", "read", "network"}:
            retryability = "auto"
        elif semantic_type in {"write", "exec", "orchestrate"}:
            retryability = "guarded"
        else:
            retryability = "manual"

    if not safe_fallback:
        fallback_map = {
            "write": "Read the target file again, narrow the scope, and propose a smaller change.",
            "exec": "Inspect the environment and command preconditions before retrying.",
            "search": "Refine the query or switch to a more specific file/path filter.",
            "network": "Use local context first and only retry if an external lookup is necessary.",
            "orchestrate": "Summarize the sub-task and continue in the main thread if delegation is unnecessary.",
        }
        safe_fallback = fallback_map.get(semantic_type, "Gather more context before retrying.")

    return {
        "semantic_type": semantic_type,
        "cost_level": cost_level,
        "retryability": retryability,
        "safe_fallback": safe_fallback,
    }


def _tool_retry_allowed(p: dict[str, Any], repeated_signatures: list[tuple[str, ...]]) -> bool:
    semantics = p.get("semantics", {}) or {}
    retryability = str(semantics.get("retryability", "auto"))
    if retryability == "auto":
        return True
    # The guard only targets genuine *repeats*: a first-time invocation (no
    # prior history, or a signature that never appeared before) is always
    # allowed.  Blocking the first call would make high-value tools such as
    # `agent` (retryability="manual") unusable.
    if not repeated_signatures:
        return True
    sig = f"{p.get('name', '')}:{p.get('args_summary', '')[:80]}"
    if retryability == "manual":
        # Manual tools must not silently auto-repeat: block only when the same
        # call was just issued in the immediately preceding turn (a tight
        # re-spawn loop), not for distinct delegations across the session.
        last = repeated_signatures[-1]
        return not any(sig == item for item in last)
    if retryability == "guarded":
        last = repeated_signatures[-1]
        if any(sig == item for item in last):
            return False
    return True


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
        # Per-session cache of auto-activated tool skills (tool_name -> body).
        # Populated after each tool run; rendered into the next turn's system
        # prompt so the model sees detailed usage guidance for tools it has
        # already used.  Idempotent and de-duplicated by tool name.
        self._active_tool_skills: dict[str, str] = {}
        self._active_doc_skills: dict[str, str] = {}
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
        self.reviewer = evo.reviewer
        self.event_store = evo.event_store
        self.recovery_engine = recovery or ErrorRecoveryEngine()
        # Wire event store to hook system for automatic lifecycle recording
        if self.event_store is not None and evo.event_store_enabled:
            self.event_store.wire_hooks(self.hook_system)
        # Cached microcompact state (per-session).  Lazily initialised on the
        # first turn when the backend is Anthropic so non-Anthropic backends
        # pay zero cost.  Mirrors Claude Code's ``CachedMCState``.
        self._cache_edits_state: Any = None
        self.feedback = feedback
        self._code_index: EncreCodeIndex | None = code_index
        self._pending_code_scan: EncreCodeIndex | None = None

        # Context renderer for tracking what changed between turns.
        from encre.context.renderer import ContextRenderer
        self._ctx_renderer = ContextRenderer()
        # Auto-resolve thinking config based on model if not explicitly set.
        # Per-model config takes precedence over the global config.
        active_model = config.get_active_model()
        self._thinking_config = active_model.thinking_config or config.thinking_config
        if self._thinking_config is None:
            self._thinking_config = resolve_thinking_config(
                None, config.model, backend_type=config.backend_type
            )
        self.backend: BaseBackend | None = create_backend(
            config.backend_type,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            models=config.models,
            thinking_config=self._thinking_config,
            **config.backend_kwargs,
        )
        self.safety = safety or EncreSafetyEngine(config)
        self.compact_engine = CompactEngine()
        self._compaction_pipeline = CompactionPipeline()
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
        # Plan-mode state. ``plan_mode_active`` is a *derived* read-only
        # property (True iff ``config.slash_command_mode == "plan"``) so the
        # boolean flag can never drift out of sync with the string mode the
        # rest of the system reads.  When plan mode is on, write-class tools
        # (``file_write``/``file_edit``/``apply_patch``) are NOT executed
        # directly.  Instead the loop builds a preview (diff/command
        # summary), emits a ``PlanProposal`` event, and waits for the user
        # to approve or reject via ``approve_plan``/``reject_plan`` before
        # continuing.  This gives desktop UI a real "plan-first" workflow
        # that matches Claude Code's plan mode.
        # All mode transitions go through :meth:`set_mode`, which keeps the
        # ``config.slash_command_mode`` string, ``session.metadata`` mirror,
        # and the derived ``plan_mode_active`` flag consistent atomically.
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
        # Whether any compaction (synchronous or background) replaced messages
        # during the current turn.  The Finish event carries this flag so the
        # frontend can request a message refresh and avoid "Message not found"
        # errors when rolling back to compacted-away messages.
        self._compacted_this_turn: bool = False
        # Streaming tool execution cache: maps client_id → precomputed execution result.
        # Populated in background during streaming when
        # ``enable_streaming_tool_execution`` is True.
        self._streaming_tool_results: dict[str, dict[str, Any]] = {}
        # Background sub-agent tracker for async/fire-and-forget mode.
        # Lazily initialised on first async sub-agent spawn.
        self._bg_sub_agents: Any = None
        # ── Recovery state ─────────────────────────────────────────
        # Unified error orchestrator — owns all recovery decisions and
        # counters.  Replaces the old RecoveryStateMachine + inline scalars.
        self._max_output_tokens_override: int | None = None
        self._error_orch: ErrorOrchestrator = ErrorOrchestrator()
        # Per-run loop state (initialized at start of each _run_impl).
        self._state: LoopState | None = None
        # Fallback model tracking: set when a fallback switch occurs.
        self._active_fallback_model: str = ""
        self._active_fallback_backend_type: str = ""
        # Reactive compact guard: set to True after first reactive compact per turn.
        self._has_attempted_reactive_compact: bool = False
        # System prompt cache: keyed by content hash so we skip rebuild when nothing changed.
        self._sys_prompt_cache: str | None = None
        self._sys_prompt_cache_key: Any = None
        # Spec engine: set externally by ws.py so the loop can parse specs
        # and enforce the approval gate in spec mode.
        self.spec_engine: Any = None
        # Steer queue for mid-conversation user instructions
        self._steer_queue: SteerQueue = SteerQueue()
        # Budget state for grace call support.  Restored from session metadata
        # so a restarted session resumes its accrued token budget instead of
        # resetting to zero (mirrors Claude Code's task_budget accrual across
        # compact boundaries / session restarts).
        self._budget_state: BudgetState = BudgetState.restore(
            self.session.metadata.get(BudgetState.META_KEY),
            fallback_max=getattr(self.config, "token_budget", 0),
        )
        # Thinking prefill toggle
        self._thinking_prefill_enabled: bool = getattr(
            self.config, "thinking_prefill_enabled", False
        )
        self.session.metadata.setdefault("task_stage", "discover")
        self.session.metadata.setdefault("task_stage_history", [])
        self.session.metadata.setdefault("working_set", {})
        self.session.metadata.setdefault("turn_summaries", [])
        self.session.metadata.setdefault("tool_semantics", {})
        self.session.metadata.setdefault("stuck_events", [])
        # P1: milestone summarisation state.  ``_milestone_last_turn`` is
        # the last turn_count at which we wrote a milestone; when the
        # current turn exceeds it by MILESTONE_INTERVAL we trigger a
        # fresh milestone write.
        self.session.metadata.setdefault("milestone_summaries", [])
        self._milestone_last_turn: int = -1

    def _cache_fresh(self, built_at: float, ttl: float = _PROMPT_CACHE_TTL_SECONDS) -> bool:
        return (time.time() - built_at) < ttl

    def _set_task_stage(self, stage: str, reason: str = "") -> None:
        if stage not in _TASK_STAGES:
            return
        prev = str(self.session.metadata.get("task_stage", "discover"))
        if prev == stage:
            return
        history = self.session.metadata.setdefault("task_stage_history", [])
        history.append({
            "from": prev,
            "to": stage,
            "reason": reason[:240],
            "turn": self.session.turn_count,
            "timestamp": time.time(),
        })
        self.session.metadata["task_stage"] = stage

    # ── P1 milestone summarisation ─────────────────────────────────────

    async def _maybe_write_milestone(
        self, context_msgs: list[dict[str, Any]],
    ) -> None:
        """Periodically snapshot the conversation into a small milestone.

        Strategy:
        - Trigger when ``turn_count - _milestone_last_turn >= MILESTONE_INTERVAL``
        - Slice the messages from the last milestone to now
        - Summarise that slice via the compact engine (cheap, since the
          slice is small)
        - Append the result to ``session.metadata["milestone_summaries"]``
          so the next full compact pass only needs to summarise
          ``messages[since_last_milestone:]``.
        - Cap the list at MILESTONE_MAX_ENTRIES to keep the metadata small.
        """
        from encre.compact.engine import MILESTONE_INTERVAL, MILESTONE_MAX_ENTRIES
        if MILESTONE_INTERVAL <= 0:
            return
        turn = self.session.turn_count
        if turn - self._milestone_last_turn < MILESTONE_INTERVAL:
            return
        start_turn = (
            max(0, turn - MILESTONE_INTERVAL)
            if self._milestone_last_turn < 0
            else self._milestone_last_turn
        )
        # Convert turn count to message index by counting assistant
        # messages from the end.  ``start_turn`` is an absolute turn
        # index; we approximate the message boundary.
        boundary = _turn_to_message_index(context_msgs, start_turn)
        if boundary is None or boundary >= len(context_msgs) - 2:
            # Nothing new to milestone
            self._milestone_last_turn = turn
            return
        slice_msgs = context_msgs[boundary:]
        if len(slice_msgs) < 4:
            self._milestone_last_turn = turn
            return
        try:
            summary = await self.compact_engine.compact(
                slice_msgs,
                backend=self.backend,
                turn_count=turn,
                enable_caching=self.config.enable_prompt_caching,
                        session_id=self.session.id or "",
            )
        except Exception as exc:
            logger.warning("[milestone] compact call failed: %s", exc)
            return
        if not summary:
            return
        # Pull the generated summary out of the compacted list (it's
        # marked is_compact_summary) and store just the text.
        summary_text = ""
        for m in summary:
            if m.get("is_compact_summary"):
                summary_text = str(m.get("content", ""))
                break
        if not summary_text:
            return
        entries = self.session.metadata.setdefault("milestone_summaries", [])
        entries.append({
            "from_turn": start_turn,
            "to_turn": turn,
            "text": summary_text[:8_000],
            "ts": time.time(),
        })
        if len(entries) > MILESTONE_MAX_ENTRIES:
            # Drop oldest; we only need recent context for the next compact.
            del entries[: len(entries) - MILESTONE_MAX_ENTRIES]
        self._milestone_last_turn = turn
        logger.info(
            "[milestone] wrote turn=%d slice=%d entries=%d",
            turn, len(slice_msgs), len(entries),
        )

    def _infer_task_stage(self, prompt: str, prepared: list[dict[str, Any]] | None = None) -> str:
        current = str(self.session.metadata.get("task_stage", "discover"))
        prompt_lower = (prompt or "").lower()
        prepared = prepared or []
        names = [str(p.get("name", "")).lower() for p in prepared]
        semantic_types = [str(p.get("semantics", {}).get("semantic_type", "")).lower() for p in prepared]

        if any(x in prompt_lower for x in ("summary", "report", "what did", "结果", "总结", "汇报")):
            return "report"
        if any(x in prompt_lower for x in ("plan", "方案", "设计", "spec", "步骤")):
            return "plan"
        if any(t in {"write", "exec"} for t in semantic_types) or any(n in _WRITE_TOOL_NAMES for n in names):
            return "execute"
        if any(x in prompt_lower for x in ("verify", "test", "check", "确认", "验证")) or any("test" in n or "lint" in n for n in names):
            return "verify"
        if any(t in {"read", "search", "network"} for t in semantic_types) or current == "discover":
            return "discover"
        return current

    def _summarize_args(self, args: dict[str, Any]) -> str:
        summary = _args_summary(args)
        return summary if len(summary) <= 180 else summary[:177] + "..."

    def _refresh_working_set(self, prompt: str, prepared: list[dict[str, Any]] | None = None) -> None:
        prepared = prepared or []
        tool_entries = []
        for p in prepared[-_WORKING_SET_TOOL_LIMIT:]:
            tool_entries.append({
                "name": p.get("name", ""),
                "semantic_type": p.get("semantics", {}).get("semantic_type", ""),
                "cost_level": p.get("semantics", {}).get("cost_level", ""),
                "args": self._summarize_args(p.get("args", {})),
            })
        artifacts = []
        for a in self.session.artifacts[-_WORKING_SET_ARTIFACT_LIMIT:]:
            artifacts.append({
                "path": a.get("path", ""),
                "tool": a.get("tool", ""),
                "name": a.get("name", ""),
            })
        references = []
        for r in self.session.references[-_WORKING_SET_REFERENCE_LIMIT:]:
            references.append({
                "tool": r.get("tool", ""),
                "summary": r.get("summary", ""),
            })
        self.session.metadata["working_set"] = {
            "prompt": (prompt or "")[:500],
            "stage": self.session.metadata.get("task_stage", "discover"),
            "tools": tool_entries,
            "artifacts": artifacts,
            "references": references,
            "plan_items": self.session.plan_items[-10:],
            "updated_at": time.time(),
        }

    def _build_working_set_prompt(self) -> str:
        ws = self.session.metadata.get("working_set") or {}
        if not ws:
            return ""
        lines = ["## Current Task State"]
        lines.append(f"Stage: {ws.get('stage', 'discover')}")
        prompt = str(ws.get("prompt", "")).strip()
        if prompt:
            lines.append(f"Current objective: {prompt[:260]}")
        plan_items = ws.get("plan_items") or []
        if plan_items:
            lines.append("Plan:")
            for item in plan_items[:6]:
                lines.append(f"- [{item.get('status', 'pending')}] {item.get('text', '')}")
        tools = ws.get("tools") or []
        if tools:
            lines.append("Recent tools:")
            for t in tools[:8]:
                lines.append(f"- {t.get('name')} ({t.get('semantic_type')}, {t.get('cost_level')}): {t.get('args')}")
        artifacts = ws.get("artifacts") or []
        if artifacts:
            lines.append("Touched files:")
            for a in artifacts[:6]:
                lines.append(f"- {a.get('path')}")
        references = ws.get("references") or []
        if references:
            lines.append("Recent external references:")
            for r in references[:6]:
                lines.append(f"- {r.get('summary')}")
        return "\n".join(lines)

    def _maybe_record_turn_summary(
        self,
        prompt: str,
        prepared: list[dict[str, Any]],
        tool_outcomes: list[dict[str, Any]],
    ) -> None:
        if self.session.turn_count == 0:
            return
        if self.session.turn_count % _SUMMARY_INTERVAL_TURNS != 0 and not any(r.get("is_error") for r in tool_outcomes):
            return
        artifacts = [a.get("path", "") for a in self.session.artifacts[-4:]]
        summary = {
            "turn": self.session.turn_count,
            "stage": self.session.metadata.get("task_stage", "discover"),
            "goal": prompt[:220],
            "tools": [p.get("name", "") for p in prepared[:8]],
            "errors": [r.get("tool_name", "") for r in tool_outcomes if r.get("is_error")][:6],
            "artifacts": artifacts,
            "timestamp": time.time(),
        }
        summaries = self.session.metadata.setdefault("turn_summaries", [])
        summaries.append(summary)
        if len(summaries) > 30:
            del summaries[:-30]

    def _build_turn_summary_prompt(self) -> str:
        summaries = self.session.metadata.get("turn_summaries") or []
        if not summaries:
            return ""
        lines = ["## Prior Turn Summaries"]
        for entry in summaries[-5:]:
            tools = ", ".join(entry.get("tools", [])[:5]) or "none"
            errors = ", ".join(entry.get("errors", [])[:4]) or "none"
            files = ", ".join(entry.get("artifacts", [])[:3]) or "none"
            lines.append(
                f"- Turn {entry.get('turn')}: stage={entry.get('stage')} | tools={tools} | errors={errors} | files={files}"
            )
        return "\n".join(lines)

    def _build_stage_prompt(self) -> str:
        stage = str(self.session.metadata.get("task_stage", "discover"))
        guidance = {
            "discover": "Collect missing facts first. Prefer read/search tools. Do not edit until the target is clear.",
            "plan": "State the intended sequence of work and keep changes scoped. Avoid premature execution.",
            "execute": "Make the smallest effective change. Prefer one concrete action over repeated searching.",
            "verify": "Validate with reads, tests, or checks. Look for regressions and mismatches with the plan.",
            "report": "Summarize outcomes, touched files, verification evidence, and remaining risks.",
        }
        # NOTE: this is an internal WORK PHASE, not a user-facing "mode".
        # The user-visible mode is the slash-command mode (plan/spec/normal)
        # declared in the Slash Commands block.  Keep the wording distinct so
        # the model never confuses "phase" with "mode" when asked which mode
        # it is in.
        return (
            f"## Work Phase (internal, not a user mode)\n"
            f"Current work phase: {stage}\n"
            f"Guidance: {guidance.get(stage, '')}\n"
            f"This is an internal scheduling hint. It is NOT a mode. "
            f"When asked which mode you are in, answer based on the "
            f"Slash Commands / mode block, not this phase."
        )

    def _should_delegate_sub_agent(self, prompt: str, prepared: list[dict[str, Any]]) -> tuple[bool, str, str]:
        if self.sub_agent_depth > 0:
            return False, "", ""
        prompt_lower = (prompt or "").lower()
        stage = str(self.session.metadata.get("task_stage", "discover"))
        tool_count = len(prepared)
        search_count = sum(1 for p in prepared if p.get("semantics", {}).get("semantic_type") in {"search", "read", "network"})
        write_count = sum(1 for p in prepared if p.get("semantics", {}).get("semantic_type") in {"write", "exec"})

        if stage == "discover" and (search_count >= 3 or any(x in prompt_lower for x in ("compare", "investigate", "research", "分析", "调研"))):
            return True, "researcher", "parallel research would reduce repeated discovery turns"
        if stage == "execute" and write_count >= 2 and tool_count >= 4:
            return True, "executor", "execution has become multi-step and benefits from a focused implementer"
        if stage in {"verify", "report"} or any(x in prompt_lower for x in ("review", "audit", "check regression", "审查", "复核")):
            return True, "critic", "a reviewer sub-agent can inspect regressions and residual risks"
        should_delegate, reason = self.meta.should_delegate(prompt)
        if should_delegate:
            return True, "researcher", reason
        return False, "", ""

    async def _maybe_run_advisor_sub_agent(self, prompt: str, prepared: list[dict[str, Any]]) -> str:
        should_delegate, delegate, reason = self._should_delegate_sub_agent(prompt, prepared)
        if not should_delegate or not delegate:
            return ""
        try:
            role = next((sa for sa in getattr(self.config, "sub_agents", []) if str(sa.name).lower() == delegate.lower()), None)
        except Exception:
            role = None
        if role is None:
            return ""
        advisor_prompt = (
            f"Parent task: {prompt}\n\n"
            f"Current work phase: {self.session.metadata.get('task_stage', 'discover')}\n"
            f"Reason for delegation: {reason}\n\n"
            "Return only concise guidance for the parent agent:\n"
            "1. What facts matter most now\n"
            "2. What next step should be taken\n"
            "3. What to avoid repeating\n"
        )
        try:
            result = await self._run_sub_agent(
                prompt=advisor_prompt,
                system_prompt=role.system_prompt or "",
                max_turns=2,
                tool_policy=role.tool_policy or "all",
            )
            content = str(result.get("content", "") or "").strip()
            if content:
                history = self.session.metadata.setdefault("delegate_history", [])
                history.append({
                    "delegate": delegate,
                    "reason": reason,
                    "turn": self.session.turn_count,
                    "timestamp": time.time(),
                })
                if len(history) > 20:
                    del history[:-20]
                self.meta.record_delegation(prompt, delegate, True)
                return content[:1500]
        except Exception:
            logger.warning("[delegate] advisor sub-agent failed", exc_info=True)
            self.meta.record_delegation(prompt, delegate, False)
        return ""

    def _build_stuck_recovery_prompt(self) -> str:
        stuck_events = self.session.metadata.get("stuck_events") or []
        if not stuck_events:
            return ""
        latest = stuck_events[-1]
        lines = ["## Stuck Recovery"]
        lines.append("You are repeating similar tool calls without enough new information.")
        lines.append(f"Repeated signature: {latest.get('signature', '')}")
        lines.append("Before calling another tool, do all of the following:")
        lines.append("1. State what is already known.")
        lines.append("2. State the smallest missing fact.")
        lines.append("3. Choose one next action that differs from the repeated loop.")
        lines.append("4. Prefer reading existing artifacts or summarizing rather than repeating the same call.")
        return "\n".join(lines)

    def _record_stuck_event(self, signature: tuple[str, ...]) -> None:
        stuck = self.session.metadata.setdefault("stuck_events", [])
        stuck.append({
            "turn": self.session.turn_count,
            "signature": " | ".join(signature),
            "timestamp": time.time(),
        })
        if len(stuck) > 20:
            del stuck[:-20]

    async def aclose(self) -> None:
        """Release backend resources (httpx clients, model memory, etc.)."""
        if self.backend is not None:
            try:
                await self.backend.aclose()
            except Exception as e:
                logger.warning(f"Error closing backend: {e}", extra={"backend": type(self.backend).__name__})

    async def _wait_for_permission_decision(self, tool_name: str) -> bool:
        """Wait for a permission decision or cancel signal.

        Returns True only when the user explicitly allows the request.
        Cancellation is treated as denial so the loop never leaves an
        unresolved permission request behind.  Never times out — the
        user must explicitly Allow or Deny before the tool proceeds.
        """
        if self._permission_event is None:
            return False

        permission_waiter = asyncio.create_task(self._permission_event.wait())
        cancel_waiter = asyncio.create_task(self._cancel_event.wait())

        async def _drain(tasks: list[asyncio.Task[Any]]) -> None:
            for task in tasks:
                if task.done():
                    continue
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

        try:
            done, pending = await asyncio.wait(
                [permission_waiter, cancel_waiter],
                return_when=asyncio.FIRST_COMPLETED,
            )
            await _drain(pending)

            if cancel_waiter in done:
                logger.info(
                    "Permission request cancelled for tool '%s'", tool_name,
                )
                return False
            return self._permission_decision
        except asyncio.CancelledError:
            await _drain([permission_waiter, cancel_waiter])
            raise

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
                logger.debug("record_permission_decision failed: {_e}")
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
    #
    # The three modes -- ``""`` (normal), ``"plan"``, ``"spec"`` -- are
    # all funnelled through :meth:`set_mode`, the single transition
    # entry point, so ``config.slash_command_mode`` (string),
    # ``session.metadata`` mirror, and the derived
    # ``plan_mode_active`` flag can never disagree.  ``plan_mode_active``
    # is ``True`` only for ``"plan"``; ``"spec"`` is a separate strict
    # mode that does NOT intercept write tools (it enforces its own
    # approval gate via ``self.spec_engine`` instead).

    @property
    def plan_mode_active(self) -> bool:
        """Whether write-class tools are currently intercepted as proposals.

        Derived from ``config.slash_command_mode`` so the flag and the
        mode string the rest of the system consults can never diverge.
        Only ``"plan"`` activates tool interception; ``"spec"`` does not.
        """
        return getattr(self.config, "slash_command_mode", "") == "plan"

    _VALID_MODES: tuple[str, ...] = ("", "plan", "spec")

    def set_mode(self, mode: str) -> None:
        """Switch the persistent slash-command mode.

        ``mode`` must be one of ``""`` (normal), ``"plan"``, or
        ``"spec"``; any other value is normalised to ``""``.  This is
        the *only* place that mutates mode state: it keeps
        ``config.slash_command_mode``, ``session.metadata`` mirror
        (``slash_command_mode`` string + the legacy ``plan_mode_active``
        bool for backward compatibility), and the derived
        ``plan_mode_active`` property consistent atomically.  Leaving
        plan mode also wakes any waiter parked on a pending plan
        proposal so the loop can decide what to do with it.
        """
        mode = mode if mode in self._VALID_MODES else ""
        prev = getattr(self.config, "slash_command_mode", "")
        self.config.slash_command_mode = mode
        # Mirror into session metadata so the mode survives a session
        # reload / reconnect.  ``""`` clears the persistent slot.
        if mode:
            self.session.metadata["slash_command_mode"] = mode
        else:
            self.session.metadata.pop("slash_command_mode", None)
        # Legacy bool kept for external readers / persisted sessions.
        self.session.metadata["plan_mode_active"] = (mode == "plan")
        # Leaving plan mode must unblock any waiter parked on a
        # pending plan proposal so it does not hang forever.
        if prev == "plan" and mode != "plan" and self._plan_event is not None:
            self._plan_event.set()

    def enter_plan_mode(self, reason: str = "") -> PlanModeChanged:
        """Switch the loop into plan mode.

        Subsequent write-class tools will be intercepted and emitted
        as ``PlanProposal`` events until ``exit_plan_mode`` is called.
        """
        self.set_mode("plan")
        return create_plan_mode_changed(True, reason=reason)

    def exit_plan_mode(self, reason: str = "") -> PlanModeChanged:
        """Leave plan mode. Pending proposals remain in the queue."""
        self.set_mode("")
        # Wake any waiters so the loop can decide what to do with the
        # remaining queued proposals.
        if self._plan_event is not None:
            self._plan_event.set()
        return create_plan_mode_changed(False, reason=reason)

    # ── Active command API ────────────────────────────────────────────
    #
    # A slash *command* (built-in action or user-defined ``*.md`` command)
    # is a sticky prompt injection that is NOT a mode: it does not intercept
    # write tools and does not run the spec approval gate.  Once activated
    # it stays in effect across turns (its ``command_instructions`` block is
    # re-injected on every run) until explicitly cleared.  This mirrors the
    # persistence model of :meth:`set_mode` so a command survives session
    # reload / reconnect / restart: ``config.active_command`` is the
    # in-memory mirror, ``session.metadata["active_command"]`` is the
    # on-disk source of truth.  A command and a mode (plan/spec) may be
    # active at the same time -- they are independent slots.

    def set_command(self, name: str, prompt: str, icon: str = "",
                    title: str = "") -> None:
        """Activate (or replace) the persistent slash command.

        Stores ``{name, prompt, icon, title}`` in both
        ``config.active_command`` and ``session.metadata["active_command"]``
        so the command's instructions are re-injected every turn until
        :meth:`clear_command` is called.  An empty ``name`` clears the slot.
        """
        name = (name or "").strip()
        if not name:
            self.clear_command()
            return
        payload = {
            "name": name,
            "prompt": prompt or "",
            "icon": icon or "",
            "title": title or name,
        }
        self.config.active_command = payload
        self.session.metadata["active_command"] = payload

    def clear_command(self) -> None:
        """Deactivate the persistent slash command (no-op if none active)."""
        self.config.active_command = None
        self.session.metadata.pop("active_command", None)

    @property
    def active_command_name(self) -> str:
        """Name of the active slash command, or ``""`` if none is active."""
        cmd = getattr(self.config, "active_command", None)
        return cmd.get("name", "") if cmd else ""

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
                    added = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
                    removed = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))
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
                        original.replace(old_s, new_s, 1) if old_s and old_s in original else original
                    )
                if file_path or original or proposed:
                    diff_text = _native_diff(original or "", proposed or "")
                    added = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
                    removed = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))
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
            added = sum(1 for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
            removed = sum(1 for ln in patch.splitlines() if ln.startswith("-") and not ln.startswith("---"))
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
                f"Plan proposal '{proposal.proposal_id}' timed out after {timeout}s -- auto-rejecting",
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
        _client_id: str,
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
            logger.error("[run] backend.chat() timed out after %.0fs -- check API key / network", timeout)
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

    def _finalize_cancelled_turn(self) -> int:
        """Defense layer: close any half-finished tool_use in session state.

        After a cancel breaks out of the run loop, the last assistant
        message may declare tool_calls whose results were never written (the
        tool was cancelled before it ran). That orphan tool_use breaks the
        history sidebar, rollback, and the next API request. This scans the
        *persisted* session messages and synthesizes an error tombstone for
        every tool_call id lacking a matching tool_result, so the session
        history is always self-consistent -- not merely repaired at request
        time by the sanitize gateway.

        Returns the number of tombstones added. Idempotent: a second call on
        an already-closed history adds nothing.
        """
        msgs = self.session.messages
        if not msgs:
            return 0
        # Walk from the end; the only assistant whose tool_calls can be
        # unmatched is the last assistant with tool_calls (results, if any,
        # sit right after it).
        last_asst_idx = -1
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "assistant" and msgs[i].get("tool_calls"):
                last_asst_idx = i
                break
        if last_asst_idx < 0:
            return 0
        asst = msgs[last_asst_idx]
        declared = {
            tc.get("id", "")
            for tc in asst.get("tool_calls", [])
            if tc.get("id")
        }
        if not declared:
            return 0
        # Collect tool_result ids that immediately follow this assistant.
        have: set[str] = set()
        j = last_asst_idx + 1
        while j < len(msgs) and msgs[j].get("role") == "tool":
            tid = msgs[j].get("tool_call_id", "")
            if tid:
                have.add(tid)
            j += 1
        missing = declared - have
        if not missing:
            return 0
        tombstone = (
            "[Error: This tool call was cancelled before it completed. "
            "No result was produced.]"
        )
        added = 0
        for mid in sorted(missing):
            self.session.add_tool_result(mid, tombstone, is_error=True)
            added += 1
        if added:
            logger.info(
                "[run] finalized cancelled turn: %d tombstone(s) for orphan tool_use",
                added,
            )
        return added

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

    async def _collect_tool_skill(self, tool_name: str) -> None:
        """Activate the matching ``tool-<name>`` skill after a tool runs.

        Caches the body on the loop so subsequent turns surface detailed
        usage guidance (when to use / pitfalls / parameters) for tools the
        agent has already used.  Idempotent: re-calling for the same tool is
        a no-op, so it is safe to invoke from every post-tool code path.
        """
        if not self.skill_registry or not tool_name:
            return
        if tool_name in self._active_tool_skills:
            return
        skill_name = f"tool-{tool_name.replace('_', '-')}"
        skill = self.skill_registry.lookup(skill_name)
        if skill is None:
            return
        try:
            body = await self.skill_registry.activate(skill_name)
        except Exception:
            return
        if not body or body.startswith("Error: "):
            return
        self._active_tool_skills[tool_name] = body

    async def _collect_doc_skills(self, args: dict) -> None:
        """Auto-activate document skills whose ``when_to_use`` matches file
        extensions referenced in the tool arguments.  Only skills with
        ``auto_activate`` are eligible, so process skills (code-review,
        refactor, ...) never fire from a mere file reference."""
        if not self.skill_registry or not args:
            return
        paths = [str(v) for v in args.values() if isinstance(v, str)]
        if not paths:
            return
        try:
            names = await self.skill_registry.activate_for_paths(paths)
        except Exception:
            return
        for skill_name in names:
            if skill_name in self._active_doc_skills:
                continue
            try:
                body = await self.skill_registry.activate(
                    skill_name, "(referenced this session)"
                )
            except Exception:
                continue
            if not body or body.startswith("Error: "):
                continue
            self._active_doc_skills[skill_name] = body

    def _render_active_tool_skills(self) -> str:
        """Render accumulated tool-skill guidance for the system prompt."""
        if not self._active_tool_skills:
            return ""
        parts = [
            "## Tool Skills (auto-activated)",
            "",
            "Detailed usage guidance for tools already used this session:",
            "",
        ]
        for tool_name, body in self._active_tool_skills.items():
            parts.append(f"### tool-{tool_name.replace('_', '-')}")
            parts.append("")
            parts.append(body.strip())
            parts.append("")
        return "\n".join(parts).rstrip()

    def _render_active_doc_skills(self) -> str:
        """Render accumulated document-skill guidance for the system prompt."""
        if not self._active_doc_skills:
            return ""
        parts = [
            "## Document Skills (auto-activated)",
            "",
            "Domain guidance for file types referenced this session:",
            "",
        ]
        for skill_name, body in self._active_doc_skills.items():
            parts.append(f"### {skill_name}")
            parts.append("")
            parts.append(body.strip())
            parts.append("")
        return "\n".join(parts).rstrip()

    def _render_skill_catalogue(self) -> str:
        """Render the dynamic skill catalogue from the live registry.

        Replaces the hard-coded skill lists that used to live in the mode and
        specialty prompt blocks.  Scans ``self.skill_registry`` (which is itself
        populated by scanning the builtin skills directory) so newly added
        SKILL.md folders appear here automatically with no code change.

        Excludes ``tool-*`` skills (those are auto-injected tool-usage guidance,
        not user/model-invokable capabilities) and anything not user-invocable.
        """
        if not self.skill_registry:
            return ""
        skills = [
            s for s in self.skill_registry.list_all()
            if s.user_invocable and not s.name.startswith("tool-")
        ]
        if not skills:
            return ""
        # Group by prefix: "travel-flights" -> "travel"; standalone names -> "general".
        groups: dict[str, list[str]] = {}
        for s in sorted(skills, key=lambda x: x.name):
            prefix = s.name.split("-", 1)[0] if "-" in s.name else "general"
            groups.setdefault(prefix, []).append(
                f"- `/{s.name}`: {s.description.strip()}"
            )
        parts = [
            "Invoke a skill by typing `/skill-name <args>` (aliases also work), "
            "or call the `skill` tool with `name` (and optional `args`) to "
            "activate it yourself when the request matches a skill's purpose.",
            "Use a skill when the request matches its purpose.",
            "",
        ]
        for group_name in sorted(groups):
            parts.append(f"**{group_name}**")
            parts.extend(groups[group_name])
            parts.append("")
        return "\n".join(parts).rstrip()

    def _workspace_info(self) -> tuple[str, str, str]:
        """Return (workspace_root, workspace_name, project_summary) for the prompt builder.

        Returns ("", "", "") when not running inside a workspace.

        Cache key includes the git branch so that switching branches
        automatically refreshes the workspace context.
        """
        ws_path = getattr(self.config, "workspace", "") or ""
        if not ws_path or not os.path.isdir(ws_path):
            self._workspace_info_cache = None
            return "", "", ""
        cache_key = ws_path
        # Include the current git branch in the cache key so that switching
        # branches immediately invalidates the cached workspace context.
        try:
            repo = getattr(self, "git", None) or getattr(self, "_git", None)
            if repo is not None:
                branch = repo.get_branch() if hasattr(repo, "get_branch") else ""
                if branch:
                    cache_key = f"{ws_path}@{branch}"
        except Exception:
            pass
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
                if state.recent_commits:
                    summary_lines.append("  recent commits:")
                    for commit in state.recent_commits[:5]:
                        summary_lines.append(f"    {commit}")
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

    def _build_codebase_context_sync(self, _ws_path: str, idx: Any) -> str:
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
        lines.append("Use `codebase_search` to find relevant code, or `codebase_context` to view a specific file's details.")

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

    async def _pre_execute_in_background(
        self,
        client_id: str,
        tool_name: str,
        args_raw: str | dict[str, Any],
    ) -> None:
        """Pre-execute a tool in background during streaming tool execution.

        Called when ``enable_streaming_tool_execution`` is True and a
        ``BackendToolCall`` event arrives.  Only tools with auto-allow
        permission are pre-executed -- ``ask``/``deny`` tools and
        interactive tools (``question``, ``agent``) are handled by the
        normal post-streaming flow.

        Stores the raw execution result in ``self._streaming_tool_results``
        so the post-streaming execution phase can skip re-execution.
        """
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            logger.debug(
                "[pre_execute] skipping %s for %s -- arguments not yet valid JSON",
                tool_name, client_id,
            )
            return

        try:
            permission = await self.safety.check_tool_permission(tool_name, args)
            if permission.behavior != "allow":
                logger.debug(
                    "[pre_execute] skipping %s for %s -- permission=%s",
                    tool_name, client_id, permission.behavior,
                )
                return

            tool = self.tool_registry.get(tool_name)
            if tool is None:
                logger.warning(
                    "[pre_execute] unknown tool %s for %s", tool_name, client_id,
                )
                return

            # Streaming pre-execution applies to any tool with auto-approve
            # permission -- not just read-only ones.  Write tools that are
            # already allowed (bypass/auto mode) can start executing during
            # streaming just like read-only tools, and their results are
            # consumed in the post-streaming phase.  Tools that need user
            # approval (ask mode) are excluded by the permission check above.

            executor = RetryableExecutor(self.recovery_engine)
            state = await executor.execute(
                tool_name=tool_name,
                tool_args=args,
                execute_fn=lambda a: tool.execute(**a),
            )
            result = state.final_result
            sub_agent_messages = None
            sub_agent_references: list[dict[str, Any]] = []
            if isinstance(result, dict):
                sub_agent_messages = result.get("messages")
                sub_agent_references = result.get("references", [])
                result = str(result.get("content", ""))
            result = self.safety.validate_tool_output(tool_name, result)

            self._streaming_tool_results[client_id] = {
                "result": result,
                "is_error": not state.succeeded,
                "latency_ms": getattr(state, "latency_ms", 0.0),
                "recovery_history": list(getattr(state, "recovery_history", [])),
                "tool": tool,
                "sub_agent_messages": sub_agent_messages,
                "sub_agent_references": sub_agent_references,
            }
        except Exception as exc:
            logger.warning(
                "[pre_execute] %s for %s failed: %s", tool_name, client_id, exc,
                exc_info=True,
            )
            self._streaming_tool_results[client_id] = {
                "result": f"Tool pre-execution crashed: {type(exc).__name__}: {exc}",
                "is_error": True,
                "latency_ms": 0.0,
                "recovery_history": [],
                "tool": self.tool_registry.get(tool_name),
            }

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
            yield create_finish("error", error="No backend configured. Send a 'configure' message first.")
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
            # Defense layer (exception/asyncio-cancel path): even if the run
            # was torn down by an exception or hard task cancellation -- which
            # skips the normal convergence point in _run_impl -- close any
            # orphan tool_use so the persisted history stays self-consistent.
            # Idempotent with the _run_impl call, so a second pass adds nothing.
            try:
                self._finalize_cancelled_turn()
            except Exception:
                logger.warning("[run] finalize in finally failed", exc_info=True)
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
        # Reset per-run recovery state via the unified orchestrator.
        self._error_orch.reset_for_new_turn()
        # Initialize per-run loop state with transition history tracking.
        self._state = LoopState.create(turn_count=self.session.turn_count)
        # Log effective max_turns so we can diagnose unexpected session stops
        logger.info("[run] _run_impl start turn=%s max_turns=%s backend=%s model=%s",
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

        # Detect mid-conversation requirement changes: when the user's
        # latest message signals a shift in direction, invalidate the
        # cached user requirements summary so the next compact produces
        # a fresh one.  This prevents the model from anchoring to stale
        # requirements after the user says "actually, let's do X instead".
        _detected_change = _detect_requirement_change(prompt)
        if _detected_change and self.session.metadata.get("user_requirements_summary"):
            logger.info("[run] detected requirement change: %s -- clearing cached summary", _detected_change)
            self.session.metadata["user_requirements_summary"] = ""

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
                tuple(sorted(s.name for s in self.skill_registry.list_all()
                       if s.user_invocable and not s.name.startswith("tool-"))) if self.skill_registry else (),
                self.active_command_name,
            )
            if self._sys_prompt_cache is not None and self._sys_prompt_cache_key == _cache_key:
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
                    skill_summary=self._render_skill_catalogue(),
                    active_command=getattr(self.config, "active_command", None),
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
                skill_summary=self._render_skill_catalogue(),
                active_command=getattr(self.config, "active_command", None),
            )
            system_prompt = system_prompt + "\n\n" + built
        else:
            # Custom system_prompt provided but we are in normal mode.  The
            # custom prompt may be silent about the current mode, so the model
            # can infer it incorrectly from earlier plan/spec messages.  Force
            # an explicit normal-mode declaration at the top.
            system_prompt = "Current mode: NORMAL MODE. You are not in plan mode or spec mode. Ignore any mode claims in earlier messages; this system instruction is authoritative.\n\n" + system_prompt

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
                self._ctx_renderer.record("Codebase Index", codebase_ctx)
                system_prompt = system_prompt + "\n\n" + codebase_ctx

        # Prepend skill prompt to system prompt
        if skill_prompt:
            system_prompt = skill_prompt + system_prompt

        # Inject auto-activated tool skills: usage guidance for tools the
        # agent has already used this session (collected after each tool run).
        tool_skills_prompt = self._render_active_tool_skills()
        if tool_skills_prompt:
            system_prompt = tool_skills_prompt + "\n\n" + system_prompt

        doc_skills_prompt = self._render_active_doc_skills()
        if doc_skills_prompt:
            system_prompt = doc_skills_prompt + "\n\n" + system_prompt

        # Inject user requirements summary: a compact description of the
        # user's core goals extracted from the last compact summary.  Lives
        # in session metadata so it survives compaction.  Only for the main
        # agent (sub-agents get their own self-contained brief).
        if not _skip_enrichment:
            _req_summary = self.session.metadata.get("user_requirements_summary", "")
            if _req_summary:
                system_prompt = system_prompt + "\n\n" + _req_summary
            # P5: coordinator-style delegation guidance.  Steers the main
            # agent toward good delegation hygiene (understand -> delegate
            # self-contained briefs -> synthesise) on complex multi-step
            # work.  Mirrors Claude Code's coordinatorMode.ts.
            system_prompt = system_prompt + "\n\n" + build_delegation_guidance()

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
                        self._ctx_renderer.record("Memory", memory_prompt)
                        system_prompt = system_prompt + "\n\n" + memory_prompt
                except Exception:
                    pass

            # Inject relevant profile context -- only fields matching the user's query
            if self.profile_system is not None:
                try:
                    profile_prompt = self._build_profile_prompt(prompt)
                    if profile_prompt:
                        self._ctx_renderer.record("Profile", profile_prompt)
                        system_prompt = system_prompt + "\n\n" + profile_prompt
                except Exception:
                    pass

            # Inject agent soul / identity context (SOUL.md, IDENTITY.md, USER.md)
            if self.soul_system is not None:
                try:
                    soul_prompt = self._build_soul_prompt()
                    if soul_prompt:
                        self._ctx_renderer.record("Soul", soul_prompt)
                        system_prompt = system_prompt + "\n\n" + soul_prompt
                except Exception:
                    pass

            # Inject reference document context
            try:
                doc_prompt = self._build_document_context()
                if doc_prompt:
                    self._ctx_renderer.record("Documents", doc_prompt)
                    system_prompt = system_prompt + "\n\n" + doc_prompt
            except Exception:
                pass

        stage_prompt = self._build_stage_prompt()
        if stage_prompt:
            self._ctx_renderer.record("Task Stage", stage_prompt)
            system_prompt = system_prompt + "\n\n" + stage_prompt
        working_set_prompt = self._build_working_set_prompt()
        if working_set_prompt:
            self._ctx_renderer.record("Current Task", working_set_prompt)
            system_prompt = system_prompt + "\n\n" + working_set_prompt
        turn_summary_prompt = self._build_turn_summary_prompt()
        if turn_summary_prompt:
            self._ctx_renderer.record("Prior Turns", turn_summary_prompt)
            system_prompt = system_prompt + "\n\n" + turn_summary_prompt
        stuck_prompt = self._build_stuck_recovery_prompt()
        if stuck_prompt:
            self._ctx_renderer.record("Recovery", stuck_prompt)
            system_prompt = system_prompt + "\n\n" + stuck_prompt
        # Inject user rules (project-level + global)
        try:
            rules_prompt = self._build_rules_prompt()
            if rules_prompt:
                from encre.prompts.loader import PromptLoader
                _loader = PromptLoader()
                rules_block = _loader.load_with_context("rules", rules_content=rules_prompt)
                self._ctx_renderer.record("User Rules", rules_prompt)
                system_prompt = system_prompt + "\n\n" + rules_block
        except Exception:
            pass

        # Append context annotation: tells the model what changed since last turn
        ctx_annotation = self._ctx_renderer.build_annotation()
        if ctx_annotation:
            system_prompt = system_prompt + "\n\n" + ctx_annotation
        self._ctx_renderer.finalize_turn()

        # Update system message on every run so prompt blocks match current intents
        has_system = any(
            m.get("role") == "system" and m.get("branch_id", self.session.active_branch_id) == self.session.active_branch_id
            for m in self.session.messages
        )
        if has_system:
            for i, m in enumerate(self.session.messages):
                if m.get("role") == "system" and m.get("branch_id", self.session.active_branch_id) == self.session.active_branch_id:
                    self.session.messages[i] = {"role": "system", "content": system_prompt, "branch_id": self.session.active_branch_id}
                    self.session.mark_messages_dirty()
                    break
        else:
            self.session.messages.insert(0, {"role": "system", "content": system_prompt, "branch_id": self.session.active_branch_id})
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
                logger.info("[sub_agent] adding user message to session | prompt_len=%s | last_ctx_user_exists=%s",
                            len(prompt), last_ctx_user is not None)
                self.session.add_message("user", prompt)
                # Flush the user message to disk before entering the model
                # loop so a process kill here still leaves a resumable
                # transcript.  Mirrors Claude Code QueryEngine.ts:450-463.
                with contextlib.suppress(Exception):
                    await self.hook_system.emit_user_message_persisted(
                        self.session.id or ""
                    )

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
            self.session.replace_branch_messages(active_branch_id, self.compact_engine.sanitize(ctx_msgs))
            self._sanitized_branches.add(active_branch_id)
            ctx_msgs = self.session.get_context_messages()

        while not self.session.is_max_turns_reached() and not self._cancelled():
            turn_start = time.time()
            self._compacted_this_turn = False
            turn_events = 0
            self._streaming_tool_results.clear()
            _t_ts = time.time()
            await self.hook_system.emit_turn_start(self.session.turn_count)
            logger.info("[run] emit_turn_start done turn=%s (%.2fs)", self.session.turn_count, time.time() - _t_ts)
            _t_ck = time.time()
            self.session.checkpoint(f"turn_{self.session.turn_count}")
            await self.hook_system.emit_checkpoint(f"turn_{self.session.turn_count}")
            logger.info("[run] emit_checkpoint done turn=%s (%.2fs)", self.session.turn_count, time.time() - _t_ck)
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
                "[run] turn={turn} msgs={msgs} tokens={est_k}dk/{window_k}dk ({pct:.0f}%)",
                turn=self.session.turn_count, msgs=len(context_msgs),
                est_k=est_tokens // 1000, window_k=window // 1000,
                pct=100 * est_tokens / window if window else 0,
            )

            # ── Unified compression pipeline ───────────────────────────
            # Replaces the ad-hoc step1/step1a/step1b/step2 with a single
            # pipeline that runs stages in order: budget → collapse →
            # microcompact → snip → autocompact (async) → milestone.
            try:
                pipeline_report = await self._compaction_pipeline.run(
                    context_msgs,
                    backend=self.backend,
                    config=self.config,
                )
                if pipeline_report.messages is not context_msgs:
                    self.session.replace_branch_messages(
                        self.session.active_branch_id, pipeline_report.messages,
                    )
                    self._compacted_this_turn = True
                    ctx_msgs = self.session.get_context_messages()
                    context_msgs = ctx_msgs
                    est_tokens = count_message_tokens(context_msgs)

                # Log any stages that did work
                for s in pipeline_report.stages:
                    if s.did_work:
                        logger.info(
                            "[pipeline] %s turn=%d msgs %d->%d tokens %dk->%dk %s",
                            s.name, self.session.turn_count,
                            s.msgs_before, s.msgs_after,
                            s.tokens_before // 1000, s.tokens_after // 1000,
                            s.detail or "",
                        )

                # Async autocompact background task (if pipeline triggered it)
                if pipeline_report.needs_compact:
                    if self._compact_task and not self._compact_task.done():
                        self._compact_task.cancel()
                    logger.info(
                        "[compact] triggering turn=%d tokens=%dk window=%dk (async)",
                        self.session.turn_count, est_tokens // 1000, window // 1000,
                    )

                    async def _do_compact(context_msgs=context_msgs, est_tokens=est_tokens):
                        try:
                            self.session.set_compact_archive(context_msgs)
                            await self.hook_system.emit_pre_compact(len(context_msgs), est_tokens)
                            compacted = await self.compact_engine.compact(
                                context_msgs, backend=self.backend,
                                turn_count=self.session.turn_count,
                                system_prompt=system_prompt or "",
                                enable_caching=self.config.enable_prompt_caching,
                                session_id=self.session.id or "",
                            )
                            if compacted is not None:
                                self.session.replace_branch_messages(self.session.active_branch_id, compacted)
                                self._compacted_this_turn = True
                                self._update_user_requirements(compacted)
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

            except Exception as _pe:
                logger.warning("[pipeline] failed turn=%d: %s", self.session.turn_count, _pe)

            # P1: milestone summarisation.  Every MILESTONE_INTERVAL turns
            # we write a compact "milestone" into session metadata.
            try:
                await self._maybe_write_milestone(context_msgs)
            except Exception as _m_err:
                logger.warning("[milestone] failed turn=%d: %s", self.session.turn_count, _m_err)

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
            # Inline thinking-tag extraction state
            _think_buf = ''
            _in_think = False

            # Patterns for community-standard thinking / CoT tags
            _THINK_OPEN = re.compile(r'<(think|thought|thinking|reasoning|analysis)>|\[internal\]')
            _THINK_CLOSE = re.compile(r'</(think|thought|thinking|reasoning|analysis)>|\[/internal\]')

            _t_pm = time.time()
            pre_model = await self.hook_system.emit_pre_model_request(
                self.session.messages, tools
            )
            logger.info("[run] emit_pre_model_request done turn=%s (%.2fs)", self.session.turn_count, time.time() - _t_pm)

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
            if _EVOLUTION_ENABLED and self.session.turn_count > 0:
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

            advisor_note = ""
            if _EVOLUTION_ENABLED:
                advisor_seed: list[dict[str, Any]] = []
                ws_tools = (self.session.metadata.get("working_set") or {}).get("tools") or []
                for item in ws_tools:
                    advisor_seed.append({
                        "name": item.get("name", ""),
                        "semantics": {
                            "semantic_type": item.get("semantic_type", ""),
                            "cost_level": item.get("cost_level", ""),
                        },
                    })
                advisor_note = await self._maybe_run_advisor_sub_agent(prompt, advisor_seed)
            if advisor_note:
                def _merge_advisor(msgs: list[dict[str, Any]], suffix: str) -> None:
                    for i in range(len(msgs) - 1, -1, -1):
                        if msgs[i].get("role") == "user":
                            msg = dict(msgs[i])
                            existing = str(msg.get("content") or "")
                            msg["content"] = existing + "\n\n" + suffix
                            msgs[i] = msg
                            return
                _merge_advisor(backend_messages, f"[SUB-AGENT ADVICE]\n{advisor_note}")

            # ── Pre-API stability checks ────────────────────────────────
            # 1. Interrupt check: abort if the user cancelled
            if check_interrupt(self):
                logger.info("[run] interrupt detected before API call turn=%d", self.session.turn_count)
                yield create_finish("cancelled")
                return

            # 1. Mid-conversation system message injection: drain any queued
            #    system directives (stage transition, stuck recovery, dynamic
            #    policy) and append them as discrete ``role: system`` entries
            #    right after the base system prompt -- without rewriting the
            #    prefix, so the cached base prompt stays stable.
            _system_msgs = self._steer_queue.drain_system()
            _injected_system_entries: list[dict[str, str]] = []
            if _system_msgs:
                # Insert after the leading system message(s) but before the
                # user/assistant history.  ``backend_messages`` typically
                # starts with one system entry; we splice ours in after it.
                _insert_at = 0
                for _i, _m in enumerate(backend_messages):
                    if _m.get("role") == "system":
                        _insert_at = _i + 1
                    else:
                        break
                for _offset, _sm in enumerate(_system_msgs):
                    _entry = {"role": "system", "content": _sm}
                    backend_messages.insert(_insert_at + _offset, _entry)
                    _injected_system_entries.append(_entry)
                logger.info(
                    "[run] injected %d mid-conversation system message(s) turn=%d",
                    len(_system_msgs), self.session.turn_count,
                )

            # 2. Steer injection: drain any queued /steer instructions
            _steer_msgs = self._steer_queue.drain()
            _steer_text = build_steer_injection(_steer_msgs)
            if _steer_text:
                backend_messages.append({"role": "user", "content": _steer_text})
                logger.info("[run] injected %d steer instruction(s) turn=%d",
                            len(_steer_msgs), self.session.turn_count)

            # 3. Message repair: fix role alternation, surrogates, whitespace
            backend_messages = repair_messages(backend_messages)
            # 3b. Re-pair tool_call groups after repair so an assistant message
            # with tool_calls is always followed by matching tool results.
            backend_messages = self.compact_engine.sanitize(backend_messages)

            # 4. Pre-API token pressure check
            _context_window = self.backend.context_window_size()
            _pressure = check_token_pressure(
                backend_messages, _context_window, _slot_budget if '_slot_budget' in dir() else self.config.max_tokens,
            )
            if _pressure > 0.85:
                logger.warning(
                    "[run] token pressure %.1f%% before API call turn=%d -- compacting",
                    _pressure * 100, self.session.turn_count,
                )
                try:
                    _context_msgs = self.session.get_context_messages()
                    self.session.set_compact_archive(_context_msgs)
                    _compacted = await self.compact_engine.compact(
                        _context_msgs, backend=self.backend,
                        turn_count=self.session.turn_count,
                        system_prompt=system_prompt or "",
                        enable_caching=self.config.enable_prompt_caching,
                        session_id=self.session.id or "",
                    )
                    if _compacted is not None:
                        self.session.replace_branch_messages(
                            self.session.active_branch_id, _compacted
                        )
                        self._compacted_this_turn = True
                        backend_messages = self.session.get_context_messages()
                        # Re-inject system messages that were lost during session refresh
                        if _injected_system_entries:
                            _reinsert_at = 0
                            for _i, _m in enumerate(backend_messages):
                                if _m.get("role") == "system":
                                    _reinsert_at = _i + 1
                                else:
                                    break
                            for _offset, _entry in enumerate(_injected_system_entries):
                                backend_messages.insert(_reinsert_at + _offset, dict(_entry))
                        # Re-inject steer messages that were lost during session refresh
                        if _steer_text:
                            backend_messages.append({"role": "user", "content": _steer_text})
                        logger.info("[run] pre-API compact succeeded turn=%d", self.session.turn_count)
                except Exception as _pc_err:
                    logger.warning("[run] pre-API compact failed: %s", _pc_err)

            # 5. Thinking prefill (if enabled)
            _thinking_prefill = build_thinking_prefill(
                prompt, enabled=self._thinking_prefill_enabled,
            )

            response_text = ""
            _backend_usage: dict[str, Any] | None = None
            _t_chat = time.time()

            # Cached microcompact: register tool_results and queue deletions
            # for the Anthropic cache_edits API layer.  Only runs when the
            # backend is Anthropic (other backends ignore the block).
            _cache_edits_state = self._cache_edits_state
            if _cache_edits_state is None and self.config.enable_prompt_caching:
                try:
                    from encre.cache_edits import create_state
                    self._cache_edits_state = create_state()
                    _cache_edits_state = self._cache_edits_state
                except Exception:
                    pass
            if _cache_edits_state is not None:
                try:
                    from encre.cache_edits import (
                        create_cache_edits_block,
                        get_tool_results_to_delete,
                        register_tool_results,
                    )
                    register_tool_results(_cache_edits_state, backend_messages)
                    to_delete = get_tool_results_to_delete(_cache_edits_state)
                    if to_delete:
                        create_cache_edits_block(_cache_edits_state, to_delete)
                except Exception:
                    logger.debug("[cache_edits] loop registration failed", exc_info=True)

            logger.info("[run] calling backend.chat() turn=%s msgs=%s tools=%s",
                        self.session.turn_count, len(backend_messages),
                        bool(backend_tools))
            _chat_first_event = True
            _llm_span = trace_llm_call(
                self._tracer,
                self.config.model,
                str(backend_messages[0])[:200] if backend_messages else "",
            )
            _llm_span.set_attribute("llm.turn", self.session.turn_count)
            self._error_orch.reset_for_new_turn()
            # Slot reservation: start with a small output budget and
            # escalate to the full budget only when the model hits the
            # limit ("max_tokens" or "length" finish reason).  This
            # encourages concise responses (~70% fit in 4K) while
            # allowing long outputs on demand.
            _slot_budget: int
            if self._max_output_tokens_override:
                _slot_budget = self._max_output_tokens_override
                self._max_output_tokens_override = None
            elif self.config.default_slot_tokens and self.config.default_slot_tokens < self.config.max_tokens:
                _slot_budget = self.config.default_slot_tokens
            else:
                _slot_budget = self.config.max_tokens
            _slot_finish_reason = "stop"
            # Fallback loop: retry with fallback model on rate-limit/overload
            _attempt_fallback = True
            _error_consumed = False
            while _attempt_fallback:
                _attempt_fallback = False
                try:
                    # Wrap the chat generator with a 120s timeout on the first event,
                    # so a hanging API call (wrong key, no network, etc.) surfaces an
                    # error rather than freezing the UI indefinitely.
                    _chat_gen = self.backend.chat(
                        messages=backend_messages,
                        tools=backend_tools,
                        max_tokens=_slot_budget,
                        enable_caching=self.config.enable_prompt_caching and self.backend.supports_prompt_caching(),
                        cache_edits_state=_cache_edits_state,
                    )
                    async for event in self._chat_with_timeout(_chat_gen, timeout=120.0):
                        if _chat_first_event:
                            logger.info("[run] backend.chat() first event after %.1fs turn=%s",
                                        time.time() - _t_chat, self.session.turn_count)
                            _chat_first_event = False
                        if isinstance(event, BackendText):
                            text = event.text
                            # Inline community thinking-tag extraction.
                            # Splits text into text_delta (outside tags) and
                            # thinking_delta (inside tags), handling cross-event
                            # tags via _think_buf / _in_think state.

                            if _in_think:
                                cm = _THINK_CLOSE.search(text)
                                if cm:
                                    _think_buf += text[:cm.start()]
                                    if _think_buf:
                                        if _tool_seen:
                                            _extra_thinking.append(_think_buf)
                                        else:
                                            thinking_parts.append(_think_buf)
                                        yield create_thinking_delta(_think_buf)
                                    _think_buf = ''
                                    _in_think = False
                                    text = text[cm.end():]
                                else:
                                    _think_buf += text
                                    text = ''
                            while text:
                                om = _THINK_OPEN.search(text)
                                if om:
                                    before = text[:om.start()]
                                    if before:
                                        if _tool_seen:
                                            if not _in_extra:
                                                _in_extra = True
                                                yield create_assistant_boundary()
                                            _extra_text.append(before)
                                            yield create_text_delta(before)
                                        else:
                                            text_parts.append(before)
                                            yield create_text_delta(before)
                                    _in_think = True
                                    _think_buf = ''
                                    text = text[om.end():]
                                    cm = _THINK_CLOSE.search(text)
                                    if cm:
                                        think = text[:cm.start()]
                                        if think:
                                            if _tool_seen:
                                                _extra_thinking.append(think)
                                            else:
                                                thinking_parts.append(think)
                                            yield create_thinking_delta(think)
                                        _in_think = False
                                        text = text[cm.end():]
                                    else:
                                        _think_buf = text
                                        text = ''
                                else:
                                    if text:
                                        if _tool_seen:
                                            if not _in_extra:
                                                _in_extra = True
                                                yield create_assistant_boundary()
                                            _extra_text.append(text)
                                            yield create_text_delta(text)
                                        else:
                                            text_parts.append(text)
                                            yield create_text_delta(text)
                                    text = ''
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
                                    if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):
                                        buf["id"] = event.id or buf["id"]
                                        buf["name"] = event.name
                                        buf["arguments"] = event.arguments
                                        found = True
                                        break
                                if not found:
                                    for _existing_idx, buf in _extra_buffers.items():
                                        if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):
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
                                _streaming_call_idx = -1
                                for _existing_idx, buf in tool_call_buffers.items():
                                    if buf["id"] == event.id or (not buf["id"] and buf["name"] == event.name):
                                        buf["id"] = event.id or buf["id"]
                                        buf["name"] = event.name
                                        buf["arguments"] = event.arguments
                                        found = True
                                        _streaming_call_idx = _existing_idx
                                        break
                                if not found:
                                    _streaming_call_idx = len(tool_call_buffers)
                                    tool_call_buffers[_streaming_call_idx] = {
                                        "id": event.id,
                                        "name": event.name,
                                        "arguments": event.arguments,
                                    }
                                # Streaming tool execution: pre-execute allowed tools in
                                # background while the model continues generating output.
                                # Exclude tools with side effects on the tool/runtime state
                                # (find_tool unlocks + mutates discovery cache, manage installs
                                # tools, agent/swarm/workflow spawn sub-agents) -- running
                                # those during streaming corrupts state because the current
                                # turn's tool schema was already sent.  They run in the normal
                                # post-streaming phase instead.
                                if (self.config.enable_streaming_tool_execution
                                    and not self.plan_mode_active
                                    and event.name not in (
                                        "question", "agent", "workflow", "swarm",
                                        "find_tool", "manage",
                                    )):
                                    _sc_client = f"call_{self.session.turn_count}_{_streaming_call_idx}"
                                    if _sc_client not in self._streaming_tool_results:
                                        asyncio.create_task(
                                            self._pre_execute_in_background(
                                                _sc_client, event.name, event.arguments,
                                            )
                                        )

                        elif isinstance(event, BackendFinish):
                            # Capture token usage from the backend
                            if event.usage:
                                _backend_usage = event.usage
                                _last_backend_usage = event.usage
                            _slot_finish_reason = event.reason

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
                            raise RuntimeError(event.error)

                except Exception as exc:
                    from encre.backends.base import format_backend_error
                    from encre.recovery_loop import is_context_overflow, is_rate_limit_or_overload, can_fallback, reactive_compact_with_retry, build_fallback_system_message
                    # build_tombstone_messages is imported at module top
                    # level from encre.loop_stability (the module that
                    # actually defines it).  Do NOT re-import it from
                    # recovery_loop -- that module does not define it and
                    # the import would raise ImportError whenever this
                    # fallback path runs.
                    from encre.loop_stability import classify_error as _legacy_classify, WithheldError
                    from encre.errors import AgentError

                    # Build structured error from the exception
                    _agent_err = AgentError.from_exception(exc, finish_reason=None)
                    _error_kind = _legacy_classify(exc)
                    _is_ctx_overflow = is_context_overflow(exc)
                    _is_rate_limit = is_rate_limit_or_overload(exc)

                    decision = self._error_orch.handle_backend_exception(
                        exc,
                        error_code=_agent_err.code.value,
                        error_category=_agent_err.category.value,
                        is_context_overflow=_is_ctx_overflow,
                        is_rate_limit=_is_rate_limit,
                        config=self.config,
                        compact_engine=self.compact_engine,
                        session=self.session,
                        backend=self.backend,
                        system_prompt=system_prompt or "",
                        tool_call_buffers=tool_call_buffers,
                        turn_count=self.session.turn_count,
                    )

                    if decision.action == RecoveryAction.COMPACT_CONTINUE:
                        # Reactive compact: compress session and retry
                        try:
                            context_msgs = self.session.get_context_messages()
                            est = count_message_tokens(context_msgs)
                            self.session.set_compact_archive(context_msgs)
                            compacted = await self.compact_engine.compact(
                                context_msgs, backend=self.backend,
                                turn_count=self.session.turn_count,
                                system_prompt=system_prompt or "",
                                enable_caching=self.config.enable_prompt_caching,
                                session_id=self.session.id or "",
                            )
                            if compacted is not None:
                                self.session.replace_branch_messages(self.session.active_branch_id, compacted)
                                self._compacted_this_turn = True
                                self._update_user_requirements(compacted)
                                logger.info("[reactive] compact succeeded turn=%d, continuing without error",
                                            self.session.turn_count)
                                self._has_attempted_reactive_compact = True
                                _llm_span.set_attribute("llm.reactive_compact", "succeeded")
                                _llm_span.end()
                                if self._state is not None:
                                    self._state.transitions.record(
                                        TurnTransition.REACTIVE_COMPACT,
                                        turn=self.session.turn_count,
                                        detail="context overflow",
                                    )
                                if self.memory_system is not None:
                                    try: self.memory_system.refresh()
                                    except Exception: logger.warning("[reactive] memory refresh failed", exc_info=True)
                                continue
                        except Exception as _ce:
                            logger.warning("[reactive] compact failed turn=%d: %s",
                                           self.session.turn_count, _ce)

                    if decision.action == RecoveryAction.FALLBACK_CONTINUE:
                        # Model fallback
                        original_model = self.config.model
                        fallback_model = self.config.fallback_model
                        logger.info("[fallback] switching from %s to %s due to: %s",
                                    original_model, fallback_model, exc)
                        self._active_fallback_model = fallback_model
                        self._active_fallback_backend_type = self.config.fallback_backend_type or self.config.backend_type
                        _llm_span.set_attribute("llm.fallback", f"{original_model}->{fallback_model}")
                        _llm_span.end()
                        yield create_system_message(build_fallback_system_message(original_model, fallback_model))
                        if tool_call_buffers:
                            _tombstones = build_tombstone_messages(tool_call_buffers, f"model fallback: {exc}")
                            for _ts in _tombstones:
                                self.session.add_message(_ts["role"], _ts.get("content", ""),
                                    tool_call_id=_ts.get("tool_call_id"), name=_ts.get("name"),
                                    is_error=_ts.get("is_error", False))
                            tool_call_buffers.clear()
                        from encre.backends.base import create_backend
                        fallback_backend = create_backend(
                            fallback_model,
                            self.config.fallback_base_url or self.config.base_url,
                            self.config.fallback_api_key or self.config.api_key,
                            backend_type=self._active_fallback_backend_type,
                        )
                        self.backend = fallback_backend
                        _attempt_fallback = True
                        if self._state is not None:
                            self._state.transitions.record(
                                TurnTransition.MODEL_FALLBACK,
                                turn=self.session.turn_count,
                                detail=f"{original_model} -> {fallback_model}",
                            )
                        continue

                    if decision.action == RecoveryAction.RETRY:
                        import asyncio as _aio
                        await _aio.sleep(decision.delay)
                        logger.info("[run] network error -- retried after %.1fs delay turn=%d", decision.delay, self.session.turn_count)
                        _attempt_fallback = True
                        if self._state is not None:
                            self._state.transitions.record(
                                TurnTransition.NETWORK_RETRY,
                                turn=self.session.turn_count,
                                detail=f"{decision.delay}s delay retry",
                            )
                        continue

                    if decision.action == RecoveryAction.CONTINUE:
                        _error_consumed = True
                        if self._state is not None:
                            self._state.transitions.record(
                                TurnTransition.ERROR_CONSUMED,
                                turn=self.session.turn_count,
                                detail=decision.detail,
                            )
                        logger.warning("[run] error consumed -- continuing turn=%d error=%s",
                                       self.session.turn_count, format_backend_error(exc))
                        continue

                    # RecoveryAction.RELEASE — surface to user
                    _llm_span.set_attribute("llm.error", str(exc))
                    _llm_span.end()
                    await self.hook_system.emit_error(exc, "backend_chat_exception")
                    await self.hook_system.emit_backend_error(str(exc), type(self.backend).__name__ if self.backend else "unknown")
                    err_msg = format_backend_error(exc)
                    yield create_finish("error", error=err_msg,
                                        error_code=_agent_err.code.value,
                                        error_category=_agent_err.category.value)
                    _last_ui = -1
                    for _j in range(len(self.session.messages) - 1, -1, -1):
                        if self.session.messages[_j].get("role") == "user":
                            _last_ui = _j; break
                    _cur_asst = None
                    for _j in range(_last_ui + 1, len(self.session.messages)):
                        if self.session.messages[_j].get("role") == "assistant":
                            _cur_asst = self.session.messages[_j]; break
                    if _cur_asst is not None:
                        _cur_asst["errorMessage"] = err_msg
                        _cur_asst["errorCode"] = _agent_err.code.value
                        _c = _cur_asst.get("content", "")
                        if isinstance(_c, str):
                            _cur_asst["content"] = _c + f"\n\n[Backend API Error]\n{err_msg}"
                    else:
                        self.session.add_message("assistant",
                            f"[Backend API Error]\n{err_msg}",
                            errorMessage=err_msg,
                            errorCode=_agent_err.code.value,
                            segments=[{"kind": "text", "text": f"[Backend API Error]\n{err_msg}"}],
                        )
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.ERROR, turn=self.session.turn_count, detail=err_msg[:200],
                        )
                    logger.info("[run] stored backend error on assistant msg turn=%s, exiting", self.session.turn_count)
                    return
                else:
                    logger.info("[run] backend.chat() completed in %.1fs turn=%s events=%s",
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

            # ── Post-stream recovery (orchestrator) ──────────────────
            post_decision = self._error_orch.handle_post_stream(
                finish_reason=_slot_finish_reason,
                is_empty=is_empty_response(text_parts, tool_call_buffers, thinking_parts) if not _error_consumed else False,
                is_truncated=bool(tool_call_buffers) and is_truncated_tool_call(tool_call_buffers),
                tool_call_buffers=tool_call_buffers,
                text_parts=text_parts,
                thinking_parts=thinking_parts,
                config=self.config,
                session=self.session,
                turn_count=self.session.turn_count,
            )

            if _error_consumed:
                yield create_finish("stop")
                return

            if post_decision.action == PostStreamAction.CONTINUE:
                if post_decision.detail == "slot escalation":
                    self._error_orch._slot_escalated = True
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.SLOT_ESCALATION,
                            turn=self.session.turn_count,
                            detail=f"{self.config.default_slot_tokens} -> {self.config.max_tokens}",
                        )
                    logger.info("[slot] escalating from %d -> %d turn=%d",
                                self.config.default_slot_tokens, self.config.max_tokens, self.session.turn_count)
                    yield create_system_message(build_slot_escalation_message())
                elif "max_tokens" in post_decision.detail:
                    self._max_output_tokens_override = ESCALATED_MAX_TOKENS
                    if tool_call_buffers:
                        _tombstones = build_tombstone_messages(tool_call_buffers, "max_tokens truncation")
                        for _ts in _tombstones:
                            self.session.add_message(_ts["role"], _ts.get("content", ""),
                                tool_call_id=_ts.get("tool_call_id"), name=_ts.get("name"),
                                is_error=_ts.get("is_error", False))
                        tool_call_buffers.clear()
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.MAX_OUTPUT_TOKENS,
                            turn=self.session.turn_count,
                            detail=post_decision.detail,
                        )
                    logger.info("[max_tokens] recovery %s turn=%d", post_decision.detail, self.session.turn_count)
                    yield create_system_message(build_max_tokens_recovery_message())
                elif "empty" in post_decision.detail:
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.EMPTY_RESPONSE,
                            turn=self.session.turn_count,
                            detail=post_decision.detail,
                        )
                    logger.warning("[run] empty response, %s turn=%d", post_decision.detail, self.session.turn_count)
                    retry_count = self._error_orch._empty_response_retry_count
                    self.session.add_message("user", build_empty_retry_message(retry_count))
                elif "truncated" in post_decision.detail:
                    _first_tc = next(iter(tool_call_buffers.values()))
                    _args_preview = str(_first_tc.get("arguments", ""))[:200]
                    _tc_name = _first_tc.get("name", "unknown")
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.TRUNCATED_TOOL_CALL,
                            turn=self.session.turn_count,
                            detail=post_decision.detail + f" tool={_tc_name}",
                        )
                    logger.warning("[run] truncated tool call '%s', %s turn=%d",
                                   _tc_name, post_decision.detail, self.session.turn_count)
                    tool_call_buffers.clear()
                    self.session.add_message("user", build_truncated_retry_message(_tc_name, _args_preview))
                continue

            if (post_decision.action == PostStreamAction.STOP or
                (_slot_finish_reason in ("max_tokens", "length") and
                 not self._error_orch._slot_escalated and
                 self._error_orch._max_output_tokens_recovery_count >= MAX_OUTPUT_TOKENS_RECOVERY_LIMIT)):
                # Empty response exhausted
                if is_empty_response(text_parts, tool_call_buffers, thinking_parts):
                    logger.warning("[run] empty response retries exhausted turn=%d", self.session.turn_count)
                    self.session.add_message("assistant",
                        "(No response generated. Please try rephrasing your request.)")
                    yield create_finish("stop")
                    return

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
                await _cleanup_terminal_sessions()
                logger.debug("Agent finished (text-only response, %s chars)", len(full_text))

                # ── Spec parsing ───────────────────────────────────
                # In spec mode, when the model produces a text-only response
                # (no tool calls), it MAY have generated a specification.
                # Only treat it as a spec when the output actually looks like
                # a structured spec document -- i.e. it contains at least one
                # ``## `` (H2) heading that ``parse_spec`` will split into
                # sections.  Without this guard, ANY text the model emits in
                # spec mode (a clarifying question, small talk, an error
                # apology) gets mis-parsed as a degenerate single-section
                # "spec" and the frontend pops a spec card / system bubble
                # for what was just a normal reply.
                _looks_like_spec = any(
                    line.lstrip().startswith("## ") and not line.lstrip().startswith("### ")
                    for line in full_text.splitlines()
                )
                if (
                    slash_command_mode == "spec"
                    and self.spec_engine
                    and full_text.strip()
                    and _looks_like_spec
                ):
                    try:
                        from encre.spec.engine import SpecStatus as _SpecStatus
                        spec_doc = self.spec_engine.parse_spec(
                            title=prompt[:80] if prompt else "Specification",
                            llm_output=full_text,
                        )
                        spec_doc.status = _SpecStatus.REVIEW
                        spec_data = spec_doc.to_dict()
                        # Emit the parsed spec as a ``__spec_data__`` payload so
                        # ws.py can re-route it as a ``spec_update`` event --
                        # the frontend renders the spec card (with sections,
                        # status and Approve/Reject) from that.  We do NOT emit
                        # a separate human-readable SystemMessage here: it would
                        # render as a redundant "System message" strip pinned
                        # to the top of the conversation, on top of the spec
                        # card which already carries the same information.
                        from encre.utils.types import SystemMessage as _SM
                        import json as _json
                        yield _SM(content=f"__spec_data__:{_json.dumps(spec_data)}", kind="spec")
                        logger.info("[spec] parsed spec with %d sections, status=review", len(spec_doc.sections))
                    except Exception as e:
                        logger.warning("[spec] failed to parse spec: %s", e)

                # ── Auto-continue: when budget remains, nudge the model to
                # keep going instead of stopping early.  Mirrors Claude Code's
                # token-budget auto-continue (query/tokenBudget.ts).
                _auto_continue = False
                if (
                    self.config.token_budget > 0
                    and not tool_call_buffers
                    and _backend_usage
                ):
                    self._budget_state.add_usage(
                        _backend_usage.get("output_tokens", 0)
                    )
                    self.session.metadata[BudgetState.META_KEY] = self._budget_state.checkpoint()
                    if (
                        not self._budget_state.is_exhausted
                        and self._budget_state.used_tokens > 0
                    ):
                        _auto_continue = True
                        if self._state is not None:
                            self._state.transitions.record(
                                TurnTransition.AUTO_CONTINUE,
                                turn=self.session.turn_count,
                                detail=f"token={self._budget_state.used_tokens}/{self._budget_state.max_tokens}",
                            )
                        logger.info(
                            "[run] auto-continue turn=%s token=%d/%d",
                            self.session.turn_count,
                            self._budget_state.used_tokens,
                            self._budget_state.max_tokens,
                        )
                        self.session.add_message(
                            "user", build_auto_continue_message(),
                        )
                        continue

                if not _auto_continue:
                    if self._state is not None:
                        self._state.transitions.record(
                            TurnTransition.TEXT_ONLY,
                            turn=self.session.turn_count,
                        )
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

            # ── Spec approval gate ───────────────────────────────────
            # In spec mode, block write tools until the spec is approved.
            # Read-only tools (file_read, grep, glob, etc.) are allowed.
            _spec_approved = True
            if slash_command_mode == "spec" and self.spec_engine is not None:
                _current = self.spec_engine.current_spec
                _spec_approved = _current is not None and (
                    hasattr(_current, "status") and getattr(_current.status, "value", None) == "approved"
                )
                if not _spec_approved:
                    # Override the spec mode instruction so the model knows to
                    # wait for approval before implementing.
                    yield create_system_message(
                        "Specification is pending approval. Write tools are blocked. "
                        "Wait for user to approve the spec before implementing.",
                        kind="spec",
                    )
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
                        self.session.add_tool_result(tc["id"], err_msg, is_error=True, client_id=client_id)
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
                else:
                    args = {}

                tool = self.tool_registry.get(tc["name"])
                if tool is None:
                    err_msg = f"Error: Unknown tool: {tc['name']}"
                    yield create_tool_result(id=client_id, content=err_msg, is_error=True)
                    self.session.add_tool_result(tc["id"], err_msg, is_error=True, client_id=client_id)
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

                # ── Spec approval gate: block write tools ───────────
                # In spec mode, if the spec hasn't been approved yet,
                # block all write-class tools (file_write, file_edit,
                # apply_patch, bash, etc.).  Read-only tools are allowed
                # so the model can still gather context.
                _spec_block = False
                if slash_command_mode == "spec" and self.spec_engine is not None and (
                    tc["name"] in _WRITE_TOOL_NAMES or tc["name"] == "bash"
                ):
                    _current = self.spec_engine.current_spec
                    _spec_approved = _current is not None and (
                        hasattr(_current, "status") and getattr(_current.status, "value", None) == "approved"
                    )
                    _spec_block = not _spec_approved
                if _spec_block:
                    _spec_msg = (
                        "Blocked: Spec mode is active and the specification has not been "
                        "approved yet. Write tools are disabled. Present the specification "
                        "for user review first."
                    )
                    yield create_tool_result(id=client_id, content=_spec_msg, is_error=True)
                    self.session.add_tool_result(tc["id"], _spec_msg, is_error=True, client_id=client_id)
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=tc["name"], latency_ms=0, success=False, error_message=_spec_msg,
                    )
                    yield create_tool_call_end(id=client_id)
                    turn_events += 1
                    prepared.append({"id": tc["id"], "client_id": client_id,
                                     "name": tc["name"], "args": args,
                                     "tool": tool, "skip": True, "error": _spec_msg})
                    continue

                is_safe = tool.is_concurrency_safe(args)
                semantics = _infer_tool_semantics(tc["name"], tool)
                self.session.metadata.setdefault("tool_semantics", {})[tc["name"]] = semantics
                prepared.append({
                    "id": tc["id"], "client_id": client_id,
                    "name": tc["name"], "args": args,
                    "tool": tool, "skip": False, "safe": is_safe,
                    "args_summary": _args_summary(args),
                    "semantics": semantics,
                })

            # Tag tools that were pre-executed during streaming so the permission
            # and execution phases can skip re-execution.
            if self._streaming_tool_results:
                for _pre_p in prepared:
                    if _pre_p["client_id"] in self._streaming_tool_results:
                        _pre_p["pre_executed"] = True

            next_stage = self._infer_task_stage(prompt, prepared)
            self._set_task_stage(next_stage, reason="tool preparation")
            self._refresh_working_set(prompt, prepared)

            # ── Permission & hooks for all tools (sequential -- these may need user input) ──
            if self._cancelled():
                # Tombstone: the user cancelled mid-turn after the model
                # issued tool_calls but before they were executed.  Synthesize
                # error tool_results so the API does not reject the *next*
                # request with an orphan tool_use / tool_result mismatch.
                for _prep in prepared:
                    if not _prep.get("skip") and not _prep.get("pre_executed"):
                        self.session.add_tool_result(
                            _prep["id"],
                            "[Cancelled by user]",
                            is_error=True,
                            client_id=_prep.get("client_id", ""),
                        )
                break
            for p in prepared:
                if self._cancelled():
                    break
                if p.get("skip") or p.get("pre_executed"):
                    continue
                if not _tool_retry_allowed(p, self._recent_tool_names):
                    retry_msg = (
                        "Blocked repeated high-risk tool retry. "
                        + p.get("semantics", {}).get("safe_fallback", "Gather more context before retrying.")
                    )
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="blocked")
                    yield create_tool_result(id=p["client_id"], content=retry_msg, is_error=True)
                    self.session.add_tool_result(p["id"], retry_msg, is_error=True, client_id=p["client_id"])
                    turn_events += 1
                    self.telemetry.record_tool_call(
                        tool_name=p["name"], latency_ms=0,
                        success=False, error_message=retry_msg,
                    )
                    yield create_tool_call_end(id=p["client_id"])
                    turn_events += 1
                    p["skip"] = True
                    p["error"] = retry_msg
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
                    permission_granted = await self._wait_for_permission_decision(p["name"])
                    self._permission_event = None
                    await self.hook_system.emit_permission_response(
                        p["name"], permission_granted
                    )
                    if not permission_granted:
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
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="blocked")
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
                        plan_err = "Plan rejected by user. Adjust your plan and try a different approach."
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
                        with contextlib.suppress(builtins.BaseException):
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

            # ── Yield results for pre-executed (streaming) tools ─────────
            for p in list(prepared):
                if not p.get("pre_executed"):
                    continue
                pr = self._streaming_tool_results[p["client_id"]]
                _pre_result = _apply_result_budget(
                    pr["result"], p["tool"],
                    session_id=self.session.id or "",
                    tool_name=p.get("name", ""),
                )
                yield create_tool_result(
                    id=p["client_id"], content=_pre_result, is_error=pr["is_error"],
                )
                self.session.add_tool_result(
                    p["id"], _pre_result, is_error=pr["is_error"], client_id=p["client_id"],
                )
                turn_events += 1
                self.telemetry.record_tool_call(
                    tool_name=p["name"], latency_ms=pr["latency_ms"],
                    success=not pr["is_error"],
                )
                if pr["is_error"]:
                    self._error_tool_names.add(p["name"])
                else:
                    self._error_tool_names.discard(p["name"])
                yield create_tool_call_end(id=p["client_id"])
                turn_events += 1
                if not pr["is_error"]:
                    _fp = _extract_file_path(p["name"], _pre_result)
                    if _fp:
                        _dt = _extract_diff_text(p["name"], _pre_result)
                        _entry = self.session.add_artifact(_fp, p["name"], diff_text=_dt)
                        yield Artifact(artifact=_entry)
                    elif _is_reference_tool(p["name"]):
                        _summary = _extract_ref_summary(p["name"], p.get("args", {}), _pre_result)
                        _entry = self.session.add_reference(p["name"], _summary)
                        yield Reference(reference=_entry)
                    _plan_items = _ensure_plan_items(p["name"], p["args"])
                    if _plan_items:
                        yield PlanUpdate(plan_items=_plan_items)
                prepared.remove(p)

            # ── Split into safe (concurrent) and unsafe (sequential) groups ──
            safe_tools = [p for p in prepared if not p.get("skip") and p.get("safe")]
            unsafe_tools = [p for p in prepared if not p.get("skip") and not p.get("safe")]

            # Path-aware parallelism: write tools that touch *different*
            # files are safe to run concurrently (mirrors Hermes'
            # ``_paths_overlap``).  Tools whose paths can't be statically
            # determined (bash, a write tool missing its path arg, ...) and
            # tools whose paths overlap with another write tool stay
            # sequential.  ``apply_patch`` participates too (all of its
            # multi-file paths are checked for overlap).
            _unsafe_writes = [p for p in unsafe_tools if p["name"] in _WRITE_TOOL_NAMES]
            _unsafe_other = [p for p in unsafe_tools if p["name"] not in _WRITE_TOOL_NAMES]
            _parallel_writes, _sequential_writes = _split_writes_by_path_conflict(_unsafe_writes)
            if _parallel_writes:
                safe_tools = safe_tools + _parallel_writes
                unsafe_tools = _sequential_writes + _unsafe_other

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
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")

                async def _execute_safe(p: dict[str, Any]) -> dict[str, Any]:
                    tool_start = time.time()
                    tool_error = False
                    _span = trace_tool_call(self._tracer, p["name"], p["args"])
                    try:
                        executor = RetryableExecutor(self.recovery_engine)
                        state = await executor.execute(
                            tool_name=p["name"],
                            tool_args=p["args"],
                            execute_fn=lambda a, p=p: p["tool"].execute(**a),
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
                        await self._collect_tool_skill(p["name"])
                        await self._collect_doc_skills(p["args"])
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

                # Cap parallel fan-out to match Claude Code (default 10) instead
                # of launching every concurrency-safe tool at once.
                _tool_sem = asyncio.Semaphore(_MAX_TOOL_CONCURRENCY)

                async def _execute_safe_bounded(p: dict[str, Any]) -> dict[str, Any]:
                    async with _tool_sem:
                        return await _execute_safe(p)

                safe_tasks = [_execute_safe_bounded(p) for p in safe_tools]
                # Cancel-aware gather: if the user hits Stop, cancel all
                # in-flight safe tool tasks immediately.
                cancel_watcher = asyncio.create_task(self._cancel_event.wait())
                gather_task = asyncio.ensure_future(asyncio.gather(*safe_tasks, return_exceptions=True))
                done, pending = await asyncio.wait(
                    {gather_task, cancel_watcher},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                cancel_watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_watcher

                if cancel_watcher in done and self._cancelled():
                    gather_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await gather_task
                    completed = [None] * len(safe_tools)
                else:
                    try:
                        completed = gather_task.result()
                    except BaseException:
                        completed = [None] * len(safe_tools)
                for idx, item in enumerate(completed):
                    p = safe_tools[idx]
                    if item is None or isinstance(item, BaseException):
                        # Cancelled (None) or crashed (BaseException): emit
                        # a tombstone result so the UI tool tag closes
                        # properly and the session history stays consistent.
                        if isinstance(item, BaseException):
                            err_msg = f"Tool execution crashed: {type(item).__name__}: {item}"
                        else:
                            err_msg = "[Cancelled by user]"
                        yield create_tool_result(id=p["client_id"], content=err_msg, is_error=True)
                        self.session.add_tool_result(p["id"], err_msg, is_error=True, client_id=p["client_id"])
                        turn_events += 1
                        self._error_tool_names.add(p["name"])
                        self.telemetry.record_tool_call(
                            tool_name=p["name"], latency_ms=0.0,
                            success=False, error_message=err_msg,
                        )
                        yield create_tool_call_end(id=p["client_id"])
                        turn_events += 1
                        continue
                    p = item
                    p["result"] = _apply_result_budget(
                        p["result"], p["tool"],
                        session_id=self.session.id or "",
                        tool_name=p.get("name", ""),
                    )
                    # Auto-verify: append LSP diagnostics (or a VERIFY
                    # reminder when LSP is unavailable) for write tools.
                    if not p["is_error"] and p["name"] in _WRITE_TOOL_NAMES:
                        fp = _extract_file_path(p["name"], p["result"])
                        if fp:
                            _lsp_text = await _try_lsp_diagnostics(fp)
                            if _lsp_text:
                                p["result"] += _lsp_text
                            else:
                                p["result"] += (
                                    f"\n\n[VERIFY] Please verify the changes to "
                                    f"`{fp}` are correct by reading the file."
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
                            correction = ErrorRecoveryEngine.infer_correction_from_history(p["recovery_history"], p["name"])
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
                                    entry = self.session.add_artifact(ap_path, p["name"], diff_text="")
                                    yield Artifact(artifact=entry)
                            else:
                                diff_text = _extract_diff_text(p["name"], p["result"])
                                entry = self.session.add_artifact(fp, p["name"], diff_text=diff_text)
                                yield Artifact(artifact=entry)
                        else:
                            # Non-file tool -> record as reference
                            if _is_reference_tool(p["name"]):
                                summary = _extract_ref_summary(p["name"], p.get("args", {}), p["result"])
                                ref_icon = ""
                                entry = self.session.add_reference(p["name"], summary, icon=ref_icon)
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
                if self._cancelled():
                    break
                tool_start = time.time()
                yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")

                tool_error = False
                sub_agent_messages = None
                sub_agent_session_id = None
                sub_agent_references: list[dict[str, Any]] = []
                try:
                    if p["name"] == "agent":
                        progress_queue: asyncio.Queue[list[dict[str, Any]] | None] = asyncio.Queue()

                        async def _sub_agent_progress(messages: list[dict[str, Any]], progress_queue=progress_queue) -> None:
                            nonlocal sub_agent_messages
                            sub_agent_messages = messages
                            await progress_queue.put(messages)

                        agent_args = dict(p["args"])
                        agent_args["progress_callback"] = _sub_agent_progress

                        async def _run_agent_tool(p=p, agent_args=agent_args, progress_queue=progress_queue) -> Any:
                            try:
                                return await p["tool"].execute(**agent_args)
                            finally:
                                await progress_queue.put(None)

                        agent_task = asyncio.create_task(_run_agent_tool())
                        _agent_cancel = asyncio.create_task(self._cancel_event.wait())
                        while True:
                            get_task = asyncio.create_task(progress_queue.get())
                            done, _ = await asyncio.wait(
                                {get_task, _agent_cancel}, return_when=asyncio.FIRST_COMPLETED,
                            )
                            if _agent_cancel in done:
                                agent_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await agent_task
                                get_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await get_task
                                _agent_cancel.cancel()
                                result = "[Cancelled by user]"
                                tool_error = True
                                self.session.add_tool_result(p["id"], result, is_error=True, client_id=p.get("client_id", ""))
                                yield create_tool_result(id=p["client_id"], content=result, is_error=True)
                                yield create_tool_call_end(id=p["client_id"])
                                turn_events += 1
                                break
                            if get_task in done:
                                live_messages = get_task.result()
                            else:
                                get_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await get_task
                                continue
                            _agent_cancel.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await _agent_cancel
                            _agent_cancel = asyncio.create_task(self._cancel_event.wait())
                            if live_messages is None:
                                break
                            yield create_tool_progress(
                                id=p["client_id"],
                                tool_name=p["name"],
                                status="running",
                                sub_agent_messages=live_messages,
                            )
                        else:
                            _agent_cancel.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await _agent_cancel
                        if not tool_error:
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

                        async def _wf_progress(messages: list[dict[str, Any]], progress_queue=progress_queue) -> None:
                            await progress_queue.put(messages)

                        wf_args = dict(p["args"])
                        wf_args["progress_callback"] = _wf_progress

                        async def _run_wf_tool(p=p, wf_args=wf_args, progress_queue=progress_queue) -> Any:
                            try:
                                return await p["tool"].execute(**wf_args)
                            finally:
                                await progress_queue.put(None)

                        wf_task = asyncio.create_task(_run_wf_tool())
                        _wf_cancel = asyncio.create_task(self._cancel_event.wait())
                        while True:
                            get_task = asyncio.create_task(progress_queue.get())
                            done, _ = await asyncio.wait(
                                {get_task, _wf_cancel}, return_when=asyncio.FIRST_COMPLETED,
                            )
                            if _wf_cancel in done:
                                wf_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await wf_task
                                get_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await get_task
                                _wf_cancel.cancel()
                                result = "[Cancelled by user]"
                                tool_error = True
                                self.session.add_tool_result(p["id"], result, is_error=True, client_id=p.get("client_id", ""))
                                yield create_tool_result(id=p["client_id"], content=result, is_error=True)
                                yield create_tool_call_end(id=p["client_id"])
                                turn_events += 1
                                break
                            if get_task in done:
                                live_messages = get_task.result()
                            else:
                                get_task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await get_task
                                continue
                            _wf_cancel.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await _wf_cancel
                            _wf_cancel = asyncio.create_task(self._cancel_event.wait())
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
                                    sub_agent_messages = [live_messages] if not isinstance(live_messages, list) else live_messages
                                    yield create_tool_progress(
                                        id=p["client_id"],
                                        tool_name=p["name"],
                                        status="running",
                                        sub_agent_messages=sub_agent_messages,
                                    )
                        else:
                            _wf_cancel.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await _wf_cancel
                        if not tool_error:
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
                        # Wrap execution in a cancel-aware wait so the user's
                        # Stop button takes effect immediately, even if the
                        # tool is mid-execution (e.g. long-running bash command).
                        exec_task = asyncio.create_task(
                            executor.execute(
                                tool_name=p["name"],
                                tool_args=p["args"],
                                execute_fn=lambda args, p=p: p["tool"].execute(**args),
                            )
                        )
                        cancel_task = asyncio.create_task(self._cancel_event.wait())
                        done, pending = await asyncio.wait(
                            {exec_task, cancel_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        cancel_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await cancel_task
                        if exec_task in done:
                            state = exec_task.result()
                        else:
                            # Cancelled: abort the tool execution
                            exec_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await exec_task
                            result = "[Cancelled by user]"
                            tool_error = True
                            self.session.add_tool_result(
                                p["id"], result, is_error=True, client_id=p.get("client_id", ""),
                            )
                            yield create_tool_result(id=p["client_id"], content=result, is_error=True)
                            yield create_tool_call_end(id=p["client_id"])
                            turn_events += 1
                            continue
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
                    await self._collect_tool_skill(p["name"])
                    await self._collect_doc_skills(p["args"])
                except Exception as exc:
                    result = f"Tool execution crashed: {type(exc).__name__}: {exc}"
                    tool_error = True

                result = _apply_result_budget(
                    result, p["tool"],
                    session_id=self.session.id or "",
                    tool_name=p.get("name", ""),
                )
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
                    client_id=p["client_id"],
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
                                extra_client_id = f"call_{self.session.turn_count}_extra_{idx}"
                                extra_tc_entry = {
                                    "id": tc["id"] or extra_client_id,
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": tc["arguments"],
                                    },
                                }
                                if extra_tc_entry["id"] != extra_client_id:
                                    extra_tc_entry["_client_id"] = extra_client_id
                                extra_tc.append(extra_tc_entry)
                            existing_tc = msg.get("tool_calls", [])
                            msg["tool_calls"] = existing_tc + extra_tc
                        if _extra_thinking:
                            existing_r = msg.get("reasoning_content", "") or ""
                            extra_r = "".join(_extra_thinking)
                            msg["reasoning_content"] = existing_r + extra_r
                        # Preserve segment ordering for intra-turn extra content
                        extra_segs = []
                        if _extra_thinking:
                            extra_segs.append({"kind": "thinking", "text": "".join(_extra_thinking)})
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
                            self.session.add_tool_result(tc["id"], err_msg, is_error=True, client_id=client_id)
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
                        self.session.add_tool_result(tc["id"], err_msg, is_error=True, client_id=client_id)
                        turn_events += 1
                        yield create_tool_call_end(id=client_id)
                        turn_events += 1
                        continue

                    # ── Spec approval gate for secondary tools ──────────
                    _spec_block = False
                    if slash_command_mode == "spec" and self.spec_engine is not None and (
                        tc["name"] in _WRITE_TOOL_NAMES or tc["name"] == "bash"
                    ):
                        _current = self.spec_engine.current_spec
                        _spec_approved = _current is not None and (
                            hasattr(_current, "status") and getattr(_current.status, "value", None) == "approved"
                        )
                        _spec_block = not _spec_approved
                    if _spec_block:
                        _spec_msg = (
                            "Blocked: Spec mode is active and the specification has not been "
                            "approved yet. Write tools are disabled. Present the specification "
                            "for user review first."
                        )
                        yield create_tool_result(id=client_id, content=_spec_msg, is_error=True)
                        self.session.add_tool_result(tc["id"], _spec_msg, is_error=True, client_id=client_id)
                        turn_events += 1
                        self.telemetry.record_tool_call(
                            tool_name=tc["name"], latency_ms=0, success=False, error_message=_spec_msg,
                        )
                        yield create_tool_call_end(id=client_id)
                        turn_events += 1
                        continue

                    is_safe = tool.is_concurrency_safe(args)
                    semantics = _infer_tool_semantics(tc["name"], tool)
                    self.session.metadata.setdefault("tool_semantics", {})[tc["name"]] = semantics
                    extra_prepared.append({
                        "id": tc["id"], "client_id": client_id,
                        "name": tc["name"], "args": args,
                        "tool": tool, "skip": False, "safe": is_safe,
                        "args_summary": _args_summary(args),
                        "semantics": semantics,
                    })

                # Permission & hooks for secondary tools
                if not self._cancelled():
                    for p in extra_prepared:
                        if self._cancelled():
                            break
                        if not _tool_retry_allowed(p, self._recent_tool_names):
                            retry_msg = (
                                "Blocked repeated high-risk tool retry. "
                                + p.get("semantics", {}).get("safe_fallback", "Gather more context before retrying.")
                            )
                            yield create_tool_result(id=p["client_id"], content=retry_msg, is_error=True)
                            self.session.add_tool_result(p["id"], retry_msg, is_error=True, client_id=p["client_id"])
                            turn_events += 1
                            self.telemetry.record_tool_call(
                                tool_name=p["name"], latency_ms=0,
                                success=False, error_message=retry_msg,
                            )
                            yield create_tool_call_end(id=p["client_id"])
                            turn_events += 1
                            p["skip"] = True
                            p["error"] = retry_msg
                            continue
                        permission = await self.safety.check_tool_permission(p["name"], p["args"])
                        if permission.behavior == "deny":
                            deny_reason = (
                                getattr(permission, "reason", "")
                                or _permission_reason(p["name"])
                                or "Permission denied by policy."
                            )
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
                            permission_granted = await self._wait_for_permission_decision(p["name"])
                            self._permission_event = None
                            await self.hook_system.emit_permission_response(
                                p["name"], permission_granted
                            )
                            if not permission_granted:
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
                                plan_err = "Plan rejected by user. Adjust your plan and try a different approach."
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

                # Execute secondary tools sequentially
                for p in extra_prepared:
                    if p.get("skip"):
                        continue
                    yield create_tool_progress(id=p["client_id"], tool_name=p["name"], status="running")
                    tool_start = time.time()
                    tool_error = False
                    try:
                        executor = RetryableExecutor(self.recovery_engine)
                        state = await executor.execute(
                            tool_name=p["name"],
                            tool_args=p["args"],
                            execute_fn=lambda args, p=p: p["tool"].execute(**args),
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
                        await self._collect_tool_skill(p["name"])
                        await self._collect_doc_skills(p["args"])
                    except Exception as exc:
                        result = f"Tool execution crashed: {type(exc).__name__}: {exc}"
                        tool_error = True
                    result = _apply_result_budget(
                        result, p["tool"],
                        session_id=self.session.id or "",
                        tool_name=p.get("name", ""),
                    )
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
                                    entry = self.session.add_artifact(ap_path, p["name"], diff_text="")
                                    yield Artifact(artifact=entry)
                            else:
                                diff_text = _extract_diff_text(p["name"], result)
                                entry = self.session.add_artifact(fp, p["name"], diff_text=diff_text)
                                yield Artifact(artifact=entry)
                        plan_items = _ensure_plan_items(p["name"], p["args"])
                        if plan_items:
                            yield PlanUpdate(plan_items=plan_items)
                            self.session.plan_items = plan_items

            # ── Post-tool compression check ──────────────────────────
            # After tool execution, check if the context has grown too large
            # and compact before the next iteration.  Mirrors Hermes agent's
            # post-response compression in conversation_loop.py.
            _post_tool_msgs = self.session.get_context_messages()
            if should_post_tool_compact(
                _post_tool_msgs,
                self.backend.context_window_size(),
                self.config.max_tokens,
            ):
                logger.info(
                    "[run] post-tool compression triggered turn=%d msgs=%d",
                    self.session.turn_count, len(_post_tool_msgs),
                )
                try:
                    self.session.set_compact_archive(_post_tool_msgs)
                    _post_compacted = await self.compact_engine.compact(
                        _post_tool_msgs, backend=self.backend,
                        turn_count=self.session.turn_count,
                        system_prompt=system_prompt or "",
                        enable_caching=self.config.enable_prompt_caching,
                        session_id=self.session.id or "",
                    )
                    if _post_compacted is not None:
                        self.session.replace_branch_messages(
                            self.session.active_branch_id, _post_compacted
                        )
                        self._compacted_this_turn = True
                        logger.info("[run] post-tool compact succeeded turn=%d", self.session.turn_count)
                        # Refresh memory so next turn sees any new memories written this turn
                        if self.memory_system is not None:
                            try:
                                self.memory_system.refresh()
                            except Exception:
                                logger.warning("[run] post-tool memory refresh failed", exc_info=True)
                except Exception as _ptc_err:
                    logger.warning("[run] post-tool compact failed: %s", _ptc_err)

            # ── Budget grace call ─────────────────────────────────────
            # When the token budget is exhausted, give the model one final
            # call to wrap up.  Mirrors Hermes agent's budget grace call.
            if _backend_usage:
                self._budget_state.add_usage(
                    _backend_usage.get("output_tokens", 0)
                )
                self.session.metadata[BudgetState.META_KEY] = self._budget_state.checkpoint()
            if self._budget_state.is_exhausted and self._budget_state.can_grace:
                self._budget_state.use_grace()
                if self._state is not None:
                    self._state.transitions.record(
                        TurnTransition.BUDGET_GRACE,
                        turn=self.session.turn_count,
                        detail=f"used={self._budget_state.used_tokens}/{self._budget_state.max_tokens}",
                    )
                logger.info("[run] budget exhausted, using grace call turn=%d", self.session.turn_count)
                self.session.add_message("user", build_grace_message())
                self._budget_state.grace_enabled = False

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
                if len(self._recent_tool_names) >= _STUCK_LOOP_THRESHOLD and not self._error_tool_names:
                    recent = self._recent_tool_names[-_STUCK_LOOP_THRESHOLD:]
                    if recent.count(recent[-1]) >= _STUCK_LOOP_THRESHOLD:
                        logger.warning(
                            "[run] repetitive tool-loop: %s turn=%d -- continuing session",
                            recent[-1], self.session.turn_count,
                        )
                        self._record_stuck_event(recent[-1])
                        self._set_task_stage("discover", reason="stuck loop recovery")
                        self._refresh_working_set(prompt, prepared)

            if not _backend_usage:
                _input_est = estimate_tokens(prompt or "")
                _output_est = estimate_tokens(assistant_content or "")
                _backend_usage = {"input_tokens": _input_est, "output_tokens": _output_est}
            self.telemetry.record_turn(
                turn_number=self.session.turn_count,
                event_count=turn_events,
                latency_ms=turn_latency,
                token_usage=_backend_usage,
                model=self.config.model,
                channel=self.session.metadata.get("channel", "normal"),
            )

            # Evolution: reflex + meta-cognition
            tool_outcomes: list[dict[str, Any]] = [
                {
                    "tool_name": p.get("name", ""),
                    "is_error": bool(p.get("is_error") or p.get("skip") and p.get("error")),
                    "semantic_type": p.get("semantics", {}).get("semantic_type", ""),
                }
                for p in prepared
            ]
            self._maybe_record_turn_summary(prompt, prepared, tool_outcomes)
            self._refresh_working_set(prompt, prepared)
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
            # Trigger background review every N turns (fire-and-forget)
            if self.reviewer is not None:
                asyncio.create_task(self.reviewer.on_turn_end(self))
            self.rollback.commit(self.session, f"turn_{self.session.turn_count}")

            # Clean up persistent terminal sessions from this turn.
            await _cleanup_terminal_sessions()

            # Record successful turn completion as NEXT_TURN
            if self._state is not None:
                self._state.transitions.record(
                    TurnTransition.NEXT_TURN,
                    turn=self.session.turn_count,
                )

        # ── Defense layer: close any half-finished tool_use block ────────
        # A cancel (user pause / abnormal exit) can break the
        # assistant.tool_calls -> tool_result pairing mid-turn: the assistant
        # message was already persisted (line ~3352) declaring N tool calls,
        # but only some got results before the loop broke out. That leaves an
        # orphan tool_use in session state -- which breaks history display,
        # rollback, and the next API call regardless of the sanitize gateway.
        # Fix the session state HERE (the single convergence point after the
        # while loop) so the persisted history is always self-consistent, not
        # just papered over at request time. Sanitize (loop.py:2594) remains
        # as a belt-and-suspenders safety net for any path that slips through.
        self._finalize_cancelled_turn()

        reason = "cancelled" if self._cancelled() else "max_tokens"
        if self._state is not None:
            self._state.transitions.record(
                TurnTransition.CANCELLED if reason == "cancelled" else TurnTransition.MAX_TURNS,
                turn=self.session.turn_count,
                detail=reason,
            )
        logger.warning("[run] session ending turn=%s max_turns=%s reason=%s",
                       self.session.turn_count, self.config.max_turns, reason)
        await self.hook_system.emit_session_end()
        yield create_finish(
            reason,
            usage=_last_backend_usage,
            compacted=self._compacted_this_turn,
        )

    async def _run_sub_agent(self, prompt: str,
                              system_prompt: str = "", max_turns: int = 0,
                              model: str = "", api_key: str = "",
                              base_url: str = "",
                              tool_policy: str = "all",
                              progress_callback: Any = None,
                              event_callback: Any = None,
                              session_id: str | None = None,
                              cache_context: Any = None) -> dict[str, Any]:
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

        logger.info("[sub_agent] _run_sub_agent | prompt_len=%s | sys_prompt_len=%s | tool_policy=%s",
                    len(prompt), len(system_prompt), tool_policy)
        logger.info("[sub_agent] prompt_text=%.300s", prompt)

        # Create a full EncreAgent (same as SessionManager.create_session / normal user flow).
        # Lazy-import to avoid circular dependency (agent.py imports EncreLoop from this module).
        from encre.agent import EncreAgent
        from encre.config import EncreConfig
        from encre.tools.builtin.agent import (
            MAX_SUB_AGENT_DEPTH,
        )
        from encre.tools.builtin.agent import (
            _enforce_tool_policy as _agent_enforce_policy,
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
                logger.info("[sub_agent] depth=%s reached MAX=%s, removed 'agent' tool from sub-agent registry",
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
            def _policy_hook(tool_name: str, _tool_input: dict[str, Any]) -> dict[str, Any] | None:
                # ``tool_input`` is part of the pre-tool hook signature
                # for future context-aware policies; current policy
                # decisions only depend on ``tool_name``.
                err = _agent_enforce_policy(tool_name, _tool_input)
                if err is not None:
                    return {"block": True, "block_reason": err}
                return None

            # Wrap the sub-agent loop's pre-tool hook to apply the policy.
            original_emit_pre_tool = sub_agent.loop.hook_system.emit_pre_tool

            async def _emit_pre_tool_with_policy(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
                result = _policy_hook(tool_name, tool_input)
                if result is not None:
                    return result
                return await original_emit_pre_tool(tool_name, tool_input)

            sub_agent.loop.hook_system.emit_pre_tool = _emit_pre_tool_with_policy  # type: ignore[assignment]
        # Add the prompt as a user message, exactly like ws.py does for normal input
        sub_agent.add_message("user", prompt)

        # If a cache context is provided, wrap the system prompt so the
        # sub-agent shares the same cached prefix bytes as the parent.
        # This is a no-op for backends that don't support prompt caching
        # (e.g. OpenAI) but provides a significant latency reduction for
        # Anthropic's prompt caching API.
        if cache_context is not None and hasattr(cache_context, "wrap_prompt"):
            system_prompt = cache_context.wrap_prompt(system_prompt or "")
            logger.info("[sub_agent] applied cache context from parent session=%s hash=%s",
                        getattr(cache_context, "parent_session_id", "?"),
                        getattr(cache_context, "prefix_hash", "?"))

        # Give the sub-agent a proper session ID. Callers such as the
        # automation scheduler can pre-allocate one so its live execution
        # record, stream events, and persisted transcript all share the same
        # identifier from the first event onward.
        import uuid
        sub_agent.session.id = session_id or sub_agent.session.id or str(uuid.uuid4())
        saved_session_id = sub_agent.session.id
        sub_agent.session.metadata["channel"] = "sub_agent"
        sub_agent.session.parent_session_id = self.session.id or ""

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
        cancelled = False
        try:
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
                    result_parts.append(f"### Tool Progress\n- id: `{event.id}`\n- name: `{event.tool_name}`\n- status: `{event.status}`\n")
                    # Forward nested sub-agent messages so the frontend sees
                    # live progress from sub-sub-agents all the way up.
                    if progress_callback is not None and event.sub_agent_messages:
                        with contextlib.suppress(Exception):
                            await progress_callback(event.sub_agent_messages)
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
                        f"### Tool Result\n- id: `{event.id}`\n- error: `{'yes' if event.is_error else 'no'}`\n\n```text\n{content}\n```\n"
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
        except asyncio.CancelledError:
            cancelled = True
            logger.info("[sub_agent] cancelled by parent, session_id={sid}", sid=saved_session_id)
        finally:
            # ALWAYS save the sub-agent session so it can be viewed later,
            # even on cancellation or exception.
            _save()
            self._child_loops.discard(sub_agent.loop)

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
        logger.info("[sub_agent] done session_id={sid} final_len={flen} msgs={mcount} cancelled={c}",
                      sid=saved_session_id, flen=len(final_text), mcount=len(sub_agent.session.messages), c=cancelled)
        logger.info("[sub_agent] final_text={t:.200s}", t=final_text)
        return {
            "content": final_text or ("[Cancelled by user]" if cancelled else "No output from sub-agent"),
            "messages": sub_agent.session.messages,
            "session_id": saved_session_id,
            "references": sub_refs,
        }


# ── Terminal session cleanup (called at end of each turn) ──────────


async def _cleanup_terminal_sessions() -> None:
    """Kill all persistent terminal sessions from the finished turn."""
    try:
        await TerminalSessionManager.instance().cleanup_all()
    except Exception:
        pass
