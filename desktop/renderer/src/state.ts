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

import { AppState, createEmptyState, createEmptySessionSnapshot, Message, ToolCallState, TelemetryData, UsageStatsData, TokenUsage, PlanItem, PlanProposal, NotificationItem, AttachmentMeta, TimelineSegment, BranchMeta, SessionSnapshot } from "./types.js";
import { t } from "./i18n.js";
import { findSlashCommand } from "./slash_commands.js";

type Listener = () => void;

let state = createEmptyState();
const listeners = new Set<Listener>();
let pendingRollbackEdit: { serverId?: string; userIdx: number; content: string } | null = null;

function getSessionKey(sessionId?: string): string {
  return sessionId ?? state.sessionId ?? "";
}

function getOrCreateSessionSnapshot(sessionId?: string): SessionSnapshot {
  const key = getSessionKey(sessionId);
  if (!state.sessionStore[key]) {
    state.sessionStore[key] = createEmptySessionSnapshot();
  }
  return state.sessionStore[key];
}

function getSessionSnapshot(sessionId?: string): SessionSnapshot {
  return state.sessionStore[getSessionKey(sessionId)] ?? createEmptySessionSnapshot();
}

function syncActiveSessionState(): void {
  const snapshot = getSessionSnapshot(state.sessionId);
  state.messages = snapshot.messages;
  state.tokenUsage = snapshot.tokenUsage;
  state.telemetry = snapshot.telemetry;
  state.planItems = snapshot.planItems;
  state.planModeActive = snapshot.planModeActive;
  state.planProposals = snapshot.planProposals;
  state.artifacts = snapshot.artifacts;
  state.references = snapshot.references;
  state.compactEvents = snapshot.compactEvents;
  state.branches = snapshot.branches;
  state.activeBranchId = snapshot.activeBranchId;
  state.running = snapshot.running;
}

function syncSessionState(sessionId?: string): void {
  if (getSessionKey(sessionId) === getSessionKey(state.sessionId)) {
    syncActiveSessionState();
  }
}

export function getState(): Readonly<AppState> {
  return state;
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let _emitPending = false;

function emit(): void {
  if (_emitPending) return;
  _emitPending = true;
  queueMicrotask(() => {
    _emitPending = false;
    for (const fn of listeners) {
      fn();
    }
  });
}

function update(partial: Partial<AppState>): void {
  state = { ...state, ...partial };
  emit();
}

export function setConnected(v: boolean): void {
  update({ connected: v });
}

export function setSessionId(id: string): void {
  state.sessionId = id;
  getOrCreateSessionSnapshot(id);
  // Reset session-scoped global fields so the sidebar canvas does not
  // display stale data from a previously active session. The fields are
  // repopulated by the next context_usage events. Per-session fields
  // (telemetry, tokenUsage, ...) are restored by syncActiveSessionState().
  state.contextTokens = 0;
  state.contextWindow = 0;
  syncActiveSessionState();
  emit();
}

export function addMessage(msg: Message, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.messages.push(msg);
  syncSessionState(sessionId);
  emit();
}

function extractMessageText(content: string | Array<{ type: string; text: string }>): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((b: any) => b.type === "text")
      .map((b: any) => b.text)
      .join("");
  }
  return "";
}

function restoreToolCalls(rawToolCalls: any[] | undefined): ToolCallState[] {
  const restoredToolCalls: ToolCallState[] = [];
  if (!rawToolCalls || !Array.isArray(rawToolCalls)) return restoredToolCalls;

  for (const tc of rawToolCalls) {
    const func = tc.function || {};
    let params: Record<string, unknown> = {};
    try {
      params = JSON.parse(func.arguments || "{}");
    } catch {
      params = { arguments: func.arguments };
    }
    // Prefer the synthetic client-facing id (``_client_id``) so that
    // streaming tool_result events delivered via client_id can be
    // correlated with the right tc.  The backend persists both the
    // protocol-mandated ``id`` (the real backend id used by the LLM)
    // and ``_client_id`` (the synthetic id used for renderer events).
    // They may differ when the backend id is something like
    // ``toolu_xxx``; matching on ``_client_id`` makes the renderer's
    // streaming update path work after a session restore.
    const clientId = tc._client_id;
    restoredToolCalls.push({
      id: clientId || tc.id || crypto.randomUUID(),
      name: func.name || "unknown",
      params,
      result: undefined,
      isError: false,
      status: "done",
    });
  }
  return restoredToolCalls;
}

