/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

import { ServerEvent, WorkspaceEntry, BranchUpdated, BranchSwitched, BranchRolledBack, TranscriptionResult, UsageStatsEvent } from "./types.js";
import * as state from "./state.js";
import { send } from "./ws.js";
import { Chat } from "./chat.js";
import { Tools } from "./tools.js";
import { Permissions } from "./permissions.js";
import { Settings } from "./settings.js";
import { t } from "./i18n.js";
import { handleEngineInstallRequest, handleEngineInstallProgress } from "./engine_install.js";
import type { AdapterTestResultEvent } from "./types.js";

let _adapterTestCallback: ((event: AdapterTestResultEvent) => void) | null = null;
let _automationJobsCallback: ((jobs: any[]) => void) | null = null;
let _automationHistoryCallback: ((history: any[]) => void) | null = null;
let _automationJobCreatedCallback: ((job: any) => void) | null = null;
let _automationJobCancelledCallback: ((jobId: string) => void) | null = null;
let _automationJobUpdatedCallback: (() => void) | null = null;
let _automationShowResultCallback: ((data: any) => void) | null = null;
let _automationStreamCallback: ((event: import("./types.js").AutomationStreamEvent) => void) | null = null;
export function onAdapterTestResult(cb: (event: AdapterTestResultEvent) => void): void {
  _adapterTestCallback = cb;
}

export function onAutomationJobs(cb: (jobs: any[]) => void): void {
  _automationJobsCallback = cb;
}

export function onAutomationHistory(cb: (history: any[]) => void): void {
  _automationHistoryCallback = cb;
}

export function onAutomationJobCreated(cb: (job: any) => void): void {
  _automationJobCreatedCallback = cb;
}

export function onAutomationJobUpdated(cb: () => void): void {
  _automationJobUpdatedCallback = cb;
}

export function onAutomationShowResult(cb: (data: any) => void): void {
  _automationShowResultCallback = cb;
}

export function onAutomationJobCancelled(cb: (jobId: string) => void): void {
  _automationJobCancelledCallback = cb;
}

export function onAutomationStreamEvent(cb: (event: import("./types.js").AutomationStreamEvent) => void): void {
  _automationStreamCallback = cb;
}
import { applyServerCommands, applyProjectCommands } from "./slash_commands.js";

let chat: Chat | null = null;
let tools: Tools | null = null;
let permissions: Permissions | null = null;
let _settings: Settings | null = null;
let permissionResolve: ((allowed: boolean) => void) | null = null;
let _sessionGeneration = 0;
let _requestedSessionId = "";
let _requestedSessionRequestId = "";
let _activeStreamSessionId = "";
let _toolCallGeneration: Record<string, number> = {};
let _validationResolve: (() => void) | null = null;
let _validationReject: ((reason: string) => void) | null = null;
let _onTranscription: ((text: string) => void) | null = null;

function _hasSessionId(event: { session_id?: string | null }): event is { session_id: string } {
  return typeof event.session_id === "string" && event.session_id.length > 0;
}

function _shouldRejectSessionScopedEvent(event: ServerEvent): boolean {
  if (event.type === "session_ready") return false;
  // Session lifecycle notifications must always be handled so the sidebar
  // stays in sync even when no session is currently active.
  if (event.type === "session_deleted" || event.type === "session_exported" || event.type === "session_renamed") return false;
  const activeSid = state.getState().sessionId;
  // Normalise: JSON null → undefined so falsy checks work correctly
  const eventSid = ((event as any).session_id as string | undefined) || undefined;

  // Any event carrying a session_id must belong to the currently active
  // session.  An explicit mismatch means it comes from a background session
  // and must not render in the active view.
  if (eventSid) {
    if (activeSid && eventSid !== activeSid) return true;
    // When the frontend has no active session (e.g. during workspace/mode
    // switches) drop session-scoped events entirely so a background session
    // cannot resurrect stale content in the empty content area.
    if (!activeSid) return true;
  }

  // For stream-bound events, REQUIRE a session_id.  The backend tags every
  // non-iClaw stream event with session_id, so an empty value means the
  // event originates from the iClaw/adapter pipeline which the desktop UI
  // must NOT render.  Also catch stale _activeStreamSessionId mismatches.
  if (_isSessionBoundStreamEvent(event.type)) {
    if (!eventSid) return true;
    if (_activeStreamSessionId && _activeStreamSessionId !== activeSid) return true;
  }

  return false;
}

function _isSessionBoundStreamEvent(type: ServerEvent["type"]): boolean {
  return type === "text_delta" ||
    type === "thinking_delta" ||
    type === "tool_call_start" ||
    type === "tool_call_delta" ||
    type === "tool_call_end" ||
    type === "tool_progress" ||
    type === "tool_result" ||
    type === "permission_request" ||
    type === "engine_install_request" ||
    type === "engine_install_progress" ||
    type === "workflow_started" ||
    type === "workflow_task" ||
    type === "workflow_completed" ||
    type === "finish" ||
    type === "error" ||
    type === "plan_update" ||
    type === "plan_proposal" ||
    type === "plan_mode_changed" ||
    type === "plan_resolved" ||
    type === "assistant_boundary" ||
    type === "compact";
}

function _requiresExplicitSessionId(type: ServerEvent["type"]): boolean {
  return _isSessionBoundStreamEvent(type) ||
    type === "messages_updated" ||
    type === "rollback_checkout" ||
    type === "telemetry" ||
    type === "context_usage" ||
    type === "artifacts_update" ||
    type === "references_update";
}

/** Create an assistant message when a queued run starts streaming.
 *  The submit() call only adds the user message (without starting an assistant),
 *  so we detect the transition here: the last message is user and no streaming
 *  assistant exists yet. */
