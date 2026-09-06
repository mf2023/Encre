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

"""Runtime-support mixin for the agent loop.

Groups the cross-phase helper methods of :class:`~encre.loop.runner.EncreLoop`:
working-set / task-stage bridges, milestone & turn summaries, delegation
(advisor sub-agents), stuck-loop bookkeeping, cancel handling, cancelled-turn
finalisation, streaming timeout wrapper, skill bridges and streaming tool
pre-execution.  Bodies are unchanged from the original monolith.
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from encre.utils.types import BackendError, BackendEvent
from encre.compact.engine import extract_user_requirements
from encre.logging_config import get_logger
from encre.recovery import RetryableExecutor
from encre.utils.loop_helpers import _PROMPT_CACHE_TTL_SECONDS

logger = get_logger(__name__)


class LoopSupportMixin:
    """Cross-phase runtime-support helpers."""

    def _cache_fresh(self, built_at: float, ttl: float = _PROMPT_CACHE_TTL_SECONDS) -> bool:
        """Return ``True`` if a cached item built at ``built_at`` is still valid.

        Args:
            built_at: Epoch timestamp when the item was cached.
            ttl: Time-to-live in seconds; defaults to the module-level
                ``_PROMPT_CACHE_TTL_SECONDS``.

        Returns:
            ``True`` when ``ttl`` seconds have not elapsed since ``built_at``.
        """
        return (time.time() - built_at) < ttl

    def _resolve_slot_budget(self) -> int:
        """Resolve the per-turn output slot budget.

        Honors a one-shot max-tokens override (consumed once used), else falls
        back to the configured default slot tokens when smaller than max_tokens.
        Centralized so both the pre-API pressure check and the chat call use
        the identical budget without fragile in-scope name probing.
        """
        if self._max_output_tokens_override:
            budget = self._max_output_tokens_override
            self._max_output_tokens_override = None
            return budget
        if self.config.default_slot_tokens and self.config.default_slot_tokens < self.config.max_tokens:
            return self.config.default_slot_tokens
        return self.config.max_tokens

    def _set_task_stage(self, stage: str, reason: str = "") -> None:
        """Update the working-set task stage and its reason string.

        Args:
            stage: The new stage label (e.g. ``discover``/``execute``/
                ``verify``/``report``).
            reason: Optional human-readable explanation for the transition.

        Returns:
            None.
        """
        self._working_set.set_task_stage(stage, reason)

    # 鈹€鈹€ P1 milestone summarisation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _maybe_write_milestone(
        self, context_msgs: list[dict[str, Any]],
    ) -> None:
        """Write a milestone summary if the working set decides it is due.

        Delegates to the working-set manager, passing the live backend and
        compaction engine so the manager can summarise context when the session
        reaches a configured milestone.

        Args:
            context_msgs: The current context messages to summarise.

        Returns:
            None.
        """
        await self._working_set.maybe_write_milestone(
            context_msgs, backend=self.backend, compact_engine=self.compact_engine,
        )

    def _update_user_requirements(self, messages: list[dict[str, Any]]) -> None:
        """Persist the user's core requirements after a compaction.

        Extracts the ``Primary Request and Intent`` section from the newest
        compact-summary block in ``messages`` and stores it in session
        metadata (``user_requirements_summary``), from where it is re-injected
        into the system prompt each turn.  Without this refresh the injected
        requirements stay stale after every compaction, so the model slowly
        forgets what the user actually asked for and starts repeating work.

        Args:
            messages: The compacted message list (result of a compaction).
        """
        try:
            summary = ""
            for m in reversed(messages or []):
                if m.get("is_compact_summary") or m.get("name") == "compact_summary":
                    content = m.get("content", "")
                    if isinstance(content, str) and content.strip():
                        summary = content
                        break
            if not summary:
                return
            req = extract_user_requirements(summary)
            if req:
                self._state_mgr.user_requirements_summary = req
                logger.debug("[compact] user requirements summary updated")
        except Exception:
            logger.warning("[compact] user requirements update failed", exc_info=True)

    def _infer_task_stage(self, prompt: str, prepared: list[dict[str, Any]] | None = None) -> str:
        """Infer the current task stage from the prompt and prepared tools.

        Args:
            prompt: The user prompt used to detect stage keywords.
            prepared: Optional prepared tool list whose semantics inform the
                stage.

        Returns:
            The inferred stage label as a string.
        """
        return self._working_set.infer_task_stage(prompt, prepared)

    def _summarize_args(self, args: dict[str, Any]) -> str:
        """Produce a short human-readable summary of a tool's arguments.

        Args:
            args: The tool argument mapping to summarise.

        Returns:
            A condensed string description of the arguments.
        """
        return self._working_set._summarize_args(args)

    def _refresh_working_set(self, prompt: str, prepared: list[dict[str, Any]] | None = None) -> None:
        """Refresh the working-set view from the latest prompt and tools.

        Args:
            prompt: The latest user prompt.
            prepared: The latest prepared tool list.

        Returns:
            None.
        """
        self._working_set.refresh_working_set(prompt, prepared)

    def _build_working_set_prompt(self) -> str:
        """Render the working-set section of the system prompt.

        Returns:
            The working-set prompt fragment as a string.
        """
        return self._working_set.build_working_set_prompt()

    def _maybe_record_turn_summary(
        self,
        prompt: str,
        prepared: list[dict[str, Any]],
        tool_outcomes: list[dict[str, Any]],
    ) -> None:
        """Record a per-turn summary into the working set when appropriate.

        Args:
            prompt: The turn's user prompt.
            prepared: The prepared tools for the turn.
            tool_outcomes: The outcomes of the tool executions this turn.

        Returns:
            None.
        """
        self._working_set.maybe_record_turn_summary(prompt, prepared, tool_outcomes)

    def _build_turn_summary_prompt(self) -> str:
        """Render the accumulated turn summaries as a prompt fragment.

        Returns:
            The turn-summary prompt fragment as a string.
        """
        return self._working_set.build_turn_summary_prompt()

    def _build_stage_prompt(self) -> str:
        """Render the current task-stage prompt fragment.

        Returns:
            The stage prompt fragment as a string.
        """
        return self._working_set.build_stage_prompt()

    def _should_delegate_sub_agent(self, prompt: str, prepared: list[dict[str, Any]]) -> tuple[bool, str, str]:
        """Decide whether to delegate the current task to a sub-agent.

        Delegation is only considered at the top level (``sub_agent_depth == 0``)
        to avoid nested sub-agents. The decision combines rule-based heuristics
        (current task stage plus counts of search/write tools, plus prompt
        keywords) with the evolution ``meta`` model's own ``should_delegate``
        judgement.

        Args:
            prompt: The user prompt, lower-cased internally for keyword checks.
            prepared: The prepared tool list whose ``semantics`` inform the
                counts.

        Returns:
            A ``(should_delegate, role, reason)`` tuple. ``role`` is one of
            ``"researcher"``, ``"executor"`` or ``"critic"`` and ``reason`` is a
            short explanation; both are empty strings when delegation is not
            recommended.
        """
        if self.sub_agent_depth > 0:
            return False, "", ""
        prompt_lower = (prompt or "").lower()
        stage = str(self._state_mgr.task_stage)
        tool_count = len(prepared)
        search_count = sum(1 for p in prepared if p.get("semantics", {}).get("semantic_type") in {"search", "read", "network"})
        write_count = sum(1 for p in prepared if p.get("semantics", {}).get("semantic_type") in {"write", "exec"})

        if stage == "discover" and (search_count >= 3 or any(x in prompt_lower for x in ("compare", "investigate", "research", "analyze", "璋冪爺"))):
            return True, "researcher", "parallel research would reduce repeated discovery turns"
        # WORKSPACE mode: before heavy implementation begins, force a
        # planner/architect pass so the coder is anchored to a written
        # design contract instead of free-styling.  The planner output is
        # persisted as a contract artifact (see save_architecture_contract)
        # and re-injected on every turn.
        if self._profile.workspace_delegation and stage == "execute" and write_count >= 2:
            return True, "planner", "workspace delivery requires a written architecture contract before implementation"
        if stage == "execute" and write_count >= 2 and tool_count >= 4:
            return True, "executor", "execution has become multi-step and benefits from a focused implementer"
        if stage in {"verify", "report"} or any(x in prompt_lower for x in ("review", "audit", "check regression", "inspect", "澶嶆牳")):
            return True, "critic", "a reviewer sub-agent can inspect regressions and residual risks"
        should_delegate, reason = self.meta.should_delegate(prompt)
        if should_delegate:
            return True, "researcher", reason
        return False, "", ""

    async def _maybe_run_advisor_sub_agent(self, prompt: str, prepared: list[dict[str, Any]]) -> str:
        """Run an advisor sub-agent and return its condensed guidance.

        First consults :meth:`_should_delegate_sub_agent`; if delegation is not
        recommended, or no configured sub-agent matches the chosen role, returns
        an empty string. Otherwise it spawns a short-lived advisor sub-agent
        (two turns max) with a focused prompt and returns up to 1500 characters
        of its reply. Success and failure are both recorded with the evolution
        ``meta`` tracker, and the delegation is appended to the session's
        delegate history (capped at 20 entries).

        Args:
            prompt: The parent task prompt.
            prepared: The prepared tool list used for the delegation decision.

        Returns:
            The advisor's trimmed guidance string, or ``""`` when no advisor ran.
        """
        should_delegate, delegate, reason = self._should_delegate_sub_agent(prompt, prepared)
        if not should_delegate or not delegate:
            return ""
        try:
            role = next((sa for sa in getattr(self.config, "sub_agents", []) if str(sa.name).lower() == delegate.lower()), None)
        except Exception:
            role = None
        if role is None:
            return ""
        # Build a tightly scoped prompt so the advisor stays concise and on-task.
        advisor_prompt = (
            f"Parent task: {prompt}\n\n"
            f"Current work phase: {self._state_mgr.task_stage}\n"
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
                # Persist planner/architect guidance as a binding architecture
                # contract artifact in the workspace (if any).  The contract is
                # re-injected into the system prompt on every turn, so the main
                # agent stays anchored to the agreed design instead of drifting.
                try:
                    from encre.contract import is_contract_role, save_architecture_contract
                    if is_contract_role(delegate):
                        ws = getattr(self.config, "workspace", "") or ""
                        _saved = save_architecture_contract(ws, delegate, content, parent_task=prompt)
                        if _saved:
                            logger.info("[delegate] saved %s contract artifact: %s", delegate, _saved)
                except Exception:
                    logger.warning("[delegate] failed to persist %s contract artifact", delegate, exc_info=True)
                history = list(self._state_mgr.delegate_history)
                history.append({
                    "delegate": delegate,
                    "reason": reason,
                    "turn": self.session.turn_count,
                    "timestamp": time.time(),
                })
                # Keep the delegate history bounded to the most recent 20 events.
                if len(history) > 20:
                    history = history[-20:]
                self._state_mgr.delegate_history = history
                self.meta.record_delegation(prompt, delegate, True)
                return content[:1500]
        except Exception:
            logger.warning("[delegate] advisor sub-agent failed", exc_info=True)
            self.meta.record_delegation(prompt, delegate, False)
        return ""

    def _build_stuck_recovery_prompt(self) -> str:
        """Build an instruction prompt injected when the loop is stuck.

        Returns an empty string when no stuck events have been recorded;
        otherwise returns a short remediation checklist that names the repeated
        tool-call signature and tells the model to diverge from the loop.

        Returns:
            The stuck-recovery prompt fragment, or ``""`` if not stuck.
        """
        stuck_events = self._state_mgr.stuck_events
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
        """Record a repeated tool-call signature as a stuck event.

        Appends a ``(turn, signature, timestamp)`` record to the session's stuck
        event list, keeping at most the most recent 20 entries.

        Args:
            signature: The tuple identifying the repeated tool-call pattern.

        Returns:
            None.
        """
        stuck = list(self._state_mgr.stuck_events)
        stuck.append({
            "turn": self.session.turn_count,
            "signature": " | ".join(signature),
            "timestamp": time.time(),
        })
        if len(stuck) > 20:
            stuck = stuck[-20:]
        self._state_mgr.stuck_events = stuck

    async def aclose(self) -> None:
        """Release backend resources (httpx clients, model memory, etc.).

        Returns:
            None.
        """
        if self.backend is not None:
            try:
                await self.backend.aclose()
            except Exception as e:
                logger.warning(f"Error closing backend: {e}", extra={"backend": type(self.backend).__name__})

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
        # Persist any partially-streamed assistant content (text/thinking) that
        # was never committed because the run was cancelled before a text block
        # completed. Without this, a refresh loses the tail the user already saw.
        pending_text = "".join(self._pending_stream_text).strip()
        pending_thinking = "".join(self._pending_stream_thinking).strip()
        if pending_text or pending_thinking:
            msgs = self.session.messages
            # Only append when the last message is a user message (i.e. no
            # committed assistant for the current turn yet). If a committed
            # assistant already exists, the content is already persisted.
            last_role = msgs[-1].get("role") if msgs else None
            if last_role == "user":
                msg_kwargs: dict[str, Any] = {}
                segs: list[dict[str, Any]] = []
                if pending_thinking:
                    msg_kwargs["reasoning_content"] = pending_thinking
                    segs.append({"kind": "thinking", "text": pending_thinking})
                if pending_text:
                    segs.append({"kind": "text", "text": pending_text})
                if segs:
                    msg_kwargs["segments"] = segs
                msg_kwargs["interrupted"] = True
                self.session.add_message("assistant", pending_text or None, **msg_kwargs)
                logger.info(
                    "[run] persisted partial streamed assistant (%d text, %d thinking chars)",
                    len(pending_text), len(pending_thinking),
                )
            self._pending_stream_text = []
            self._pending_stream_thinking = []

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

    # 鈹€鈹€ Skill bridges 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _activate_skills(self, prompt: str) -> tuple[str, str]:
        """Activate relevant skills for the prompt via the skill manager.

        Args:
            prompt: The user prompt used to match skill triggers.

        Returns:
            The ``(skills_block, sources_block)`` tuple from the manager.
        """
        return await self._skill_mgr.activate_skills(prompt)

    async def _collect_tool_skill(self, tool_name: str) -> None:
        """Collect a tool-referenced skill for ``tool_name`` in the background.

        Args:
            tool_name: The tool whose associated skill should be collected.

        Returns:
            None.
        """
        await self._skill_mgr.collect_tool_skill(tool_name)

    async def _collect_doc_skills(self, args: dict) -> None:
        """Collect documentation skills described by ``args``.

        Args:
            args: Arguments describing which doc skills to collect.

        Returns:
            None.
        """
        await self._skill_mgr.collect_doc_skills(args)

    def _render_active_tool_skills(self) -> str:
        """Render the active tool-skill block for inclusion in the prompt.

        Returns:
            The rendered tool-skill markdown string.
        """
        return self._skill_mgr.render_active_tool_skills()

    def _render_active_doc_skills(self) -> str:
        """Render the active documentation-skill block for the prompt.

        Returns:
            The rendered doc-skill markdown string.
        """
        return self._skill_mgr.render_active_doc_skills()

    def _render_skill_catalogue(self) -> str:
        """Render the full skill catalogue block for the prompt.

        Returns:
            The rendered skill-catalogue markdown string.
        """
        return self._skill_mgr.render_skill_catalogue()

    # 鈹€鈹€ Context building 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # Delegates to :class:`ContextBuilder`.  ``inject_code_index`` is kept
    # as a bridge because it is called from ``ws.py``.

    def inject_code_index(self, idx: Any) -> None:
        """Inject a pre-built code index into the context builder.

        Args:
            idx: The code index object to attach.

        Returns:
            None.
        """
        self._ctx_bldr.inject_code_index(idx)

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