export function restoreMessages(rawMessages: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string; segments?: Array<{kind: string; text?: string; tool_id?: string}>; created_at?: number; mode?: string }>): Message[] {
  const messages: Message[] = [];
  for (const raw of rawMessages || []) {
    if (raw.role === "system") continue;
    if (raw.role === "tool") {
      const lastAssistant = messages[messages.length - 1];
      if (lastAssistant?.role === "assistant") {
        const toolCallId = (raw as any).tool_call_id;
        const clientId = (raw as any)._client_id;
        // See the streaming-path comment for why client_id is preferred.
        const target = clientId
          ? lastAssistant.toolCalls.find((tc) => tc.id === clientId)
          : toolCallId
            ? lastAssistant.toolCalls.find((tc) => tc.id === toolCallId)
            : lastAssistant.toolCalls[lastAssistant.toolCalls.length - 1];
        if (target) {
          const toolText = extractMessageText(raw.content);
          target.result = toolText;
          target.isError = /^error:/i.test(toolText) || /^permission denied/i.test(toolText);
          target.status = "done";
          const subAgentMessages = (raw as any).sub_agent_messages;
          if (Array.isArray(subAgentMessages)) {
            target.subAgentMessages = restoreMessages(subAgentMessages);
          }
        }
      }
      continue;
    }
    const toolCalls = restoreToolCalls(raw.tool_calls);
    const rawSegments = raw.segments;
    const segments: TimelineSegment[] = rawSegments?.length
      ? rawSegments.reduce<TimelineSegment[]>((acc, s) => {
          const next = s.kind === "thinking"
            ? { kind: "thinking" as const, text: s.text ?? "" }
            : s.kind === "tool"
              ? { kind: "tool" as const, toolId: s.tool_id || "" }
              : { kind: "text" as const, text: s.text ?? "" };
          const prev = acc[acc.length - 1];
          if (prev?.kind === "thinking" && next.kind === "thinking") {
            prev.text = (prev.text || "") + (next.text || "");
          } else if (prev?.kind === "text" && next.kind === "text") {
            prev.text = (prev.text || "") + (next.text || "");
          } else {
            acc.push(next);
          }
          return acc;
        }, [])
      : [
          ...((raw.reasoning_content ? [{ kind: "thinking" as const, text: raw.reasoning_content }] : [])),
          ...((extractMessageText(raw.content).trim() ? [{ kind: "text" as const, text: extractMessageText(raw.content) }] : [])),
          ...toolCalls.map((tc) => ({ kind: "tool" as const, toolId: tc.id })),
        ];
    messages.push({
      id: crypto.randomUUID(),
      role: raw.role === "assistant" ? "assistant" : "user",
      content: extractMessageText(raw.content),
      isStreaming: false,
      toolCalls,
      segments,
      timestamp: raw.created_at || Date.now(),
      thinking: raw.reasoning_content,
      mode: raw.mode,
      serverId: (raw as any).id,
    });
  }
  if (rawMessages && rawMessages.length > 0) { console.log("[restoreMessages] input=" + rawMessages.length + " output=" + messages.length + " roles=" + JSON.stringify(messages.map(m => m.role))); }
  return messages;
}

export function loadSessionMessages(rawMessages: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string }>, sessionId = state.sessionId): void {
  const messages: Message[] = [];
  let totalInput = 0;
  let totalOutput = 0;

  for (const raw of rawMessages) {
    if (raw.role === "system") continue;

    if (raw.role === "tool") {
      const lastAssistant = messages[messages.length - 1];
      if (lastAssistant?.role === "assistant" && lastAssistant.toolCalls.length > 0) {
        const toolCallId = (raw as any).tool_call_id;
        const clientId = (raw as any)._client_id;
        const toolText = extractMessageText(raw.content);
        // Prefer matching by client_id: tc.id was overridden to client_id
        // during restore (see restoreToolCalls).  Fall back to the
        // backend tool_call_id for messages saved before the _client_id
        // annotation was added.
        const target = clientId
          ? lastAssistant.toolCalls.find((tc) => tc.id === clientId)
          : toolCallId
            ? lastAssistant.toolCalls.find((tc) => tc.id === toolCallId)
            : lastAssistant.toolCalls[lastAssistant.toolCalls.length - 1];
        if (target) {
          target.result = toolText;
          target.isError = /^error:/i.test(toolText) || /^permission denied/i.test(toolText);
          target.status = "done";
          const subAgentMessages = (raw as any).sub_agent_messages;
          if (Array.isArray(subAgentMessages)) {
            target.subAgentMessages = restoreMessages(subAgentMessages);
          }
          target.subAgentSessionId = (raw as any).sub_agent_session_id;
        }
      }
      continue;
    }

    const content = extractMessageText(raw.content);
    const cleanContent = (content.includes("<attach ") || content.includes("<terminal>")) ? "" : content;
    const usage = (raw as any).usage || (raw as any).token_usage;
    const tu = usage ? {
      input_tokens: usage.input_tokens ?? 0,
      output_tokens: usage.output_tokens ?? 0,
      total_tokens: usage.total_tokens ?? 0,
    } : undefined;
    if (tu) {
      totalInput += tu.input_tokens;
      totalOutput += tu.output_tokens;
    }

    const toolCalls = restoreToolCalls(raw.tool_calls);
    // Use server-provided segments if available (preserves original streaming order),
    // otherwise reconstruct as thinking → text → tools.
    const rawSegments = (raw as any).segments as Array<{kind: string; text?: string; tool_id?: string}> | undefined;
    let segments: TimelineSegment[];
    if (rawSegments && rawSegments.length > 0) {
      segments = rawSegments.map(s => {
        if (s.kind === "thinking") return { kind: "thinking" as const, text: s.text ?? "" };
        if (s.kind === "text") return { kind: "text" as const, text: s.text ?? "" };
        if (s.kind === "tool") {
          const tc = toolCalls.find(t => t.id === s.tool_id);
          return { kind: "tool" as const, toolId: tc?.id || s.tool_id || "" };
        }
        return { kind: "text" as const, text: "" };
      });
    } else {
      segments = [];
      const thinkingText = (raw as any).reasoning_content as string | undefined;
      if (thinkingText) segments.push({ kind: "thinking", text: thinkingText });
      if (cleanContent) segments.push({ kind: "text", text: cleanContent });
      for (const tc of toolCalls) {
        segments.push({ kind: "tool", toolId: tc.id });
      }
    }

    const msgMode = (raw as any).mode;
    let rawFileRefs = (raw as any).fileRefs as { name: string; size: number; icon: string; path?: string; mime_type?: string }[] | undefined;
    if (!rawFileRefs) {
      const atts = (raw as any).attachments as any[] | undefined;
      if (atts) {
        rawFileRefs = atts.map(a => ({ name: a.name, size: a.size, icon: a.mime_type === "text/x-terminal" ? "terminal" : a.mime_type === "text/x-directory" ? "folder" : "paperclip", path: a.path, mime_type: a.mime_type }));
      }
    }
    if (!rawFileRefs) {
      const sid = sessionId;
      const idx = messages.filter(m => m.role === "user").length;
      try {
        const stored = localStorage.getItem(`fr:${sid}:${idx}`);
        if (stored) rawFileRefs = JSON.parse(stored);
      } catch {}
    }

    messages.push({
      id: crypto.randomUUID(),
      role: raw.role === "assistant" ? "assistant" : "user",
      content: cleanContent,
      isStreaming: false,
      toolCalls,
      segments,
      timestamp: (raw as any).created_at || Date.now(),
      thinking: (raw as any).reasoning_content,
      tokenUsage: tu,
      serverId: (raw as any).id,
      mode: msgMode,
      fileRefs: rawFileRefs,
    });
  }
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  const hadTokenUsage = snapshot.tokenUsage;
  snapshot.messages = messages;
  snapshot.artifacts = [];
  snapshot.compactEvents = [];
  if (totalInput > 0 || totalOutput > 0) {
    snapshot.tokenUsage = { input_tokens: totalInput, output_tokens: totalOutput, total_tokens: totalInput + totalOutput };
    state.contextTokens = totalInput + totalOutput;
  } else if (hadTokenUsage) {
    // preserve existing token usage if messages don't carry per-message data
    state.contextTokens = hadTokenUsage.total_tokens;
  } else if (messages.length > 0) {
    // fallback: estimate token count from content length
    const estimated = Math.round(messages.reduce((sum, m) => sum + m.content.length, 0) / 4);
    snapshot.tokenUsage = { input_tokens: estimated, output_tokens: 0, total_tokens: estimated };
    state.contextTokens = estimated;
  } else {
    snapshot.tokenUsage = null;
  }
  syncSessionState(sessionId);
  emit();
}