function _ensureAssistantMessage(sessionId?: string): void {
  const st = state.getState();
  // Bail early if the event belongs to a different session than the one
  // being viewed — never mutate another session's messages from here.
  const resolvedSid = sessionId || st.sessionId;
  if (resolvedSid && resolvedSid !== st.sessionId) return;

  let msgs = st.messages;
  const last = msgs[msgs.length - 1];
  let shouldSendRun = false;
  if (last?.role !== "user" && st.queuedPrompts.length > 0 && !st.running) {
    const qp = st.queuedPrompts[0];
    state.addUserMessage(qp.text, qp.mode);
    msgs = state.getState().messages;
    shouldSendRun = true;
  }
  const lastAfter = msgs[msgs.length - 1];
  if (lastAfter?.role !== "user") return;
  const streamingAsst = msgs.find(m => m.role === "assistant" && m.isStreaming);
  if (streamingAsst) return;
  state.startAssistantMessage();
  if (shouldSendRun) {
    state.setRunning(true);
    state.shiftQueuedPrompt();
    state.setPendingQueueCount(Math.max(0, st.pendingQueueCount - 1));
    const text = typeof lastAfter.content === "string" ? lastAfter.content : "";
    if (text) {
      // Use the explicit session id passed in (already validated above
      // to match st.sessionId) so we always record the right owner.
      _activeStreamSessionId = st.sessionId || "";
      send({ type: "run", prompt: text, session_id: st.sessionId || undefined } as any);
    }
  }
}

function _eventSessionId(event: { session_id?: string }): string {
  return event.session_id || state.getState().sessionId || "";
}

export function setRequestedSessionId(sid: string, requestId = ""): void {
  _requestedSessionId = sid;
  _requestedSessionRequestId = requestId;
}

export function init(c: Chat, t: Tools, p: Permissions, s?: Settings): void {
  chat = c;
  tools = t;
  permissions = p;
  _settings = s ?? null;
}

export function waitForModelValidation(): Promise<void> {
  return new Promise((resolve, reject) => {
    _validationResolve = resolve;
    _validationReject = reject;
    setTimeout(() => {
      if (_validationReject) {
        _validationReject(t("stream.validationTimedOut"));
        _validationResolve = null;
        _validationReject = null;
      }
    }, 30000);
  });
}

export function setOnTranscription(cb: (text: string) => void): void {
  _onTranscription = cb;
}

