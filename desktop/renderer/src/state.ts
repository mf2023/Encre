/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
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

import { AppState, createEmptyState, Message, ToolCallState, TelemetryData, TokenUsage, PlanItem, NotificationItem } from "./types.js";

type Listener = () => void;

let state = createEmptyState();
const listeners = new Set<Listener>();

export function getState(): Readonly<AppState> {
  return state;
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(): void {
  for (const fn of listeners) {
    fn();
  }
}

function update(partial: Partial<AppState>): void {
  state = { ...state, ...partial };
  emit();
}

export function setConnected(v: boolean): void {
  update({ connected: v });
}

export function setSessionId(id: string): void {
  update({ sessionId: id });
}

export function addMessage(msg: Message): void {
  state.messages.push(msg);
  emit();
}

export function loadSessionMessages(rawMessages: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[] }>): void {
  const messages: Message[] = [];
  for (const raw of rawMessages) {
    if (raw.role === "tool" || raw.role === "system") continue;
    const content = typeof raw.content === "string"
      ? raw.content
      : Array.isArray(raw.content)
        ? raw.content
            .filter((b: any) => b.type === "text")
            .map((b: any) => b.text)
            .join("")
        : "";
    const usage = (raw as any).usage;
    messages.push({
      id: crypto.randomUUID(),
      role: raw.role === "assistant" ? "assistant" : "user",
      content,
      isStreaming: false,
      toolCalls: [],
      timestamp: Date.now(),
      tokenUsage: usage ? {
        input_tokens: usage.input_tokens ?? 0,
        output_tokens: usage.output_tokens ?? 0,
        total_tokens: usage.total_tokens ?? 0,
      } : undefined,
    });
  }
  state.messages = messages;
  emit();
}

export function addUserMessage(content: string): Message {
  const msg: Message = {
    id: crypto.randomUUID(),
    role: "user",
    content,
    isStreaming: false,
    toolCalls: [],
    timestamp: Date.now(),
  };
  addMessage(msg);
  return msg;
}

export function startAssistantMessage(): Message {
  const msg: Message = {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "",
    isStreaming: true,
    toolCalls: [],
    timestamp: Date.now(),
  };
  addMessage(msg);
  return msg;
}

export function getLastAssistantMessage(): Message | undefined {
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].role === "assistant") {
      return state.messages[i];
    }
  }
  return undefined;
}

export function appendContent(content: string): void {
  const msg = getLastAssistantMessage();
  if (msg) {
    msg.content += content;
    emit();
  }
}

export function appendThinking(text: string): void {
  const msg = getLastAssistantMessage();
  if (msg) {
    msg.thinking = (msg.thinking ?? "") + text;
    emit();
  }
}

export function finishAssistantMessage(tokenUsage?: { input_tokens: number; output_tokens: number; total_tokens: number }): void {
  const msg = getLastAssistantMessage();
  if (msg) {
    msg.isStreaming = false;
    if (tokenUsage) {
      msg.tokenUsage = tokenUsage;
    }
    emit();
  }
}

export function addToolCall(tc: ToolCallState): void {
  const msg = getLastAssistantMessage();
  if (msg) {
    msg.toolCalls.push(tc);
    emit();
  }
}

export function updateToolCall(
  id: string,
  patch: Partial<ToolCallState>
): void {
  for (const msg of state.messages) {
    const tc = msg.toolCalls.find((t) => t.id === id);
    if (tc) {
      Object.assign(tc, patch);
      emit();
      return;
    }
  }
}

export function setRunning(v: boolean): void {
  update({ running: v });
}

export function setPendingPermission(
  p: AppState["pendingPermission"]
): void {
  update({ pendingPermission: p });
}

export function setActiveToolId(id: string | null): void {
  update({ activeToolId: id });
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

export function findToolCall(id: string): ToolCallState | null {
  for (const msg of state.messages) {
    for (const tc of msg.toolCalls) {
      if (tc.id === id) return tc;
    }
  }
  return null;
}

export function setTelemetry(data: TelemetryData): void {
  update({ telemetry: data });
}

export function setTokenUsage(data: TokenUsage): void {
  update({ tokenUsage: data });
}

// ── Plan ──────────────────────────────────────────────────────────────────

export function setPlanItems(items: PlanItem[]): void {
  update({ planItems: items });
}

export function updatePlanItem(id: string, patch: Partial<PlanItem>): void {
  const updated = state.planItems.map((item) =>
    item.id === id ? { ...item, ...patch } : item
  );
  update({ planItems: updated });
}

// ── Notifications ─────────────────────────────────────────────────────────

export function resetChat(): void {
  update({
    messages: [],
    sessionId: "",
    running: false,
    pendingPermission: null,
    activeToolId: null,
    telemetry: null,
    tokenUsage: null,
    planItems: [],
  });
}

export function addNotification(item: NotificationItem): void {
  state.notifications.push(item);
  emit();
}

export function markNotificationsRead(): void {
  const updated = state.notifications.map((n) => ({ ...n, read: true }));
  update({ notifications: updated });
}

export function getUnreadCount(): number {
  return state.notifications.filter((n) => !n.read).length;
}

// ── Models ──────────────────────────────────────────────────────────────────

export function setAvailableModels(models: string[]): void {
  update({ availableModels: models });
}

export function setSessionsList(sessions: import("./types.js").SessionEntryData[]): void {
  update({ sessionsList: sessions });
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

export function setAgentConfig(config: {
  system_prompt: string;
  specialty: string;
  permission_mode: string;
  max_turns: number;
}): void {
  update({ agentConfig: config });
}