export function rememberRollbackEditTarget(message: Message, userIdx: number): void {
  pendingRollbackEdit = {
    serverId: message.serverId,
    userIdx,
    content: message.content,
  };
}

export function applyPendingRollbackEdit<T extends { role?: string; content?: string | Array<{ type: string; text: string }>; id?: string }>(rawMessages: T[]): T[] {
  if (!pendingRollbackEdit) return rawMessages;

  let userOrdinal = -1;
  let cutIdx = -1;
  for (let i = 0; i < rawMessages.length; i++) {
    const raw = rawMessages[i];
    if (raw.role !== "user") continue;
    userOrdinal++;

    const rawId = raw.id || "";
    const idMatches = pendingRollbackEdit.serverId
      ? rawId === pendingRollbackEdit.serverId || rawId.endsWith(`:M:${pendingRollbackEdit.serverId}`)
      : false;
    const contentMatches = userOrdinal === pendingRollbackEdit.userIdx
      && extractMessageText(raw.content || "") === pendingRollbackEdit.content;

    if (idMatches || contentMatches) {
      cutIdx = i;
      break;
    }
  }

  if (cutIdx < 0) return rawMessages;
  pendingRollbackEdit = null;
  return rawMessages.slice(0, cutIdx);
}

export function clearMessages(sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.messages = [];
  snapshot.tokenUsage = null;
  snapshot.telemetry = null;
  snapshot.planItems = [];
  snapshot.artifacts = [];
  snapshot.references = [];
  snapshot.compactEvents = [];
  snapshot.branches = [];
  snapshot.activeBranchId = "";
  snapshot.running = false;
  if (getSessionKey(sessionId) === getSessionKey(state.sessionId)) {
    state.activeToolId = null;
    state.telemetry = null;
    state.subAgentView = null;
    state.subAgentBreadcrumb = [];
  }
  syncSessionState(sessionId);
  emit();
}

// ── Thinking duration tracking ──────────────────────────────────────

let _thinkingStartTime: number | null = null;

export function beginThinking(): void {
  if (_thinkingStartTime === null) {
    _thinkingStartTime = Date.now();
  }
}

export function finishThinking(): void {
  if (_thinkingStartTime !== null) {
    const msg = getLastAssistantMessage();
    if (msg) {
      msg.thinkingElapsed = Math.round((Date.now() - _thinkingStartTime) / 1000);
    }
    _thinkingStartTime = null;
  }
}

export function addUserMessage(content: string, mode?: string, fileRefs?: { name: string; size: number; icon: string; path?: string; mime_type?: string }[]): Message {
  const msg: Message = {
    id: crypto.randomUUID(),
    role: "user",
    content,
    isStreaming: false,
    toolCalls: [],
    segments: [],
    timestamp: Date.now(),
    mode,
    fileRefs,
  };
  const sid = state.sessionId;
  addMessage(msg, sid);
  if (sid && fileRefs && fileRefs.length > 0) {
    const snapshot = getOrCreateSessionSnapshot(sid);
    const idx = snapshot.messages.filter(m => m.role === "user").length - 1;
    try { localStorage.setItem(`fr:${sid}:${idx}`, JSON.stringify(fileRefs)); } catch {}
  }
  return msg;
}