export function handleEvent(event: ServerEvent): void {
  if (_requiresExplicitSessionId(event.type) && !_hasSessionId(event as { session_id?: string | null })) {
    return;
  }
  // Skip streaming events from background sessions -- they carry a session_id
  // that does not match the currently active session.  session_ready is exempt
  // because it IS the message that sets the current session_id.
  if (event.type !== "session_ready") {
    if (_shouldRejectSessionScopedEvent(event)) {
      return;
    }
  } else {
    // session_ready: only process if it matches the last user-requested session
    const eventSid = (event as any).session_id;
    const eventRequestId = (event as any).request_id as string | undefined;
    if (_requestedSessionRequestId && !eventRequestId) {
      console.log("[stream] REJECT session_ready missing requestId requested=%s sid=%s", _requestedSessionRequestId, eventSid);
      return;
    }
    if (_requestedSessionRequestId && eventRequestId && eventRequestId !== _requestedSessionRequestId) {
      console.log("[stream] REJECT session_ready requestId=%s requested=%s", eventRequestId, _requestedSessionRequestId);
      return;
    }
    if (_requestedSessionId && eventSid && eventSid !== _requestedSessionId) {
      console.log("[stream] REJECT session_ready eventSid=%s requested=%s", eventSid, _requestedSessionId);
      return;
    }
    // Guard against a WebSocket reconnect (or a stray startup reply) yanking
    // the user away from the session they are already viewing.  Once we have
    // an active sessionId, only accept a session_ready that explicitly
    // matches it (or is a genuine user-initiated resume/new).  Unsolicited
    // session_ready events for a different session are dropped.
    const _activeReadySid = state.getState().sessionId;
    if (
      _activeReadySid &&
      eventSid &&
      eventSid !== _activeReadySid &&
      !_requestedSessionRequestId
    ) {
      console.log("[stream] REJECT session_ready stray sid=%s active=%s", eventSid, _activeReadySid);
      return;
    }
  }
  switch (event.type) {
    case "session_ready": {
      // New session — increment generation to discard stale tool events.
      // Also clear _activeStreamSessionId because the previous stream may
      // belong to a different session (e.g. user clicked a different
      // session while one was running).  Without this reset, the old
      // stream sid would race against the new session and could either
      // (a) lock out legitimate events for the new session, or
      // (b) make the rejected-by-_shouldRejectSessionScopedEvent check
      //     miss the swap and let the old session's events render here.
      _sessionGeneration++;
      const previousSid = state.getState().sessionId;
      const nextSid = event.session_id || "";
      const switched = previousSid && previousSid !== nextSid;
      // Drop the stale active-stream pointer unless the new session is
      // explicitly continuing the same run.  Also discard any sub-agent view
      // state from the previous session so it cannot bleed into the new one.
      if (switched) {
        _activeStreamSessionId = "";
        _toolCallGeneration = {};
        state.setSubAgentView(null);
        state.clearSubAgentBreadcrumb();
      }
      console.log("[stream] session_ready received, messages:", event.messages?.length ?? 0, "session_id:", event.session_id, "gen:", _sessionGeneration);
      state.setSessionId(event.session_id);
      if (!(event as any).is_running) {
        _activeStreamSessionId = "";
      } else {
        _activeStreamSessionId = (event.session_id || "");
      }
      state.setConnected(true);
      state.setRunning(!!(event as any).is_running, event.session_id);
      if (event.messages && event.messages.length > 0) {
        state.loadSessionMessages(event.messages, event.session_id);
        console.log("[stream] loadSessionMessages done, state.messages.length:", state.getState().messages.length);
      } else {
        state.clearMessages(event.session_id);
      }
      if (event.plan_items) {
        state.setPlanItems(event.plan_items, event.session_id);
      } else {
        state.setPlanItems([], event.session_id);
      }
      if (event.artifacts) {
        state.setArtifacts(event.artifacts, event.session_id);
      }
      if (event.references) {
        state.setReferences(event.references, event.session_id);
      }
      // Restore branch state
      if (event.branches && event.active_branch_id) {
        state.setBranches(event.branches, event.active_branch_id, event.session_id);
      }
      // Re-render when session changes (skip sub-agent sessions)
      chat?.render?.();
      (window as any).__sessionInner?.render?.();
      send({ type: "list_sessions" });
      send({ type: "list_all_sessions" });
      send({ type: "list_workspaces" });
      send({ type: "get_config" } as any);
      _requestedSessionId = "";
      _requestedSessionRequestId = "";
      break;
    }

    case "text_delta": {
      // Defense-in-depth: even though the outer _shouldRejectSessionScopedEvent
      // already filters mismatched events, also guard inside the handler so a
      // token from session 1 can never be appended to session 2's snapshot
      // (e.g. if the outer filter is bypassed by a future code change).
      const _tdSid = _eventSessionId(event);
      const _activeTdSid = state.getState().sessionId;
      if (_tdSid && _activeTdSid && _tdSid !== _activeTdSid) break;
      _ensureAssistantMessage(_tdSid);
      state.appendTextDelta(event.text, _tdSid);
      chat?.render();
      _syncSessionEntry(_activeTdSid, state.getState());
      break;
    }

    case "thinking_delta": {
      const _thSid = _eventSessionId(event);
      const _activeThSid = state.getState().sessionId;
      if (_thSid && _activeThSid && _thSid !== _activeThSid) break;
      _ensureAssistantMessage(_thSid);
      state.appendThinkingDelta(event.text, _thSid);
      chat?.render();
      _syncSessionEntry(_activeThSid, state.getState());
      break;
    }

    case "tool_call_start": {
      // Track which session generation this tool call belongs to
      _toolCallGeneration[event.id] = _sessionGeneration;
      _ensureAssistantMessage(_eventSessionId(event));
      // Thinking phase ends when tool calls begin
      state.finishThinking();
      state.recordSegment("tool", event.id, _eventSessionId(event));
      // Find existing (may have been auto-created by deltas arriving first) or create
      let tc = state.findToolCall(event.id, _eventSessionId(event));
      if (tc) {
        tc.name = event.name || tc.name;
        tc.status = "pending";
      } else {
        state.addToolCall({
          id: event.id,
          name: event.name,
          params: {},
          status: "pending",
        }, _eventSessionId(event));
      }
      // Auto-open the sub-agent view when the main agent spawns a sub-agent,
      // so the user can see the inner process live (matching the spec the
      // main process produces when it streams). The view is still closable
      // and re-openable via the agent card. Gated by the
      // ``sub_agent_auto_open_view`` setting (default ON) — when disabled
      // the view only opens if the user clicks the agent card manually.
      //
      // Multi-call guard: when the main agent spawns MULTIPLE sub-agents
      // in a single turn (e.g. two parallel ``agent`` tool calls), the
      // second tool_call_start would clobber the first's view.  We only
      // auto-open the FIRST one in a turn; the rest must be opened
      // explicitly via the agent card.  A user who has already navigated
      // away (setSubAgentView was set to a different tc) also wins.
      if (event.name === "agent") {
        const tcf = state.findToolCall(event.id, _eventSessionId(event));
        if (tcf) {
          const raw = state.getState().settings?.sub_agent_auto_open_view;
          const autoOpen = raw === true || raw === "true" || raw === undefined;
          const cur = state.getState().subAgentView;
          // Only auto-open if no view is currently active.  If the user
          // already has a sub-agent open (or another tool_call_start
          // just opened one), do NOT overwrite their selection.
          if (autoOpen && cur == null) {
            state.setSubAgentView(tcf);
            chat?.renderForce?.();
          }
        }
      }
      tools?.requestRender();
      chat?.renderForce?.();
      break;
    }

    case "tool_call_delta": {
      // Reject stale tool events from previous sessions
      if (_toolCallGeneration[event.id] !== undefined && _toolCallGeneration[event.id] !== _sessionGeneration) break;
      // Accumulate params bytes into the tool call — create if not yet seen
      let tc = state.findToolCall(event.id, _eventSessionId(event));
      if (!tc) {
        state.addToolCall({
          id: event.id,
          name: "",
          params: {},
          status: "running",
        }, _eventSessionId(event));
        state.recordSegment("tool", event.id, _eventSessionId(event));
        tc = state.findToolCall(event.id, _eventSessionId(event));
      }
      if (tc) {
        const key = event.key;
        tc.params[key] = (tc.params[key] ?? "") + event.value;
        tc.status = "running";
        tools?.requestRender();
        // Only render chat when name is known — without it renderToolCall
        // falls through to a generic strip instead of the correct tool UI.
        if (tc.name) chat?.render();
      }
      break;
    }

    case "tool_call_end": {
      if (_toolCallGeneration[event.id] !== _sessionGeneration) break;
      // Try to parse accumulated JSON params into a structured form
      const tc = state.findToolCall(event.id, _eventSessionId(event));
      if (tc) {
        try {
          const rawArgs = tc.params["arguments"];
          if (typeof rawArgs === "string" && rawArgs) {
            tc.params = JSON.parse(rawArgs) as Record<string, unknown>;
          }
        } catch {
          // Keep raw string params if JSON parse fails
        }
      }
      // Force re-render so question card shows parsed params
      chat?.renderForce?.();
      break;
    }

    case "tool_progress":
      if (_toolCallGeneration[event.id] !== _sessionGeneration) break;
      state.updateToolCall(event.id, {
        status: event.status === "done" ? "done" : "running",
        subAgentMessages: event.sub_agent_messages ? state.restoreMessages(event.sub_agent_messages) : undefined,
        subAgentSessionId: (event as any).sub_agent_session_id,
      }, _eventSessionId(event));
      // Keep the sub-agent view's snapshot in sync with the latest tool
      // call state so the in-progress timeline keeps streaming.
      _syncSubAgentView(event.id);
      tools?.requestRender();
      chat?.renderForce?.();
      break;

    case "tool_result":
      if (_toolCallGeneration[event.id] !== undefined && _toolCallGeneration[event.id] !== _sessionGeneration) break;
      state.updateToolCall(event.id, {
        result: event.content,
        isError: event.is_error,
        status: "done",
        subAgentMessages: event.sub_agent_messages ? state.restoreMessages(event.sub_agent_messages) : undefined,
        subAgentSessionId: (event as any).sub_agent_session_id,
      }, _eventSessionId(event));
      _syncSubAgentView(event.id);
      tools?.requestRender();
      chat?.render();
      _syncSessionEntry(state.getState().sessionId, state.getState());
      break;

    case "permission_request":
      if (permissionResolve) {
        permissionResolve(false);
      }
      permissions?.show(
        event.tool_name,
        event.reason,
        (allowed: boolean) => {
          send({
            type: "respond_permission",
            tool_name: event.tool_name,
            decision: allowed,
          });
          permissionResolve = null;
          permissions?.hide();
        }
      );
      // Ensure the main chat area updates immediately so users see the
      // tool call card with a "pending" indicator rather than a frozen UI.
      chat?.renderForce?.();
      break;

    case "engine_install_request":
      // Backend raised a request for the user (NOT the LLM) to
      // provision a browser engine.  Pop the dialog chain; the
      // choice is shipped back via the engine_install_response
      // message so the original tool action resumes.
      void handleEngineInstallRequest({
        request_id: (event as any).request_id,
        engine: (event as any).engine,
        title: (event as any).title,
        body: (event as any).body,
        hint: (event as any).hint,
        options: (event as any).options,
      });
      break;

    case "engine_install_progress":
      handleEngineInstallProgress({
        request_id: (event as any).request_id,
        pct: (event as any).pct,
        message: (event as any).message,
        sub_message: (event as any).sub_message,
        indeterminate: (event as any).indeterminate,
        status: (event as any).status,
        message_code: (event as any).message_code,
        message_args: (event as any).message_args,
        sub_message_code: (event as any).sub_message_code,
        sub_message_args: (event as any).sub_message_args,
      });
      break;

    case "finish": {
      if (!_hasSessionId(event)) break;
      if (event.reason === "error" || event.error) {
        console.log("[stream] finish with error:", event.reason, event.error);
      }
      // Background session finished — update its snapshot's running flag
      // so the state is correct when the user switches back, but don't
      // touch the active session's UI state.
      if (event.session_id && event.session_id !== state.getState().sessionId) {
        state.setRunning(false, event.session_id);
        break;
      }
      _activeStreamSessionId = "";
      state.setRunning(false, _eventSessionId(event));
      // Store server-side message ID before finishing — emit() in
      // finishAssistantMessage will trigger segment cache save with this set.
      const sid = _eventSessionId(event);
      const lastMsg = state.getLastAssistantMessage(sid);
      if (lastMsg) {
        if (event.assistant_message_id) {
          lastMsg.serverId = event.assistant_message_id;
        }
        // Capture turn status card data from finish event
        if (event.reason === "error" || event.error) {
          lastMsg.errorMessage = event.error || "";
          lastMsg.errorCode = event.reason === "error" ? "execution_error" : "unknown";
        } else if (event.reason === "interrupted" || event.reason === "cancelled") {
          if (event.reason === "cancelled") {
            lastMsg.cancelledText = t("chat.abnormalInterruption");
          } else {
            lastMsg.interruptedReason = event.error || event.reason;
          }
        } else if (event.reason === "complete" || event.reason === "ok" || event.reason === "stop") {
          lastMsg.turnStatusText = t("chat.taskComplete");
        }
      }
      if (event.usage) {
        const u = event.usage as Record<string, unknown>;
        const input = typeof u.input_tokens === "number" ? u.input_tokens : 0;
        const output = typeof u.output_tokens === "number" ? u.output_tokens : 0;
        const total = typeof u.total_tokens === "number" ? u.total_tokens : input + output;
        state.setTokenUsage({
          input_tokens: input,
          output_tokens: output,
          total_tokens: total,
        }, sid);
        state.finishAssistantMessage({
          input_tokens: input,
          output_tokens: output,
          total_tokens: total,
        }, sid);
      } else {
        state.finishAssistantMessage(undefined, sid);
      }
      const btnStop = document.getElementById("btn-stop");
      btnStop?.classList.remove("cancelling");
      if (btnStop) btnStop.style.pointerEvents = "";
      _ensureAssistantMessage();
      chat?.render();
      (window as any).__sessionInner?.render?.();
      send({ type: "list_sessions" });
      break;
    }

    case "run_queued":
      state.setPendingQueueCount(event.position);
      chat?.render();
      break;

    case "pong":
      state.setConnected(true);
      break;

    case "error":
      if (!_hasSessionId(event)) break;
      _activeStreamSessionId = "";
      // Background session error — update snapshot without touching active UI.
      if (event.session_id && event.session_id !== state.getState().sessionId) {
        state.setRunning(false, event.session_id);
        break;
      }
      state.setRunning(false, _eventSessionId(event));
      state.clearPendingQueueCount();
      // Mark last assistant message as errored and capture error data
      const lastMsg = state.getLastAssistantMessage(_eventSessionId(event));
      if (lastMsg) {
        lastMsg.hasError = true;
        lastMsg.errorMessage = event.message;
        lastMsg.errorCode = event.code;
      }
      state.addNotification({
        id: crypto.randomUUID(),
        type: "error",
        title: t("stream.notificationError"),
        message: event.message,
        timestamp: Date.now(),
        read: false,
      });
      break;

    case "configured":
      console.log("[stream] configured event, config keys:", Object.keys(event.config ?? {}));
      state.setSettings({ ...state.getState().settings, ...event.config });
      break;

    case "telemetry":
      if (!_hasSessionId(event)) break;
      // Ignore telemetry updates for non-active sessions so background
      // sessions cannot overwrite the canvas panel currently shown.
      if (event.session_id && event.session_id !== state.getState().sessionId) break;
      state.setTelemetry(event.data, event.session_id);
      break;

    case "usage_stats":
      state.setUsageStats(event.stats);
      break;

    case "gateway_status":
      state.setGatewayStatus(event.status);
      break;

    case "adapter_test_result":
      // Dispatch to registered callback
      if (typeof _adapterTestCallback === "function") {
        _adapterTestCallback(event as any);
      }
      break;

    case "plan_update":
      if (!_hasSessionId(event)) break;
      state.setPlanItems(event.plan_items, _eventSessionId(event));
      chat?.render();
      (window as any).__sessionInner?.render?.();
      break;

    case "plan_proposal":
      if (!_hasSessionId(event)) break;
      state.addPlanProposal(event, _eventSessionId(event));
      break;

    case "plan_mode_changed":
      if (!_hasSessionId(event)) break;
      state.setPlanModeActive(event.active, _eventSessionId(event));
      (window as any).__sessionInner?.render?.();
      break;

    case "plan_resolved":
      if (!_hasSessionId(event)) break;
      state.removePlanProposal(event.proposal_id, _eventSessionId(event));
      (window as any).__sessionInner?.render?.();
      break;

    case "models_list":
      state.setAvailableModels(event.models);
      break;

    case "sessions_list":
      state.setSessionsList(event.sessions);
      window.electronAPI?.traySessionsUpdate?.(event.sessions);
      if (state.getState().sessionId) {
        const cur = (event.sessions as any[]).find(
          (s: any) => s.session_id === state.getState().sessionId
        );
        if (cur && cur.is_running !== state.getState().running) {
          state.setRunning(cur.is_running);
        }
      }
      break;

    case "sessions_all": {
      // Tray popup needs both normal + iwork sessions at once.
      const normal = (event as any).normal || [];
      const iwork = (event as any).iwork || [];
      state.setTraySessions(normal, iwork);
      window.electronAPI?.traySessionsBothUpdate?.({ normal, iwork });
      break;
    }

    case "config_data": {
      const cfg = event.config as Record<string, unknown>;
      if (cfg.models && Array.isArray(cfg.models)) {
        state.setModelConfigs(cfg.models as any[], (cfg.active_model_index as number) || 0);
      }
      if (cfg.mcp_servers && Array.isArray(cfg.mcp_servers)) {
        // Normalize old-format MCP servers to new standard format
        const normalized = (cfg.mcp_servers as any[]).map(srv => {
          if (srv.type) return srv; // already new format
          return {
            name: srv.name,
            type: srv.transport || "stdio",
            ...(srv.transport === "http"
              ? { url: srv.server_url || "", timeout: srv.http_timeout ?? 60, headers: srv.headers || {} }
              : { command: srv.command || "", args: srv.args || [] }),
            ...(srv.cwd ? { cwd: srv.cwd } : {}),
            ...(srv.env ? { env: srv.env } : {}),
            ...(srv.disabled ? { disabled: true } : {}),
          };
        });
        state.setMcpServers(normalized);
      }
      if (cfg.enabled_skills && Array.isArray(cfg.enabled_skills)) {
        state.setEnabledSkills(cfg.enabled_skills as string[]);
      }
      if (cfg.available_skills && Array.isArray(cfg.available_skills)) {
        state.setSkillsList(cfg.available_skills as any[]);
      }
      if (cfg.model_catalog && typeof cfg.model_catalog === "object") {
        state.setModelCatalog(cfg.model_catalog as any);
      }
      if (cfg.mcp_catalog && typeof cfg.mcp_catalog === "object") {
        state.setMcpCatalog(cfg.mcp_catalog as any);
      }
      if (cfg.custom_slash_commands && Array.isArray(cfg.custom_slash_commands)) {
        state.setCustomCommands(cfg.custom_slash_commands as any[]);
        applyServerCommands(cfg.custom_slash_commands as any[]);
      }
      if (cfg.slash_commands && Array.isArray(cfg.slash_commands)) {
        applyProjectCommands(cfg.slash_commands as any[]);
      }
      window.dispatchEvent(new CustomEvent("slash-commands-updated"));
      if (cfg.sub_agents && Array.isArray(cfg.sub_agents)) {
        state.setSubAgents(cfg.sub_agents as any[]);
      }
      state.setAgentConfig({
        system_prompt: (cfg.system_prompt as string) || "",
        specialty: (cfg.default_specialty as string) || "general",
        permission_mode: (cfg.permission_mode as string) || "default",
        max_turns: (cfg.max_turns as number) ?? 0,
      });
      // Sync workspace mode from server config (don't override active workspace)
      if (!state.getState().activeWorkspace) {
        if (cfg.workspace_mode === "iwork") {
          state.setWorkspaceMode("iwork");
        } else {
          state.setWorkspaceMode("normal");
        }
      }
      // Surface general settings from backend config into state.settings
      // so the settings panel shows the correct values on page refresh.
      const _settingsUpdate: Record<string, unknown> = {};
      const _generalKeys = [
        "shortcut_send_mode", "default_link_behavior",
        "default_markdown_behavior", "startup_session_mode", "startup_session_behavior",
      ] as const;
      for (const key of _generalKeys) {
        const val = cfg[key];
        if (val !== undefined && val !== null && val !== "") {
          _settingsUpdate[key] = val;
        }
      }
      if (Object.keys(_settingsUpdate).length > 0) {
        state.setSettings({ ...state.getState().settings, ..._settingsUpdate });
      }
      // Sync keybinds from backend config
      const cfgAny = cfg as any;
      if (cfgAny.keybinds && typeof cfgAny.keybinds === "object" && Array.isArray(cfgAny.keybinds.keybinds)) {
        state.setSettings({ ...state.getState().settings, keybinds: cfgAny.keybinds });
      }
      // Sync adapter_* keys from backend config into settings (for gateway panel)
      const _adapterKeys = Object.keys(cfgAny).filter(k => k.startsWith("adapter_"));
      if (_adapterKeys.length > 0) {
        const _adapterSettings: Record<string, unknown> = {};
        for (const k of _adapterKeys) {
          _adapterSettings[k] = cfg[k];
        }
        state.setSettings({ ...state.getState().settings, ..._adapterSettings });
      }
      break;
    }

    case "models_updated": {
      console.log("[stream] models_updated, count:", event.models?.length, "active_index:", event.active_model_index);
      state.setModelConfigs(event.models, event.active_model_index);
      break;
    }

    case "skills_updated":
      state.setEnabledSkills(event.enabled_skills);
      if (event.available_skills) {
        state.setSkillsList(event.available_skills);
      }
      break;

    case "skills_list":
      state.setSkillsList(event.skills);
      break;

    case "mcp_updated":
      console.log("[stream] mcp_updated, count:", event.mcp_servers?.length);
      state.setMcpServers((event.mcp_servers as any[] || []).map(srv => {
        if (srv.type) return srv;
        return {
          name: srv.name,
          type: srv.transport || "stdio",
          ...(srv.transport === "http"
            ? { url: srv.server_url || "", timeout: srv.http_timeout ?? 60, headers: srv.headers || {} }
            : { command: srv.command || "", args: srv.args || [] }),
          ...(srv.cwd ? { cwd: srv.cwd } : {}),
          ...(srv.env ? { env: srv.env } : {}),
          ...(srv.disabled ? { disabled: true } : {}),
        };
      }));
      break;

    case "agent_updated": {
      const ac = event.config as Record<string, unknown>;
      state.setAgentConfig({
        system_prompt: (ac.system_prompt as string) || "",
        specialty: (ac.specialty as string) || "general",
        permission_mode: (ac.permission_mode as string) || "default",
        max_turns: (ac.max_turns as number) ?? 0,
      });
      break;
    }

    case "search_results":
      state.setSearchResults(event.results);
      break;

    case "memory_list":
      state.setMemoryList(event.entries);
      break;

    case "global_rules_list":
      state.setGlobalRulesList(event.rules);
      break;

    case "project_rules_list":
      state.setProjectRulesList(event.rules);
      break;

    case "project_hooks_list":
      state.setProjectHooksList(event.hooks);
      break;

    case "global_rule_saved":
    case "global_rule_deleted":
      send({ type: "list_global_rules" });
      break;

    case "global_rule_content":
      state.setViewingGlobalRule({ name: event.name, content: event.content, error: event.error });
      break;

    case "profile_data":
      state.setProfile(event.profile);
      break;

    case "index_status":
      state.setIndexStatus(event.status as any);
      state.setIndexFiles(event.files);
      if (event.progress !== undefined) {
        state.setIndexProgress(event.progress);
      }
      // Also update per-workspace index state for sidebar tree
      if ((event as any).workspace_id) {
        state.updateWorkspaceIndex(
          (event as any).workspace_id,
          event.status as string,
          event.files,
        );
      }
      break;

    case "gitignore_content":
      state.setGitignoreContent(event.content);
      break;

    case "documents_list":
      state.setDocsList(event.documents);
      break;

    case "document_added":
    case "document_updated":
    case "document_removed":
    case "document_error":
      send({ type: "list_documents" } as any);
      break;

    case "skill_installed":
      if (event.available_skills) {
        state.setSkillsList(event.available_skills);
      }
      break;

    case "skill_install_error":
      break;

    case "skill_uninstalled":
      if (event.available_skills) {
        state.setSkillsList(event.available_skills);
      }
      break;

    case "sub_agents_updated":
      console.log("[stream] sub_agents_updated, count:", event.sub_agents?.length);
      state.setSubAgents(event.sub_agents);
      break;

    case "memory_detail":
      state.setMemoryDetail({ path: event.path, content: event.content, error: event.error });
      break;

    case "compact":
      if (!_hasSessionId(event as any)) break;
      state.addCompactEvent({
        old_count: (event as any).old_count,
        new_count: (event as any).new_count,
        old_tokens: (event as any).old_tokens,
        new_tokens: (event as any).new_tokens,
      }, _eventSessionId(event as any));
      break;

    case "context_usage":
      if (!_hasSessionId(event as any)) break;
      state.updateContextUsage(
        (event as any).context_tokens,
        (event as any).context_window,
        _eventSessionId(event as any),
      );
      (window as any).__sessionInner?.render?.();
      break;

    case "artifacts_update":
      if (!_hasSessionId(event)) break;
      // Append new artifacts; the server sends one at a time during streaming.
      state.appendArtifacts(event.artifacts, _eventSessionId(event));
      (window as any).__sessionInner?.render?.();
      break;

    case "references_update":
      if (!_hasSessionId(event)) break;
      // Append new references; the server sends one at a time during streaming.
      state.appendReferences(event.references, _eventSessionId(event));
      (window as any).__sessionInner?.render?.();
      break;

    case "messages_updated":
      if (!_hasSessionId(event)) break;
      if (_shouldRejectSessionScopedEvent(event)) break;
      // If the user already started a new run (submit() raced ahead of this
      // response), do NOT override the running state or replace messages.
      if (state.getState().running) {
        if (event.session_id) {
          state.setSessionId(event.session_id);
        }
        break;
      }
      // Sync session ID and reset running state for reliable subsequent sends.
      // Do NOT call resetChat() on empty messages — that clears sessionId and
      // locks the user out of sending further messages on the same session.
      if (event.session_id) {
        state.setSessionId(event.session_id);
      }
      state.setRunning(false, _eventSessionId(event));
      state.loadSessionMessages(state.applyPendingRollbackEdit(event.messages || []), _eventSessionId(event));
      state.setPlanItems(event.plan_items || [], _eventSessionId(event));
      if ((event as any).artifacts) {
        state.setArtifacts((event as any).artifacts, _eventSessionId(event));
      }
      if ((event as any).references) {
        state.setReferences((event as any).references, _eventSessionId(event));
      }
      chat?.render();
      (window as any).__sessionInner?.render?.();
      // Sync sidebar session entry (message count, preview)
      _syncSessionEntry(event.session_id, state.getState());
      break;

    case "rollback_checkout":
      if (!_hasSessionId(event)) break;
      if (_shouldRejectSessionScopedEvent(event)) break;
      // Server has truncated the session to the chosen commit and persisted it.
      // Mirror that on the client so the UI actually reflects the rollback.
      if (event.session_id) {
        state.setSessionId(event.session_id);
      }
      state.setRunning(false, _eventSessionId(event));
      state.loadSessionMessages(state.applyPendingRollbackEdit(event.messages || []), _eventSessionId(event));
      state.setPlanItems(event.plan_items || [], _eventSessionId(event));
      if ((event as any).artifacts) {
        state.setArtifacts((event as any).artifacts, _eventSessionId(event));
      }
      if ((event as any).references) {
        state.setReferences((event as any).references, _eventSessionId(event));
      }
      _syncSessionEntry(event.session_id, state.getState());
      // Restore the last user message into the input box for re-editing
      let userInput = (event as any).user_input as string | undefined;
      if (userInput) {
        if (userInput.includes("<terminal>") || userInput.includes("<attach ")) userInput = "";
        const input = document.getElementById("prompt-input") as HTMLElement | null;
        if (input) { input.textContent = userInput; input.focus(); }
      }
      // Restore mode chip AFTER user_input (which clears the input via textContent)
      {
        const msgs = state.getState().messages;
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === "user" && (msgs[i] as any).mode) {
            state.restoreInputModeChip((msgs[i] as any).mode);
            break;
          }
        }
      }
      // Restore attachment chips from the rolled-back user message
      {
        const msgs = state.getState().messages;
        for (let i = msgs.length - 1; i >= 0; i--) {
          const refs = msgs[i].fileRefs;
          if (msgs[i].role === "user" && refs && refs.length > 0) {
            const atts: import("./types.js").AttachmentMeta[] = [];
            for (const r of refs) {
              if (r.mime_type === "text/x-terminal") continue;
              if (r.path) {
                atts.push({ name: r.name, path: r.path, content: "", mime_type: r.mime_type || "", size: r.size, is_binary: false });
              }
            }
            if (atts.length > 0) state.addAttachments(atts);
            break;
          }
        }
      }
      _syncSessionEntry(event.session_id, state.getState());
      chat?.renderForce?.();
      (window as any).__sessionInner?.render?.();
      break;

    case "session_deleted":
      // Local removal — the server has already deleted it, so don't
      // re-fetch the session list (it may resurrect the session from
      // other data sources like the EventRouter).  Rely on the local
      // state filter to keep the UI consistent.
      state.removeSessionById(event.session_id);
      // If the deleted session is currently open, clear chat immediately.
      if (state.getState().sessionId === event.session_id) {
        state.setSessionId("");
        state.clearMessages();
        state.setRunning(false, "");
      }
      chat?.render();
      (window as any).__sessionInner?.render?.();
      // Refresh automation history — the deleted session may be a sub-agent
      // session shown in the automation history timeline, which uses its own
      // independent this.history array (not global sessionsList).
      send({ type: "automation_get_history" });
      break;

    case "session_exported":
      downloadMarkdownFile(event.markdown, event.filename || event.session_id);
      break;

    case "session_renamed":
      send({ type: "list_sessions" });
      (window as any).__sessionInner?.render?.();
      break;

    case "model_validated":
      if (_validationResolve) {
        _validationResolve();
        _validationResolve = null;
        _validationReject = null;
      }
      break;

    case "model_validation_error":
      if (_validationReject) {
        _validationReject(event.message);
        _validationResolve = null;
        _validationReject = null;
      }
      break;

    case "workspace_opened":
      state.setWorkspaces(event.workspaces);
      state.setActiveWorkspace(event.path);
      state.setWorkspaceMode("iwork");
      state.setSessionsList([]);
      // Capture initial index state for sidebar tree display
      if ((event as any).index_status) {
        state.updateWorkspaceIndex(
          (event as any).id || "",
          (event as any).index_status,
          (event as any).index_files || 0,
        );
      }
      // If a tray-driven resume is pending after opening this workspace, fire it.
      // IMPORTANT: list_sessions is NOT sent here — it fires AFTER resume's
      // session_ready completes (see session_ready handler), ensuring the
      // target session is already in memory when the sidebar tree queries it.
      const pending = (window as any).__pendingTrayResume;
      if (pending && pending.sessionId) {
        (window as any).__pendingTrayResume = null;
        state.setSessionId(pending.sessionId);
        send({ type: "resume", session_id: pending.sessionId, request_id: pending.requestId });
      }
      // Refresh tray dual cache so both normal and iwork lists are complete
      send({ type: "list_all_sessions" });
      (window as any).__sessionInner?.render?.();
      break;

    case "workspace_closed":
      state.setActiveWorkspace("");
      state.setWorkspaceMode("normal");
      state.setSessionsList([]);
      send({ type: "list_sessions" });
      state.setRunning(false);
      (window as any).__sessionInner?.render?.();
      break;

    case "workspaces_list":
      state.setWorkspaces(event.workspaces);
      (window as any).__sessionInner?.render?.();
      break;

    case "workspace_removed":
      state.setWorkspaces(event.workspaces);
      // If the deleted workspace was active, clean up state
      if (state.getState().activeWorkspace === (event as any).path) {
        state.setActiveWorkspace("");
        state.setWorkspaceMode("normal");
        state.setSessionsList([]);
        state.setRunning(false);
        send({ type: "list_sessions" });
      }
      (window as any).__sessionInner?.render?.();
      break;

    case "assistant_boundary":
      // Intra-turn segment marker — no longer creates a new message bubble.
      // The session now keeps a single assistant message per user turn, so
      // splitting on this boundary would leave an orphan "empty" bubble and
      // duplicate the assistant output in the timeline.
      _syncSessionEntry(state.getState().sessionId, state.getState());
      break;

    case "branch_updated": {
      const ev = event as BranchUpdated;
      if (_shouldRejectSessionScopedEvent(ev)) break;
      state.setBranches(ev.branches, ev.active_branch_id, ev.session_id);
      if (ev.messages) {
        state.loadSessionMessages(ev.messages, ev.session_id);
      }
      chat?.render();
      (window as any).__sessionInner?.render?.();
      break;
    }

    case "branch_switched": {
      const ev = event as BranchSwitched;
      if (_shouldRejectSessionScopedEvent(ev)) break;
      state.setBranches(ev.branches, ev.branch_id, ev.session_id);
      state.loadSessionMessages(state.applyPendingRollbackEdit(ev.messages), ev.session_id);
      if (ev.artifacts) {
        state.setArtifacts(ev.artifacts, ev.session_id);
      }
      if (ev.references) {
        state.setReferences(ev.references, ev.session_id);
      }
      // Ensure the session is marked as not running and the session ID is
      // synced so the next user message is sent immediately rather than
      // being queued waiting for a "running=false" transition that never comes.
      state.setRunning(false, ev.session_id);
      state.setSessionId(ev.session_id);
      chat?.render();
      (window as any).__sessionInner?.render?.();
      break;
    }

    case "branch_rolled_back": {
      const ev = event as BranchRolledBack;
      state.removeBranchMessages(new Set(ev.removed_message_ids), ev.session_id);
      chat?.render();
      (window as any).__sessionInner?.render?.();
      break;
    }

    case "transcription_result": {
      const ev = event as TranscriptionResult;
      _onTranscription?.(ev.text);
      break;
    }

    case "automation_jobs_list":
      _automationJobsCallback?.(event.jobs);
      break;

    case "automation_job_history":
      // Store in global state so automation panel reads from the same
      // data source as general/workspace mode (sessionsList).
      state.setAutomationHistory(event.history || []);
      break;

    case "automation_job_created":
      _automationJobCreatedCallback?.(event);
      // Refresh list after creating
      send({ type: "automation_list_jobs" });
      break;

    case "automation_job_cancelled":
      _automationJobCancelledCallback?.(event.job_id);
      send({ type: "automation_list_jobs" });
      break;

    case "automation_job_toggled":
      send({ type: "automation_list_jobs" });
      break;

    case "automation_job_updated":
      _automationJobUpdatedCallback?.();
      send({ type: "automation_list_jobs" });
      break;

    case "automation_job_deleted":
      send({ type: "automation_list_jobs" });
      send({ type: "automation_get_history" });
      break;

    case "automation_stream_event":
      _automationStreamCallback?.(event as import("./types.js").AutomationStreamEvent);
      break;

    case "automation_job_update":
      // A job's state changed (e.g. running → completed) — refresh lists
      // Use inline history data so the view updates immediately
      if ((event as any).history && _automationHistoryCallback) {
        _automationHistoryCallback((event as any).history);
      }
      // If the backend included result data, show it in the chat area
      if ((event as any).result && _automationShowResultCallback) {
        _automationShowResultCallback((event as any).result);
      }
      send({ type: "automation_list_jobs" });
      break;

    case "workflow_started":
      if (_shouldRejectSessionScopedEvent(event)) break;
      state.setWorkflowState({
        workflowId: (event as any).workflow_id,
        goal: (event as any).goal,
        totalTasks: (event as any).total_tasks,
        taskIds: (event as any).task_ids,
        active: true,
        completedCount: 0,
        failedCount: 0,
        skippedCount: 0,
      });
      chat?.render();
      break;

    case "workflow_task":
      if (_shouldRejectSessionScopedEvent(event)) break;
      state.updateWorkflowTask({
        workflowId: (event as any).workflow_id,
        taskId: (event as any).task_id,
        taskName: (event as any).task_name,
        status: (event as any).status,
      });
      chat?.render();
      break;

    case "workflow_completed":
      if (_shouldRejectSessionScopedEvent(event)) break;
      state.setWorkflowState({
        workflowId: (event as any).workflow_id,
        goal: (event as any).goal,
        totalTasks: state.getState().workflowState?.totalTasks ?? 0,
        taskIds: state.getState().workflowState?.taskIds ?? [],
        active: false,
        success: (event as any).success,
        completedCount: (event as any).completed_count,
        failedCount: (event as any).failed_count,
        skippedCount: (event as any).skipped_count,
        totalDuration: (event as any).total_duration,
      });
      chat?.render();
      break;

    default:
      break;
  }
}