export function startAssistantMessage(sessionId = state.sessionId): Message {
  const msg: Message = {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "",
    isStreaming: true,
    toolCalls: [],
    segments: [],
    timestamp: Date.now(),
  };
  addMessage(msg, sessionId);
  return msg;
}

/**
 * Record a segment in the current assistant message's timeline, preserving the
 * order of thinking / text / tool call events as they arrive from the server.
 * Skips duplicate consecutive segments of the same kind.
 */
export function recordSegment(kind: TimelineSegment["kind"], toolId?: string, sessionId = state.sessionId): void {
  const msg = getLastAssistantMessage(sessionId);
  if (!msg) return;
  // Skip duplicate continuous deltas of same kind.
  // Tool segments must preserve per-call ordering, so only dedupe when toolId is identical.
  const last = msg.segments[msg.segments.length - 1];
  if (last && last.kind === kind) {
    if (kind !== "tool" || last.toolId === toolId) return;
  }
  msg.segments.push({ kind, toolId });
  syncSessionState(sessionId);
  emit();
}

export function getLastAssistantMessage(sessionId = state.sessionId): Message | undefined {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  for (let i = snapshot.messages.length - 1; i >= 0; i--) {
    if (snapshot.messages[i].role === "assistant") {
      return snapshot.messages[i];
    }
  }
  return undefined;
}

export function appendContent(content: string): void {
  if (!content) return;
  finishThinking();
  const msg = getLastAssistantMessage();
  if (msg) {
    msg.content += content;
    syncSessionState();
    emit();
  }
}

/**
 * Atomic append of a text delta — records the "text" segment and appends
 * content in a single emit(). Use this from stream.ts for text_delta events.
 */
export function appendTextDelta(text: string, sessionId = state.sessionId): void {
  if (!text) return;
  finishThinking();
  const msg = getLastAssistantMessage(sessionId);
  if (!msg) return;
  const last = msg.segments[msg.segments.length - 1];
  if (!last || last.kind !== "text") {
    msg.segments.push({ kind: "text", text: text });
  } else {
    last.text = (last.text || "") + text;
  }
  msg.content += text;
  syncSessionState(sessionId);
  emit();
}

/**
 * Atomic append of a thinking delta — records the "thinking" segment and
 * appends content in a single emit(). Use this from stream.ts for thinking_delta events.
 */
export function appendThinkingDelta(text: string, sessionId = state.sessionId): void {
  if (!text) return;
  const msg = getLastAssistantMessage(sessionId);
  if (!msg) return;
  if (!msg.thinking) {
    beginThinking();
  }
  const last = msg.segments[msg.segments.length - 1];
  if (!last || last.kind !== "thinking") {
    msg.segments.push({ kind: "thinking", text: text });
  } else {
    last.text = (last.text || "") + text;
  }
  msg.thinking = (msg.thinking ?? "") + text;
  syncSessionState(sessionId);
  emit();
}

export function appendThinking(text: string): void {
  if (!text) return;
  const msg = getLastAssistantMessage();
  if (msg) {
    if (!msg.thinking) {
      beginThinking();
    }
    msg.thinking = (msg.thinking ?? "") + text;
    syncSessionState();
    emit();
  }
}

export function finishAssistantMessage(tokenUsage?: { input_tokens: number; output_tokens: number; total_tokens: number }, sessionId = state.sessionId): void {
  const msg = getLastAssistantMessage(sessionId);
  if (msg) {
    msg.isStreaming = false;
    if (tokenUsage) {
      msg.tokenUsage = tokenUsage;
    }
    // Sweep any tool calls that never received a tool_result (crashed/cancelled)
    // so the UI doesn't sit in "waiting" forever.
    for (const tc of msg.toolCalls) {
      if (tc.status !== "done") {
        tc.status = "done";
        if (tc.result === undefined) {
          tc.result = t("general.noResult");
          tc.isError = true;
        }
      }
    }
    syncSessionState(sessionId);
    emit();
  }
}

export function addToolCall(tc: ToolCallState, sessionId = state.sessionId): void {
  const msg = getLastAssistantMessage(sessionId);
  if (msg) {
    msg.toolCalls.push(tc);
    syncSessionState(sessionId);
    emit();
  }
}

export function updateToolCall(
  id: string,
  patch: Partial<ToolCallState>,
  sessionId = state.sessionId
): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  for (const msg of snapshot.messages) {
    const tc = msg.toolCalls.find((t) => t.id === id);
    if (tc) {
      Object.assign(tc, patch);
      syncSessionState(sessionId);
      emit();
      return;
    }
  }
}

export function setRunning(v: boolean, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.running = v;
  syncSessionState(sessionId);
  emit();
  // Sync the sidebar + tray running indicator so the green dot/breathing
  // light reflects the actual running state immediately.
  const sid = sessionId;
  if (sid) {
    state.sessionsList = state.sessionsList.map(e =>
      e.session_id === sid ? { ...e, is_running: v } : e
    );
    window.electronAPI?.traySessionsUpdate?.(state.sessionsList);
  }
}

export function setActiveToolId(id: string | null): void {
  update({ activeToolId: id });
}

export function setSubAgentView(tc: import("./types.js").ToolCallState | null): void {
  update({ subAgentView: tc });
}

export function getSubAgentBreadcrumb(): Array<{sessionId: string; name: string; toolCallId: string; parentToolCallId: string | null}> {
  return state.subAgentBreadcrumb;
}