let _lastSync = "";

/** If the sub-agent view is currently pointing at a tool call that just
 *  received a fresh sub_agent_messages payload, re-anchor the view to the
 *  updated tool call state so the timeline keeps streaming. */
function _syncSubAgentView(toolCallId: string): void {
  const st = state.getState();
  const view = st.subAgentView;
  if (!view || view.id !== toolCallId) return;
  const fresh = state.findToolCall(toolCallId);
  if (!fresh) return;
  state.setSubAgentView(fresh);
}

/** Update the sidebar session entry to reflect current message count + preview.
 *  Called from streaming event handlers so the sidebar stays live during a run.
 *  IMPORTANT: always read from the target session's own snapshot, never from
 *  the currently active session, otherwise background sessions overwrite the
 *  wrong sidebar entry when the user switches sessions while one is running.
 *  Also: derive `last_active` and `created_at` from message timestamps so
 *  the displayed time reflects the real last conversation (matching the
 *  backend's `sess.last_message_at` semantics), NOT wall-clock `Date.now()`. */
function _syncSessionEntry(sessionId: string, st: ReturnType<typeof state.getState>): void {
  if (!sessionId) return;
  if (st.tempChat) return;
  const snapshot = st.sessionStore[sessionId] || { messages: [], running: false };
  const snapMsgs = snapshot.messages;
  const lastContent = snapMsgs.length > 0 ? String(snapMsgs[snapMsgs.length - 1].content || "").slice(0, 20) : "";
  const key = `${sessionId}:${snapMsgs.length}:${lastContent}`;
  if (key === _lastSync) return;
  _lastSync = key;
  const firstUser = snapMsgs.find(m => m.role === "user");
  const preview = firstUser?.content?.slice(0, 100) || "";
  const isRunning = snapshot.running ?? false;
  // Derive sidebar ordering timestamps from the real message stream so the
  // user sees when the conversation actually happened, not when this sync
  // function happened to be called. Message.timestamp is in milliseconds
  // (see Message interface); SessionEntryData.* uses Unix seconds.
  const nowSec = Date.now() / 1000;
  const lastMsgMs = snapMsgs.length > 0 ? snapMsgs[snapMsgs.length - 1].timestamp : 0;
  const firstMsgMs = snapMsgs.length > 0 ? snapMsgs[0].timestamp : 0;
  const derivedLastActive = lastMsgMs > 0 ? Math.floor(lastMsgMs / 1000) : nowSec;
  const derivedCreatedAt = firstMsgMs > 0 ? Math.floor(firstMsgMs / 1000) : nowSec;
  const found = st.sessionsList.some(e => e.session_id === sessionId);
  const updated = found
    ? st.sessionsList.map(e =>
        e.session_id === sessionId
          ? {
              ...e,
              // Refresh last_active so the sidebar re-orders when this session
              // receives a new message. We clamp to never go backwards.
              last_active: Math.max(e.last_active ?? 0, derivedLastActive),
              message_count: snapMsgs.length,
              preview,
              is_running: isRunning,
            }
          : e
      )
    : [...st.sessionsList, {
        session_id: sessionId,
        message_count: snapMsgs.length,
        preview,
        created_at: derivedCreatedAt,
        last_active: derivedLastActive,
        is_running: isRunning,
        channel: st.workspaceMode === "iwork" ? "iwork" : "normal",
      }];
  state.setSessionsList(updated);
}

export function downloadMarkdownFile(markdown: string, filename: string): void {
  const sanitized = filename.replace(/[<>:"/\\|?*]/g, "_");
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = sanitized;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