export function pushSubAgentBreadcrumb(entry: {sessionId: string; name: string; toolCallId: string; parentToolCallId: string | null}): void {
  const MAX_DEPTH = 4;
  // Dedupe: if a crumb with the same toolCallId already exists, replace it
  // rather than appending. This prevents the breadcrumb from accumulating
  // duplicate entries when the user re-opens the same sub-agent.
  const existing_idx = state.subAgentBreadcrumb.findIndex(
    (c) => c.toolCallId === entry.toolCallId
  );
  if (existing_idx >= 0) {
    const next = state.subAgentBreadcrumb.slice();
    next[existing_idx] = entry;
    update({ subAgentBreadcrumb: next });
    return;
  }
  const crumb = [...state.subAgentBreadcrumb, entry].slice(-MAX_DEPTH);
  update({ subAgentBreadcrumb: crumb });
}

export function popSubAgentBreadcrumb(): {sessionId: string; name: string; toolCallId: string; parentToolCallId: string | null} | null {
  if (state.subAgentBreadcrumb.length === 0) return null;
  const popped = state.subAgentBreadcrumb[state.subAgentBreadcrumb.length - 1];
  update({ subAgentBreadcrumb: state.subAgentBreadcrumb.slice(0, -1) });
  return popped;
}

export function clearSubAgentBreadcrumb(): void {
  update({ subAgentBreadcrumb: [] });
}

export function resetToSubAgentBreadcrumbIndex(index: number): {sessionId: string; name: string; toolCallId: string; parentToolCallId: string | null} | null {
  if (index < 0 || index >= state.subAgentBreadcrumb.length) return null;
  const target = state.subAgentBreadcrumb[index];
  // Truncate to [0..index] -- the user is now "at" stack[index], so the
  // stack above it is discarded. This matches the on-screen order: clicking
  // the N-th crumb should not leave crumbs N+1..end visible.
  update({ subAgentBreadcrumb: state.subAgentBreadcrumb.slice(0, index + 1) });
  return target;
}

export function setSettings(settings: Record<string, unknown>): void {
  update({ settings });
}

export function setTheme(theme: "dark" | "light"): void {
  update({ theme });
  document.documentElement.setAttribute("data-theme", theme);
}

export function setThemePreference(pref: "system" | "dark" | "light"): void {
  update({ themePreference: pref });
}

export function generateId(): string {
  return crypto.randomUUID();
}

export function findToolCall(id: string, sessionId = state.sessionId): ToolCallState | null {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  for (const msg of snapshot.messages) {
    for (const tc of msg.toolCalls) {
      if (tc.id === id) return tc;
    }
  }
  return null;
}

export function setTelemetry(data: TelemetryData, sessionId = state.sessionId): void {
  if (!sessionId) return;
  // Persist to per-session snapshot so the canvas panel survives
  // session switches and refreshes.
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.telemetry = data;
  if (sessionId === state.sessionId) {
    state.telemetry = data;
    emit();
  }
}

export function setUsageStats(data: UsageStatsData | null): void {
  update({ usageStats: data });
}

export function setTokenUsage(data: TokenUsage, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  const prev = snapshot.tokenUsage ?? { input_tokens: 0, output_tokens: 0, total_tokens: 0 };
  snapshot.tokenUsage = {
    input_tokens: prev.input_tokens + data.input_tokens,
    output_tokens: prev.output_tokens + data.output_tokens,
    total_tokens: prev.total_tokens + data.total_tokens,
  };
  syncSessionState(sessionId);
  emit();
}

// ── Attachments ──────────────────────────────────────────────────────────

export function addAttachments(items: AttachmentMeta[]): void {
  state.attachments.push(...items);
  emit();
}

export function clearAttachments(): void {
  state.attachments = [];
  emit();
}

export function removeAttachment(path: string): void {
  state.attachments = state.attachments.filter((a) => a.path !== path);
  emit();
}

// ── Plan ──────────────────────────────────────────────────────────────────

export function setPlanItems(items: PlanItem[], sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.planItems = items;
  syncSessionState(sessionId);
  emit();
}

export function setPlanModeActive(active: boolean, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.planModeActive = active;
  if (!active) {
    snapshot.planProposals = [];
  }
  syncSessionState(sessionId);
  emit();
}

export function addPlanProposal(proposal: PlanProposal, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.planProposals = [...snapshot.planProposals, proposal];
  syncSessionState(sessionId);
  emit();
}

export function removePlanProposal(proposalId: string, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.planProposals = snapshot.planProposals.filter((p) => p.proposal_id !== proposalId);
  syncSessionState(sessionId);
  emit();
}

export function updatePlanItem(id: string, patch: Partial<PlanItem>): void {
  const updated = state.planItems.map((item) =>
    item.id === id ? { ...item, ...patch } : item
  );
  setPlanItems(updated);
}

export function setArtifacts(artifacts: import("./types.js").ArtifactItem[], sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.artifacts = artifacts;
  syncSessionState(sessionId);
  emit();
}

/** Append new artifacts, deduplicating by path. Used for streaming artifacts_update events. */
export function appendArtifacts(newArtifacts: import("./types.js").ArtifactItem[], sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  const existing = new Set(snapshot.artifacts.map(a => a.path));
  const toAdd = newArtifacts.filter(a => !existing.has(a.path));
  if (toAdd.length > 0) {
    snapshot.artifacts = [...snapshot.artifacts, ...toAdd];
    syncSessionState(sessionId);
    emit();
  }
}

export function setReferences(references: import("./types.js").ReferenceItem[], sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.references = references;
  syncSessionState(sessionId);
  emit();
}

export function appendReferences(newRefs: import("./types.js").ReferenceItem[], sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.references = [...(snapshot.references || []), ...newRefs];
  syncSessionState(sessionId);
  emit();
}

export function addCompactEvent(evt: import("./types.js").CompactInfo, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.compactEvents = [...snapshot.compactEvents, evt];
  syncSessionState(sessionId);
  emit();
  // Notify the user that context was just compacted; the silent
  // timeline-only insertion was too easy to miss.
  if (sessionId === state.sessionId) {
    const reductionPct = evt.old_tokens > 0
      ? Math.round((1 - evt.new_tokens / evt.old_tokens) * 100)
      : 0;
    showToast(
      "Context compacted",
      `${evt.old_count} → ${evt.new_count} messages, ${reductionPct}% tokens reduced`,
      "info",
    );
  }
}

export function clearCompactEvents(): void {
  const snapshot = getOrCreateSessionSnapshot();
  snapshot.compactEvents = [];
  syncSessionState();
  emit();
}

// ── Notifications ─────────────────────────────────────────────────────────

export function resetChat(): void {
  state.sessionId = "";
  state.sessionStore[""] = createEmptySessionSnapshot();
  syncActiveSessionState();
  state.activeToolId = null;
  state.telemetry = null;
  state.inputMode = "";
  state.tempChat = false;
  state.pendingQueueCount = 0;
  state.queuedPrompts = [];
  state.subAgentView = null;
  state.subAgentBreadcrumb = [];
  // Clear automation sub-agent flags so the session bar label resets
  (window as any).__isAutomationView = false;
  emit();
}

export function addNotification(item: NotificationItem): void {
  state.notifications.push(item);
  emit();
  scheduleNotificationSave();
}

export function showToast(
  title: string,
  message: string,
  type: NotificationItem["type"] = "info",
  source?: string
): void {
  const displayMessage = message ? `${title}: ${message}` : title;
  addNotification({
    id: crypto.randomUUID(),
    type,
    title: displayMessage,
    message: "",
    source: source || t("general.sourceYim"),
    timestamp: Date.now(),
    read: false,
  });
}

export function markNotificationsRead(): void {
  const updated = state.notifications.map((n) => ({ ...n, read: true }));
  update({ notifications: updated });
  scheduleNotificationSave();
}

export function markOneNotificationRead(id: string): void {
  const updated = state.notifications.map((n) =>
    n.id === id ? { ...n, read: true } : n
  );
  update({ notifications: updated });
  scheduleNotificationSave();
}

export function dismissNotification(id: string): void {
  update({ notifications: state.notifications.filter((n) => n.id !== id) });
  scheduleNotificationSave();
}

export function clearAllNotifications(): void {
  update({ notifications: [] });
  scheduleNotificationSave();
}

export function getUnreadCount(): number {
  return state.notifications.filter((n) => !n.read).length;
}

// ── Notification Persistence ───────────────────────────────────────────────

let _notificationsFilePath: string | null = null;
let _persistReady = false;
let _persistDirty = false;

function scheduleNotificationSave(): void {
  _persistDirty = true;
  if (!_persistReady) return;
  debouncePersist();
}

let _saveTimer: ReturnType<typeof setTimeout> | null = null;
function debouncePersist(): void {
  if (_saveTimer) clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => persistNotifications(), 500);
}

async function persistNotifications(): Promise<void> {
  if (!_persistDirty || !_notificationsFilePath) return;
  _persistDirty = false;
  try {
    const { encrypt, isReady } = await import("./crypto.js");
    if (!isReady()) return; // crypto not ready — keep dirty flag to retry later
    const json = JSON.stringify(state.notifications);
    const data = await encrypt(json);
    await window.electronAPI?.writeFile(_notificationsFilePath, data);
  } catch {
    _persistDirty = true; // retry next time
  }
}

export async function initNotificationPersistence(onLoaded?: () => void): Promise<void> {
  try {
    const appPath = await window.electronAPI?.getAppPath();
    if (appPath) {
      _notificationsFilePath = appPath + "/notifications.enc";
      const raw = await window.electronAPI?.readFile(_notificationsFilePath);
      if (raw) {
        const { decrypt } = await import("./crypto.js");
        const json = await decrypt(raw.content);
        const items = JSON.parse(json);
        if (Array.isArray(items)) {
          state.notifications = items;
          emit();
          onLoaded?.();
        }
      }
    }
  } catch {
    // Corrupted file or first run — start fresh
  } finally {
    _persistReady = true;
    if (_persistDirty && _notificationsFilePath) debouncePersist();
  }
}

// ── Models ──────────────────────────────────────────────────────────────────

export function setAvailableModels(models: string[]): void {
  update({ availableModels: models });
}

export function setInputMode(mode: string): void {
  update({ inputMode: mode });
}

/** Restore a mode chip into the prompt input and sync state. */
export function restoreInputModeChip(mode: string): void {
  setInputMode(mode);
  const input = document.getElementById("prompt-input") as HTMLElement | null;
  if (!input) return;

  const old = input.querySelector(".mode-chip");
  if (old) old.remove();

  const cmd = findSlashCommand(mode);
  const label = cmd ? cmd.title : mode;
  const icon = cmd ? cmd.icon : "list-checks";

  const chip = document.createElement("span");
  chip.contentEditable = "false";
  chip.className = "mode-chip";
  chip.setAttribute("data-mode", mode);
  chip.innerHTML = `<i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${label}</span>`;
  input.insertBefore(chip, input.firstChild);

  if ((window as any).lucide) {
    (window as any).lucide.createIcons();
  }
}

export function setSessionsList(sessions: import("./types.js").SessionEntryData[]): void {
  update({ sessionsList: sessions });
  // Note: do NOT update traySessionsCache here — it only has one mode's
  // data and would corrupt the dual-mode cache.  The tray cache is
  // maintained by setTraySessions() which is called from the
  // "sessions_all" response and updates both normal + iwork at once.
}

// Dual-channel session cache for the tray popup (normal + iwork).
const traySessionsCache: { normal: any[]; iwork: any[] } = { normal: [], iwork: [] };

export function setTraySessions(normal: any[], iwork: any[]): void {
  traySessionsCache.normal = normal;
  traySessionsCache.iwork = iwork;
}

export function getTraySessions(): { normal: any[]; iwork: any[] } {
  return traySessionsCache;
}

export function removeSessionById(sessionId: string): void {
  const sessions = state.sessionsList.filter((s) => s.session_id !== sessionId);
  const history = state.automationHistory.filter((h: any) => h.session_id !== sessionId);
  update({ sessionsList: sessions, automationHistory: history });
}

export function setAutomationHistory(history: any[]): void {
  update({ automationHistory: history });
}

export function setSearchResults(results: import("./types.js").SearchResultEntry[]): void {
  update({ searchResults: results });
}

export function setModelConfigs(models: import("./types.js").ModelConfigMeta[], activeIndex: number): void {
  update({ modelConfigs: models, activeModelIndex: activeIndex });
}

export function setSkillsList(skills: import("./types.js").SkillInfo[]): void {
  update({ skillsList: skills });
}

export function setEnabledSkills(skills: string[]): void {
  update({ enabledSkills: skills });
}

export function setMcpServers(servers: import("./types.js").MCPServerConfig[]): void {
  update({ mcpServers: servers });
}

export function setCustomCommands(commands: import("./types.js").CustomCommand[]): void {
  update({ customCommands: commands });
}

export function setPendingQueueCount(n: number): void {
  update({ pendingQueueCount: n });
}

export function clearPendingQueueCount(): void {
  update({ pendingQueueCount: 0, queuedPrompts: [] });
}

export function pushQueuedPrompt(text: string, mode?: string): void {
  state.queuedPrompts.push({ text, mode });
  state.pendingQueueCount = state.queuedPrompts.length;
  emit();
}

export function shiftQueuedPrompt(): void {
  state.queuedPrompts.shift();
  emit();
}

export function clearQueuedPrompts(): void {
  state.queuedPrompts = [];
  emit();
}

export function removeQueuedPromptAt(index: number): void {
  state.queuedPrompts.splice(index, 1);
  emit();
}

export function removeLastMessage(): void {
  const snapshot = getOrCreateSessionSnapshot();
  if (snapshot.messages.length > 0) {
    snapshot.messages.pop();
    syncSessionState();
    emit();
  }
}

export function truncateToUserMessage(userIdx: number): boolean {
  const snapshot = getOrCreateSessionSnapshot();
  let ui = 0;
  let cutIdx = -1;
  for (let i = 0; i < snapshot.messages.length; i++) {
    if (snapshot.messages[i].role === "user") {
      if (ui === userIdx) {
        cutIdx = i;
        break;
      }
      ui++;
    }
  }
  if (cutIdx >= 0) {
    snapshot.messages = snapshot.messages.slice(0, cutIdx);
    syncSessionState();
    emit();
    return true;
  }
  return false;
}

export function setSubAgents(agents: import("./types.js").SubAgentConfig[]): void {
  update({ subAgents: agents });
}

export function setAgentConfig(config: {
  system_prompt: string;
  specialty: string;
  permission_mode: string;
  max_turns: number;
}): void {
  update({ agentConfig: config });
}

// ── Workspace ───────────────────────────────────────────────────────────────

export function setWorkspaces(workspaces: import("./types.js").WorkspaceEntry[]): void {
  // Filter out invalid entries
  const valid = workspaces.filter((w) => w.path && w.name);
  // Clear orphaned activeWorkspace if no longer in list
  if (state.activeWorkspace && !valid.some((w) => w.path === state.activeWorkspace)) {
    setActiveWorkspace("");
  }
  update({ workspaces: valid });
}

export function setActiveWorkspace(path: string): void {
  update({ activeWorkspace: path });
}

export function setWorkspaceMode(mode: "iwork" | "normal"): void {
  update({ workspaceMode: mode });
}

export function setIndexStatus(status: "idle" | "ready" | "indexing" | "error" | "no_workspace"): void {
  update({ indexStatus: status });
}

export function setIndexFiles(files: number): void {
  update({ indexFiles: files });
}

export function setIndexProgress(progress: number): void {
  update({ indexProgress: progress });
}

export function updateContextUsage(tokens: number, window: number, sessionId = state.sessionId): void {
  if (!sessionId) return;
  // Ignore events from non-active sessions so background sessions cannot
  // overwrite the canvas panel currently shown in the sidebar.
  if (sessionId !== state.sessionId) return;
  state.contextTokens = tokens;
  state.contextWindow = window;
  emit();
}

export function updateWorkspaceIndex(wsId: string, status: string, files: number): void {
  if (!wsId) return;
  state.workspaces = state.workspaces.map(w =>
    w.id === wsId ? { ...w, index_status: status, index_files: files } : w
  );
  // Also update global for session-inner panel
  state.indexStatus = status as any;
  state.indexFiles = files;
  emit();
}

export function setGitignoreContent(content: string): void {
  update({ gitignoreContent: content });
}

export function setDocsList(docs: import("./types.js").DocumentEntry[]): void {
  update({ docsList: docs });
}

export function setGatewayStatus(status: import("./types.js").GatewayStatusData | null): void {
  update({ gatewayStatus: status });
}

export function setToolsInfo(info: import("./types.js").ToolsInfo): void {
  update({ toolsInfo: info });
}

export function setModelCatalog(catalog: import("./types.js").ModelCatalog): void {
  update({ modelCatalog: catalog });
}

export function setMcpCatalog(catalog: import("./types.js").McpCatalog): void {
  update({ mcpCatalog: catalog });
}

export function setMemoryList(entries: import("./types.js").MemoryEntry[]): void {
  update({ memoryList: entries });
}

export function setMemoryDetail(detail: { path: string; content: string; error?: string } | null): void {
  update({ memoryDetail: detail });
}

export function setGlobalRulesList(rules: import("./types.js").GlobalRuleEntry[]): void {
  update({ globalRules: rules });
}

export function setProjectRulesList(rules: import("./types.js").ProjectRuleEntry[]): void {
  update({ projectRules: rules });
}

export function setProjectHooksList(hooks: import("./types.js").ProjectHookEntry[]): void {
  update({ projectHooks: hooks });
}

export function setViewingGlobalRule(data: { name: string; content: string; error?: string } | null): void {
  update({ viewingGlobalRule: data });
}

export function setProfile(profile: import("./types.js").ProfileData | null): void {
  update({ profile });
}

export function setPendingPermission(
  toolName: string | null | { tool: string; reason: string },
): void {
  if (toolName == null) {
    update({ pendingPermission: null });
    return;
  }
  if (typeof toolName === "string") {
    update({ pendingPermission: toolName });
    return;
  }
  // Object form -- { tool, reason }.  The shared state only stores the
  // tool name; the dialog keeps the reason next to its own state.
  update({ pendingPermission: toolName.tool });
}

export function setTempChat(v: boolean): void {
  update({ tempChat: v });
}

export function switchBranch(branchId: string, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.activeBranchId = branchId;
  syncSessionState(sessionId);
  emit();
}

export function setBranchState(
  activeBranchId: string,
  branches: BranchMeta[],
  messages?: Message[],
  sessionId = state.sessionId
): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.activeBranchId = activeBranchId;
  snapshot.branches = branches;
  if (messages !== undefined) {
    snapshot.messages = messages;
  }
  syncSessionState(sessionId);
  emit();
}

export function setBranches(branches: BranchMeta[], activeBranchId: string, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.branches = branches;
  snapshot.activeBranchId = activeBranchId;
  syncSessionState(sessionId);
  emit();
}

export function removeBranchMessages(removedIds: Set<string>, sessionId = state.sessionId): void {
  const snapshot = getOrCreateSessionSnapshot(sessionId);
  snapshot.messages = snapshot.messages.filter(m => !removedIds.has(m.id));
  syncSessionState(sessionId);
  emit();
}

// ── Workflow state ──────────────────────────────────────────────────────

export function setWorkflowState(partial: {
  workflowId: string;
  goal: string;
  totalTasks: number;
  taskIds: string[];
  active: boolean;
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  success?: boolean;
  totalDuration?: number;
}): void {
  const existing = state.workflowState;
  if (!existing || existing.workflowId !== partial.workflowId) {
    // New workflow: create fresh task list
    state.workflowState = {
      workflowId: partial.workflowId,
      goal: partial.goal,
      totalTasks: partial.totalTasks,
      taskIds: partial.taskIds,
      active: partial.active,
      tasks: partial.taskIds.map(id => ({ taskId: id, taskName: "", status: "pending" })),
      completedCount: partial.completedCount,
      failedCount: partial.failedCount,
      skippedCount: partial.skippedCount,
      success: partial.success,
      totalDuration: partial.totalDuration,
    };
  } else {
    // Update existing workflow
    existing.active = partial.active;
    existing.completedCount = partial.completedCount;
    existing.failedCount = partial.failedCount;
    existing.skippedCount = partial.skippedCount;
    if (partial.success !== undefined) existing.success = partial.success;
    if (partial.totalDuration !== undefined) existing.totalDuration = partial.totalDuration;
  }
  emit();
}

export function updateWorkflowTask(info: {
  workflowId: string;
  taskId: string;
  taskName: string;
  status: string;
}): void {
  const wf = state.workflowState;
  if (!wf || wf.workflowId !== info.workflowId) return;
  const task = wf.tasks.find(t => t.taskId === info.taskId);
  if (task) {
    task.taskName = info.taskName;
    task.status = info.status;
  } else {
    wf.tasks.push({
      taskId: info.taskId,
      taskName: info.taskName,
      status: info.status,
    });
  }
  if (info.status === "completed") wf.completedCount = wf.tasks.filter(t => t.status === "completed").length;
  if (info.status === "failed") wf.failedCount = wf.tasks.filter(t => t.status === "failed").length;
  if (info.status === "skipped") wf.skippedCount = wf.tasks.filter(t => t.status === "skipped").length;
  emit();
}
